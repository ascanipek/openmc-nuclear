"""Fixed-hyperparameter exploratory k-effective comparison for the Halton branch."""
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold

sys.path.insert(0, "/tmp/openmc_xgboost_320")
import xgboost
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_384_halton_v1"
OLD = ROOT / "datasets/v2_256_preview_v1"
OLD_PRED = ROOT / "kaggle/ml_keff_v1/results/test_predictions.csv"
OUT = ROOT / "reports/keff_384_halton_v1"
FEATURES = ["u235_enrichment_wt_percent", "fuel_temperature_K", "moderator_temperature_K",
            "coolant_pressure_MPa", "elemental_boron_ppm", "pin_pitch_cm",
            "pellet_radius_cm", "insertion_percent"]
SEED = 20261025
PARAMS = {"objective": "reg:squarederror", "tree_method": "hist", "random_state": SEED,
          "n_jobs": min(4, os.cpu_count() or 1), "subsample": 1.0,
          "colsample_bytree": 1.0, "n_estimators": 400, "max_depth": 2,
          "learning_rate": 0.05}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    if manifest["scenario_count"] != 384 or manifest["branch"] != "halton":
        raise ValueError("Dataset is not the frozen 384 Halton branch")
    for name, digest in manifest["output_sha256"].items():
        if sha(DATA / name) != digest:
            raise ValueError(f"Dataset hash changed: {name}")
    splits = json.loads((DATA / "splits.json").read_text())
    rows = pd.read_csv(DATA / "scenarios.csv")
    targets = pd.read_csv(DATA / "targets_keff.csv")
    old = pd.read_csv(OLD / "scenarios.csv")
    if not rows.iloc[:256].reset_index(drop=True).equals(old):
        raise ValueError("Original scenario rows changed")
    if (rows.scenario_id != targets.scenario_id).any() or len(rows) != 384:
        raise ValueError("Target identity/order mismatch")
    role = {sid: part for part in ("train", "calibration", "test") for sid in splits[part]}
    if any(role[sid] != part for sid, part in zip(rows.scenario_id, rows.split)):
        raise ValueError("Split mismatch")
    if {k: len(splits[k]) for k in ("train", "calibration", "test")} != {"train": 336, "calibration": 25, "test": 23}:
        raise ValueError("Split count mismatch")
    X = rows[FEATURES].to_numpy(float)
    y = targets.k_mean.to_numpy(float)
    train = np.flatnonzero(rows.split.to_numpy() == "train")
    test = np.flatnonzero(rows.split.to_numpy() == "test")
    cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    cv_rows = []
    for fold, (fit_local, val_local) in enumerate(cv.split(train), 1):
        fit, val = train[fit_local], train[val_local]
        model = XGBRegressor(**PARAMS)
        model.fit(X[fit], y[fit])
        pred = model.predict(X[val])
        cv_rows.append({"fold": fold, "fit_count": len(fit), "validation_count": len(val),
                        "mae": float(mean_absolute_error(y[val], pred)),
                        "rmse": float(np.sqrt(mean_squared_error(y[val], pred))),
                        "r2": float(r2_score(y[val], pred))})
    model = XGBRegressor(**PARAMS)
    model.fit(X[train], y[train])
    pred = model.predict(X[test])
    actual = y[test]
    old_predictions = pd.read_csv(OLD_PRED).set_index("scenario_id")
    test_ids = rows.iloc[test].scenario_id.tolist()
    if set(test_ids) != set(old_predictions.index) or len(old_predictions) != 23:
        raise ValueError("Saved 256 test predictions are not the same test cases")
    baseline = old_predictions.loc[test_ids]
    if not np.allclose(actual, baseline.k_mean.to_numpy(), rtol=0, atol=1e-12):
        raise ValueError("Saved baseline test targets differ")
    result = pd.DataFrame({"scenario_id": test_ids, "k_actual": actual,
                           "k_mc_standard_error": targets.iloc[test].k_mc_standard_error.to_numpy(float),
                           "k_predicted_384": pred, "k_predicted_256": baseline.k_predicted.to_numpy(float),
                           "insertion_percent": rows.iloc[test].insertion_percent.to_numpy(float)})
    for suffix in ("384", "256"):
        result[f"abs_error_{suffix}"] = np.abs(result[f"k_predicted_{suffix}"] - actual)
    result["insertion_band"] = pd.cut(result.insertion_percent, [-1, 100/3, 200/3, 101],
                                       labels=["low", "middle", "high"])
    result["distance_to_critical"] = np.abs(result.k_actual - 1)
    old_train = rows.iloc[train[train < 256]]
    scale = (old_train[FEATURES].max() - old_train[FEATURES].min()).replace(0, 1).to_numpy(float)
    normalized_test = X[test] / scale
    normalized_old_train = old_train[FEATURES].to_numpy(float) / scale
    result["distance_to_old_train_nearest"] = np.min(
        np.linalg.norm(normalized_test[:, None, :] - normalized_old_train[None, :, :], axis=2), axis=1)
    result["sparse_region_top_quartile_old_train"] = (
        result.distance_to_old_train_nearest >= result.distance_to_old_train_nearest.quantile(.75))
    OUT.mkdir(parents=True)
    pd.DataFrame(cv_rows).to_csv(OUT / "cv_folds.csv", index=False)
    result.to_csv(OUT / "test_predictions.csv", index=False)
    joblib.dump(model, OUT / "selected_keff_model.joblib")
    metrics = {}
    for suffix in ("256", "384"):
        p = result[f"k_predicted_{suffix}"].to_numpy()
        metrics[suffix] = {"mae": float(mean_absolute_error(actual, p)),
                           "rmse": float(np.sqrt(mean_squared_error(actual, p))),
                           "r2": float(r2_score(actual, p)),
                           "max_absolute_error": float(np.max(np.abs(p - actual)))}
    delta = {metric: {"absolute_new_minus_old": metrics["384"][metric] - metrics["256"][metric],
                      "percent_change": 100 * (metrics["384"][metric] / metrics["256"][metric] - 1)}
             for metric in ("mae", "rmse", "max_absolute_error")}
    bands = result.groupby("insertion_band", observed=False).agg(
        count=("scenario_id", "size"), old_mae=("abs_error_256", "mean"),
        new_mae=("abs_error_384", "mean")).reset_index()
    bands["absolute_new_minus_old"] = bands.new_mae - bands.old_mae
    bands.to_csv(OUT / "insertion_bands.csv", index=False)
    nearest = result.nsmallest(5, "distance_to_critical")
    nearest.to_csv(OUT / "near_critical.csv", index=False)
    sparse = result[result.sparse_region_top_quartile_old_train]
    report = {"schema": "keff_384_halton_exploratory_v1",
              "scientific_status": "PROVISIONAL_EXPLORATORY; no physical/statistical training acceptance",
              "features": FEATURES, "model": "XGBoost", "hyperparameters": PARAMS,
              "cv": {"folds": 5, "seed": SEED, "fold_metrics": cv_rows,
                     "mean_mae": float(np.mean([r["mae"] for r in cv_rows])),
                     "mean_rmse": float(np.mean([r["rmse"] for r in cv_rows]))},
              "test_count": 23, "baseline_256": metrics["256"], "halton_384": metrics["384"],
              "change": delta, "near_critical_five": nearest.to_dict("records"),
              "sparse_top_quartile_descriptive": {"count": len(sparse),
                  "old_mae": float(sparse.abs_error_256.mean()),
                  "new_mae": float(sparse.abs_error_384.mean())},
              "source_dataset_sha256": sha(DATA / "dataset_manifest.json"),
              "baseline_predictions_sha256": sha(OLD_PRED),
              "software": {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
              "warning": "Baseline XGBoost was trained with 3.4.1 on 256 samples; 384 model uses 3.2.0. Same fixed hyperparameters; version difference limits pure sample-count attribution. Test set was examined before and is not fully untouched."}
    (OUT / "training_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(actual, result.k_predicted_256, label="256", alpha=.7)
    ax.scatter(actual, result.k_predicted_384, label="384", alpha=.7)
    low = min(actual.min(), pred.min(), result.k_predicted_256.min())
    high = max(actual.max(), pred.max(), result.k_predicted_256.max())
    ax.plot([low, high], [low, high], "k--")
    ax.set(xlabel="OpenMC k", ylabel="Predicted k", title="Same 23 test cases")
    ax.legend(); fig.tight_layout(); fig.savefig(OUT / "test_actual_vs_pred.png", dpi=150); plt.close(fig)
    (OUT / "README.md").write_text(
        "# k-effective, 384 Halton branch\n\n"
        "PROVISIONAL / EXPLORATORY. Fixed 256 split preserved; 128 Halton cases enter train only. "
        "XGBoost uses the recorded 256 hyperparameters and 5-fold train-only CV. "
        "The same 23 previously examined test cases are compared by scenario ID. "
        "MC standard error measures transport sampling, not physical accuracy. "
        "See training_report.json, test_predictions.csv and insertion_bands.csv.\n")
    print(json.dumps({"old": metrics["256"], "new": metrics["384"], "cv_rmse": report["cv"]["mean_rmse"]}))


if __name__ == "__main__":
    main()


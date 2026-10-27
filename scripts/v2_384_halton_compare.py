"""Compare frozen 256 and 384 Halton branch on the identical 23 test cases."""
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
sys.path.insert(0, "/tmp/openmc_xgboost_320")
import xgboost
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
OLD_DATA = ROOT / "datasets/v2_256_preview_v1"
NEW_DATA = ROOT / "datasets/v2_384_halton_v1"
K_REPORT = ROOT / "reports/keff_384_halton_v1"
FIELD_REPORT = ROOT / "reports/field3d_384_halton_v1"
OUT = ROOT / "reports/comparison_256_vs_384_halton_v1"
FEATURES = ["u235_enrichment_wt_percent", "fuel_temperature_K", "moderator_temperature_K",
            "coolant_pressure_MPa", "elemental_boron_ppm", "pin_pitch_cm",
            "pellet_radius_cm", "insertion_percent"]
PARAMS = {"objective": "reg:squarederror", "tree_method": "hist", "random_state": 20261025,
          "n_jobs": min(4, os.cpu_count() or 1), "subsample": 1.0,
          "colsample_bytree": 1.0, "n_estimators": 400, "max_depth": 2,
          "learning_rate": 0.05}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(y, pred):
    return {"mae": float(mean_absolute_error(y, pred)),
            "rmse": float(np.sqrt(mean_squared_error(y, pred))),
            "r2": float(r2_score(y, pred)),
            "max_absolute_error": float(np.max(np.abs(y-pred)))}


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    old_manifest = json.loads((OLD_DATA / "dataset_manifest.json").read_text())
    new_manifest = json.loads((NEW_DATA / "dataset_manifest.json").read_text())
    if any(sha(OLD_DATA / name) != digest for name, digest in new_manifest["old_dataset_sha256"].items()):
        raise ValueError("Original 256 source changed")
    if any(sha(NEW_DATA / name) != digest for name, digest in new_manifest["output_sha256"].items()):
        raise ValueError("New dataset changed")
    old_splits = json.loads((OLD_DATA / "splits.json").read_text())
    new_splits = json.loads((NEW_DATA / "splits.json").read_text())
    if old_splits["test"] != new_splits["test"] or old_splits["calibration"] != new_splits["calibration"] or old_splits["train"] != new_splits["train"][:208]:
        raise ValueError("Original split membership/order changed")
    old_rows = pd.read_csv(OLD_DATA / "scenarios.csv")
    old_targets = pd.read_csv(OLD_DATA / "targets_keff.csv")
    new_rows = pd.read_csv(NEW_DATA / "scenarios.csv")
    if not old_rows.equals(new_rows.iloc[:256].reset_index(drop=True)):
        raise ValueError("Original 256 scenarios changed")
    train = np.flatnonzero(old_rows.split.to_numpy() == "train")
    test = np.flatnonzero(old_rows.split.to_numpy() == "test")
    X = old_rows[FEATURES].to_numpy(float)
    y = old_targets.k_mean.to_numpy(float)
    model = XGBRegressor(**PARAMS)
    model.fit(X[train], y[train])
    p_same = model.predict(X[test])
    old_pred = pd.read_csv(ROOT / "kaggle/ml_keff_v1/results/test_predictions.csv").set_index("scenario_id")
    new_k = pd.read_csv(K_REPORT / "test_predictions.csv").set_index("scenario_id")
    old_field = pd.read_csv(ROOT / "reports/field3d_surrogate_v1/test_case_metrics.csv").set_index("scenario_id")
    new_field = pd.read_csv(FIELD_REPORT / "test_case_metrics.csv").set_index("scenario_id")
    ids = old_rows.iloc[test].scenario_id.tolist()
    if any(set(table.index) != set(ids) or len(table) != 23 for table in (old_pred, new_k, old_field, new_field)):
        raise ValueError("Test IDs differ")
    old_pred, new_k, old_field, new_field = (table.loc[ids] for table in (old_pred, new_k, old_field, new_field))
    actual = y[test]
    if not np.allclose(actual, old_pred.k_mean, atol=1e-12, rtol=0) or not np.allclose(actual, new_k.k_actual, atol=1e-12, rtol=0):
        raise ValueError("Test target values differ")
    if not np.allclose(old_field.insertion_percent, new_field.insertion_percent, atol=1e-10, rtol=0):
        raise ValueError("Test insertion controls differ")
    p_published = old_pred.k_predicted.to_numpy(float)
    p_new = new_k.k_predicted_384.to_numpy(float)
    k_published = metrics(actual, p_published)
    k_same = metrics(actual, p_same)
    k_new = metrics(actual, p_new)
    field_old = old_field.ml_relative_l2_fuel.to_numpy(float)
    field_new = new_field.ml_relative_l2_fuel.to_numpy(float)
    keys = [("k_mae", k_same["mae"], k_new["mae"]),
            ("k_rmse", k_same["rmse"], k_new["rmse"]),
            ("k_max_absolute_error", k_same["max_absolute_error"], k_new["max_absolute_error"]),
            ("field3d_relative_l2", float(field_old.mean()), float(field_new.mean())),
            ("field3d_half_l1_share", float(old_field.ml_half_l1_share_error_raw.mean()),
             float(new_field.ml_half_l1_share_error_raw.mean())),
            ("field3d_axial_half_l1_share", float(old_field.ml_axial_half_l1_share_error_raw.mean()),
             float(new_field.ml_axial_half_l1_share_error_raw.mean()))]
    comparison = pd.DataFrame([
        {"metric": name, "baseline_256": old, "halton_384": new,
         "absolute_new_minus_old": new-old, "percent_change": 100*(new/old-1)}
        for name, old, new in keys])
    result = pd.DataFrame({
        "scenario_id": ids, "k_actual": actual, "insertion_percent": old_field.insertion_percent.to_numpy(float),
        "k_pred_256_published": p_published, "k_pred_256_same_env": p_same, "k_pred_384": p_new,
        "k_abs_error_256_published": np.abs(p_published-actual),
        "k_abs_error_256_same_env": np.abs(p_same-actual), "k_abs_error_384": np.abs(p_new-actual),
        "field_relative_l2_256": field_old, "field_relative_l2_384": field_new,
        "field_pca_relative_l2_256": old_field.pca_relative_l2_fuel.to_numpy(float),
        "field_pca_relative_l2_384": new_field.pca_relative_l2_fuel.to_numpy(float)})
    result["insertion_band"] = pd.cut(result.insertion_percent,
                                      [-1, 100/3, 200/3, 101], labels=["low", "middle", "high"])
    result["distance_to_old_train_nearest"] = new_k.distance_to_old_train_nearest.to_numpy(float)
    result["sparse_region_top_quartile_old_train"] = new_k.sparse_region_top_quartile_old_train.to_numpy(bool)
    band = result.groupby("insertion_band", observed=False).agg(
        count=("scenario_id", "size"),
        k_mae_256=("k_abs_error_256_same_env", "mean"), k_mae_384=("k_abs_error_384", "mean"),
        field_l2_256=("field_relative_l2_256", "mean"),
        field_l2_384=("field_relative_l2_384", "mean")).reset_index()
    band["k_mae_percent_change"] = 100*(band.k_mae_384/band.k_mae_256-1)
    band["field_l2_percent_change"] = 100*(band.field_l2_384/band.field_l2_256-1)
    sparse = result[result.sparse_region_top_quartile_old_train]
    near = result.iloc[np.argsort(np.abs(actual-1))[:5]]
    sign_old = int(np.count_nonzero((p_same >= 1) != (actual >= 1)))
    sign_new = int(np.count_nonzero((p_new >= 1) != (actual >= 1)))
    OUT.mkdir(parents=True)
    joblib.dump(model, OUT / "keff_baseline_256_same_env.joblib")
    comparison.to_csv(OUT / "metrics.csv", index=False)
    result.to_csv(OUT / "same_test_predictions.csv", index=False)
    band.to_csv(OUT / "insertion_bands.csv", index=False)
    near.to_csv(OUT / "near_critical_five.csv", index=False)
    report = {
        "schema": "halton_256_vs_384_comparison_v1",
        "scientific_status": "PROVISIONAL_EXPLORATORY; no physical/statistical training acceptance",
        "branch": "halton", "split_counts": {"train_256": 208, "train_384": 336, "calibration": 25, "test": 23},
        "test_identity": {"same_ids": True, "same_k_targets": True, "same_3d_targets": True,
                          "test_examined_previously": True},
        "keff": {"published_256_xgboost_3_4_1": k_published,
                 "same_env_256_xgboost_3_2_0": k_same,
                 "halton_384_xgboost_3_2_0": k_new,
                 "criticality_side_errors_same_env_256": sign_old,
                 "criticality_side_errors_384": sign_new,
                 "near_critical_five_ids": near.scenario_id.tolist()},
        "field3d": {"baseline_256_mean_relative_l2": float(field_old.mean()),
                    "halton_384_mean_relative_l2": float(field_new.mean()),
                    "baseline_256_pca_reconstruction_l2": float(old_field.pca_relative_l2_fuel.mean()),
                    "halton_384_pca_reconstruction_l2": float(new_field.pca_relative_l2_fuel.mean())},
        "sparse_top_quartile_descriptive": {"count": len(sparse),
            "k_mae_256": float(sparse.k_abs_error_256_same_env.mean()),
            "k_mae_384": float(sparse.k_abs_error_384.mean()),
            "field_l2_256": float(sparse.field_relative_l2_256.mean()),
            "field_l2_384": float(sparse.field_relative_l2_384.mean())},
        "input_sha256": {"old_dataset_manifest": sha(OLD_DATA / "dataset_manifest.json"),
                         "new_dataset_manifest": sha(NEW_DATA / "dataset_manifest.json"),
                         "keff_384_report": sha(K_REPORT / "training_report.json"),
                         "field3d_384_report": sha(FIELD_REPORT / "training_report.json")},
        "quality": {"new_halton_failed_attempts_unused": len(new_manifest["failed_or_incomplete_attempts_not_used"]),
                    "nuclear_index_hash_counts": new_manifest["nuclear_index_hash_counts"],
                    "training_acceptance": "not_granted"},
        "software": {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
        "warnings": ["The original 23 test cases were examined during prior research; this is not a final untouched test.",
                     "The published 256 k model used XGBoost 3.4.1. Same-environment 256 baseline uses 3.2.0 for primary data-size comparison.",
                     "Original 256 and new 128 scenarios remain provisional; completed does not establish physics or source convergence.",
                     "Future adaptive selection must not use the 128 Halton outcomes."]}
    (OUT / "comparison.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    lines = ["# 256 → 384 Halton comparison", "",
             "PROVISIONAL / EXPLORATORY. No physical or training acceptance.",
             "Same original 23 test IDs. Original 208/25/23 split is frozen; 128 Halton cases join train only.",
             "The original 23 test cases were examined previously, so this is not a final untouched test.",
             "", "| Metric | 256 | 384 | New − old | Change |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for row in comparison.itertuples():
        lines.append(f"| {row.metric} | {row.baseline_256:.6g} | {row.halton_384:.6g} | {row.absolute_new_minus_old:+.6g} | {row.percent_change:+.2f}% |")
    lines += ["", "Primary k comparison retrains the 256 XGBoost model in the same local 3.2.0 runtime as the 384 model.",
              f"Published 256 k MAE/RMSE (XGBoost 3.4.1): {k_published['mae']:.6g} / {k_published['rmse']:.6g}.",
              f"Criticality-side mistakes around k=1: {sign_old} → {sign_new} (descriptive; not a safety classification).",
              "", "## Control insertion bands", "",
              "| Band | n | k MAE 256 → 384 | field L2 256 → 384 |",
              "| --- | ---: | ---: | ---: |"]
    for row in band.itertuples():
        lines.append(f"| {row.insertion_band} | {row.count} | {row.k_mae_256:.5g} → {row.k_mae_384:.5g} | {row.field_l2_256:.5g} → {row.field_l2_384:.5g} |")
    lines += ["", "## Limits", "",
              "Sparse region means the upper quartile of the 23 test cases by eight-dimensional normalized nearest-neighbor distance to the original 208 training cases. It is descriptive, not a validated domain threshold.",
              "Pitch changes physical x/y coordinates even when array indices match. The 3D target is relative kappa-fission, an approximation to fission energy generation.",
              "Raw negative 3D predictions and a separate clipped/renormalized comparison are recorded in the 3D report.",
              "The 11 alternate nuclear-index cases in the original 256 still need HDF5 byte-equivalence review.",
              "The two failed Halton-03 attempts were excluded, recorded, and replaced by its one completed attempt.",
              "No adaptive scenario selection should use the 128 Halton physical results.",
              ""]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].scatter(result.insertion_percent, result.k_abs_error_256_same_env, label="256", alpha=.75)
    axes[0].scatter(result.insertion_percent, result.k_abs_error_384, label="384", alpha=.75)
    axes[0].set(xlabel="Rod insertion (%)", ylabel="Absolute k error")
    axes[1].scatter(result.insertion_percent, result.field_relative_l2_256, label="256", alpha=.75)
    axes[1].scatter(result.insertion_percent, result.field_relative_l2_384, label="384", alpha=.75)
    axes[1].set(xlabel="Rod insertion (%)", ylabel="3D relative L2")
    for ax in axes:
        ax.legend()
        ax.grid(True, alpha=.25)
    fig.tight_layout(); fig.savefig(OUT / "test_error_by_insertion.png", dpi=150); plt.close(fig)
    print(json.dumps({"k_same_env_old": k_same, "k_new": k_new,
                      "field_old": float(field_old.mean()), "field_new": float(field_new.mean()),
                      "sparse": report["sparse_top_quartile_descriptive"]}))


if __name__ == "__main__":
    main()


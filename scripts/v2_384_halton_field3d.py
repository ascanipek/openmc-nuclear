"""Fixed 12-PCA + XGBoost exploratory 3D Halton branch training."""
import hashlib
import json
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
from sklearn.model_selection import KFold
from field3d_surrogate_v1 import FEATURES, SEED, field_metrics, make_model, rel_l2

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_384_halton_v1"
OLD = ROOT / "reports/field3d_surrogate_v1/test_case_metrics.csv"
OUT = ROOT / "reports/field3d_384_halton_v1"
PARAMS = {"max_depth": 4, "n_estimators": 120, "learning_rate": 0.05}
RANK = 12


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    if manifest["scenario_count"] != 384 or manifest["branch"] != "halton":
        raise ValueError("Wrong dataset branch")
    for name, digest in manifest["output_sha256"].items():
        if sha(DATA / name) != digest:
            raise ValueError(f"Dataset changed: {name}")
    splits = json.loads((DATA / "splits.json").read_text())
    rows = pd.read_csv(DATA / "scenarios.csv")
    if {k: len(splits[k]) for k in ("train", "calibration", "test")} != {
        "train": 336, "calibration": 25, "test": 23}:
        raise ValueError("Split counts differ")
    role = {sid: part for part in ("train", "calibration", "test") for sid in splits[part]}
    if any(role[sid] != part for sid, part in zip(rows.scenario_id, rows.split)):
        raise ValueError("Split identity differs")
    X = rows[FEATURES].to_numpy(float)
    with np.load(DATA / "fields.npz", allow_pickle=False) as fields:
        target = fields["target_normalized_kappa"].copy()
        fuel = fields["fuel_volume_fraction"] > 0
        fission = fields["fission_mean"]
        fission_se = fields["fission_std_dev"]
        raw_se = fields["kappa_fission_std_dev"].copy()
        x_edges, y_edges, z_edges = (fields[k].copy() for k in ("x_edges_cm", "y_edges_cm", "z_edges_cm"))
    if target.shape != (384, 20, 17, 17) or not np.allclose(target.sum(axis=(1, 2, 3)), 1, rtol=0, atol=1e-10):
        raise ValueError("Target shape/normalization differs")
    if np.any(target < 0) or np.any(target[~fuel] != 0):
        raise ValueError("Target mask/nonnegativity differs")
    if len(set(rows.scenario_id)) != 384:
        raise ValueError("Duplicate scenario")
    low = fuel & ((fission == 0) | (fission < 5*fission_se) |
                  (fission < 1e-6*fission.max(axis=(1, 2, 3))[:, None, None, None]))
    y = target.reshape(384, 5780, order="C")
    train = np.flatnonzero(rows.split.to_numpy() == "train")
    test = np.flatnonzero(rows.split.to_numpy() == "test")
    if max(test) >= 256:
        raise ValueError("Halton scenario leaked into test")
    cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    fold_rows = []
    for fold, (fit_local, val_local) in enumerate(cv.split(train), 1):
        fit, val = train[fit_local], train[val_local]
        mean = y[fit].mean(axis=0)
        _, _, basis = np.linalg.svd(y[fit]-mean, full_matrices=False)
        axes = basis[:RANK]
        coeff_fit = (y[fit]-mean) @ axes.T
        pca_val = (mean + (y[val]-mean) @ axes.T @ axes).reshape(-1, 20, 17, 17)
        model = make_model("XGBoost", PARAMS)
        model.fit(X[fit], coeff_fit)
        pred = (mean + model.predict(X[val]) @ axes).reshape(-1, 20, 17, 17)
        fold_rows.append({"fold": fold, "fit_count": len(fit), "validation_count": len(val),
                          "pca_relative_l2_mean": float(rel_l2(target[val], pca_val, fuel[val]).mean()),
                          "total_relative_l2_mean": float(rel_l2(target[val], pred, fuel[val]).mean())})
        print("CV", fold, fold_rows[-1]["total_relative_l2_mean"], flush=True)
    mean = y[train].mean(axis=0)
    _, singular, basis = np.linalg.svd(y[train]-mean, full_matrices=False)
    axes = basis[:RANK]
    coeff_train = (y[train]-mean) @ axes.T
    model = make_model("XGBoost", PARAMS)
    model.fit(X[train], coeff_train)
    pca = (mean + (y[test]-mean) @ axes.T @ axes).reshape(-1, 20, 17, 17)
    raw = (mean + model.predict(X[test]) @ axes).reshape(-1, 20, 17, 17)
    post = np.where(fuel[test], np.maximum(raw, 0), 0)
    denom = post.sum(axis=(1, 2, 3))
    if np.any(denom <= 0):
        raise ValueError("Postprocessed prediction has no positive fuel signal")
    post /= denom[:, None, None, None]
    pca_metrics = field_metrics(target[test], pca, fuel[test], low[test], raw_se[test])
    ml_metrics = field_metrics(target[test], raw, fuel[test], low[test], raw_se[test])
    post_metrics = field_metrics(target[test], post, fuel[test], low[test], raw_se[test])
    result = pd.DataFrame({"row": test, "scenario_id": rows.iloc[test].scenario_id.tolist(),
                           "insertion_percent": rows.iloc[test].insertion_percent.to_numpy(float)})
    for prefix, metrics in (("pca", pca_metrics), ("ml", ml_metrics), ("post", post_metrics)):
        for col in metrics:
            result[f"{prefix}_{col}"] = metrics[col].to_numpy()
    baseline = pd.read_csv(OLD).set_index("scenario_id")
    if set(result.scenario_id) != set(baseline.index) or len(baseline) != 23:
        raise ValueError("Baseline 3D test cases differ")
    baseline = baseline.loc[result.scenario_id]
    if not np.allclose(result.insertion_percent, baseline.insertion_percent.to_numpy(), rtol=0, atol=1e-10):
        raise ValueError("Baseline 3D physical controls differ")
    result["baseline_ml_relative_l2_fuel"] = baseline.ml_relative_l2_fuel.to_numpy()
    result["baseline_pca_relative_l2_fuel"] = baseline.pca_relative_l2_fuel.to_numpy()
    result["insertion_band"] = pd.cut(result.insertion_percent,
                                      bins=[-1, 100/3, 200/3, 101],
                                      labels=["low", "middle", "high"])
    old_train = rows[(rows.split == "train") & (rows.row < 256)]
    scale = (old_train[FEATURES].max() - old_train[FEATURES].min()).replace(0, 1).to_numpy(float)
    distance = np.linalg.norm(X[test, None, :] / scale - old_train[FEATURES].to_numpy(float)[None, :, :] / scale, axis=2)
    result["distance_to_old_train_nearest"] = distance.min(axis=1)
    result["sparse_region_top_quartile_old_train"] = (
        result.distance_to_old_train_nearest >= result.distance_to_old_train_nearest.quantile(.75))
    OUT.mkdir(parents=True)
    pd.DataFrame(fold_rows).to_csv(OUT / "cv_folds.csv", index=False)
    result.to_csv(OUT / "test_case_metrics.csv", index=False)
    joblib.dump(model, OUT / "selected_model.joblib")
    np.savez_compressed(OUT / "selected_pca.npz", mean=mean, basis=axes,
                        singular_values=singular, rank=RANK, feature_names=np.array(FEATURES),
                        train_scenario_ids=np.array(rows.iloc[train].scenario_id.tolist(), dtype="U64"))
    np.savez_compressed(OUT / "test_fields.npz", scenario_id=np.array(result.scenario_id.tolist(), dtype="U64"),
                        actual=target[test], pca_reconstructed=pca,
                        ml_predicted_raw=raw, ml_predicted_postprocessed=post,
                        fuel_mask=fuel[test], low_signal_mask=low[test],
                        raw_kappa_standard_error=raw_se[test],
                        x_edges_cm=x_edges[test], y_edges_cm=y_edges[test],
                        z_edges_cm=z_edges[test], axis_order=np.array(["sample", "z", "y", "x"]))
    bands = result.groupby("insertion_band", observed=False).agg(
        count=("scenario_id", "size"), old_relative_l2=("baseline_ml_relative_l2_fuel", "mean"),
        new_relative_l2=("ml_relative_l2_fuel", "mean")).reset_index()
    bands["absolute_new_minus_old"] = bands.new_relative_l2 - bands.old_relative_l2
    bands.to_csv(OUT / "insertion_bands.csv", index=False)
    example = [int(np.argmin(np.abs(result.insertion_percent.to_numpy()-v))) for v in (0, 50, 100)]
    for index in sorted(set(example)):
        fig, ax = plt.subplots(2, 3, figsize=(11, 7))
        for j, (name, data) in enumerate((("OpenMC", target[test][index]), ("PCA", pca[index]), ("ML raw", raw[index]))):
            xy = np.where(fuel[test][index, 10], data[10], np.nan)
            xz = np.where(fuel[test][index, :, 8, :], data[:, 8, :], np.nan)
            ax[0, j].imshow(xy, origin="lower", aspect="equal")
            ax[1, j].imshow(xz, origin="lower", aspect="auto")
            ax[0, j].set_title(name + " XY z=10")
            ax[1, j].set_title(name + " XZ y=8")
        fig.suptitle(str(result.scenario_id.iloc[index])[:12] + " | OpenMC vs PCA vs raw ML")
        fig.tight_layout()
        fig.savefig(OUT / f"test_compare_{int(result.row.iloc[index]):03d}.png", dpi=140)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    for index in sorted(set(example)):
        zc = (z_edges[test][index, :-1] + z_edges[test][index, 1:]) / 2
        ax.plot(zc, target[test][index].sum(axis=(1, 2)), label=f"OpenMC {index}")
        ax.plot(zc, raw[index].sum(axis=(1, 2)), "--", label=f"ML {index}")
    ax.set(xlabel="z (cm)", ylabel="normalized kappa share per slice",
           title="Axial production: same test cases")
    ax.legend(fontsize=7); fig.tight_layout(); fig.savefig(OUT / "test_axial_profiles.png", dpi=150); plt.close(fig)
    old_l2 = float(result.baseline_ml_relative_l2_fuel.mean())
    new_l2 = float(result.ml_relative_l2_fuel.mean())
    sparse = result[result.sparse_region_top_quartile_old_train]
    report = {"schema": "field3d_384_halton_exploratory_v1",
              "scientific_status": "PROVISIONAL_EXPLORATORY; no physical/statistical training acceptance",
              "features": FEATURES, "rank": RANK, "model": "XGBoost", "hyperparameters": PARAMS,
              "cv": {"folds": 5, "seed": SEED, "pca_fit": "each fold training subset only",
                     "fold_metrics": fold_rows,
                     "mean_pca_relative_l2": float(np.mean([x["pca_relative_l2_mean"] for x in fold_rows])),
                     "mean_total_relative_l2": float(np.mean([x["total_relative_l2_mean"] for x in fold_rows]))},
              "test_count": 23,
              "test": {"baseline_256_relative_l2_mean": old_l2,
                       "halton_384_relative_l2_mean": new_l2,
                       "absolute_change": new_l2-old_l2,
                       "percent_change": 100*(new_l2/old_l2-1),
                       "pca_reconstruction_relative_l2_mean": float(pca_metrics.relative_l2_fuel.mean()),
                       "ml_half_l1_share_error_mean": float(ml_metrics.half_l1_share_error_raw.mean()),
                       "ml_axial_half_l1_share_error_mean": float(ml_metrics.axial_half_l1_share_error_raw.mean()),
                       "ml_negative_fuel_voxels_total": int(ml_metrics.negative_fuel_voxels.sum()),
                       "ml_negative_fuel_voxel_fraction": float(ml_metrics.negative_fuel_voxels.sum() / fuel[test].sum()),
                       "ml_negative_fuel_share_magnitude_total": float(ml_metrics.negative_fuel_share_magnitude.sum()),
                       "raw_predicted_fuel_sum_min": float(ml_metrics.raw_predicted_fuel_sum.min()),
                       "raw_predicted_fuel_sum_max": float(ml_metrics.raw_predicted_fuel_sum.max()),
                       "post_relative_l2_mean": float(post_metrics.relative_l2_fuel.mean()),
                       "post_half_l1_share_error_mean": float(post_metrics.half_l1_share_error_raw.mean())},
              "sparse_top_quartile_descriptive": {"count": len(sparse),
                  "old_relative_l2": float(sparse.baseline_ml_relative_l2_fuel.mean()),
                  "new_relative_l2": float(sparse.ml_relative_l2_fuel.mean())},
              "axis_order": ["sample", "z", "y", "x"], "mesh_shape": [20, 17, 17],
              "source_dataset_manifest_sha256": sha(DATA / "dataset_manifest.json"),
              "baseline_test_metrics_sha256": sha(OLD),
              "software": {"sklearn": sklearn.__version__, "xgboost": xgboost.__version__},
              "warnings": ["XY coordinates vary with pin pitch; common array indices are not identical physical coordinates.",
                           "Normalized target uncertainty covariance is unavailable; raw MC tally standard errors are retained.",
                           "Raw negative values are reported; clipping and fuel renormalization are separate descriptive postprocessing.",
                           "These 23 test cases were examined previously and are not a fully untouched final validation set."]}
    (OUT / "training_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (OUT / "README.md").write_text(
        "# 3B relative kappa-fission, Halton 384 branch\n\n"
        "PROVISIONAL / EXPLORATORY. Frozen 256 split; 128 new Halton cases enter train only. "
        "12-component PCA is fit inside each of five training folds and once on the full 336 training cases. "
        "XGBoost depth=4, 120 trees, learning_rate=0.05. Raw predictions and separate clipped/renormalized "
        "comparison are retained. Same 23 previously examined test cases. "
        "Target is a fission energy generation approximation, not absolute reactor power. "
        "See training_report.json, test_case_metrics.csv and the XY/XZ/axial figures.\n")
    print(json.dumps({"old_relative_l2": old_l2, "new_relative_l2": new_l2,
                      "pca_relative_l2": report["test"]["pca_reconstruction_relative_l2_mean"],
                      "cv_total_relative_l2": report["cv"]["mean_total_relative_l2"]}), flush=True)


if __name__ == "__main__":
    main()



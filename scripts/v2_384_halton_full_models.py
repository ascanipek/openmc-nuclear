"""Train provisional 384-case full-data k and 3D surrogate candidates; no independent test."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import tempfile
import time
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
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor
from field3d_surrogate_v1 import field_metrics, make_model, rel_l2
from v2_384_halton_repeated_cv import FEATURES, K_PARAMS, FIELD_PARAMS, RANK, sha

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_384_halton_v1"
OLD = ROOT / "datasets/v2_256_preview_v1"
CV = ROOT / "reports/repeated_cv_256_vs_384_v1"
OUT = ROOT / "reports/full384_models_v1"


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    source = json.loads((DATA / "dataset_manifest.json").read_text())
    if source["scenario_count"] != 384 or source["branch"] != "halton":
        raise ValueError("Wrong full-data source")
    for name, digest in source["output_sha256"].items():
        if sha(DATA / name) != digest:
            raise ValueError(f"Dataset changed: {name}")
    for name, digest in source["old_dataset_sha256"].items():
        if sha(OLD / name) != digest:
            raise ValueError(f"Old source changed: {name}")
    cv_manifest = json.loads((CV / "reproducibility_manifest.json").read_text())
    if cv_manifest["source_dataset_manifest_sha256"] != sha(DATA / "dataset_manifest.json"):
        raise ValueError("CV and full-data source differ")
    if cv_manifest["model_settings"]["k"] != K_PARAMS or cv_manifest["model_settings"]["field"] != {
            "pca_rank": RANK, "xgboost": FIELD_PARAMS}:
        raise ValueError("CV and full-data model settings differ")
    rows = pd.read_csv(DATA / "scenarios.csv")
    targets = pd.read_csv(DATA / "targets_keff.csv")
    if len(rows) != 384 or rows.scenario_id.nunique() != 384 or not rows.scenario_id.equals(targets.scenario_id):
        raise ValueError("Scenario/target identity mismatch")
    X = rows[FEATURES].to_numpy(float)
    k = targets.k_mean.to_numpy(float)
    with np.load(DATA / "fields.npz", allow_pickle=False) as fields:
        truth = fields["target_normalized_kappa"].copy()
        fuel = fields["fuel_volume_fraction"] > 0
        fission = fields["fission_mean"].copy()
        fission_se = fields["fission_std_dev"].copy()
        raw_se = fields["kappa_fission_std_dev"].copy()
    if truth.shape != (384, 20, 17, 17) or not np.allclose(truth.sum(axis=(1,2,3)), 1, rtol=0, atol=1e-10):
        raise ValueError("Full-data 3D target invalid")
    low = fuel & ((fission == 0) | (fission < 5*fission_se) |
                  (fission < 1e-6*fission.max(axis=(1,2,3))[:,None,None,None]))
    start = time.monotonic()
    keff_model = XGBRegressor(**K_PARAMS)
    keff_model.fit(X, k)
    k_fit = keff_model.predict(X).astype(float)
    flat = truth.reshape(384, 5780, order="C")
    mean = flat.mean(axis=0)
    _, singular, basis = np.linalg.svd(flat-mean, full_matrices=False)
    axes = basis[:RANK]
    coefficient = (flat-mean) @ axes.T
    field_model = make_model("XGBoost", FIELD_PARAMS)
    field_model.fit(X, coefficient)
    raw = (mean + field_model.predict(X) @ axes).reshape(384, 20, 17, 17)
    pca_reconstruction = (mean + coefficient @ axes).reshape(384, 20, 17, 17)
    post = np.where(fuel, np.maximum(raw, 0), 0)
    denom = post.sum(axis=(1,2,3))
    if np.any(denom <= 0):
        raise ValueError("Postprocessing has no positive fuel signal")
    post /= denom[:,None,None,None]
    raw_metrics = field_metrics(truth, raw, fuel, low, raw_se)
    post_metrics = field_metrics(truth, post, fuel, low, raw_se)
    pca_l2 = rel_l2(truth, pca_reconstruction, fuel)
    apparent = {
        "label": "APPARENT_IN_SAMPLE_ONLY; NOT independent generalization or physical accuracy",
        "keff_mae": float(mean_absolute_error(k, k_fit)),
        "keff_rmse": float(np.sqrt(mean_squared_error(k, k_fit))),
        "field_raw_relative_l2_mean": float(raw_metrics.relative_l2_fuel.mean()),
        "field_pca_reconstruction_relative_l2_mean": float(pca_l2.mean()),
        "field_raw_half_l1_mean": float(raw_metrics.half_l1_share_error_raw.mean()),
        "field_raw_axial_half_l1_mean": float(raw_metrics.axial_half_l1_share_error_raw.mean()),
        "field_negative_fuel_voxel_fraction": float(raw_metrics.negative_fuel_voxels.sum()/fuel.sum()),
        "field_post_relative_l2_mean": float(post_metrics.relative_l2_fuel.mean()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".full384_work_", dir=OUT.parent) as temporary:
        work = Path(temporary)
        joblib.dump(keff_model, work / "keff_model.joblib")
        joblib.dump(field_model, work / "field3d_coefficient_model.joblib")
        np.savez_compressed(work / "field3d_pca.npz", mean=mean, basis=axes,
                            singular_values=singular, rank=RANK,
                            feature_names=np.asarray(FEATURES, dtype="U64"),
                            fit_scenario_ids=np.asarray(rows.scenario_id.tolist(), dtype="U64"),
                            axis_order=np.asarray(["sample", "z", "y", "x"], dtype="U8"))
        pd.DataFrame({"scenario_id": rows.scenario_id, "k_true": k,
                      "k_apparent_fit": k_fit,
                      "k_mc_standard_error": targets.k_mc_standard_error,
                      "split_before_full_fit": rows.split}).to_csv(work / "keff_apparent_fit.csv", index=False)
        np.savez_compressed(work / "field3d_apparent_fit.npz",
                            scenario_id=np.asarray(rows.scenario_id.tolist(), dtype="U64"),
                            predicted_raw=raw, predicted_postprocessed=post,
                            fuel_mask=fuel, axis_order=np.asarray(["sample","z","y","x"],dtype="U8"))
        (work / "apparent_fit_metrics.json").write_text(
            json.dumps(apparent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fig, axes_plot = plt.subplots(1, 2, figsize=(10, 4))
        axes_plot[0].scatter(k, k_fit, s=12, alpha=.55)
        lim = [min(k.min(), k_fit.min()), max(k.max(), k_fit.max())]
        axes_plot[0].plot(lim, lim, "k--", lw=1)
        axes_plot[0].set(xlabel="OpenMC k", ylabel="Full-data apparent fit k",
                         title="Training fit only")
        axes_plot[1].hist(raw_metrics.relative_l2_fuel, bins=20)
        axes_plot[1].set(xlabel="Apparent 3D relative L2", ylabel="Scenarios",
                         title="Training fit only")
        fig.tight_layout(); fig.savefig(work / "apparent_fit.png", dpi=150); plt.close(fig)
        report = {
            "schema": "beavrs_v2_full384_candidate_v1",
            "status": "RESEARCH_APPLICATION_PROTOTYPE; PROVISIONAL_EXPLORATORY; not physics validated",
            "fit_count": 384, "fit_membership": "all 384, including old 23 test scenarios",
            "independent_test_count_for_this_model": 0,
            "source_dataset_manifest_sha256": sha(DATA / "dataset_manifest.json"),
            "source_cv_manifest_sha256": sha(CV / "reproducibility_manifest.json"),
            "features": FEATURES,
            "model_settings": {"k": K_PARAMS, "field_pca_rank": RANK,
                               "field_xgboost": FIELD_PARAMS},
            "array_order": ["sample","z","y","x"], "mesh_shape": [20,17,17],
            "target": "normalized kappa-fission energy-generation approximation",
            "apparent_fit": apparent,
            "software": {"python": platform.python_version(), "numpy": np.__version__,
                         "pandas": pd.__version__, "sklearn": sklearn.__version__,
                         "xgboost": xgboost.__version__, "joblib": joblib.__version__},
            "runtime_seconds": time.monotonic()-start,
            "warnings": [
                "Apparent fit errors are in-sample and cannot be used as independent test performance.",
                "The original 23 test scenarios are now in this model's training set.",
                "Generalization of this candidate requires new independent OpenMC scenarios.",
                "The first 256 and Halton 128 remain review_required/provisional; no physical or statistical acceptance.",
                "11 old cases use an alternate nuclear-index hash; HDF5 byte equivalence remains unassessed.",
                "Measured-zero and low-signal voxels remain; raw MC standard errors are in the source dataset.",
                "Do not use Halton 128 physical outcomes for future adaptive scenario selection."
            ]
        }
        (work / "README.md").write_text(
            "# Full 384 research model candidates\n\n"
            "**RESEARCH APPLICATION PROTOTYPE — PROVISIONAL / EXPLORATORY.** "
            "All 384 scenarios, including the former 23 test cases, trained these models. "
            "There is no independent test of this full-data model. "
            "The CV report is separate and does not become an external validation of the full-data fit.\n\n"
            "Models: keff_model.joblib; field3d_coefficient_model.joblib with field3d_pca.npz. "
            "The 3D target is relative kappa-fission, not absolute reactor power. "
            "Use the eight features in the manifest order and preserve [z,y,x] geometry. "
            "The apparent fit outputs are training diagnostics only. "
            "New independent OpenMC scenarios and physical review are required before reliability claims.\n",
            encoding="utf-8")
        report["output_sha256"] = {p.name: sha(p) for p in work.iterdir() if p.is_file()}
        (work / "reproducibility_manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        work.rename(OUT)
    print(json.dumps({"output": str(OUT), "fit_count": 384,
                      "apparent": apparent, "independent_test": 0,
                      "seconds": time.monotonic()-start}))


if __name__ == "__main__":
    main()


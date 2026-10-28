"""Train the frozen exploratory models on 208+32+32 adaptive rows; no transport."""
from __future__ import annotations

import json
import platform
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.model_selection import KFold
from v2_288_adaptive01_train import (
    FEATURES, K_PARAMS, FIELD_PARAMS, RANK, SEED, fit_field,
    predict_field, summary_k, sha, rms, field_metrics, rel_l2,
)
from xgboost import XGBRegressor
import xgboost

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_320_adaptive02_exploratory_v1"
PREVIOUS = ROOT / "datasets/v2_288_adaptive01_exploratory_v1"
BASELINE = ROOT / "reports/adaptive01_vs_256_v1"
OUT = ROOT / "reports/adaptive02_vs_256_adaptive01_v1"


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    prior_manifest = json.loads((PREVIOUS / "dataset_manifest.json").read_text())
    for folder, record in ((DATA, manifest), (PREVIOUS, prior_manifest)):
        for name, expected in record["output_sha256"].items():
            if sha(folder / name) != expected:
                raise ValueError(f"Frozen input changed: {folder / name}")
    if manifest["scenario_count"] != 320 or manifest["branch"] != "adaptive_02":
        raise ValueError("Wrong adaptive dataset")
    rows = pd.read_csv(DATA / "scenarios.csv")
    targets = pd.read_csv(DATA / "targets_keff.csv")
    previous_rows = pd.read_csv(PREVIOUS / "scenarios.csv")
    previous_targets = pd.read_csv(PREVIOUS / "targets_keff.csv")
    split = json.loads((DATA / "splits.json").read_text())
    previous_split = json.loads((PREVIOUS / "splits.json").read_text())
    if (len(rows) != 320 or rows.scenario_id.nunique() != 320 or
            not rows.scenario_id.equals(targets.scenario_id) or
            not rows.iloc[:288].reset_index(drop=True).equals(previous_rows) or
            not targets.iloc[:288].reset_index(drop=True).equals(previous_targets) or
            split["train"] != [*previous_split["train"], *rows.scenario_id.iloc[288:].tolist()] or
            split["calibration"] != previous_split["calibration"] or
            split["test"] != previous_split["test"] or
            {key: len(split[key]) for key in ("train", "calibration", "test")} !=
            {"train": 272, "calibration": 25, "test": 23}):
        raise ValueError("Adaptive data or frozen split mismatch")
    with np.load(DATA / "fields.npz", allow_pickle=False) as data, np.load(PREVIOUS / "fields.npz", allow_pickle=False) as prior:
        for key in prior.files:
            if not np.array_equal(data[key][:288], prior[key]):
                raise ValueError(f"Previous field changed: {key}")
        field = data["target_normalized_kappa"].copy()
        fuel = data["fuel_volume_fraction"] > 0
        fission = data["fission_mean"].copy()
        fission_se = data["fission_std_dev"].copy()
        raw_se = data["kappa_fission_std_dev"].copy()
        z_edges = data["z_edges_cm"].copy()
    if (field.shape != (320, 20, 17, 17) or np.any(field < 0) or
            np.any(field[~fuel] != 0) or
            not np.allclose(field.sum(axis=(1, 2, 3)), 1, atol=1e-10, rtol=0)):
        raise ValueError("Field geometry or normalization mismatch")
    X = rows[FEATURES].to_numpy(float)
    k = targets.k_mean.to_numpy(float)
    flat = field.reshape(320, 5780, order="C")
    train = np.flatnonzero(rows.split.to_numpy() == "train")
    cal = np.flatnonzero(rows.split.to_numpy() == "calibration")
    test = np.flatnonzero(rows.split.to_numpy() == "test")
    if (len(train), len(cal), len(test)) != (272, 25, 23):
        raise ValueError("Unexpected training split")
    cv_rows = []
    for fold, (fit_local, val_local) in enumerate(KFold(5, shuffle=True, random_state=SEED).split(train), 1):
        fit, val = train[fit_local], train[val_local]
        if set(fit) & set(val) or (set(fit) | set(val)) & (set(cal) | set(test)):
            raise ValueError("Cross-validation leakage")
        km = XGBRegressor(**K_PARAMS)
        km.fit(X[fit], k[fit])
        fm, mean, basis, _ = fit_field(X, flat, fit)
        kp = km.predict(X[val])
        fp = predict_field(fm, mean, basis, X[val])
        pca_val = (mean + (flat[val] - mean) @ basis.T @ basis).reshape(-1, 20, 17, 17)
        cv_rows.append({
            "fold": fold, "fit_count": len(fit), "validation_count": len(val),
            "k_mae": float(np.abs(kp - k[val]).mean()), "k_rmse": rms(k[val], kp),
            "field_relative_l2": float(rel_l2(field[val], fp, fuel[val]).mean()),
            "pca_reconstruction_relative_l2": float(rel_l2(field[val], pca_val, fuel[val]).mean()),
            "fit_scenario_ids": rows.scenario_id.iloc[fit].tolist(),
            "validation_scenario_ids": rows.scenario_id.iloc[val].tolist(),
        })
        print(f"train-only CV {fold}/5", flush=True)
    km = XGBRegressor(**K_PARAMS)
    km.fit(X[train], k[train])
    fm, mean, basis, singular = fit_field(X, flat, train)
    kp = km.predict(X[test]).astype(float)
    raw = predict_field(fm, mean, basis, X[test])
    pca = (mean + (flat[test] - mean) @ basis.T @ basis).reshape(-1, 20, 17, 17)
    post = np.where(fuel[test], np.maximum(raw, 0), 0)
    post_total = post.sum(axis=(1, 2, 3))
    if np.any(post_total <= 0):
        raise ValueError("Postprocessed field has nonpositive total")
    post /= post_total[:, None, None, None]
    low = fuel[test] & ((fission[test] == 0) | (fission[test] < 5 * fission_se[test]) |
                        (fission[test] < 1e-6 * fission[test].max(axis=(1, 2, 3))[:, None, None, None]))
    raw_m = field_metrics(field[test], raw, fuel[test], low, raw_se[test])
    post_m = field_metrics(field[test], post, fuel[test], low, raw_se[test])
    pca_m = field_metrics(field[test], pca, fuel[test], low, raw_se[test])
    ids = rows.scenario_id.iloc[test].tolist()
    old = pd.read_csv(BASELINE / "test_per_scenario.csv").set_index("scenario_id").loc[ids]
    if (len(old) != 23 or not np.allclose(old.k_openmc.to_numpy(float), k[test], rtol=0, atol=1e-12) or
            not np.allclose(old.insertion_percent.to_numpy(float), rows.iloc[test].insertion_percent.to_numpy(float), rtol=0, atol=1e-12)):
        raise ValueError("Archived 23-case predictions or truth differ")
    per_case = pd.DataFrame({
        "scenario_id": ids, "insertion_percent": rows.iloc[test].insertion_percent.to_numpy(float),
        "k_openmc": k[test], "k_mc_standard_error": targets.iloc[test].k_mc_standard_error.to_numpy(float),
        "k_initial_256": old.k_initial_256_same_env.to_numpy(float),
        "k_adaptive01_288": old.k_adaptive01_288.to_numpy(float),
        "k_adaptive02_320": kp,
    })
    for stage in ("initial_256", "adaptive01_288"):
        for metric in raw_m.columns:
            per_case[f"{stage}_field_raw_{metric}"] = old[f"{stage}_field_raw_{metric}"].to_numpy()
            per_case[f"{stage}_field_post_{metric}"] = old[f"{stage}_field_post_{metric}"].to_numpy()
    for label, values in (("field_raw", raw_m), ("field_post", post_m), ("pca", pca_m)):
        for metric in values:
            per_case[f"adaptive02_320_{label}_{metric}"] = values[metric].to_numpy()
    per_case["insertion_band"] = pd.cut(per_case.insertion_percent, [-1, 100/3, 200/3, 101],
                                         labels=["low", "middle", "high"])
    metric_rows, physical = [], {}
    for stage in ("initial_256", "adaptive01_288", "adaptive02_320"):
        ks = summary_k(k[test], per_case[f"k_{stage}"].to_numpy(float))
        rel = per_case[f"{stage}_field_raw_relative_l2_fuel"].to_numpy(float)
        post_rel = per_case[f"{stage}_field_post_relative_l2_fuel"].to_numpy(float)
        neg = per_case[f"{stage}_field_raw_negative_fuel_voxels"].to_numpy(int)
        neg_share = per_case[f"{stage}_field_raw_negative_fuel_share_magnitude"].to_numpy(float)
        physical[stage] = {
            "field_relative_l2_mean": float(rel.mean()), "field_relative_l2_p95": float(np.percentile(rel, 95)),
            "field_post_relative_l2_mean": float(post_rel.mean()),
            "field_post_minus_raw_relative_l2": float(post_rel.mean() - rel.mean()),
            "negative_fuel_voxels_total": int(neg.sum()),
            "negative_fuel_voxel_fraction": float(neg.sum() / fuel[test].sum()),
            "negative_fuel_share_magnitude_total": float(neg_share.sum()),
            "raw_fuel_sum_min": float(per_case[f"{stage}_field_raw_raw_predicted_fuel_sum"].min()),
            "raw_fuel_sum_max": float(per_case[f"{stage}_field_raw_raw_predicted_fuel_sum"].max()),
        }
        metric_rows.append({"stage": stage, "training_count": {"initial_256": 208, "adaptive01_288": 240, "adaptive02_320": 272}[stage],
                            **ks, **physical[stage]})
    bands = []
    for band, frame in per_case.groupby("insertion_band", observed=False):
        record = {"insertion_band": str(band), "test_count": len(frame)}
        for stage in ("initial_256", "adaptive01_288", "adaptive02_320"):
            record[f"{stage}_k_mae"] = float(np.abs(frame[f"k_{stage}"] - frame.k_openmc).mean())
            record[f"{stage}_field_l2"] = float(frame[f"{stage}_field_raw_relative_l2_fuel"].mean())
        bands.append(record)
    report = {
        "schema": "adaptive02_vs_256_adaptive01_exploratory_v1",
        "scientific_status": "PROVISIONAL_EXPLORATORY",
        "data": {"source_dataset_manifest_sha256": sha(DATA / "dataset_manifest.json"),
                 "baseline_test_predictions_sha256": sha(BASELINE / "test_per_scenario.csv"),
                 "train_count": 272, "calibration_excluded": 25, "same_test_count": 23,
                 "test_policy": "Held out of fitting, PCA, CV and hyperparameter choice; previously inspected, not external"},
        "models": {"keff": {"algorithm": "XGBoost", "params": K_PARAMS},
                   "field": {"algorithm": "PCA(12)+XGBoost", "rank": RANK, "params": FIELD_PARAMS},
                   "feature_order": FEATURES, "cv_seed": SEED,
                   "hyperparameter_policy": "Frozen from prior model; no search"},
        "cv": {"folds": 5, "mean_k_mae": float(np.mean([x["k_mae"] for x in cv_rows])),
               "mean_k_rmse": float(np.mean([x["k_rmse"] for x in cv_rows])),
               "mean_field_relative_l2": float(np.mean([x["field_relative_l2"] for x in cv_rows])),
               "mean_pca_reconstruction_relative_l2": float(np.mean([x["pca_reconstruction_relative_l2"] for x in cv_rows]))},
        "same_23_test": metric_rows,
        "insertion_bands": bands,
        "warnings": [
            "All datasets are exploratory and lack physical/statistical/training acceptance.",
            "Thirty-two ADAPTIVE-02 source statepoints were omitted from the lightweight handoff.",
            "Eleven original scenarios use an alternate nuclear index; HDF5 byte equivalence is unassessed.",
            "Source convergence and zero/low-signal fuel voxels need independent review.",
            "The same 23 test scenarios have been examined repeatedly; they are not untouched external validation.",
            "Pitch changes physical XY coordinates despite fixed [z,y,x] mesh indices.",
        ],
        "software": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "sklearn": sklearn.__version__,
                     "xgboost": xgboost.__version__},
    }
    OUT.mkdir(parents=True)
    joblib.dump(km, OUT / "adaptive02_320_keff.joblib")
    joblib.dump(fm, OUT / "adaptive02_320_field_coefficients.joblib")
    np.savez_compressed(OUT / "adaptive02_320_pca.npz", mean=mean, basis=basis,
                        singular_values=singular, train_scenario_ids=np.asarray(rows.scenario_id.iloc[train].tolist(), dtype="U64"),
                        rank=RANK, feature_names=np.asarray(FEATURES, dtype="U48"))
    per_case.to_csv(OUT / "test_per_scenario.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(OUT / "same_test_comparison.csv", index=False)
    pd.DataFrame(bands).to_csv(OUT / "insertion_bands.csv", index=False)
    pd.DataFrame([{key: val for key, val in row.items() if key not in ("fit_scenario_ids", "validation_scenario_ids")}
                  for row in cv_rows]).to_csv(OUT / "cv_folds.csv", index=False)
    (OUT / "cv_memberships.json").write_text(json.dumps(cv_rows, indent=2) + "\n")
    np.savez_compressed(OUT / "test_fields.npz", scenario_id=np.asarray(ids, dtype="U64"),
                        actual=field[test], adaptive02_raw=raw, adaptive02_post=post,
                        pca_reconstruction=pca, fuel_mask=fuel[test], low_signal_mask=low,
                        z_edges_cm=z_edges[test], axis_order=np.asarray(["sample", "z", "y", "x"]))
    (OUT / "training_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for stage in ("initial_256", "adaptive01_288", "adaptive02_320"):
        axes[0].scatter(k[test], per_case[f"k_{stage}"], label=stage, alpha=.7)
    lo = min(k[test].min(), *(per_case[f"k_{stage}"].min() for stage in ("initial_256", "adaptive01_288", "adaptive02_320")))
    hi = max(k[test].max(), *(per_case[f"k_{stage}"].max() for stage in ("initial_256", "adaptive01_288", "adaptive02_320")))
    axes[0].plot([lo, hi], [lo, hi], "k--")
    axes[0].set(xlabel="OpenMC k", ylabel="Predicted k")
    axes[0].legend(fontsize=8)
    axes[1].boxplot([per_case[f"{stage}_field_raw_relative_l2_fuel"] for stage in
                     ("initial_256", "adaptive01_288", "adaptive02_320")],
                    tick_labels=["256", "+A01", "+A02"])
    axes[1].set(ylabel="Fuel field relative L2")
    fig.tight_layout()
    fig.savefig(OUT / "same_test_comparison.png", dpi=150)
    plt.close(fig)
    lines = ["# Adaptive 02 sonrası model karşılaştırması", "",
             "**PROVISIONAL_EXPLORATORY.** Fiziksel, istatistiksel ve eğitim kabulü verilmedi.", "",
             "Aynı 23 eski test senaryosu; 208 → 240 → 272 eğitim. Kalibrasyon 25 değişmedi.",
             "PCA ve modeller yalnız eğitim fold'unda fit edildi; hiperparametre araması yapılmadı.", "",
             "| Aşama | Eğitim | k MAE | k RMSE | k max abs | k=1 uyuşmazlık | 3B L2 ort. | 3B L2 P95 | Negatif voxel oranı | Kırpılmış 3B L2 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for item in metric_rows:
        lines.append(f"| {item['stage']} | {item['training_count']} | {item['mae']:.6f} | {item['rmse']:.6f} | "
                     f"{item['max_absolute_error']:.6f} | {item['k_one_threshold_disagreements']} | "
                     f"{item['field_relative_l2_mean']:.6f} | {item['field_relative_l2_p95']:.6f} | "
                     f"{item['negative_fuel_voxel_fraction']:.6f} | {item['field_post_relative_l2_mean']:.6f} |")
    lines += ["", "Negatif enerji payı, toplam normalizasyon, giriş bantları ve test bazlı metrikler JSON/CSV'dedir.",
              "Kırpma ve yeniden normalizasyon yalnız ayrı değerlendirmedir; ham tahminler korunmuştur.",
              "Adaptive 02 statepoint'leri öğrenci kaynak makinesindedir. Kaynak yakınsaması ve veri eşdeğerliği açık konulardır.",
              "Bu 23 test senaryosu önceki çalışmalarda incelendi; yeni dış doğrulama değildir.", ""]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": str(OUT), "cv": report["cv"], "same_test": metric_rows}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

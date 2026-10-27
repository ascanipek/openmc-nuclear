"""Exploratory 256 versus 256+ADAPTIVE-01 surrogate comparison; no transport."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold

sys.path.insert(0, "/tmp/openmc_xgboost_320")
import xgboost
from xgboost import XGBRegressor
from field3d_surrogate_v1 import field_metrics, make_model, rel_l2

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "datasets/v2_256_preview_v1"
DATA = ROOT / "datasets/v2_288_adaptive01_exploratory_v1"
OUT = ROOT / "reports/adaptive01_vs_256_v1"
OLD_KEFF_PRED = ROOT / "kaggle/ml_keff_v1/results/test_predictions.csv"
OLD_FIELD_PRED = ROOT / "reports/field3d_surrogate_v1/test_case_metrics.csv"
FEATURES = ["u235_enrichment_wt_percent", "fuel_temperature_K", "moderator_temperature_K",
            "coolant_pressure_MPa", "elemental_boron_ppm", "pin_pitch_cm",
            "pellet_radius_cm", "insertion_percent"]
SEED = 20261025
K_PARAMS = {"objective": "reg:squarederror", "tree_method": "hist", "random_state": SEED,
            "n_jobs": min(4, os.cpu_count() or 1), "subsample": 1.0,
            "colsample_bytree": 1.0, "n_estimators": 400, "max_depth": 2,
            "learning_rate": 0.05}
FIELD_PARAMS = {"max_depth": 4, "n_estimators": 120, "learning_rate": 0.05}
RANK = 12


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rms(actual, prediction):
    return float(np.sqrt(mean_squared_error(actual, prediction)))


def summary_k(actual, pred):
    error = pred - actual
    return {"mae": float(mean_absolute_error(actual, pred)), "rmse": rms(actual, pred),
            "r2": float(r2_score(actual, pred)),
            "max_absolute_error": float(np.max(np.abs(error))),
            "k_one_threshold_disagreements": int(np.count_nonzero((pred >= 1) != (actual >= 1)))}


def fit_field(X, yflat, fit):
    mean = yflat[fit].mean(axis=0)
    _, singular, vectors = np.linalg.svd(yflat[fit] - mean, full_matrices=False)
    basis = vectors[:RANK].copy()
    coefficients = (yflat[fit] - mean) @ basis.T
    model = make_model("XGBoost", FIELD_PARAMS)
    model.fit(X[fit], coefficients)
    return model, mean, basis, singular


def predict_field(model, mean, basis, X):
    return (mean + model.predict(X) @ basis).reshape(-1, 20, 17, 17)


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    old_manifest = json.loads((OLD / "dataset_manifest.json").read_text())
    if manifest["branch"] != "adaptive_01" or manifest["scenario_count"] != 288:
        raise ValueError("Wrong adaptive dataset")
    for name, digest in manifest["output_sha256"].items():
        if sha(DATA / name) != digest:
            raise ValueError(f"Adaptive dataset changed: {name}")
    for name, digest in old_manifest["output_sha256"].items():
        if sha(OLD / name) != digest:
            raise ValueError(f"Frozen 256 changed: {name}")
    rows = pd.read_csv(DATA / "scenarios.csv")
    targets = pd.read_csv(DATA / "targets_keff.csv")
    old_rows = pd.read_csv(OLD / "scenarios.csv")
    old_targets = pd.read_csv(OLD / "targets_keff.csv")
    old_split = json.loads((OLD / "splits.json").read_text())
    split = json.loads((DATA / "splits.json").read_text())
    if (not rows.iloc[:256].reset_index(drop=True).equals(old_rows) or
            not targets.iloc[:256].reset_index(drop=True).equals(old_targets) or
            len(rows) != 288 or rows.scenario_id.nunique() != 288 or
            not rows.scenario_id.equals(targets.scenario_id) or
            split["train"] != [*old_split["train"], *rows.scenario_id.iloc[256:].tolist()] or
            split["calibration"] != old_split["calibration"] or
            split["test"] != old_split["test"]):
        raise ValueError("Frozen rows/targets/splits differ")
    role = {sid: key for key in ("train", "calibration", "test") for sid in split[key]}
    if len(role) != 288 or any(role[sid] != part for sid, part in zip(rows.scenario_id, rows.split)):
        raise ValueError("Split role mismatch")
    with np.load(DATA / "fields.npz", allow_pickle=False) as data, np.load(OLD / "fields.npz", allow_pickle=False) as old:
        for key in old.files:
            if not np.array_equal(data[key][:256], old[key]):
                raise ValueError(f"Old field changed: {key}")
        field = data["target_normalized_kappa"].copy()
        fuel = data["fuel_volume_fraction"] > 0
        fission = data["fission_mean"].copy()
        fission_se = data["fission_std_dev"].copy()
        raw_se = data["kappa_fission_std_dev"].copy()
        z_edges = data["z_edges_cm"].copy()
    if (field.shape != (288, 20, 17, 17) or
            not np.allclose(field.sum(axis=(1,2,3)), 1, atol=1e-10, rtol=0) or
            np.any(field < 0) or np.any(field[~fuel] != 0)):
        raise ValueError("Field shape/mask/normalization incompatible")
    X = rows[FEATURES].to_numpy(float)
    k = targets.k_mean.to_numpy(float)
    flat = field.reshape(288, 5780, order="C")
    train_old = np.flatnonzero((rows.split == "train").to_numpy() & (rows.row < 256).to_numpy())
    train_new = np.flatnonzero((rows.split == "train").to_numpy())
    test = np.flatnonzero((rows.split == "test").to_numpy())
    cal = np.flatnonzero((rows.split == "calibration").to_numpy())
    if (len(train_old), len(train_new), len(cal), len(test)) != (208, 240, 25, 23) or max(test) >= 256:
        raise ValueError("Training/calibration/test partition differs")
    cv_rows = []
    for fold, (fit_local, val_local) in enumerate(KFold(5, shuffle=True, random_state=SEED).split(train_new), 1):
        fit, val = train_new[fit_local], train_new[val_local]
        if set(fit) & set(val) or set(fit) & (set(cal) | set(test)) or set(val) & (set(cal) | set(test)):
            raise ValueError("CV data leakage")
        km = XGBRegressor(**K_PARAMS)
        km.fit(X[fit], k[fit])
        kp = km.predict(X[val])
        fm, mean, basis, _ = fit_field(X, flat, fit)
        fp = predict_field(fm, mean, basis, X[val])
        pca_val = (mean + (flat[val]-mean) @ basis.T @ basis).reshape(-1,20,17,17)
        cv_rows.append({"fold": fold, "fit_count": len(fit), "validation_count": len(val),
                        "k_mae": float(mean_absolute_error(k[val], kp)),
                        "k_rmse": rms(k[val], kp),
                        "field_relative_l2": float(rel_l2(field[val], fp, fuel[val]).mean()),
                        "pca_reconstruction_relative_l2": float(rel_l2(field[val], pca_val, fuel[val]).mean()),
                        "fit_scenario_ids": rows.scenario_id.iloc[fit].tolist(),
                        "validation_scenario_ids": rows.scenario_id.iloc[val].tolist()})
        print("train-only CV", fold, "field L2", cv_rows[-1]["field_relative_l2"], flush=True)
    models = {}
    for label, fit in (("initial_256", train_old), ("adaptive01_288", train_new)):
        km = XGBRegressor(**K_PARAMS)
        km.fit(X[fit], k[fit])
        fm, mean, basis, singular = fit_field(X, flat, fit)
        kp = km.predict(X[test]).astype(float)
        fp = predict_field(fm, mean, basis, X[test])
        pca = (mean + (flat[test]-mean) @ basis.T @ basis).reshape(-1,20,17,17)
        models[label] = {"keff_model": km, "field_model": fm, "pca_mean": mean,
                         "pca_basis": basis, "pca_singular": singular,
                         "k_pred": kp, "field_pred": fp, "pca_test": pca,
                         "train_ids": rows.scenario_id.iloc[fit].tolist()}
    low = fuel[test] & ((fission[test] == 0) | (fission[test] < 5*fission_se[test]) |
                        (fission[test] < 1e-6*fission[test].max(axis=(1,2,3))[:,None,None,None]))
    results = {}
    ids = rows.scenario_id.iloc[test].tolist()
    for label, bundle in models.items():
        raw = bundle["field_pred"]
        post = np.where(fuel[test], np.maximum(raw, 0), 0)
        denom = post.sum(axis=(1,2,3))
        if np.any(denom <= 0):
            raise ValueError("Postprocessed field has zero fuel total")
        post /= denom[:,None,None,None]
        results[label] = {"k": summary_k(k[test], bundle["k_pred"]),
                          "field_raw": field_metrics(field[test], raw, fuel[test], low, raw_se[test]),
                          "field_post": field_metrics(field[test], post, fuel[test], low, raw_se[test]),
                          "pca": field_metrics(field[test], bundle["pca_test"], fuel[test], low, raw_se[test]),
                          "post_field": post}
    old_saved_k = pd.read_csv(OLD_KEFF_PRED).set_index("scenario_id")
    old_saved_field = pd.read_csv(OLD_FIELD_PRED).set_index("scenario_id")
    if (set(ids) != set(old_saved_k.index) or set(ids) != set(old_saved_field.index) or
            not np.allclose(old_saved_k.loc[ids].k_mean, k[test], rtol=0, atol=1e-12)):
        raise ValueError("Archived 256 test baseline differs")
    per_case = pd.DataFrame({"scenario_id": ids, "insertion_percent": rows.iloc[test].insertion_percent.to_numpy(float),
                             "k_openmc": k[test], "k_mc_standard_error": targets.iloc[test].k_mc_standard_error.to_numpy(float),
                             "k_initial_256_same_env": models["initial_256"]["k_pred"],
                             "k_adaptive01_288": models["adaptive01_288"]["k_pred"],
                             "k_archived_256": old_saved_k.loc[ids].k_predicted.to_numpy(float),
                             "field_archived_256_relative_l2": old_saved_field.loc[ids].ml_relative_l2_fuel.to_numpy(float)})
    for label, bundle in results.items():
        for prefix in ("field_raw", "field_post", "pca"):
            for metric in bundle[prefix]:
                per_case[f"{label}_{prefix}_{metric}"] = bundle[prefix][metric].to_numpy()
    for label in ("initial_256", "adaptive01_288"):
        per_case[f"k_abs_error_{label}"] = np.abs(per_case[f"k_{label}_same_env" if label == "initial_256" else f"k_{label}" ] - per_case.k_openmc)
    per_case["insertion_band"] = pd.cut(per_case.insertion_percent,
                                         [-1,100/3,200/3,101], labels=["low","middle","high"])
    old_k = results["initial_256"]["k"]
    new_k = results["adaptive01_288"]["k"]
    old_field = results["initial_256"]["field_raw"]
    new_field = results["adaptive01_288"]["field_raw"]
    metric_comparison = {}
    for name, a, b in (("k_mae", old_k["mae"], new_k["mae"]),
                       ("k_rmse", old_k["rmse"], new_k["rmse"]),
                       ("field_relative_l2", float(old_field.relative_l2_fuel.mean()),
                        float(new_field.relative_l2_fuel.mean()))):
        metric_comparison[name] = {"initial_256_same_env": a, "adaptive01_288": b,
                                   "absolute_new_minus_old": b-a,
                                   "percent_change": 100*(b/a-1)}
    raw_new = results["adaptive01_288"]["field_raw"]
    post_new = results["adaptive01_288"]["field_post"]
    physical_comparison = {}
    for label in ("initial_256", "adaptive01_288"):
        raw_metrics = results[label]["field_raw"]
        post_metrics = results[label]["field_post"]
        pca_metrics = results[label]["pca"]
        physical_comparison[label] = {
            "pca_reconstruction_relative_l2_mean": float(pca_metrics.relative_l2_fuel.mean()),
            "raw_half_l1_share_error_mean": float(raw_metrics.half_l1_share_error_raw.mean()),
            "raw_axial_half_l1_share_error_mean": float(raw_metrics.axial_half_l1_share_error_raw.mean()),
            "raw_upper4_low_signal_absolute_share_error_mean": float(raw_metrics.upper4_low_signal_absolute_share_error.mean()),
            "raw_negative_fuel_voxels_total": int(raw_metrics.negative_fuel_voxels.sum()),
            "raw_negative_fuel_voxel_fraction": float(raw_metrics.negative_fuel_voxels.sum()/fuel[test].sum()),
            "raw_negative_fuel_share_magnitude_total": float(raw_metrics.negative_fuel_share_magnitude.sum()),
            "raw_fuel_sum_min": float(raw_metrics.raw_predicted_fuel_sum.min()),
            "raw_fuel_sum_max": float(raw_metrics.raw_predicted_fuel_sum.max()),
            "post_relative_l2_mean": float(post_metrics.relative_l2_fuel.mean()),
            "post_half_l1_share_error_mean": float(post_metrics.half_l1_share_error_raw.mean()),
        }
    report = {"schema": "adaptive01_vs_256_exploratory_v1",
              "scientific_status": "PROVISIONAL_EXPLORATORY; neither source dataset is physically/statistically accepted",
              "data": {"old_dataset_manifest_sha256": sha(OLD/"dataset_manifest.json"),
                       "new_dataset_manifest_sha256": sha(DATA/"dataset_manifest.json"),
                       "old_train": 208, "adaptive_additions": 32, "new_train": 240,
                       "calibration_unchanged_excluded": 25, "test_unchanged": 23,
                       "test_policy": "No test sample in fit/CV/PCA/scaling/hyperparameter choice; test evaluated only after fixed training"},
              "models": {"keff": {"algorithm": "XGBoost", "params": K_PARAMS},
                         "field": {"algorithm": "PCA(12) + XGBoost", "rank": RANK,
                                   "params": FIELD_PARAMS, "axis_order": ["sample","z","y","x"]},
                         "hyperparameter_policy": "Frozen from previous successful 256/384 research models; no new search",
                         "scaling_policy": "No learned feature scaling for tree models; PCA centered and fit only within training folds"},
              "cv": {"seed": SEED, "folds": 5,
                     "mean_k_mae": float(np.mean([x["k_mae"] for x in cv_rows])),
                     "mean_k_rmse": float(np.mean([x["k_rmse"] for x in cv_rows])),
                     "mean_field_relative_l2": float(np.mean([x["field_relative_l2"] for x in cv_rows])),
                     "mean_pca_reconstruction_relative_l2": float(np.mean([x["pca_reconstruction_relative_l2"] for x in cv_rows]))},
              "same_23_test": {"initial_256_same_env": {
                         "k": old_k, "field_raw_relative_l2_mean": float(old_field.relative_l2_fuel.mean())},
                     "adaptive01_288": {"k": new_k,
                         "field_raw_relative_l2_mean": float(new_field.relative_l2_fuel.mean()),
                         "field_pca_reconstruction_relative_l2_mean": float(results["adaptive01_288"]["pca"].relative_l2_fuel.mean()),
                         "field_half_l1_share_error_mean": float(raw_new.half_l1_share_error_raw.mean()),
                         "field_axial_half_l1_share_error_mean": float(raw_new.axial_half_l1_share_error_raw.mean()),
                         "field_negative_fuel_voxels_total": int(raw_new.negative_fuel_voxels.sum()),
                         "field_negative_fuel_voxel_fraction": float(raw_new.negative_fuel_voxels.sum()/fuel[test].sum()),
                         "field_raw_sum_min": float(raw_new.raw_predicted_fuel_sum.min()),
                         "field_raw_sum_max": float(raw_new.raw_predicted_fuel_sum.max()),
                         "field_post_relative_l2_mean": float(post_new.relative_l2_fuel.mean()),
                         "field_post_half_l1_share_error_mean": float(post_new.half_l1_share_error_raw.mean())},
                     "archived_256": {"k": summary_k(k[test], per_case.k_archived_256.to_numpy(float)),
                         "field_raw_relative_l2_mean": float(per_case.field_archived_256_relative_l2.mean())}},
              "change_same_environment": metric_comparison,
              "physical_consistency_same_test": physical_comparison,
              "warnings": ["Source 256 is preview_not_accepted_for_training; Adaptive-01 summary records physical_acceptance=not_assessed and review_required.",
                           "OpenMC completion and MC standard error do not establish physical accuracy or source convergence.",
                           "11 original 256 cases use an alternate nuclear index; HDF5 byte equivalence remains unassessed.",
                           "Zero/low signal fuel voxels are measurements with sampling limits, not proven zero physics.",
                           "XY coordinates change with pitch even though [z,y,x] mesh index shape is fixed.",
                           "These same 23 test cases were examined in earlier work, so they are not a fully untouched external test set.",
                           "Training set is not formally accepted; these surrogate models are research prototypes only."],
              "software": {"python": platform.python_version(), "numpy": np.__version__,
                           "scipy": scipy.__version__, "sklearn": sklearn.__version__,
                           "xgboost": xgboost.__version__}}
    OUT.mkdir(parents=True)
    for label, bundle in models.items():
        joblib.dump(bundle["keff_model"], OUT / f"{label}_keff.joblib")
        joblib.dump(bundle["field_model"], OUT / f"{label}_field_coefficients.joblib")
        np.savez_compressed(OUT / f"{label}_pca.npz", mean=bundle["pca_mean"], basis=bundle["pca_basis"],
                            singular_values=bundle["pca_singular"], train_scenario_ids=np.asarray(bundle["train_ids"],dtype="U64"),
                            rank=RANK, feature_names=np.asarray(FEATURES,dtype="U48"))
    per_case.to_csv(OUT / "test_per_scenario.csv", index=False)
    pd.DataFrame([{ "metric": key, **values } for key, values in metric_comparison.items()]).to_csv(OUT / "metric_comparison.csv", index=False)
    pd.DataFrame([{ "model": label, **values } for label, values in physical_comparison.items()]).to_csv(OUT / "physical_consistency_comparison.csv", index=False)
    pd.DataFrame([{k:v for k,v in row.items() if k not in ("fit_scenario_ids","validation_scenario_ids")}
                  for row in cv_rows]).to_csv(OUT / "cv_folds.csv", index=False)
    (OUT / "cv_memberships.json").write_text(json.dumps(cv_rows, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(OUT / "test_fields.npz", scenario_id=np.asarray(ids,dtype="U64"),
                        actual=field[test], old_raw=models["initial_256"]["field_pred"],
                        new_raw=models["adaptive01_288"]["field_pred"],
                        new_post=results["adaptive01_288"]["post_field"],
                        fuel_mask=fuel[test], low_signal_mask=low, z_edges_cm=z_edges[test],
                        axis_order=np.asarray(["sample","z","y","x"]))
    (OUT / "training_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    axes[0].scatter(k[test],per_case.k_initial_256_same_env,alpha=.8,label="256")
    axes[0].scatter(k[test],per_case.k_adaptive01_288,alpha=.8,label="256 + adaptive 32")
    lo=min(k[test].min(),per_case.k_initial_256_same_env.min(),per_case.k_adaptive01_288.min())
    hi=max(k[test].max(),per_case.k_initial_256_same_env.max(),per_case.k_adaptive01_288.max())
    axes[0].plot([lo,hi],[lo,hi],"k--");axes[0].set(xlabel="OpenMC k",ylabel="Predicted k")
    axes[0].legend()
    axes[1].scatter(old_field.relative_l2_fuel,new_field.relative_l2_fuel)
    hi=max(float(old_field.relative_l2_fuel.max()),float(new_field.relative_l2_fuel.max()))
    axes[1].plot([0,hi],[0,hi],"k--")
    axes[1].set(xlabel="256 field relative L2",ylabel="288 field relative L2")
    fig.tight_layout();fig.savefig(OUT/"same_test_comparison.png",dpi=150);plt.close(fig)
    band = per_case.groupby("insertion_band",observed=False).agg(
        count=("scenario_id","size"),old_k_mae=("k_abs_error_initial_256","mean"),
        new_k_mae=("k_abs_error_adaptive01_288","mean"),
        old_field_l2=("initial_256_field_raw_relative_l2_fuel","mean"),
        new_field_l2=("adaptive01_288_field_raw_relative_l2_fuel","mean")).reset_index()
    band.to_csv(OUT/"insertion_bands.csv",index=False)
    fig,ax=plt.subplots(figsize=(9,4))
    choices=[]
    for position in (0,50,100):
        choices.append(min((i for i in range(len(test)) if i not in choices),
                           key=lambda i:abs(per_case.insertion_percent.iloc[i]-position)))
    for index in choices:
        zc=(z_edges[test][index,1:]+z_edges[test][index,:-1])/2
        ax.plot(zc,field[test][index].sum(axis=(1,2)),label=f"OpenMC {index}")
        ax.plot(zc,models["adaptive01_288"]["field_pred"][index].sum(axis=(1,2)),"--",label=f"adaptive ML {index}")
    ax.set(xlabel="z (cm)",ylabel="Normalized energy-generation share per slice")
    ax.legend(fontsize=7);fig.tight_layout();fig.savefig(OUT/"test_axial_profiles.png",dpi=150);plt.close(fig)
    markdown = f"""# ADAPTIVE-01 sonrası ilk vekil model karşılaştırması\n\n**PROVISIONAL / EXPLORATORY.** Fiziksel, kaynak yakınsaması ve eğitim veri kabulü tamamlanmadı.\n\n- İlk 256 kayıt aynen korundu; eğitim 208 → 240, kalibrasyon 25, test 23.\n- Sabit hiperparametreler; 5-fold yalnız eğitim içi CV; PCA her fold eğitiminde ayrı fit. Kalibrasyon ve test model seçimi için kullanılmadı.\n- Aynı 23 test daha önceki çalışmalarda incelendi; tamamen yeni bağımsız doğrulama değildir.\n\n| Test metriği | 256 aynı ortam | 256 + Adaptive 01 | Fark | Değişim |\n|---|---:|---:|---:|---:|\n"""
    for label in ("k_mae","k_rmse","field_relative_l2"):
        item=metric_comparison[label]
        markdown += f"| {label} | {item['initial_256_same_env']:.6f} | {item['adaptive01_288']:.6f} | {item['absolute_new_minus_old']:+.6f} | {item['percent_change']:+.1f}% |\n"
    markdown += "\nHam 3B tahminler ayrıca negatif voxel ve toplam normalize pay açısından raporlandı; kırpma/yeniden normalizasyon ayrı gösterilir.\n\nKaynak kütüphane eşdeğerliği, düşük sinyalli voxel'ler ve kaynak yakınsaması inceleme gerektirir.\n"
    markdown += "\n| Aynı testte fiziksel tutarlılık | 256 | 288 |\n|---|---:|---:|\n"
    for metric in ("raw_half_l1_share_error_mean", "raw_axial_half_l1_share_error_mean",
                   "raw_upper4_low_signal_absolute_share_error_mean",
                   "raw_negative_fuel_voxel_fraction", "raw_negative_fuel_share_magnitude_total",
                   "raw_fuel_sum_min", "raw_fuel_sum_max", "post_relative_l2_mean"):
        markdown += (f"| {metric} | {physical_comparison['initial_256'][metric]:.6f} | "
                     f"{physical_comparison['adaptive01_288'][metric]:.6f} |\n")
    markdown += "\nDüşük sinyalli üst bölge hatası ve negatif pay büyüklüğü artmıştır; toplam L2 iyileşmesi tek başına fiziksel kabul değildir.\n"
    (OUT/"README.md").write_text(markdown,encoding="utf-8")
    print(json.dumps({"out":str(OUT),"comparison":metric_comparison,"cv":report["cv"],
                      "physical":report["same_23_test"]["adaptive01_288"]},default=str),flush=True)


if __name__ == "__main__":
    main()






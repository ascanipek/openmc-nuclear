"""Select only ADAPTIVE-01 from the frozen 256 branch; never read Halton outputs.

The old test set is excluded from fitting, calibration, scoring and diversity.
Its IDs are checked only after selection to catch an accidental exact duplicate.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
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
import scipy
import sklearn
from scipy.spatial.distance import cdist
from scipy.stats import norm, rankdata, spearmanr
from scipy.stats import qmc
from sklearn.model_selection import KFold


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, "/tmp/openmc_xgboost_320")
from xgboost import XGBRegressor

import xgboost  # noqa: E402

OLD = ROOT / "datasets/v2_256_preview_v1"
SPACE = ROOT / "configs/v2_parameter_space_pilot_scope_v1.json"
REPORT = ROOT / "reports/adaptive_selection_v1"
SELECTED = ROOT / "scenarios/v2_adaptive128_v1/adaptive_01/selected_32.json"
HALTON_INPUTS = ROOT / "scenarios/v2_halton128_v1/catalogue_new_128.json"
FEATURES = [
    "u235_enrichment_wt_percent", "fuel_temperature_K", "moderator_temperature_K",
    "coolant_pressure_MPa", "elemental_boron_ppm", "pin_pitch_cm",
    "pellet_radius_cm", "insertion_percent",
]
K_PARAMS = {
    "objective": "reg:squarederror", "tree_method": "hist",
    "random_state": 20261025, "n_jobs": min(4, os.cpu_count() or 1),
    "subsample": 1.0, "colsample_bytree": 1.0,
    "n_estimators": 400, "max_depth": 2, "learning_rate": 0.05,
}
FIELD_PARAMS = {
    "objective": "reg:squarederror", "tree_method": "hist",
    "multi_strategy": "one_output_per_tree", "random_state": 20261025,
    "n_jobs": 4, "max_depth": 4, "n_estimators": 120,
    "learning_rate": 0.05, "subsample": 1.0, "colsample_bytree": 1.0,
}
N_MEMBERS = 5
FRACTION = 0.8
MEMBER_SEEDS = [20261110, 20261111, 20261112, 20261113, 20261114]
OOF_SEED = 20261120
SOBOL_SEED = 20261121
SOBOL_POWER = 12  # 4096 candidates
MIN_DISTANCE = 0.35  # L2 in eight-dimensional [0,1] coordinates
MAX_PER_INSERTION_BAND = 12  # forces at least 8 in each band at 32 selections
WEIGHTS = {"k_uncertainty": .35, "field_uncertainty": .35,
           "sparsity": .20, "criticality": .10}
CHUNK = 128


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def percentile(values):
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Invalid candidate scoring vector")
    if np.max(values) == np.min(values):
        return np.full(len(values), .5)
    return (rankdata(values, method="average")-1)/(len(values)-1)


def rel_l2(truth, prediction, mask):
    delta = np.where(mask, prediction-truth, 0)
    baseline = np.where(mask, truth, 0)
    return np.linalg.norm(delta.reshape(len(truth), -1), axis=1) / np.linalg.norm(
        baseline.reshape(len(truth), -1), axis=1)


def fit_ensemble(fit_indices, X, k, field_flat, seed_offset):
    count = max(13, int(round(FRACTION*len(fit_indices))))
    if count <= 12:
        raise ValueError("PCA rank requires more than 12 training examples")
    models = []
    for member, seed in enumerate(MEMBER_SEEDS):
        rng = np.random.default_rng(seed+seed_offset)
        subset = np.sort(rng.choice(fit_indices, size=count, replace=False))
        mean = field_flat[subset].mean(axis=0)
        _, _, basis = np.linalg.svd(field_flat[subset]-mean, full_matrices=False)
        axes = basis[:12].copy()
        coef = (field_flat[subset]-mean) @ axes.T
        km = XGBRegressor(**K_PARAMS)
        km.fit(X[subset], k[subset])
        fm = XGBRegressor(**FIELD_PARAMS)
        fm.fit(X[subset], coef)
        models.append({"member": member, "seed": seed+seed_offset,
                       "training_indices": subset, "k": km, "field": fm,
                       "pca_mean": mean, "pca_basis": axes})
    return models


def predict_models(models, x, fixed_fuel_mask):
    k_pred = np.stack([model["k"].predict(x).astype(float) for model in models])
    field_pred = np.stack([
        (model["pca_mean"] + model["field"].predict(x) @ model["pca_basis"])
        for model in models])
    if field_pred.shape != (len(models), len(x), 5780):
        raise ValueError("Invalid ensemble field shape")
    k_mean = k_pred.mean(axis=0)
    k_std = k_pred.std(axis=0, ddof=1)
    field_mean = field_pred.mean(axis=0)
    centered = field_pred-field_mean[None]
    spread = np.sqrt(np.sum(np.mean(centered**2, axis=0)[:, fixed_fuel_mask], axis=1))
    norm_field = np.linalg.norm(field_mean[:, fixed_fuel_mask], axis=1)
    if np.any(norm_field <= 0):
        raise ValueError("Ensemble mean has zero fuel field")
    field_relative_spread = spread/norm_field
    return k_mean, k_std, field_mean, field_relative_spread


def insertion_band(insertion):
    if insertion < 100/3:
        return "low"
    if insertion < 200/3:
        return "middle"
    return "high"


def validate_inputs():
    if REPORT.exists() or SELECTED.exists():
        raise FileExistsError("Adaptive-01 selection already exists")
    manifest = json.loads((OLD / "dataset_manifest.json").read_text())
    for name, digest in manifest["output_sha256"].items():
        if sha(OLD / name) != digest:
            raise ValueError(f"Frozen 256 changed: {name}")
    split = json.loads((OLD / "splits.json").read_text())
    if {name: len(split[name]) for name in ("train","calibration","test")} != {
        "train": 208, "calibration": 25, "test": 23}:
        raise ValueError("Frozen 256 split differs")
    rows = pd.read_csv(OLD / "scenarios.csv")
    targets = pd.read_csv(OLD / "targets_keff.csv")
    if len(rows) != 256 or rows.scenario_id.nunique() != 256 or not rows.scenario_id.equals(targets.scenario_id):
        raise ValueError("Frozen 256 scenario/target mismatch")
    role = {sid: name for name in ("train","calibration","test") for sid in split[name]}
    if len(role) != 256 or any(role[sid] != name for sid,name in zip(rows.scenario_id,rows.split)):
        raise ValueError("Frozen 256 row/split mismatch")
    train = np.flatnonzero(rows.split.to_numpy() == "train")
    cal = np.flatnonzero(rows.split.to_numpy() == "calibration")
    test = np.flatnonzero(rows.split.to_numpy() == "test")
    with np.load(OLD / "fields.npz", allow_pickle=False) as fields:
        field = fields["target_normalized_kappa"].copy()
        fuel = fields["fuel_volume_fraction"] > 0
        raw_mean = fields["kappa_fission_mean"].copy()
        raw_se = fields["kappa_fission_std_dev"].copy()
    if (field.shape != (256,20,17,17) or not np.allclose(field.sum(axis=(1,2,3)),1,atol=1e-10,rtol=0)
            or np.any(field[~fuel] != 0) or
            not all(np.array_equal(fuel[i],fuel[0]) for i in range(256))):
        raise ValueError("Source field/mask incompatibility")
    space = json.loads(SPACE.read_text())
    if space["status"] != "approved" or space["schema_version"] != 1:
        raise ValueError("Unapproved parameter space")
    return rows, targets, field, fuel, raw_mean, raw_se, train, cal, test, space


def main():
    start = time.monotonic()
    rows, targets, field, fuel, raw_mean, raw_se, train, cal, test, space = validate_inputs()
    X = rows[FEATURES].to_numpy(float)
    k = targets.k_mean.to_numpy(float)
    flat = field.reshape(256,5780,order="C")
    fixed_mask = fuel[0].reshape(5780,order="C")
    lower = np.array([space["ranges"][name]["lower"] for name in FEATURES])
    upper = np.array([space["ranges"][name]["upper"] for name in FEATURES])
    span = upper-lower
    if np.any(span <= 0):
        raise ValueError("Unapproved or degenerate parameter range")
    train_u = (X[train]-lower)/span
    oof_rows = []
    oof_folds = []
    cv = KFold(n_splits=5, shuffle=True, random_state=OOF_SEED)
    for fold_no,(fit_local,val_local) in enumerate(cv.split(train)):
        fit, val = train[fit_local], train[val_local]
        if set(fit)&set(val) or set(fit)&(set(cal)|set(test)) or set(val)&(set(cal)|set(test)):
            raise ValueError("OOF leakage")
        ensemble = fit_ensemble(fit,X,k,flat,1000*(fold_no+1))
        km,ks,fm,fs = predict_models(ensemble,X[val],fixed_mask)
        truth = field[val]
        pred = fm.reshape(-1,20,17,17)
        ferr = rel_l2(truth,pred,fuel[val])
        for position,index in enumerate(val):
            oof_rows.append({"scenario_id":rows.scenario_id.iloc[index],
                             "fold":fold_no,"k_true":float(k[index]),
                             "k_pred":float(km[position]),
                             "k_absolute_error":float(abs(km[position]-k[index])),
                             "k_ensemble_sd":float(ks[position]),
                             "field_relative_l2_error":float(ferr[position]),
                             "field_ensemble_relative_spread":float(fs[position]),
                             "k_mc_standard_error":float(targets.k_mc_standard_error.iloc[index])})
        oof_folds.append({"fold":fold_no,"fit_scenario_ids":rows.scenario_id.iloc[fit].tolist(),
                          "validation_scenario_ids":rows.scenario_id.iloc[val].tolist(),
                          "member_seeds":[seed+1000*(fold_no+1) for seed in MEMBER_SEEDS]})
        print("training-only OOF",fold_no,"n",len(val),flush=True)
    oof = pd.DataFrame(oof_rows)
    if len(oof) != 208 or oof.scenario_id.nunique() != 208 or set(oof.scenario_id)&set(rows.scenario_id.iloc[np.r_[cal,test]]):
        raise ValueError("OOF coverage or leakage")
    oof_k_corr = spearmanr(oof.k_ensemble_sd,oof.k_absolute_error)
    oof_f_corr = spearmanr(oof.field_ensemble_relative_spread,oof.field_relative_l2_error)
    final_models = fit_ensemble(train,X,k,flat,50000)
    cal_k,cal_ks,cal_f,cal_fs = predict_models(final_models,X[cal],fixed_mask)
    cal_k_abs = np.abs(cal_k-k[cal])
    cal_field_err = rel_l2(field[cal],cal_f.reshape(-1,20,17,17),fuel[cal])
    k_rms_disagreement = float(np.sqrt(np.mean(cal_ks**2)))
    if k_rms_disagreement <= 0:
        raise ValueError("Zero ensemble k disagreement")
    k_scale = float(np.sqrt(np.mean(cal_k_abs**2))/k_rms_disagreement)
    k_floor = float(np.median(cal_k_abs))
    field_scale = float(np.sqrt(np.mean(cal_field_err**2))/
                        np.sqrt(np.mean(cal_fs**2))) if np.any(cal_fs > 0) else float("inf")
    cal_k_corr = spearmanr(cal_ks,cal_k_abs)
    cal_f_corr = spearmanr(cal_fs,cal_field_err)
    raw_rel = np.divide(raw_se[cal],raw_mean[cal],
                        out=np.full_like(raw_mean[cal],np.nan),
                        where=fuel[cal] & (raw_mean[cal] > 0))
    mc_median = np.array([np.nanmedian(raw_rel[i]) for i in range(len(cal))])
    noise_corr = spearmanr(cal_fs,mc_median)
    if not np.isfinite(k_scale) or k_scale <= 0 or not np.isfinite(k_floor):
        raise ValueError("Invalid calibration of k uncertainty")
    cal_rows = pd.DataFrame({
        "scenario_id":rows.scenario_id.iloc[cal].tolist(),
        "k_true":k[cal],"k_ensemble_mean":cal_k,"k_ensemble_sd":cal_ks,
        "k_absolute_error":cal_k_abs,
        "field_ensemble_relative_spread":cal_fs,
        "field_relative_l2_error":cal_field_err,
        "median_positive_raw_kappa_relative_mc_error":mc_median,
    })
    # Sobol inputs only: no Halton observations or 384-trained model is read.
    unit = qmc.Sobol(d=8, scramble=True, seed=SOBOL_SEED).random_base2(SOBOL_POWER)
    physical = lower+unit*span
    with tempfile.TemporaryDirectory(prefix="adaptive_validator_") as validator_dir:
        source = Path(validator_dir) / "candidates.json"
        result = Path(validator_dir) / "validation.json"
        source.write_text(json.dumps([{name: float(value) for name, value in zip(FEATURES, values)}
                                      for values in physical], allow_nan=False), encoding="utf-8")
        subprocess.run(["/home/ascanipek/miniconda3/bin/conda", "run", "-n", "openmc-proje",
                        "python", str(ROOT / "scripts/v2_adaptive01_validate.py"),
                        str(source), str(result)], check=True, cwd=ROOT)
        checked = json.loads(result.read_text(encoding="utf-8"))
    reference_sha = checked["reference_sha256"]
    rejected = checked["rejected"]
    valid_index = [item["candidate_index"] for item in checked["valid"]]
    valid_ids = [item["scenario_id"] for item in checked["valid"]]
    valid_controls = [{name:float(value) for name,value in zip(FEATURES,physical[index])}
                      for index in valid_index]
    valid_unit = unit[valid_index]
    if len(valid_controls) < 32:
        raise ValueError("Too few physically valid Sobol candidates")
    candidates = np.array([[c[name] for name in FEATURES] for c in valid_controls])
    candidate_u = np.asarray(valid_unit)
    k_mean_parts,k_sd_parts,field_spread_parts = [],[],[]
    for begin in range(0,len(candidates),CHUNK):
        km,ks,_,fs = predict_models(final_models,candidates[begin:begin+CHUNK],fixed_mask)
        k_mean_parts.append(km);k_sd_parts.append(ks);field_spread_parts.append(fs)
    k_mean = np.concatenate(k_mean_parts)
    k_unc = np.concatenate(k_sd_parts)
    f_unc = np.concatenate(field_spread_parts)
    sparse = cdist(candidate_u,train_u).min(axis=1)
    sigma = np.sqrt((k_scale*k_unc)**2+k_floor**2)
    if np.any(sigma <= 0):
        raise ValueError("Zero calibrated criticality uncertainty")
    critical_p = norm.cdf((k_mean-1)/sigma)
    critical_raw = 4*critical_p*(1-critical_p)
    raw_components = {
        "k_uncertainty":k_unc,"field_uncertainty":f_unc,
        "sparsity":sparse,"criticality":critical_raw,
    }
    scores = {name:percentile(values) for name,values in raw_components.items()}
    weighted = sum(WEIGHTS[name]*scores[name] for name in WEIGHTS)
    order = np.lexsort((np.asarray(valid_index),-weighted))
    selected = []
    bands = {"low":0,"middle":0,"high":0}
    selected_u = []
    for local in order:
        band = insertion_band(valid_controls[local]["insertion_percent"])
        if bands[band] >= MAX_PER_INSERTION_BAND:
            continue
        if selected_u and min(np.linalg.norm(candidate_u[local]-u) for u in selected_u) < MIN_DISTANCE:
            continue
        selected.append(int(local))
        selected_u.append(candidate_u[local])
        bands[band] += 1
        if len(selected) == 32:
            break
    if len(selected) != 32 or min(bands.values()) < 8:
        raise ValueError("Diversity constraints could not select 32 candidates")
    selected_ids = [valid_ids[i] for i in selected]
    initial_ids = set(rows.scenario_id)
    if len(set(selected_ids)) != 32 or set(selected_ids)&initial_ids:
        raise ValueError("Selected scenario duplicates an initial 256 or itself")
    # Input-only collision audit, AFTER selection. No Halton outcomes are read.
    halton = json.loads(HALTON_INPUTS.read_text())
    halton_ids = {record["scenario_id"] for record in halton["scenarios"]}
    halton_controls = {json.dumps(record["controls"],sort_keys=True) for record in halton["scenarios"]}
    if set(selected_ids)&halton_ids or any(json.dumps(valid_controls[i],sort_keys=True) in halton_controls for i in selected):
        raise ValueError("Selected scenario duplicates a Halton input")
    selected_distances = cdist(candidate_u[selected],candidate_u[selected])
    np.fill_diagonal(selected_distances,np.inf)
    min_selected_pairwise = float(selected_distances.min())
    selected_records = []
    for rank,i in enumerate(selected,1):
        record = {"selection_rank":rank,"candidate_index":int(valid_index[i]),
                  "scenario_id":selected_ids[rank-1],"controls":valid_controls[i],
                  "insertion_band":insertion_band(valid_controls[i]["insertion_percent"]),
                  "predicted_k_mean":float(k_mean[i]),
                  "raw_k_ensemble_sd":float(k_unc[i]),
                  "raw_field_ensemble_relative_spread":float(f_unc[i]),
                  "nearest_training_distance_normalized_8d":float(sparse[i]),
                  "criticality_probability_above_one_approx":float(critical_p[i]),
                  "component_percentiles":{name:float(scores[name][i]) for name in WEIGHTS},
                  "component_weighted":{name:float(WEIGHTS[name]*scores[name][i]) for name in WEIGHTS},
                  "total_score":float(weighted[i])}
        selected_records.append(record)
    score_rows = []
    for i,controls in enumerate(valid_controls):
        score_rows.append({
            "candidate_index":valid_index[i],
            **controls,
            "scenario_id":valid_ids[i],
            "predicted_k_mean":k_mean[i],
            "raw_k_ensemble_sd":k_unc[i],
            "raw_field_ensemble_relative_spread":f_unc[i],
            "nearest_training_distance_normalized_8d":sparse[i],
            "criticality_probability_above_one_approx":critical_p[i],
            **{f"percentile_{name}":scores[name][i] for name in WEIGHTS},
            "total_score":weighted[i],
            "selected":i in set(selected),
        })
    # Output is staged, then renamed; no existing analysis or source file is edited.
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".adaptive_selection_work_",dir=REPORT.parent) as temp:
        work = Path(temp)
        (work/"ensemble").mkdir()
        for model in final_models:
            member = model["member"]
            joblib.dump(model["k"],work/"ensemble"/f"member_{member}_keff.joblib")
            joblib.dump(model["field"],work/"ensemble"/f"member_{member}_field.joblib")
            np.savez_compressed(work/"ensemble"/f"member_{member}_pca.npz",
                                mean=model["pca_mean"],basis=model["pca_basis"],
                                fit_scenario_ids=np.asarray(rows.scenario_id.iloc[model["training_indices"]].tolist(),dtype="U64"))
        pd.DataFrame(score_rows).to_csv(work/"candidate_scores.csv",index=False)
        pd.DataFrame(selected_records).drop(columns=["controls","component_percentiles","component_weighted"]).to_csv(work/"selected_scores.csv",index=False)
        pd.DataFrame(rejected,columns=["candidate_index","reason"]).to_csv(work/"rejected_candidates.csv",index=False)
        oof.to_csv(work/"training_only_oof_uncertainty.csv",index=False)
        cal_rows.to_csv(work/"calibration_diagnostics.csv",index=False)
        (work/"oof_folds.json").write_text(json.dumps(oof_folds,indent=2)+"\n")
        (work/"selected_32.json").write_text(json.dumps(selected_records,indent=2,ensure_ascii=False)+"\n")
        fig,axes=plt.subplots(2,4,figsize=(13,6))
        for ax,name,j in zip(axes.flat,FEATURES,range(8)):
            ax.hist(X[train,j],bins=12,alpha=.5,label="208 training")
            ax.hist(candidates[selected,j],bins=12,alpha=.6,label="adaptive_01")
            ax.set_title(name,fontsize=8)
        axes.flat[0].legend(fontsize=7)
        fig.tight_layout();fig.savefig(work/"parameter_coverage.png",dpi=150);plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(10,4))
        axes[0].scatter(candidate_u[:,0],candidate_u[:,7],c=weighted,s=4,cmap="viridis")
        axes[0].scatter(candidate_u[selected,0],candidate_u[selected,7],facecolors="none",edgecolors="red",s=48)
        axes[0].set(xlabel=FEATURES[0]+" normalized",ylabel=FEATURES[7]+" normalized",
                    title="Sobol pool and 32 selected")
        axes[1].hist(weighted,bins=25,alpha=.6,label="candidate score")
        axes[1].hist(weighted[selected],bins=12,alpha=.8,label="selected")
        axes[1].legend();axes[1].set(xlabel="weighted percentile score",ylabel="count")
        fig.tight_layout();fig.savefig(work/"candidate_selection.png",dpi=150);plt.close(fig)
        report = {
            "schema":"beavrs_v2_adaptive01_selection_v1",
            "status":"selection_complete_technical_research_only",
            "data_firewall":{
                "fit_scenario_count":208,"calibration_count":25,"excluded_test_count":23,
                "training_source":"datasets/v2_256_preview_v1 only",
                "halton_outcomes_read":False,"halton_models_read":False,"full384_models_read":False,
                "halton_input_ids_read_only_after_selection_for_collision_audit":True,
            },
            "source_sha256":{
                "old_dataset_manifest":sha(OLD/"dataset_manifest.json"),
                "old_splits":sha(OLD/"splits.json"),
                "old_scenarios":sha(OLD/"scenarios.csv"),
                "old_targets":sha(OLD/"targets_keff.csv"),
                "old_fields":sha(OLD/"fields.npz"),
                "space":sha(SPACE),"physics_validator":sha(ROOT/"scripts/v2_adaptive01_validate.py"),"halton_input_catalogue_collision_audit_only":sha(HALTON_INPUTS),
            },
            "candidate_generation":{
                "method":"scrambled Sobol","seed":SOBOL_SEED,"power":SOBOL_POWER,
                "requested":2**SOBOL_POWER,"valid":len(valid_controls),"rejected":len(rejected),
                "parameter_order":FEATURES,
                "bounds":{name:space["ranges"][name] for name in FEATURES},
                "validation":"resolve_proposed controls and IF97 water phase before scoring",
            },
            "ensemble":{
                "members":N_MEMBERS,"member_base_seeds":MEMBER_SEEDS,
                "training_fraction_without_replacement":FRACTION,
                "k_model_parameters":K_PARAMS,"field_model_parameters":FIELD_PARAMS,
                "pca_rank":12,"pca_fit":"each member's own training subset; OOF uses fold training only",
                "field_uncertainty":"sqrt(sum of mean squared member deviations over geometric fuel voxels) / L2 norm of ensemble mean field on fuel",
                "k_uncertainty":"sample standard deviation of member k predictions",
            },
            "calibration":{
                "k_rms_error_over_rms_disagreement":k_scale,
                "k_median_absolute_error_floor":k_floor,
                "field_rms_error_over_rms_disagreement":field_scale,
                "training_only_oof_k_uncertainty_error_spearman":float(oof_k_corr.statistic),
                "training_only_oof_field_uncertainty_error_spearman":float(oof_f_corr.statistic),
                "calibration_k_uncertainty_error_spearman":float(cal_k_corr.statistic),
                "calibration_field_uncertainty_error_spearman":float(cal_f_corr.statistic),
                "calibration_field_disagreement_vs_raw_MC_relative_error_spearman":float(noise_corr.statistic),
                "interpretation":"Disagreement is a heuristic; correlations do not guarantee true error or physical validity",
            },
            "scoring":{
                "weights":WEIGHTS,
                "weight_rationale":"Advisor-prescribed 35/35/20/10 balance; fixed before evaluating candidate outcomes",
                "normalization":"empirical percentile rank within valid Sobol candidate pool, [0,1], per component",
                "sparsity":"minimum Euclidean distance to 208 training inputs in fixed approved [0,1]^8 bounds",
                "criticality":"4p(1-p), p=NormalCDF((mean_k-1)/sqrt((calibration_scale*k_ensemble_sd)^2+median_calibration_abs_error^2)); then percentile rank",
                "total":"0.35*k_percentile + 0.35*field_percentile + 0.20*sparsity_percentile + 0.10*criticality_percentile",
            },
            "diversity":{
                "method":"greedy descending total score with hard normalized 8D minimum distance and insertion-band cap",
                "minimum_pairwise_distance_requirement":MIN_DISTANCE,
                "maximum_per_insertion_band":MAX_PER_INSERTION_BAND,
                "selected_pairwise_minimum":min_selected_pairwise,
                "selected_band_counts":bands,
                "heuristic_notice":"Distance and band cap are precommitted researcher choices; not validated physical thresholds",
            },
            "selected_count":32,
            "collision_audit":{"initial_256":0,"halton_128_input_only":0},
            "selected_scenario_ids":selected_ids,
            "scientific_warnings":[
                "Uncertainty disagreement can be affected by MC tally noise and model bias; it does not bound true error.",
                "The 256 preview has review_required physics/field quality; source convergence and nuclear HDF5 equivalence remain unassessed.",
                "No Halton physical outcome, 384 model or old test outcome was used in fitting or scoring.",
                "Adaptive sampling is not presumed better than Halton; compare at equal transport budget later.",
            ],
            "software":{"python":platform.python_version(),"numpy":np.__version__,
                        "pandas":pd.__version__,"scipy":scipy.__version__,
                        "sklearn":sklearn.__version__,"xgboost":xgboost.__version__},
            "runtime_seconds":time.monotonic()-start,
        }
        report["output_sha256"]={str(p.relative_to(work)):sha(p) for p in work.rglob("*") if p.is_file()}
        (work/"selection_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        (work/"README.md").write_text(
            "# ADAPTIVE-01 seçimi — yalnız ilk 32\n\n"
            "İlk 256'nın 208 eğitim/25 kalibrasyon verisi kullanıldı; 23 test ve Halton fiziksel çıktıları kullanılmadı. "
            "4096 scrambled Sobol adayının fizik/geometri geçerliliği kontrol edildi. "
            "Beşli alt örnek ensemble k ve 3B fiziksel alan anlaşmazlığını üretti. "
            "35/35/20/10 puan bileşenleri aday havuzunda yüzdelik sıraya dönüştürülerek toplandı. "
            "Greedy seçimde 8B minimum uzaklık ve çubuk konumu üst sınırı uygulandı. "
            "Bu sayılar araştırmacı tasarım tercihidir; fiziksel doğruluk ya da belirsizlik garantisi değildir. "
            "İlk 32 tamamlandıktan sonra sonraki grup yalnız yeni adaptif sonuçlar eklenerek yeniden seçilmelidir.\n",
            encoding="utf-8")
        work.rename(REPORT)
    SELECTED.parent.mkdir(parents=True,exist_ok=True)
    SELECTED.write_text(json.dumps({
        "schema":"beavrs_v2_adaptive01_selected_v1",
        "selection_report_sha256":sha(REPORT/"selection_report.json"),
        "source_256_splits_sha256":sha(OLD/"splits.json"),
        "reference_config_sha256":reference_sha,
        "selected_count":32,
        "selected":[{"scenario_id":record["scenario_id"],"controls":record["controls"]}
                    for record in selected_records],
    },indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"report":str(REPORT),"selected":str(SELECTED),
                      "valid_candidates":len(valid_controls),"rejected":len(rejected),
                      "bands":bands,"min_pairwise_distance":min_selected_pairwise,
                      "training_oof_k_spearman":float(oof_k_corr.statistic),
                      "training_oof_field_spearman":float(oof_f_corr.statistic),
                      "seconds":time.monotonic()-start}))


if __name__ == "__main__":
    main()







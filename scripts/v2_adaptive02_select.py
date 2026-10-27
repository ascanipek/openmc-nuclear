"""ADAPTIVE-02: same fixed scoring rule on 240 train rows, no calibration/test targets."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
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
from scipy.stats import norm, spearmanr, qmc
from sklearn.model_selection import KFold

from v2_adaptive01_select import (FEATURES, K_PARAMS, FIELD_PARAMS, MEMBER_SEEDS,
    N_MEMBERS, FRACTION, OOF_SEED, SOBOL_SEED, SOBOL_POWER, MIN_DISTANCE,
    MAX_PER_INSERTION_BAND, WEIGHTS, CHUNK, fit_ensemble, predict_models,
    insertion_band, percentile, rel_l2, sha)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_288_adaptive01_exploratory_v1"
OLD = ROOT / "datasets/v2_256_preview_v1"
SPACE = ROOT / "configs/v2_parameter_space_pilot_scope_v1.json"
A1_SELECTED = ROOT / "scenarios/v2_adaptive128_v1/adaptive_01/selected_32.json"
UPDATED_MODELS = ROOT / "reports/adaptive01_vs_256_v1"
HALTON_INPUTS = ROOT / "scenarios/v2_halton128_v1/catalogue_new_128.json"
REPORT = ROOT / "reports/adaptive_selection_02_v1"
SELECTED = ROOT / "scenarios/v2_adaptive128_v1/adaptive_02/selected_32.json"


def main():
    start = time.monotonic()
    if REPORT.exists() or SELECTED.exists():
        raise FileExistsError("ADAPTIVE-02 selection exists")
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    if manifest["branch"] != "adaptive_01" or manifest["scenario_count"] != 288:
        raise ValueError("Wrong input branch")
    for name, expected in manifest["output_sha256"].items():
        if sha(DATA / name) != expected:
            raise ValueError(f"Input changed: {name}")
    split = json.loads((DATA / "splits.json").read_text())
    old_split = json.loads((OLD / "splits.json").read_text())
    rows = pd.read_csv(DATA / "scenarios.csv")
    targets = pd.read_csv(DATA / "targets_keff.csv")
    if (len(rows) != 288 or rows.scenario_id.nunique() != 288 or
        not rows.scenario_id.equals(targets.scenario_id) or
        split["train"] != [*old_split["train"], *rows.scenario_id.iloc[256:].tolist()] or
        split["calibration"] != old_split["calibration"] or
        split["test"] != old_split["test"]):
        raise ValueError("Fixed input split changed")
    role = {sid: part for part in ("train","calibration","test") for sid in split[part]}
    if len(role) != 288 or any(role[sid] != part for sid,part in zip(rows.scenario_id,rows.split)):
        raise ValueError("Split membership changed")
    train = np.flatnonzero(rows.split.to_numpy() == "train")
    cal = np.flatnonzero(rows.split.to_numpy() == "calibration")
    test = np.flatnonzero(rows.split.to_numpy() == "test")
    if (len(train),len(cal),len(test)) != (240,25,23):
        raise ValueError("Wrong train/cal/test counts")
    X = rows[FEATURES].to_numpy(float)
    k = targets.k_mean.to_numpy(float)
    with np.load(DATA / "fields.npz",allow_pickle=False) as fields:
        field = fields["target_normalized_kappa"].copy()
        fuel = fields["fuel_volume_fraction"] > 0
        raw = fields["kappa_fission_mean"].copy()
        raw_se = fields["kappa_fission_std_dev"].copy()
    if field.shape != (288,20,17,17) or not np.allclose(field.sum(axis=(1,2,3)),1,atol=1e-10,rtol=0):
        raise ValueError("Invalid training field")
    if not all(np.array_equal(fuel[i],fuel[0]) for i in train):
        raise ValueError("Fuel mask changes across training rows")
    flat = field.reshape(288,5780,order="C")
    fixed_mask = fuel[train[0]].reshape(5780,order="C")
    space = json.loads(SPACE.read_text())
    if space["status"] != "approved":
        raise ValueError("Unapproved parameter space")
    lower = np.array([space["ranges"][name]["lower"] for name in FEATURES])
    upper = np.array([space["ranges"][name]["upper"] for name in FEATURES])
    span = upper-lower
    train_u = (X[train]-lower)/span
    if np.any(span <= 0) or np.any(train_u < -1e-10) or np.any(train_u > 1+1e-10):
        raise ValueError("Training inputs outside approved ranges")
    oof_rows,folds = [],[]
    for fold_no,(fit_local,val_local) in enumerate(KFold(5,shuffle=True,random_state=OOF_SEED).split(train)):
        fit,val = train[fit_local],train[val_local]
        if set(fit)&set(val) or (set(fit)|set(val))&(set(cal)|set(test)):
            raise ValueError("OOF leakage")
        ensemble = fit_ensemble(fit,X,k,flat,1000*(fold_no+1))
        km,ks,fm,fs = predict_models(ensemble,X[val],fixed_mask)
        error = rel_l2(field[val],fm.reshape(-1,20,17,17),fuel[val])
        for j,index in enumerate(val):
            valid = fuel[index] & (raw[index] > 0)
            mc_rel = raw_se[index][valid]/raw[index][valid]
            oof_rows.append({"scenario_id":rows.scenario_id.iloc[index],"fold":fold_no,
                             "k_absolute_error":float(abs(km[j]-k[index])),
                             "k_ensemble_sd":float(ks[j]),
                             "field_relative_l2_error":float(error[j]),
                             "field_ensemble_relative_spread":float(fs[j]),
                             "raw_kappa_mc_relative_error_median_positive":float(np.median(mc_rel)) if mc_rel.size else None})
        folds.append({"fold":fold_no,"fit_scenario_ids":rows.scenario_id.iloc[fit].tolist(),
                      "validation_scenario_ids":rows.scenario_id.iloc[val].tolist()})
        print("train-only OOF",fold_no,flush=True)
    oof=pd.DataFrame(oof_rows)
    if len(oof)!=240 or set(oof.scenario_id)!=set(split["train"]):
        raise ValueError("OOF coverage differs")
    k_rms_disagreement=float(np.sqrt(np.mean(oof.k_ensemble_sd**2)))
    k_scale=float(np.sqrt(np.mean(oof.k_absolute_error**2))/k_rms_disagreement)
    k_floor=float(np.median(oof.k_absolute_error))
    if not np.isfinite(k_scale) or k_scale<=0 or not np.isfinite(k_floor):
        raise ValueError("Invalid train-only criticality calibration")
    final=fit_ensemble(train,X,k,flat,50000)
    saved_k=joblib.load(UPDATED_MODELS/"adaptive01_288_keff.joblib")
    saved_field=joblib.load(UPDATED_MODELS/"adaptive01_288_field_coefficients.joblib")
    with np.load(UPDATED_MODELS/"adaptive01_288_pca.npz",allow_pickle=False) as pca:
        if set(pca["train_scenario_ids"].tolist()) != set(split["train"]):
            raise ValueError("Updated source model trained on wrong rows")
        saved_mean,saved_basis=pca["mean"].copy(),pca["basis"].copy()
    unit=qmc.Sobol(d=8,scramble=True,seed=SOBOL_SEED).random_base2(SOBOL_POWER)
    physical=lower+unit*span
    with tempfile.TemporaryDirectory(prefix="adaptive02_validator_") as temp:
        source=Path(temp)/"candidates.json"; result=Path(temp)/"validated.json"
        source.write_text(json.dumps([{name:float(v) for name,v in zip(FEATURES,point)} for point in physical],allow_nan=False))
        subprocess.run(["/home/ascanipek/miniconda3/bin/conda","run","-n","openmc-proje","python",
                        str(ROOT/"scripts/v2_adaptive01_validate.py"),str(source),str(result)],check=True,cwd=ROOT)
        checked=json.loads(result.read_text())
    indices=[item["candidate_index"] for item in checked["valid"]]
    ids=[item["scenario_id"] for item in checked["valid"]]
    controls=[{name:float(v) for name,v in zip(FEATURES,physical[index])} for index in indices]
    U=unit[indices]
    if len(ids)<32 or len(set(ids))!=len(ids):
        raise ValueError("Candidate identities not unique")
    candidates=np.array([[c[name] for name in FEATURES] for c in controls])
    km_all=[];ks_all=[];fs_all=[];source_k_all=[]
    for begin in range(0,len(candidates),CHUNK):
        chunk=candidates[begin:begin+CHUNK]
        km,ks,_,fs=predict_models(final,chunk,fixed_mask)
        km_all.append(km);ks_all.append(ks);fs_all.append(fs)
        source_k_all.append(saved_k.predict(chunk).astype(float))
        # The saved field model/PCA is used for model-version consistency, never for a new scoring formula.
        source_field=saved_mean+saved_field.predict(chunk)@saved_basis
        if source_field.shape!=(len(chunk),5780) or not np.isfinite(source_field).all():
            raise ValueError("Updated field model cannot predict candidate fields")
    k_mean=np.concatenate(km_all); k_unc=np.concatenate(ks_all)
    f_unc=np.concatenate(fs_all); source_k=np.concatenate(source_k_all)
    sparse=cdist(U,train_u).min(axis=1)
    sigma=np.sqrt((k_scale*k_unc)**2+k_floor**2)
    if np.any(sigma<=0):
        raise ValueError("Invalid criticality scale")
    p=norm.cdf((k_mean-1)/sigma)
    critical=4*p*(1-p)
    raw_components={"k_uncertainty":k_unc,"field_uncertainty":f_unc,
                    "sparsity":sparse,"criticality":critical}
    percentiles={name:percentile(values) for name,values in raw_components.items()}
    score=sum(WEIGHTS[name]*percentiles[name] for name in WEIGHTS)
    existing=set(rows.scenario_id)
    halton=json.loads(HALTON_INPUTS.read_text())
    halton_ids={item["scenario_id"] for item in halton["scenarios"]}
    forbidden=existing|halton_ids
    order=np.lexsort((np.asarray(indices),-score))
    selected=[];selected_u=[];bands={"low":0,"middle":0,"high":0}
    for loc in order:
        if ids[loc] in forbidden:
            continue
        band=insertion_band(controls[loc]["insertion_percent"])
        if bands[band]>=MAX_PER_INSERTION_BAND:
            continue
        if selected_u and min(np.linalg.norm(U[loc]-point) for point in selected_u)<MIN_DISTANCE:
            continue
        selected.append(int(loc));selected_u.append(U[loc]);bands[band]+=1
        if len(selected)==32:
            break
    if len(selected)!=32 or min(bands.values())<8 or len({ids[i] for i in selected})!=32:
        raise ValueError("Could not select diverse 32 new scenarios")
    distance=cdist(U[selected],U[selected]);np.fill_diagonal(distance,np.inf)
    chosen=[]
    for rank,loc in enumerate(selected,1):
        chosen.append({"selection_rank":rank,"candidate_index":indices[loc],
                       "scenario_id":ids[loc],"controls":controls[loc],
                       "insertion_band":insertion_band(controls[loc]["insertion_percent"]),
                       "source_model_version":"adaptive01_vs_256_v1: 240 train",
                       "predicted_k_saved_model":float(source_k[loc]),
                       "predicted_k_ensemble_mean":float(k_mean[loc]),
                       "raw_k_ensemble_sd":float(k_unc[loc]),
                       "raw_field_ensemble_relative_spread":float(f_unc[loc]),
                       "nearest_training_distance_normalized_8d":float(sparse[loc]),
                       "criticality_probability_above_one_approx":float(p[loc]),
                       "component_percentiles":{name:float(percentiles[name][loc]) for name in WEIGHTS},
                       "component_weighted":{name:float(WEIGHTS[name]*percentiles[name][loc]) for name in WEIGHTS},
                       "total_score":float(score[loc])})
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".adaptive02_selection_",dir=REPORT.parent) as temporary:
        work=Path(temporary);(work/"ensemble").mkdir()
        for model in final:
            member=model["member"]
            joblib.dump(model["k"],work/"ensemble"/f"member_{member}_keff.joblib")
            joblib.dump(model["field"],work/"ensemble"/f"member_{member}_field.joblib")
            np.savez_compressed(work/"ensemble"/f"member_{member}_pca.npz",
                                mean=model["pca_mean"],basis=model["pca_basis"],
                                fit_scenario_ids=np.asarray(rows.scenario_id.iloc[model["training_indices"]].tolist(),dtype="U64"))
        oof.to_csv(work/"training_only_oof_uncertainty.csv",index=False)
        (work/"oof_folds.json").write_text(json.dumps(folds,indent=2)+"\n")
        pd.DataFrame(chosen).drop(columns=["controls","component_percentiles","component_weighted"]).to_csv(work/"selected_scores.csv",index=False)
        (work/"selected_32.json").write_text(json.dumps(chosen,indent=2,ensure_ascii=False)+"\n")
        pd.DataFrame([{"candidate_index":indices[i],"scenario_id":ids[i],"selected":i in set(selected),
                       "excluded_previous":ids[i] in forbidden,"total_score":score[i],
                       **{f"raw_{name}":raw_components[name][i] for name in WEIGHTS},
                       **{f"percentile_{name}":percentiles[name][i] for name in WEIGHTS}}
                      for i in range(len(indices))]).to_csv(work/"candidate_scores.csv",index=False)
        pd.DataFrame(checked["rejected"],columns=["candidate_index","reason"]).to_csv(work/"rejected_candidates.csv",index=False)
        fig,axes=plt.subplots(2,4,figsize=(13,6))
        for j,name in enumerate(FEATURES):
            ax=axes.flat[j];ax.hist(X[train,j],bins=12,alpha=.5,label="240 train")
            ax.hist(candidates[selected,j],bins=12,alpha=.6,label="Adaptive 02")
            ax.set_title(name,fontsize=8)
        axes.flat[0].legend(fontsize=7);fig.tight_layout();fig.savefig(work/"parameter_coverage.png",dpi=150);plt.close(fig)
        report={"schema":"beavrs_v2_adaptive02_selection_v1","status":"selection_complete_technical_research_only",
                "data_firewall":{"train_count":240,"calibration_excluded":25,"test_excluded":23,
                    "training_source":"datasets/v2_288_adaptive01_exploratory_v1 only",
                    "halton_outcomes_read":False,"calibration_targets_used":False,"test_targets_used":False,
                    "halton_input_ids_collision_only":True},
                "source_sha256":{"dataset_manifest":sha(DATA/"dataset_manifest.json"),
                    "scenarios":sha(DATA/"scenarios.csv"),"targets":sha(DATA/"targets_keff.csv"),
                    "fields":sha(DATA/"fields.npz"),"splits":sha(DATA/"splits.json"),
                    "adaptive01_selected":sha(A1_SELECTED),"parameter_space":sha(SPACE),
                    "saved_keff_model":sha(UPDATED_MODELS/"adaptive01_288_keff.joblib"),
                    "saved_field_model":sha(UPDATED_MODELS/"adaptive01_288_field_coefficients.joblib"),
                    "saved_field_pca":sha(UPDATED_MODELS/"adaptive01_288_pca.npz"),
                    "halton_input_catalogue_collision_only":sha(HALTON_INPUTS)},
                "algorithm":{"version":"adaptive01_fixed_35_35_20_10_v1_retrained_on_240",
                    "candidate_generation":"same scrambled Sobol 4096-point pool as Adaptive 01",
                    "candidate_seed":SOBOL_SEED,"candidate_power":SOBOL_POWER,
                    "ensemble_member_base_seeds":MEMBER_SEEDS,"member_seed_offset":50000,
                    "oof_seed":OOF_SEED,"ensemble_members":N_MEMBERS,"training_fraction":FRACTION,
                    "k_parameters":K_PARAMS,"field_parameters":FIELD_PARAMS,"pca_rank":12,
                    "weights":WEIGHTS,"score_normalization":"empirical percentile among valid Sobol candidates",
                    "sparsity":"minimum normalized [0,1]^8 Euclidean distance to 240 training inputs",
                    "criticality":"4p(1-p), p=NormalCDF((ensemble mean k prediction -1)/sqrt((OOF_scale*k_ensemble_sd)^2+OOF_median_abs_error^2))",
                    "criticality_scale_change":"Same formula as Adaptive 01, but OOF training-only errors replace 25 calibration errors to satisfy explicit calibration firewall",
                    "diversity_min_distance":MIN_DISTANCE,"maximum_per_insertion_band":MAX_PER_INSERTION_BAND},
                "training_only_oof":{"k_rms_error_over_rms_disagreement":k_scale,
                    "k_median_absolute_error_floor":k_floor,
                    "k_uncertainty_error_spearman":float(spearmanr(oof.k_ensemble_sd,oof.k_absolute_error).statistic),
                    "field_uncertainty_error_spearman":float(spearmanr(oof.field_ensemble_relative_spread,oof.field_relative_l2_error).statistic),
                    "field_disagreement_vs_raw_MC_relative_error_spearman":float(spearmanr(oof.field_ensemble_relative_spread,oof.raw_kappa_mc_relative_error_median_positive).statistic)},
                "candidate_counts":{"requested":2**SOBOL_POWER,"valid":len(indices),
                    "rejected":len(checked["rejected"]),"excluded_existing_or_halton":int(sum(sid in forbidden for sid in ids))},
                "selection":{"count":32,"bands":bands,"min_pairwise_distance_normalized_8d":float(distance.min()),
                    "duplicate_initial_256":0,"duplicate_adaptive01":0,"duplicate_halton_input":0,
                    "selected_scenario_ids":[ids[i] for i in selected]},
                "warnings":["Ensemble disagreement does not guarantee actual prediction error.",
                    "Training data have review_required quality; selected scenarios are research candidates only.",
                    "The 25 calibration and 23 test targets were not used for selection.",
                    "The same 23 test cases were examined in prior model reports, not a fresh independent test.",
                    "No new weighting or sampling method was introduced."],
                "software":{"python":platform.python_version(),"numpy":np.__version__,
                    "scipy":scipy.__version__,"sklearn":sklearn.__version__}}
        report["output_sha256"]={str(path.relative_to(work)):sha(path) for path in work.rglob("*") if path.is_file()}
        (work/"selection_report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        (work/"README.md").write_text("# Adaptive 02 seçim raporu\n\nYalnız 240 eğitim senaryosu; kalibrasyon/test hedefleri seçim dışında. Adaptive 01 sabit ağırlıkları ve aynı Sobol havuzu kullanıldı. Üretim başlatılmadı.\n",encoding="utf-8")
        work.rename(REPORT)
    SELECTED.parent.mkdir(parents=True,exist_ok=True)
    SELECTED.write_text(json.dumps({"schema":"beavrs_v2_adaptive02_selected_v1",
        "selection_report_sha256":sha(REPORT/"selection_report.json"),
        "source_dataset_manifest_sha256":sha(DATA/"dataset_manifest.json"),
        "selected_count":32,
        "selected":[{"scenario_id":item["scenario_id"],"controls":item["controls"]} for item in chosen]},
        indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"report":str(REPORT),"selected":str(SELECTED),"bands":bands,
                      "min_distance":float(distance.min()),"valid_candidates":len(indices),
                      "seconds":time.monotonic()-start}))


if __name__=="__main__":
    main()


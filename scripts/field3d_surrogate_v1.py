"""Exploratory 3D surrogate training from frozen OpenMC fields. No transport."""
import csv
import hashlib
import json
import os
import platform
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
import xgboost
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, RBF, WhiteKernel
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_256_preview_v1"
PCA_REPORT = ROOT / "reports/field3d_pca_v1/pca_summary.json"
OUT = ROOT / "reports/field3d_surrogate_v1"
FEATURES = ["u235_enrichment_wt_percent", "fuel_temperature_K",
            "moderator_temperature_K", "coolant_pressure_MPa",
            "elemental_boron_ppm", "pin_pitch_cm", "pellet_radius_cm",
            "insertion_percent"]
RANKS = (8, 12, 16, 24)
SEED = 20261025
CV = KFold(n_splits=5, shuffle=True, random_state=SEED)
SPECS = [
    ("Ridge", {"alpha": alpha}) for alpha in (0.1, 1.0, 10.0)
] + [
    ("GPR", {"kernel": kernel}) for kernel in ("RBF", "Matern32")
] + [
    ("XGBoost", {"max_depth": depth, "n_estimators": 120, "learning_rate": 0.05})
    for depth in (2, 4)
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_model(name, params):
    if name == "Ridge":
        return Pipeline([("scale", StandardScaler()),
                         ("model", Ridge(alpha=params["alpha"]))])
    if name == "GPR":
        core = RBF(1.0) if params["kernel"] == "RBF" else Matern(1.0, nu=1.5)
        kernel = ConstantKernel(1.0) * core + WhiteKernel(1e-4)
        return Pipeline([("scale", StandardScaler()),
                         ("model", GaussianProcessRegressor(
                             kernel=kernel, alpha=1e-8, optimizer=None,
                             normalize_y=True, random_state=SEED))])
    if name == "XGBoost":
        return XGBRegressor(
            objective="reg:squarederror", tree_method="hist",
            multi_strategy="one_output_per_tree", random_state=SEED,
            n_jobs=4, max_depth=params["max_depth"],
            n_estimators=params["n_estimators"],
            learning_rate=params["learning_rate"], subsample=1.0,
            colsample_bytree=1.0)
    raise ValueError(name)


def rel_l2(truth, pred, mask):
    delta = np.where(mask, pred - truth, 0.0)
    reference = np.where(mask, truth, 0.0)
    return np.linalg.norm(delta.reshape(len(truth), -1), axis=1) / np.linalg.norm(
        reference.reshape(len(truth), -1), axis=1)


def field_metrics(truth, pred, mask, low, raw_se):
    n = len(truth)
    rel = rel_l2(truth, pred, mask)
    half_l1 = 0.5 * np.abs(np.where(mask, pred-truth, 0)).sum(axis=(1,2,3))
    axial_true = np.where(mask, truth, 0).sum(axis=(2,3))
    axial_pred = np.where(mask, pred, 0).sum(axis=(2,3))
    axial_half_l1 = 0.5 * np.abs(axial_pred-axial_true).sum(axis=1)
    upper_low = low.copy()
    upper_low[:,:-4] = False
    upper_abs = np.abs(np.where(upper_low, pred-truth, 0)).sum(axis=(1,2,3))
    upper_true = np.where(upper_low,truth,0).sum(axis=(1,2,3))
    negative = (pred < 0) & mask
    return pd.DataFrame({
        "relative_l2_fuel":rel,
        "half_l1_share_error_raw":half_l1,
        "axial_half_l1_share_error_raw":axial_half_l1,
        "upper4_low_signal_absolute_share_error":upper_abs,
        "upper4_low_signal_true_share":upper_true,
        "negative_fuel_voxels":negative.sum(axis=(1,2,3)),
        "negative_fuel_share_magnitude":(-np.where(negative,pred,0)).sum(axis=(1,2,3)),
        "raw_predicted_fuel_sum":np.where(mask,pred,0).sum(axis=(1,2,3)),
        "raw_kappa_se_median_fuel":np.array([
            np.median(raw_se[i][mask[i]]) for i in range(n)]),
    })


def draw_examples(rows, truth, pca, pred, mask, x_edges, y_edges, z_edges):
    insertion = np.array([float(r["insertion_percent"]) for r in rows])
    selected = []
    for target in (0.,50.,100.):
        selected.append(min((i for i in range(len(rows)) if i not in selected),
                            key=lambda i:abs(insertion[i]-target)))
    fig, ax = plt.subplots(figsize=(8,5))
    for i in selected:
        centers=(z_edges[i,1:]+z_edges[i,:-1])/2
        for label,field,style in (("OpenMC",truth,"-"),("PCA",pca,"--"),("ML",pred,":")):
            ax.plot(centers,field[i].sum(axis=(1,2)),style,
                    label=f"giriş %{insertion[i]:.1f} {label}")
    ax.set(xlabel="z (cm)",ylabel="Normalize kappa-fission payı / dilim",
           title="Bağımsız test: gerçek OpenMC, PCA ve ML eksenel profilleri")
    ax.legend(fontsize=7,ncol=2);ax.grid(True);fig.tight_layout()
    fig.savefig(OUT/"test_axial_profiles.png",dpi=160);plt.close(fig)
    for i in selected:
        fig,axs=plt.subplots(2,3,figsize=(14,8),constrained_layout=True)
        for axis,selector,edge_y,title in (
                (0,lambda field:field[10],y_edges[i],"XY z=10"),
                (1,lambda field:field[:,8,:],z_edges[i],"XZ y=8")):
            section_mask=selector(mask[i])
            sections=[np.ma.masked_where(~section_mask,selector(f[i])) for f in (truth,pca,pred)]
            lo=min(float(s.min()) for s in sections)
            hi=max(float(s.max()) for s in sections)
            for col,(section,label) in enumerate(zip(sections,("Gerçek OpenMC","PCA yeniden oluşturma","ML tahmini"))):
                im=axs[axis,col].pcolormesh(x_edges[i],edge_y,section,
                    shading="flat",cmap="viridis",vmin=lo,vmax=hi)
                fig.colorbar(im,ax=axs[axis,col],label="Normalize pay / voxel")
                axs[axis,col].set(title=f"{title}: {label}",xlabel="x (cm)",
                                   ylabel="y (cm)" if axis==0 else "z (cm)")
        fig.suptitle(f"Bağımsız test row {rows[i]['row']}; çubuk giriş %{insertion[i]:.1f}")
        fig.savefig(OUT/f"test_compare_row_{int(rows[i]['row']):03d}.png",dpi=145)
        plt.close(fig)
    return [int(rows[i]["row"]) for i in selected]


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pca_review=json.loads(PCA_REPORT.read_text())
    assert pca_review["source_fields_sha256"]==sha(DATA/"fields.npz")
    assert pca_review["source_splits_sha256"]==sha(DATA/"splits.json")
    assert pca_review["source_manifest_sha256"]==sha(DATA/"dataset_manifest.json")
    manifest=json.loads((DATA/"dataset_manifest.json").read_text())
    splits=json.loads((DATA/"splits.json").read_text())
    assert manifest["training_eligible_count"]==0
    assert manifest["array_order"]==["sample","z","y","x"]
    assert {k:len(splits[k]) for k in ("train","calibration","test")}=={"train":208,"calibration":25,"test":23}
    with (DATA/"scenarios.csv").open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==256 and len({r["scenario_id"] for r in rows})==256
    role={sid:k for k in ("train","calibration","test") for sid in splits[k]}
    assert all(int(r["row"])==i and r["split"]==role[r["scenario_id"]] for i,r in enumerate(rows))
    X=np.array([[float(row[c]) for c in FEATURES] for row in rows])
    assert np.isfinite(X).all()
    with np.load(DATA/"fields.npz") as fields:
        target=fields["target_normalized_kappa"]
        fuel=fields["fuel_volume_fraction"]>0
        fission=fields["fission_mean"]
        fission_se=fields["fission_std_dev"]
        raw_se=fields["kappa_fission_std_dev"]
        x_edges=fields["x_edges_cm"]
        y_edges=fields["y_edges_cm"]
        z_edges=fields["z_edges_cm"]
    assert target.shape==(256,20,17,17) and np.allclose(target.sum(axis=(1,2,3)),1)
    assert (target>=0).all() and not np.count_nonzero(target[~fuel])
    assert (fuel.sum(axis=(1,2,3))==5280).all()
    low=fuel & ((fission==0)|(fission<5*fission_se)|
                (fission<1e-6*fission.max(axis=(1,2,3))[:,None,None,None]))
    y=target.reshape(256,5780,order="C")
    train=np.array([i for i,r in enumerate(rows) if r["split"]=="train"])
    test=np.array([i for i,r in enumerate(rows) if r["split"]=="test"])
    assert len(train)==208 and len(test)==23
    cv_err={(rank,name,json.dumps(params,sort_keys=True)):[] for rank in RANKS for name,params in SPECS}
    pca_err={rank:[] for rank in RANKS}
    start=time.monotonic()
    for fold_no,(fit_local,val_local) in enumerate(CV.split(train),1):
        fit=train[fit_local];val=train[val_local]
        mean=y[fit].mean(axis=0)
        _,_,basis=np.linalg.svd(y[fit]-mean,full_matrices=False)
        mask=fuel[val]
        for rank in RANKS:
            axes=basis[:rank]
            coef_train=(y[fit]-mean)@axes.T
            pca_val=mean+(y[val]-mean)@axes.T@axes
            pca_err[rank].extend(rel_l2(target[val],pca_val.reshape(-1,20,17,17),mask))
            for name,params in SPECS:
                model=make_model(name,params)
                model.fit(X[fit],coef_train)
                coef_pred=model.predict(X[val])
                pred=(mean+coef_pred@axes).reshape(-1,20,17,17)
                cv_err[(rank,name,json.dumps(params,sort_keys=True))].extend(
                    rel_l2(target[val],pred,mask))
                print("CV",fold_no,rank,name,params,
                      "mean",float(np.mean(cv_err[(rank,name,json.dumps(params,sort_keys=True))])),flush=True)
    records=[]
    for (rank,name,param_json),errors in cv_err.items():
        assert len(errors)==208
        records.append({"rank":rank,"model":name,"parameters":param_json,
            "cv_total_relative_l2_mean":float(np.mean(errors)),
            "cv_total_relative_l2_p95":float(np.percentile(errors,95)),
            "cv_pca_only_relative_l2_mean":float(np.mean(pca_err[rank])),
            "cv_pca_only_relative_l2_p95":float(np.percentile(pca_err[rank],95))})
    comparison=pd.DataFrame(records).sort_values("cv_total_relative_l2_mean")
    comparison.to_csv(OUT/"cv_model_comparison.csv",index=False)
    best_error=float(comparison.iloc[0]["cv_total_relative_l2_mean"])
    near=comparison[np.isclose(comparison.cv_total_relative_l2_mean,best_error,rtol=1e-9,atol=1e-12)]
    winner=near.sort_values(["rank","cv_total_relative_l2_mean"]).iloc[0]
    rank=int(winner["rank"]); name=str(winner["model"]); params=json.loads(winner["parameters"])
    print("WINNER",rank,name,params,"CV",winner["cv_total_relative_l2_mean"],flush=True)
    mean=y[train].mean(axis=0)
    _,singular,basis=np.linalg.svd(y[train]-mean,full_matrices=False)
    axes=basis[:rank]
    coefficient_train=(y[train]-mean)@axes.T
    final=make_model(name,params)
    final.fit(X[train],coefficient_train)
    pca_test=(mean+(y[test]-mean)@axes.T@axes).reshape(-1,20,17,17)
    prediction=(mean+final.predict(X[test])@axes).reshape(-1,20,17,17)
    # Fixed physical postprocessing comparison. Raw prediction remains the selection target.
    postprocessed=np.where(fuel[test],np.maximum(prediction,0.0),0.0)
    postprocessed/=postprocessed.sum(axis=(1,2,3))[:,None,None,None]
    test_rows=[rows[i] for i in test]
    pca_metrics=field_metrics(target[test],pca_test,fuel[test],low[test],raw_se[test])
    total_metrics=field_metrics(target[test],prediction,fuel[test],low[test],raw_se[test])
    post_metrics=field_metrics(target[test],postprocessed,fuel[test],low[test],raw_se[test])
    result=pd.DataFrame({"row":test,"scenario_id":[r["scenario_id"] for r in test_rows],
        "insertion_percent":[float(r["insertion_percent"]) for r in test_rows]})
    for col in pca_metrics:
        result["pca_"+col]=pca_metrics[col].to_numpy()
        result["ml_"+col]=total_metrics[col].to_numpy()
        result["post_"+col]=post_metrics[col].to_numpy()
    result["insertion_band"]=pd.cut(result.insertion_percent,
        bins=[-1,100/3,200/3,101],labels=["low","middle","high"])
    result.to_csv(OUT/"test_case_metrics.csv",index=False)
    joblib.dump(final,OUT/"selected_model.joblib")
    np.savez_compressed(OUT/"selected_pca.npz",mean=mean,basis=axes,
        singular_values=singular,rank=rank,feature_names=np.array(FEATURES),
        train_scenario_ids=np.array([rows[i]["scenario_id"] for i in train]))
    np.savez_compressed(OUT/"test_fields.npz",row=test,
        scenario_id=np.array([r["scenario_id"] for r in test_rows]),
        actual=target[test],pca_reconstructed=pca_test,ml_predicted_raw=prediction,
        ml_predicted_postprocessed=postprocessed,
        fuel_mask=fuel[test],low_signal_mask=low[test],
        raw_kappa_standard_error=raw_se[test],
        x_edges_cm=x_edges[test],y_edges_cm=y_edges[test],z_edges_cm=z_edges[test],
        axis_order=np.array(["sample","z","y","x"]))
    example_rows=draw_examples(test_rows,target[test],pca_test,prediction,
                               fuel[test],x_edges[test],y_edges[test],z_edges[test])
    fig,ax=plt.subplots(figsize=(8,4.5))
    for model in ("Ridge","GPR","XGBoost"):
        subset=comparison[comparison.model==model]
        best=subset.groupby("rank").cv_total_relative_l2_mean.min()
        ax.plot(best.index,best.values,marker="o",label=model)
    ax.plot(RANKS,[np.mean(pca_err[k]) for k in RANKS],marker="s",linestyle="--",label="PCA tek başına")
    ax.set(xlabel="PCA bileşen sayısı",ylabel="Eğitim içi ortalama göreli L2",
           title="3B alan: PCA alt sınırı ve toplam ML hatası")
    ax.legend();ax.grid(True);fig.tight_layout()
    fig.savefig(OUT/"cv_model_comparison.png",dpi=160);plt.close(fig)
    band=result.groupby("insertion_band",observed=False).agg(
        count=("row","size"),mean_total_relative_l2=("ml_relative_l2_fuel","mean"),
        mean_pca_relative_l2=("pca_relative_l2_fuel","mean")).reset_index()
    report={
        "schema":"field3d_pca_surrogate_exploratory_v1",
        "status":"PROVISIONAL_EXPLORATORY; field3d REVIEW_REQUIRED; no physical/statistical acceptance",
        "warning":"PCA is on common [z,y,x] mesh indices; x/y coordinates vary with pitch. Normalized uncertainty covariance unavailable. Predictions are raw, without clipping or renormalization.",
        "source_fields_sha256":sha(DATA/"fields.npz"),
        "source_scenarios_sha256":sha(DATA/"scenarios.csv"),
        "source_splits_sha256":sha(DATA/"splits.json"),
        "source_manifest_sha256":sha(DATA/"dataset_manifest.json"),
        "source_pca_summary_sha256":sha(PCA_REPORT),
        "source_dataset_state":manifest["state"],
        "nuclear_index_hash_counts":manifest["nuclear_index_hash_counts"],
        "nuclear_hdf5_byte_equivalence":manifest["nuclear_hdf5_byte_equivalence"],
        "split_counts":{"train":208,"calibration_untouched":25,"test":23},
        "feature_names":FEATURES,"target":"target_normalized_kappa",
        "axis_order":["sample","z","y","x"],"mesh_shape":[20,17,17],
        "cv":{"folds":5,"seed":SEED,"selection_metric":"mean total relative L2 on geometric fuel voxels",
              "pca_fit":"each fold training subset only",
              "scaling_fit":"each fold training subset only",
              "gpr":"optimizer=None; RBF/Matern kernel chosen by CV",
              "near_tie_policy":"np.isclose(rtol=1e-9, atol=1e-12), then smallest rank"},
        "selected":{"rank":rank,"model":name,"parameters":params,
                    "cv_total_relative_l2_mean":float(winner["cv_total_relative_l2_mean"]),
                    "cv_pca_only_relative_l2_mean":float(winner["cv_pca_only_relative_l2_mean"])},
        "test":{"pca_relative_l2_mean":float(pca_metrics.relative_l2_fuel.mean()),
                "pca_relative_l2_p95":float(pca_metrics.relative_l2_fuel.quantile(.95)),
                "ml_relative_l2_mean":float(total_metrics.relative_l2_fuel.mean()),
                "ml_relative_l2_p95":float(total_metrics.relative_l2_fuel.quantile(.95)),
                "ml_half_l1_share_error_mean":float(total_metrics.half_l1_share_error_raw.mean()),
                "ml_axial_half_l1_share_error_mean":float(total_metrics.axial_half_l1_share_error_raw.mean()),
                "ml_upper4_low_signal_absolute_share_error_mean":float(total_metrics.upper4_low_signal_absolute_share_error.mean()),
                "ml_upper4_low_signal_true_share_mean":float(total_metrics.upper4_low_signal_true_share.mean()),
                "ml_negative_fuel_voxels_total":int(total_metrics.negative_fuel_voxels.sum()),
                "ml_negative_fuel_share_magnitude_total":float(total_metrics.negative_fuel_share_magnitude.sum()),
                "ml_raw_predicted_fuel_sum_min":float(total_metrics.raw_predicted_fuel_sum.min()),
                "ml_raw_predicted_fuel_sum_max":float(total_metrics.raw_predicted_fuel_sum.max()),
                "post_relative_l2_mean":float(post_metrics.relative_l2_fuel.mean()),
                "post_relative_l2_p95":float(post_metrics.relative_l2_fuel.quantile(.95)),
                "post_half_l1_share_error_mean":float(post_metrics.half_l1_share_error_raw.mean()),
                "post_axial_half_l1_share_error_mean":float(post_metrics.axial_half_l1_share_error_raw.mean()),
                "post_upper4_low_signal_absolute_share_error_mean":float(post_metrics.upper4_low_signal_absolute_share_error.mean()),
                "post_negative_fuel_voxels_total":int(post_metrics.negative_fuel_voxels.sum()),
                "post_predicted_fuel_sum_min":float(post_metrics.raw_predicted_fuel_sum.min()),
                "post_predicted_fuel_sum_max":float(post_metrics.raw_predicted_fuel_sum.max())},
        "postprocessing":"Separate comparison only: max(raw_prediction,0) on geometric fuel, then divide by positive fuel sum; no tuning, raw CV model selection unchanged",
        "test_by_insertion_band":band.to_dict(orient="records"),
        "test_example_rows":example_rows,
        "runtime_seconds":time.monotonic()-start,
        "software":{"python":platform.python_version(),"numpy":np.__version__,
                    "scipy":scipy.__version__,"sklearn":sklearn.__version__,
                    "xgboost":xgboost.__version__,"joblib":joblib.__version__},
        "xgboost_install":"temporary /tmp target; Conda environments unchanged",
    }
    (OUT/"training_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("DONE",OUT,"seconds",round(report["runtime_seconds"],1),flush=True)


if __name__=="__main__":
    main()

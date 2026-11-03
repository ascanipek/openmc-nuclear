"""Frozen-model OOF physical diagnostics; no transport or source mutation."""
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib;matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from sklearn.model_selection import KFold
from xgboost import XGBRegressor
from v2_288_adaptive01_train import FEATURES,K_PARAMS,FIELD_PARAMS,SEED,fit_field,predict_field,rel_l2
R=Path(__file__).resolve().parents[2]
O=R/"reports/physical_error_analysis_v1"
D={"initial":(R/"datasets/v2_512_combined_v1",208),"halton":(R/"datasets/v2_384_halton_v1",336),"adaptive":(R/"datasets/v2_384_adaptive04_exploratory_v1",336),"combined":(R/"datasets/v2_512_combined_v1",464)}
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def band(x):return "low" if x<=100/3 else ("middle" if x<=200/3 else "high")
def main():
    if O.exists():raise FileExistsError(O)
    O.mkdir(parents=True)
    cases=[];regional=[];negatives=[];maps={};example=None
    for branch,(folder,ntrain) in D.items():
        manifest=json.loads((folder/"dataset_manifest.json").read_text())
        for name,digest in manifest["output_sha256"].items():
            if sha(folder/name)!=digest:raise ValueError("Source hash mismatch: "+str(folder/name))
        rows=pd.read_csv(folder/"scenarios.csv");targets=pd.read_csv(folder/"targets_keff.csv")
        split=json.loads((folder/"splits.json").read_text())
        ids=pd.Index(rows.scenario_id)
        train=ids.get_indexer(split["train"][:ntrain]);cal=ids.get_indexer(split["calibration"]);test=ids.get_indexer(split["test"])
        if len(train)!=ntrain or min(np.r_[train,cal,test])<0 or (set(train)&(set(cal)|set(test))):raise ValueError("Split leakage")
        with np.load(folder/"fields.npz",allow_pickle=False) as f:
            truth=f["target_normalized_kappa"].copy();fuel=f["fuel_volume_fraction"]>0
            kappa=f["kappa_fission_mean"].copy();se=f["kappa_fission_std_dev"].copy()
            expected=f["kappa_fission_expected_zero"].copy()
            edges=f["z_edges_cm"].copy()
        if truth.shape[1:]!=(20,17,17) or np.any(truth[~fuel]!=0):raise ValueError("Field geometry mismatch")
        X=rows[FEATURES].to_numpy(float);k=targets.k_mean.to_numpy(float);flat=truth.reshape(len(rows),-1)
        abs_map=np.zeros((20,17,17));negative_map=np.zeros((20,17,17),dtype=int);count_map=np.zeros((20,17,17),dtype=int)
        print("OOF",branch,ntrain,flush=True)
        for fold,(fi,vi) in enumerate(KFold(5,shuffle=True,random_state=SEED).split(train),1):
            fit,val=train[fi],train[vi]
            if set(fit)&set(val) or (set(fit)|set(val))&(set(cal)|set(test)):raise ValueError("CV leakage")
            km=XGBRegressor(**K_PARAMS);km.fit(X[fit],k[fit])
            fm,mean,basis,_=fit_field(X,flat,fit)
            kp=km.predict(X[val]);pred=predict_field(fm,mean,basis,X[val])
            pca=(mean+(flat[val]-mean)@basis.T@basis).reshape(-1,20,17,17)
            for j,row in enumerate(val):
                mask=fuel[row];actual=truth[row];estimate=pred[j];pc=pca[j]
                denom=np.square(actual[mask]).sum()
                err=np.abs(estimate-actual);pcaerr=np.abs(pc-actual)
                model_l2=float(np.sqrt(np.square(err[mask]).sum()/denom))
                pca_l2=float(np.sqrt(np.square(pcaerr[mask]).sum()/denom))
                rawsum=float(kappa[row][mask].sum())
                if rawsum<=0:raise ValueError("Nonpositive kappa sum")
                zero=mask&(kappa[row]==0)
                weak=mask&(kappa[row]>0)&((kappa[row]<5*se[row])|(actual<1e-6*actual[mask].max()))
                strong=mask&~zero&~weak
                abs_map+=err*mask;negative_map+=(estimate<0)&mask;count_map+=mask
                rec={"branch":branch,"fold":fold,"scenario_id":ids[row],"insertion_percent":float(rows.insertion_percent.iloc[row]),"boron_ppm":float(rows.elemental_boron_ppm.iloc[row]),"fuel_temperature_K":float(rows.fuel_temperature_K.iloc[row]),"moderator_temperature_K":float(rows.moderator_temperature_K.iloc[row]),"insertion_band":band(float(rows.insertion_percent.iloc[row])),"k_actual":float(k[row]),"k_predicted":float(kp[j]),"k_abs_error":float(abs(kp[j]-k[row])),"k_mc_se":float(targets.k_mc_standard_error.iloc[row]),"field_l2":model_l2,"pca_l2":pca_l2,"coefficient_prediction_excess_l2":model_l2-pca_l2,"zero_fuel_voxels":int(zero.sum()),"low_signal_positive_voxels":int(weak.sum()),"strong_voxels":int(strong.sum()),"fuel_voxels":int(mask.sum()),"upper4_true_share":float(actual[16:].sum()),"upper4_predicted_share":float((estimate*mask)[16:].sum()),"negative_voxels":int(((estimate<0)&mask).sum()),"negative_share":float(-np.minimum(estimate[mask],0).sum())}
                for label,m in (("zero",zero),("low",weak),("strong",strong)):
                    rec[label+"_mean_abs_share_error"]=float(err[m].mean()) if m.any() else None
                    rec[label+"_total_abs_share_error"]=float(err[m].sum())
                    rec[label+"_median_raw_mc_se_over_raw_sum"]=float(np.median(se[row][m]/rawsum)) if m.any() else None
                cases.append(rec)
                if branch=="combined" and (example is None or rec["insertion_percent"]>example["insertion_percent"]):
                    example={"insertion_percent":rec["insertion_percent"],"scenario_id":ids[row],"actual":actual.copy(),"estimate":estimate.copy(),"fuel":mask.copy(),"weak":weak.copy(),"zero":zero.copy(),"z_edges":edges[row].copy()}
                ring=np.maximum(np.abs(np.arange(17)[:,None]-8),np.abs(np.arange(17)[None,:]-8))
                for axial,zsel in (("bottom",np.arange(20)<5),("middle",(np.arange(20)>=5)&(np.arange(20)<15)),("top",np.arange(20)>=15)):
                    for radial,rsel in (("central",ring<=3),("middle",(ring>3)&(ring<=6)),("outer",ring>6)):
                        m=mask&zsel[:,None,None]&rsel[None,:,:]
                        if not m.any():continue
                        regional.append({"branch":branch,"scenario_id":ids[row],"insertion_band":rec["insertion_band"],"axial":axial,"radial":radial,"fuel_voxels":int(m.sum()),"true_share":float(actual[m].sum()),"abs_share_error":float(err[m].sum()),"mean_abs_voxel_error":float(err[m].mean()),"negative_voxels":int(((estimate<0)&m).sum()),"zero_measured_voxels":int((zero&m).sum()),"low_positive_voxels":int((weak&m).sum()),"raw_mc_se_scaled_median_positive":float(np.median(se[row][m&(kappa[row]>0)]/rawsum)) if (m&(kappa[row]>0)).any() else None})
        maps[branch]={"abs_error_sum":abs_map,"negative_count":negative_map,"fuel_count":count_map}
    case=pd.DataFrame(cases);region=pd.DataFrame(regional)
    case.to_csv(O/"oof_case_metrics.csv",index=False);region.to_csv(O/"regional_oof_errors.csv",index=False)
    np.savez_compressed(O/"oof_voxel_maps.npz",**{branch+"_"+key:value for branch,items in maps.items() for key,value in items.items()})
    group=case.groupby(["branch","insertion_band"],observed=False).agg(count=("scenario_id","count"),k_mae=("k_abs_error","mean"),field_l2=("field_l2","mean"),pca_l2=("pca_l2","mean"),low_fraction=("low_signal_positive_voxels",lambda v:float(v.sum()/case.loc[v.index,"fuel_voxels"].sum())),zero_fraction=("zero_fuel_voxels",lambda v:float(v.sum()/case.loc[v.index,"fuel_voxels"].sum())),negative_fraction=("negative_voxels",lambda v:float(v.sum()/case.loc[v.index,"fuel_voxels"].sum()))).reset_index()
    group.to_csv(O/"insertion_band_oof.csv",index=False)
    association=[]
    for branch,part in case.groupby("branch"):
        for x in ("insertion_percent","boron_ppm","fuel_temperature_K","moderator_temperature_K"):
            for y in ("k_actual","k_abs_error","field_l2","pca_l2","low_signal_positive_voxels"):
                rho,p=spearmanr(part[x],part[y])
                association.append({"branch":branch,"input":x,"outcome":y,"spearman_rho":float(rho),"p_descriptive":float(p),"n":len(part)})
    pd.DataFrame(association).to_csv(O/"parameter_associations.csv",index=False)
    summary={"scientific_status":"PROVISIONAL_EXPLORATORY","method":"Frozen 5-fold OOF; PCA and XGBoost fitted inside training fold","scenario_counts":{k:int(v) for k,v in case.branch.value_counts().items()}}
    summary["signal_definition"]="zero: fuel and raw kappa=0; low: positive raw kappa<5 raw MC SE or normalized share<1e-6 max; strong: other fuel"
    summary["mc_uncertainty_note"]="Raw kappa SE/raw fuel total is a descriptive scale proxy; normalized covariance unavailable"
    summary["band_metrics"]=group.to_dict(orient="records")
    summary["source_manifest_sha256"]={k:sha(folder/"dataset_manifest.json") for k,(folder,_) in D.items()}
    summary["test_policy"]="23 previously examined test cases used only for explanation, not selection or tuning"
    (O/"summary.json").write_text(json.dumps(summary,indent=2))
    fig,ax=plt.subplots(1,2,figsize=(11,4))
    for branch,g in group.groupby("branch"):
        ax[0].plot(g.insertion_band,g.field_l2,marker="o",label=branch)
        ax[1].plot(g.insertion_band,g.pca_l2,marker="o",label=branch)
    ax[0].set(ylabel="OOF 3D relative L2",title="Full surrogate error")
    ax[1].set(ylabel="OOF 3D relative L2",title="PCA reconstruction floor")
    ax[0].legend();fig.tight_layout();fig.savefig(O/"oof_insertion_errors.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(2,2,figsize=(9,8))
    for axis,name in zip(ax.flat,("initial","halton","adaptive","combined")):
        v=maps[name];data=np.divide(v["negative_count"].sum(axis=0),v["fuel_count"].sum(axis=0),out=np.zeros((17,17)),where=v["fuel_count"].sum(axis=0)>0)
        im=axis.imshow(data,origin="lower",vmin=0,vmax=.5,cmap="magma");axis.set_title(name)
    fig.colorbar(im,ax=ax.ravel().tolist(),shrink=.7,label="OOF negative prediction fraction")
    fig.savefig(O/"negative_xy_maps.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(2,3,figsize=(12,8))
    z=10;v=example;truth2=np.where(v["fuel"],v["actual"],np.nan);pred2=np.where(v["fuel"],v["estimate"],np.nan)
    vmax=float(np.nanpercentile(truth2,99))
    for axis,data,title in ((ax[0,0],truth2[z],"OpenMC XY z=10"),(ax[0,1],pred2[z],"OOF predicted XY z=10"),(ax[0,2],np.abs(pred2[z]-truth2[z]),"Absolute share error XY")):
        axis.imshow(data,origin="lower",vmin=0,vmax=vmax if title!="Absolute share error XY" else None);axis.set_title(title)
    for axis,data,title in ((ax[1,0],truth2[:,:,8],"OpenMC XZ y=8"),(ax[1,1],pred2[:,:,8],"OOF predicted XZ y=8"),(ax[1,2],v["weak"][:,:,8]|v["zero"][:,:,8],"Low/zero signal XZ")):
        axis.imshow(data,origin="lower",aspect="auto");axis.set_title(title)
    fig.suptitle("Highest insertion OOF training case: "+v["scenario_id"][:12]+"...; "+str(round(v["insertion_percent"],2))+"%")
    fig.tight_layout();fig.savefig(O/"high_insertion_xy_xz.png",dpi=170);plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(10,4))
    part=case[case.branch=="combined"]
    ax[0].scatter(part.insertion_percent,part.field_l2,c=part.low_signal_positive_voxels/part.fuel_voxels,cmap="viridis")
    ax[0].set(xlabel="Rod insertion (%)",ylabel="OOF field L2")
    ax[1].scatter(part.pca_l2,part.field_l2,c=part.insertion_percent,cmap="viridis")
    ax[1].plot([0,.2],[0,.2],"k--");ax[1].set(xlabel="PCA reconstruction L2",ylabel="Total OOF L2")
    fig.tight_layout();fig.savefig(O/"combined_oof_diagnostics.png",dpi=160);plt.close(fig)
    print(group.to_string(index=False))
if __name__=="__main__":main()

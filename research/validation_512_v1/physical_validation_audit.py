import matplotlib;matplotlib.use("Agg")
import matplotlib.pyplot as plt
"""Read-only validation evidence audit; no HDF5 payload reads or transport."""
import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
import xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[2]
D=R/"datasets/v2_512_combined_v1"
O=R/"reports/physical_validation_audit_v1"
LOCAL=R/"data/endfb-viii.0/endfb-viii.0-hdf5/cross_sections.xml"
KAGGLE=R/"runs/beavrs_3d/kaggle/v2_stage_128_all_results/cross_sections_kaggle.xml"
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def libraries(path):
    items=[]
    for e in ET.parse(path).getroot().findall("library"):
        p=e.attrib["path"];suffix=p.split("endfb-viii.0-hdf5/")[-1]
        items.append((e.attrib.get("materials"),e.attrib.get("type"),suffix))
    return items
def main():
    O.mkdir(parents=True,exist_ok=True)
    m=json.loads((D/"dataset_manifest.json").read_text())
    for name,expected in m["output_sha256"].items():
        if sha(D/name)!=expected:raise ValueError("Dataset source hash mismatch: "+name)
    rows=pd.read_csv(D/"scenarios.csv");targets=pd.read_csv(D/"targets_keff.csv");quality=pd.read_csv(D/"quality_report.csv")
    if len(rows)!=512 or rows.scenario_id.nunique()!=512 or not rows.scenario_id.equals(targets.scenario_id):raise ValueError("Identity mismatch")
    O.mkdir(parents=True,exist_ok=True)
    with np.load(D/"fields.npz",allow_pickle=False) as f:
        kh=f["k_generation"].copy();entropy=f["shannon_entropy"].copy()
        fuel=f["fuel_volume_fraction"]>0;kappa=f["kappa_fission_mean"].copy();se=f["kappa_fission_std_dev"].copy()
    if kh.shape!=(512,600) or entropy.shape!=(512,600) or not np.isfinite(kh).all() or not np.isfinite(entropy).all():raise ValueError("History missing/nonfinite")
    early_k=kh[:,300:400].mean(axis=1);late_k=kh[:,500:600].mean(axis=1)
    early_h=entropy[:,300:400].mean(axis=1);late_h=entropy[:,500:600].mean(axis=1)
    x=np.arange(100,dtype=float);center=x-x.mean()
    ent_slope=((entropy[:,500:600]-late_h[:,None])*center).sum(axis=1)/np.square(center).sum()
    hist=pd.DataFrame({"scenario_id":rows.scenario_id,"experiment_id":rows.experiment_id,"stage":rows.stage,"insertion_percent":rows.insertion_percent,"k_mc_standard_error":targets.k_mc_standard_error,"k_active_early100_mean":early_k,"k_active_late100_mean":late_k,"k_late_minus_early":late_k-early_k,"entropy_active_early100_mean":early_h,"entropy_active_late100_mean":late_h,"entropy_late_minus_early":late_h-early_h,"entropy_last100_slope_per_generation":ent_slope})
    hist.to_csv(O/"history_descriptors.csv",index=False)
    checks=quality.groupby(["check","status"]).size().rename("count").reset_index()
    checks.to_csv(O/"quality_check_counts.csv",index=False)
    one=quality.drop_duplicates("scenario_id").set_index("scenario_id").loc[rows.scenario_id]
    one[["zero_fuel_kappa_voxels","low_signal_fuel_voxels","fuel_voxels","kappa_relative_mc_error_median_positive_signal","kappa_relative_mc_error_p95_positive_signal"]].describe().to_csv(O/"voxel_quality_descriptives.csv")
    files=list(R.rglob("statepoint.600.h5"))
    by_exp={}
    for path in files:by_exp.setdefault(path.parent.parent.name,[]).append(path)
    sp=[]
    for row in rows.itertuples():
        direct=R/row.source_attempt/"statepoint.600.h5"
        matches=by_exp.get(row.experiment_id,[])
        sp.append({"scenario_id":row.scenario_id,"experiment_id":row.experiment_id,"stage":row.stage,"direct_source_attempt_statepoint":direct.is_file(),"any_same_experiment_statepoint":bool(matches),"matching_file_count":len(matches),"example_path":str(matches[0].relative_to(R)) if matches else ""})
    sp=pd.DataFrame(sp);sp.to_csv(O/"statepoint_availability.csv",index=False)
    original=libraries(LOCAL);alternate=libraries(KAGGLE)
    if len(original)!=690 or len(alternate)!=690:raise ValueError("Unexpected library count")
    alt_paths=[e.attrib["path"] for e in ET.parse(KAGGLE).getroot().findall("library")]
    index={"local_xml_sha256":sha(LOCAL),"alternate_xml_sha256":sha(KAGGLE),"index_entry_count":len(original),"logical_material_type_suffix_entries_equal":original==alternate,"alternate_hdf5_paths_existing_here":sum(Path(p).is_file() for p in alt_paths),"hdf5_byte_equivalence":"NOT_ASSESSED; source Kaggle HDF5 payloads unavailable locally"}
    (O/"nuclear_index_comparison.json").write_text(json.dumps(index,indent=2))
    print("statepoint",sp.direct_source_attempt_statepoint.sum(),sp.any_same_experiment_statepoint.sum(),"nuclear_mapping",index["logical_material_type_suffix_entries_equal"])
    report={"scientific_status":"PROVISIONAL_EXPLORATORY","dataset_manifest_sha256":sha(D/"dataset_manifest.json"),"scenarios":512,"k_mc_se_median":float(targets.k_mc_standard_error.median()),"k_mc_se_p95":float(targets.k_mc_standard_error.quantile(.95)),"k_mc_se_max":float(targets.k_mc_standard_error.max()),"k_late_minus_early_median":float(np.median(late_k-early_k)),"k_late_minus_early_p95_abs":float(np.percentile(np.abs(late_k-early_k),95)),"entropy_last100_slope_median":float(np.median(ent_slope)),"statepoint_direct_source_attempt_count":int(sp.direct_source_attempt_statepoint.sum()),"statepoint_same_experiment_name_count":int(sp.any_same_experiment_statepoint.sum()),"statepoint_total_files_locally":len(files),"quality_status_counts":{k:int(v) for k,v in quality.status.value_counts().items()},"nuclear_index_hash_counts":{k:int(v) for k,v in rows.cross_sections_xml_sha256.value_counts().items()},"nuclear_index_comparison":index,"warnings":["Histories permit descriptive source diagnostics, not convergence acceptance without predeclared criterion","Same experiment-name statepoint may come from a different attempt; metadata/tally identity unverified","Zero tally SE=0 does not prove zero uncertainty","Alternate index HDF5 byte equivalence not established"]}
    (O/"audit_summary.json").write_text(json.dumps(report,indent=2))
    fig,ax=plt.subplots(1,2,figsize=(12,4))
    for axis,data,title in ((ax[0],kh,"Generation k"),(ax[1],entropy,"Shannon entropy")):
        axis.plot(np.arange(600),np.median(data,axis=0),label="median")
        lo,hi=np.percentile(data,[25,75],axis=0);axis.fill_between(np.arange(600),lo,hi,alpha=.25,label="IQR")
        axis.axvline(300,color="k",linestyle="--",label="active begins")
        axis.set(xlabel="generation",title=title);axis.legend(fontsize=8)
    fig.tight_layout();fig.savefig(O/"history_descriptive.png",dpi=160);plt.close(fig)
    sp.groupby("stage")[["direct_source_attempt_statepoint","any_same_experiment_statepoint"]].sum().to_csv(O/"statepoint_by_stage.csv")
if __name__=="__main__":main()

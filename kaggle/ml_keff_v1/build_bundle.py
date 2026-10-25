import csv, hashlib, io, json, math, zipfile
from pathlib import Path
root=Path('/home/ascanipek/openmc-proje')
data=root/'datasets/v2_256_preview_v1'
review=root/'datasets/v2_256_training_review_v1'
outdir=root/'kaggle/ml_keff_v1'
features=['u235_enrichment_wt_percent','fuel_temperature_K','moderator_temperature_K','coolant_pressure_MPa','elemental_boron_ppm','pin_pitch_cm','pellet_radius_cm','insertion_percent']
cols=['row','scenario_id',*features,'k_mean','k_mc_standard_error','split','run_id','package_id','cross_sections_xml_sha256']
sha=lambda x:hashlib.sha256(x).hexdigest()
enc=lambda x:(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
def rows(p):
    with p.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
mb=(data/'dataset_manifest.json').read_bytes(); sb=(data/'splits.json').read_bytes()
manifest=json.loads(mb); splits=json.loads(sb); summary=json.loads((review/'review_summary.json').read_text())
assert summary['source_preview_manifest_sha256']==sha(mb)
assert summary['source_split_sha256']==sha(sb)
assert manifest['scenario_count']==256
assert sha((root/'scenarios/v2_students_portable_v1/catalogue_total_256.json').read_bytes())==manifest['catalogue_sha256']
assert summary['decision_counts']['keff']=={'ACCEPT':0,'REVIEW_REQUIRED':256,'REJECT':0,'NOT_ASSESSED':0}
ss=rows(data/'scenarios.csv'); ts=rows(data/'targets_keff.csv'); ds=rows(review/'training_decisions.csv')
assert len(ss)==len(ts)==len(ds)==256
ids=[s['scenario_id'] for s in ss]; assert len(set(ids))==256
assert {k:len(splits[k]) for k in ('train','calibration','test')}=={'train':208,'calibration':25,'test':23}
roles={sid:k for k in ('train','calibration','test') for sid in splits[k]}
assert len(roles)==256 and set(roles)==set(ids)
buf=io.StringIO(newline=''); writer=csv.DictWriter(buf,fieldnames=cols,lineterminator='\n');writer.writeheader()
for i,(s,t,d) in enumerate(zip(ss,ts,ds)):
    assert s['scenario_id']==t['scenario_id']==d['scenario_id']
    assert s['row']==t['row']==d['row']==str(i)
    assert s['split']==d['split']==roles[s['scenario_id']]
    assert d['keff_training_status']=='REVIEW_REQUIRED'
    for c in features: assert s[c] and math.isfinite(float(s[c]))
    for c in ('k_mean','k_mc_standard_error'): assert t[c] and math.isfinite(float(t[c]))
    assert float(t['k_mc_standard_error'])>0
    writer.writerow({**{c:s[c] for c in ('row','scenario_id',*features,'split','run_id','package_id','cross_sections_xml_sha256')},'k_mean':t['k_mean'],'k_mc_standard_error':t['k_mc_standard_error']})
contract={'schema':'provisional_keff_ml_v1','rows':256,'scientific_status':'PROVISIONAL_EXPLORATORY; 256/256 keff REVIEW_REQUIRED; no physical/statistical training acceptance','features_in_order':features,'target':'k_mean','target_unit':'dimensionless','mc_error_column':'k_mc_standard_error','mc_error_meaning':'MC statistical standard error, not physical accuracy','split_counts':{k:len(splits[k]) for k in ('train','calibration','test')},'split_policy':'unchanged; train-only CV; calibration uncertainty; test once after selection','row_order':'source scenarios.csv catalogue order','source_preview_manifest_sha256':sha(mb),'source_scenarios_csv_sha256':sha((data/'scenarios.csv').read_bytes()),'source_targets_keff_csv_sha256':sha((data/'targets_keff.csv').read_bytes()),'source_splits_json_sha256':sha(sb),'source_review_summary_sha256':sha((review/'review_summary.json').read_bytes())}
quality={'keff_decisions':summary['decision_counts']['keff'],'statepoints_available_on_source_machine':manifest['statepoints_available_on_this_machine'],'cross_sections_index_hash_counts':manifest['nuclear_index_hash_counts'],'nuclear_hdf5_byte_equivalence':manifest['nuclear_hdf5_byte_equivalence'],'warning':'11 alternate index cases require source library equivalence review. Completion and MC error do not establish physical validity or source convergence.'}
readme='''# 256 k-effective senaryosu — geçici Kaggle verisi

Yalnız ilk keşif amaçlı ML karşılaştırması içindir. 256/256 k koşusu bilimsel inceleme bekliyor; fiziksel doğrulama ve eğitim kabulü verilmedi. 11 koşuda nükleer veri indeksi hash'i farklı; HDF5 eşdeğerliği doğrulanmadı.

ml_keff.csv sekiz fiziksel girdiyi, boyutsuz k_mean hedefini, k_mc_standard_error istatistiksel hatasını ve sabit split'i içerir. splits.json özgün kayıttır. bundle_hashes.json dosyaları doğrular. 3B alan verisi yoktur.

Notebook'u ayrıca Kaggle'a import edin. ZIP'i Dataset olarak Input'a bağlayın. Eğitim ve raporlar yalnız /kaggle/working altında oluşur.
'''
files={'ml_keff.csv':buf.getvalue().encode(),'splits.json':sb,'data_contract.json':enc(contract),'quality_summary.json':enc(quality),'README.md':readme.encode()}
files['bundle_hashes.json']=enc({'schema':'sha256_files_v1','files':{k:sha(v) for k,v in files.items()}})
archive=outdir/'openmc_keff_256_provisional_v1.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,content in files.items():
        info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,content)
print(archive,archive.stat().st_size)

import json
from pathlib import Path
out=Path('/home/ascanipek/openmc-proje/kaggle/ml_keff_v1/01_keff_kaggle_egitim.ipynb')
cells=[]
def md(s): cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(True)})
def code(s): cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':s.splitlines(True)})
md("""# 256 OpenMC senaryosuyla ilk k-effective tahmini

**PROVISIONAL / EXPLORATORY.** 256 koşunun tamamı bilimsel inceleme bekliyor. Buradaki ML sonuçları fiziksel doğrulama veya eğitim veri seti kabulü değildir. MC standart hatası fiziksel doğruluk yüzdesi değildir.

Bu notebook yalnız Kaggle'da ML eğitir; OpenMC çalıştırmaz. Sabit 208 eğitim / 25 kalibrasyon / 23 bağımsız test kimlikleri korunur. Model ve hiperparametre seçimi yalnız eğitim kümesindeki çapraz doğrulamayla yapılır. Test en sonda bir kez kullanılır.
""")
md("## 1. Veri ve bağımlılık ön kontrolü\nZIP Dataset olarak Input'a bağlanmış olmalı. Çıkarılmış dosyalar da desteklenir. Gerekirse DATASET_ROOT değerini Kaggle Input yoluna ayarlayın.")
code("""from pathlib import Path
import csv, hashlib, io, json, os, platform, sys, zipfile
import importlib.util
DATASET_ROOT = None  # Örn. '/kaggle/input/openmc-keff-256'; otomatik arama için None
required = ['numpy','pandas','matplotlib','sklearn','xgboost','joblib']
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise RuntimeError('Kaggle ortamında eksik ML bağımlılığı: ' + ', '.join(missing))
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import sklearn, xgboost, joblib
from IPython.display import display
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, Matern, WhiteKernel, ConstantKernel
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor
SEED = 20261025
WORK = Path('/kaggle/working')
WORK.mkdir(parents=True, exist_ok=True)
print('Python:', sys.version.split()[0], 'sklearn:', sklearn.__version__, 'xgboost:', xgboost.__version__)
print('CPU:', os.cpu_count())
""")
code("""input_root = Path('/kaggle/input')
if not input_root.is_dir():
    raise FileNotFoundError('Bu notebook Kaggle /kaggle/input dizinini bekliyor.')
if DATASET_ROOT:
    selected = Path(DATASET_ROOT)
    candidates = [selected] if selected.is_file() else [*selected.rglob('bundle_hashes.json'), *selected.rglob('*.zip')]
else:
    candidates = [*input_root.rglob('bundle_hashes.json'), *input_root.rglob('*.zip')]
valid = []
for p in candidates:
    try:
        if p.name == 'bundle_hashes.json' and (p.parent / 'ml_keff.csv').is_file():
            valid.append(('directory', p.parent))
        elif p.suffix.lower() == '.zip':
            with zipfile.ZipFile(p) as z:
                if {'bundle_hashes.json','ml_keff.csv','splits.json','data_contract.json','quality_summary.json'} <= set(z.namelist()):
                    valid.append(('zip', p))
    except zipfile.BadZipFile:
        continue
if len(valid) != 1:
    raise ValueError(f'Tek k-effective veri paketi bekleniyor; bulunan: {valid}. DATASET_ROOT ayarlayın.')
mode, source = valid[0]
if mode == 'zip':
    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any('/' in n or '\\\\' in n or n.startswith('.') for n in names):
            raise ValueError('Beklenmeyen ZIP yolu')
        payload = {name: z.read(name) for name in names}
else:
    names = ['ml_keff.csv','splits.json','data_contract.json','quality_summary.json','README.md','bundle_hashes.json']
    payload = {name:(source/name).read_bytes() for name in names}
ledger = json.loads(payload['bundle_hashes.json'])
assert set(ledger['files']) == set(payload) - {'bundle_hashes.json'}
for name, expected in ledger['files'].items():
    assert hashlib.sha256(payload[name]).hexdigest() == expected, f'Hash uyuşmazlığı: {name}'
bundle_sha256 = hashlib.sha256(source.read_bytes()).hexdigest() if mode == 'zip' else None
print('Doğrulanan Dataset:', source, 'ZIP SHA256:', bundle_sha256)
""")
md("## 2. Sekiz fiziksel girdi ve k hedefi\nZenginlik ağırlık %, sıcaklıklar K, basınç MPa, elementel bor ppm, adım ve yarıçap cm, giriş aktif yüksekliğin % değeridir. Hedef boyutsuz k-effective değeridir.")
code("""contract = json.loads(payload['data_contract.json'])
quality = json.loads(payload['quality_summary.json'])
split_ids = json.loads(payload['splits.json'])
df = pd.read_csv(io.BytesIO(payload['ml_keff.csv']), encoding='utf-8')
features = contract['features_in_order']
assert features == ['u235_enrichment_wt_percent','fuel_temperature_K','moderator_temperature_K','coolant_pressure_MPa','elemental_boron_ppm','pin_pitch_cm','pellet_radius_cm','insertion_percent']
assert len(df) == 256 and df['scenario_id'].is_unique and df['row'].tolist() == list(range(256))
assert not df[features + ['k_mean','k_mc_standard_error']].isna().any().any()
assert np.isfinite(df[features + ['k_mean','k_mc_standard_error']].to_numpy(dtype=float)).all()
assert (df['k_mc_standard_error'] > 0).all()
assert quality['keff_decisions'] == {'ACCEPT':0,'REVIEW_REQUIRED':256,'REJECT':0,'NOT_ASSESSED':0}
print('Girdiler:', features, '\\nHedef: k_mean; MC istatistiksel hata: k_mc_standard_error')
display(df.head(10))
""")
code("""fig, ax = plt.subplots(figsize=(7,4))
ax.hist(df['k_mean'], bins=25)
ax.set(xlabel='k-effective', ylabel='Senaryo', title='256 senaryonun k dağılımı')
fig.tight_layout()
fig.savefig(WORK/'keff_distribution.png', dpi=150)
plt.show()
plt.close(fig)
""")
md("## 3. Sabit bölmeleri doğrula\nKalibrasyon ve test senaryoları eğitim içi çapraz doğrulamaya girmez.")
code("""expected = {'train':208,'calibration':25,'test':23}
assert {role:len(split_ids[role]) for role in expected} == expected
assert len(set().union(*(set(split_ids[role]) for role in expected))) == 256
assert sum(len(split_ids[role]) for role in expected) == 256
for role in expected:
    assert set(df.loc[df['split']==role,'scenario_id']) == set(split_ids[role])
assert df['split'].value_counts().to_dict() == expected
display(df.groupby('split', sort=False).agg(senaryo=('scenario_id','size'), k_ortalama=('k_mean','mean'), mc_hata_medyan=('k_mc_standard_error','median')))
X_train = df.loc[df.split=='train',features].to_numpy(float)
y_train = df.loc[df.split=='train','k_mean'].to_numpy(float)
X_cal = df.loc[df.split=='calibration',features].to_numpy(float)
y_cal = df.loc[df.split=='calibration','k_mean'].to_numpy(float)
X_test = df.loc[df.split=='test',features].to_numpy(float)
y_test = df.loc[df.split=='test','k_mean'].to_numpy(float)
cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
""")
md("## 4. Yalnız eğitim verisiyle model seçimi\nÖlçekleme her CV katının eğitim kısmından öğrenilir. Arama sınırlıdır; bu ilk karşılaştırmadır.")
code("""scoring = {'mae':'neg_mean_absolute_error','rmse':'neg_root_mean_squared_error'}
def fit_search(name, estimator, grid):
    search = GridSearchCV(estimator, grid, scoring=scoring, refit='rmse', cv=cv, n_jobs=1, error_score='raise', return_train_score=False)
    search.fit(X_train, y_train)
    i = search.best_index_
    return {'name':name, 'search':search, 'cv_mae':-float(search.cv_results_['mean_test_mae'][i]), 'cv_rmse':-float(search.cv_results_['mean_test_rmse'][i]), 'params':search.best_params_}
results = []
results.append(fit_search('Ridge', Pipeline([('scale',StandardScaler()),('model',Ridge())]), {'model__alpha':[0.01,0.1,1.0,10.0,100.0]}))
print('Ridge CV RMSE:', results[-1]['cv_rmse'])
""")
code("""kernels = [ConstantKernel(1.0)*RBF(length_scale=1.0)+WhiteKernel(noise_level=1e-4),
           ConstantKernel(1.0)*Matern(length_scale=1.0,nu=1.5)+WhiteKernel(noise_level=1e-4)]
gpr = Pipeline([('scale',StandardScaler()),('model',GaussianProcessRegressor(normalize_y=True,n_restarts_optimizer=0,random_state=SEED))])
results.append(fit_search('GPR', gpr, {'model__kernel':kernels, 'model__alpha':[1e-8]}))
print('GPR CV RMSE:', results[-1]['cv_rmse'])
""")
code("""threads = min(4, os.cpu_count() or 1)
xgb = XGBRegressor(objective='reg:squarederror',tree_method='hist',random_state=SEED,n_jobs=threads,subsample=1.0,colsample_bytree=1.0)
results.append(fit_search('XGBoost',xgb,{'n_estimators':[200,400],'max_depth':[2,4],'learning_rate':[0.05]}))
print('XGBoost CV RMSE:', results[-1]['cv_rmse'])
""")
code("""comparison = pd.DataFrame([{'model':r['name'],'train_cv_mae':r['cv_mae'],'train_cv_rmse':r['cv_rmse'],'best_params':str(r['params'])} for r in results]).sort_values('train_cv_rmse')
comparison.to_csv(WORK/'model_comparison.csv',index=False)
display(comparison)
selected_name = comparison.iloc[0]['model']
selected = next(r for r in results if r['name']==selected_name)
print('Seçilen model (yalnız train-CV):', selected_name)
""")
md("## 5. Kalibrasyon belirsizliği ve bağımsız test\nKalibrasyon bulgusu model seçimini değiştirmez. GPR belirsizliği varsa açıklayıcı kapsam olarak raporlanır; MC hatası fiziksel doğruluk değildir.")
code("""calibration_report = {'role':'uncertainty_description_only','count':25}
gpr_best = next(r for r in results if r['name']=='GPR')['search'].best_estimator_
cal_scaled = gpr_best.named_steps['scale'].transform(X_cal)
cal_pred, cal_std = gpr_best.named_steps['model'].predict(cal_scaled,return_std=True)
cal_mc = df.loc[df.split=='calibration','k_mc_standard_error'].to_numpy(float)
combined_std = np.sqrt(cal_std**2 + cal_mc**2)
calibration_report.update({'gpr_mae':float(mean_absolute_error(y_cal,cal_pred)),
 'gpr_mean_predictive_std':float(np.mean(cal_std)),
 'gpr_coverage_2sigma_descriptive':float(np.mean(np.abs(y_cal-cal_pred)<=2*combined_std))})
display(pd.DataFrame([calibration_report]))
""")
code("""prediction = selected['search'].best_estimator_.predict(X_test)
test_mae = float(mean_absolute_error(y_test,prediction))
test_rmse = float(np.sqrt(mean_squared_error(y_test,prediction)))
test_df = df.loc[df.split=='test',['scenario_id','k_mean','k_mc_standard_error']].copy()
test_df['k_predicted'] = prediction
test_df['residual_pred_minus_true'] = prediction-y_test
test_df.to_csv(WORK/'test_predictions.csv',index=False)
print('Bağımsız test MAE:',test_mae,'RMSE:',test_rmse)
display(test_df.head(10))
fig,ax=plt.subplots(figsize=(5,5))
ax.scatter(y_test,prediction)
lo=min(y_test.min(),prediction.min()); hi=max(y_test.max(),prediction.max())
ax.plot([lo,hi],[lo,hi],color='black',linestyle='--')
ax.set(xlabel='OpenMC k',ylabel='Tahmin edilen k',title='Bağımsız test')
fig.tight_layout();fig.savefig(WORK/'actual_vs_pred.png',dpi=150);plt.show();plt.close(fig)
fig,ax=plt.subplots(figsize=(7,4))
ax.hist(prediction-y_test,bins=15)
ax.set(xlabel='Tahmin - OpenMC k',ylabel='Senaryo',title='Test hata dağılımı')
fig.tight_layout();fig.savefig(WORK/'residuals.png',dpi=150);plt.show();plt.close(fig)
""")
md("## 6. Çıktıları kaydet\nModel dosyası yalnız güvenilir kaynaklardan yüklenmelidir. Rapor hem veri kaynağını hem yazılım sürümlerini kaydeder.")
code("""model_path = WORK/'selected_keff_model.joblib'
joblib.dump(selected['search'].best_estimator_,model_path)
report={'schema':'provisional_keff_ml_result_v1','scientific_status':contract['scientific_status'],
 'selected_model':selected_name,'selection_metric':'train_cv_rmse','seed':SEED,
 'train_count':208,'calibration_count':25,'test_count':23,
 'test_mae':test_mae,'test_rmse':test_rmse,'calibration':calibration_report,
 'data_contract':contract,'quality_warning':quality['warning'],
 'dataset_source':str(source),'dataset_zip_sha256':bundle_sha256,
 'input_file_hashes':ledger['files'],'python':platform.python_version(),
 'numpy':np.__version__,'pandas':pd.__version__,'scikit_learn':sklearn.__version__,
 'xgboost':xgboost.__version__,'threads_xgboost':threads}
(WORK/'training_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print('Kaydedilenler:',*[p.name for p in sorted(WORK.iterdir()) if p.name in {'model_comparison.csv','test_predictions.csv','actual_vs_pred.png','residuals.png','keff_distribution.png','selected_keff_model.joblib','training_report.json'}],sep='\\n- ')
""")
nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'}},'nbformat':4,'nbformat_minor':4}
out.write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
print(out,len(cells),'cells')

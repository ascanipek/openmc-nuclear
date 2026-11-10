"""Additional entropy-only diagnostics at the inactive/active boundary."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

R=Path(__file__).resolve().parents[2]
D=R/'datasets/v2_512_combined_v1'
O=R/'reports/entropy_300_diagnostic_v1'
manifest=json.loads((D/'dataset_manifest.json').read_text())
assert hashlib.sha256((D/'fields.npz').read_bytes()).hexdigest()==manifest['output_sha256']['fields.npz']
prior=pd.read_csv(R/'reports/physical_acceptance_followup_v1/scenario_evidence.csv')
with np.load(D/'fields.npz',allow_pickle=False) as data:
    h=data['shannon_entropy'].copy()
assert h.shape==(512,600) and np.isfinite(h).all() and prior.scenario_id.nunique()==512
# Existing first/last 100 means remain in the earlier audit; these windows are new.
before=h[:,250:300].mean(axis=1)
after=h[:,300:350].mean(axis=1)
drift=h[:,300:400].mean(axis=1)-h[:,200:300].mean(axis=1)
x=np.arange(250,300,dtype=float);x-=x.mean()
slope=((h[:,250:300]-before[:,None])*x).sum(axis=1)/(x*x).sum()
late_noise=h[:,400:600].std(axis=1,ddof=1)
frame=prior[['scenario_id','experiment_id','stage','insertion_percent']].copy()
frame['entropy_before_250_299']=before
frame['entropy_after_300_349']=after
frame['boundary_change_50']=after-before
frame['boundary_change_abs']=np.abs(after-before)
frame['inactive_last50_slope_per_generation']=slope
frame['inactive_last100_to_active_first100']=drift
frame['active_400_599_sd']=late_noise
frame=frame.sort_values('boundary_change_abs',ascending=False).reset_index(drop=True)
frame.to_csv(O/'entropy_boundary_diagnostics.csv',index=False)
top=frame.head(10)
fig,axes=plt.subplots(5,2,figsize=(13,15),sharex=True)
idx={sid:i for i,sid in enumerate(prior.scenario_id)}
for ax,row in zip(axes.flat,top.itertuples()):
    y=h[idx[row.scenario_id]]
    ax.plot(np.arange(200,401),y[200:401],lw=.8,alpha=.7)
    ax.plot([250,299],[row.entropy_before_250_299]*2,lw=2,label='250–299 mean')
    ax.plot([300,349],[row.entropy_after_300_349]*2,lw=2,label='300–349 mean')
    ax.axvline(300,color='black',ls='--',lw=.8)
    ax.set(title=f'{row.experiment_id}  Δ50={row.boundary_change_50:+.4f}',ylabel='Shannon entropy')
axes[0,0].legend(fontsize=8)
for ax in axes[-1]:ax.set_xlabel('Generation (zero-based index; active starts at 300)')
fig.tight_layout();fig.savefig(O/'top10_entropy_boundary.png',dpi=150);plt.close(fig)
q=frame.boundary_change_abs.quantile([.5,.9,.95,1]).to_dict()
lines=['# 300 inaktif nesil sınırında entropi tanısı — v1','',
       '**PROVISIONAL_EXPLORATORY.** Bu ölçüler kaynak yakınsaması veya fiziksel kabul kararı değildir. Yeni MC veya model eğitimi yapılmadı.','',
       'Önceki takip analizindeki 0–99/200–299 ve 300–399/500–599 ortalamaları yeniden hesaplanmadı. Yalnız sınır çevresindeki 250–299 ve 300–349 ellişer neslin ortalama farkı, inaktif son 50 eğimi ve aktif 400–599 dalgalanması eklendi. Nesiller korelasyonlu olduğu için bu fark için bağımsız-örneklem anlamlılık testi yapılmadı.','',
       f'512 senaryoda |sınır farkı| medyanı {q[.5]:.5f}, P90 {q[.9]:.5f}, P95 {q[.95]:.5f}, en büyük {q[1.0]:.5f}. Bunlar eşik değil, dağılım betimlemesidir.','',
       '## En belirgin 10 sınır değişimi','',
       '| Deney | Giriş % | 250–299 → 300–349 entropi farkı | Son 50 inaktif eğim/nesil |','|---|---:|---:|---:|']
for row in top.itertuples():lines.append(f'| {row.experiment_id} | {row.insertion_percent:.2f} | {row.boundary_change_50:+.5f} | {row.inactive_last50_slope_per_generation:+.6f} |')
lines += ['', '![En belirgin 10 entropi eğrisi](top10_entropy_boundary.png)','',
          'Sıralama yalnız sınırdaki mutlak 50 nesillik ortalama değişimine göredir; grafikte 200–400 aralığı gösterilir. Farkın büyüklüğü entropi meshine ve MC dalgalanmasına bağlıdır. Tek global Shannon entropisi uzaysal kaynak dağılımının bütün biçimlerini ayırt edemez. Kaynak yakınsaması için ayrıca k geçmişi, uzaysal kaynak göstergeleri ve gerekçeli değerlendirme kuralı gerekir. 512/512 için `source_convergence_status=NOT_ASSESSED` korunur.','',
          'Kaynaklar: `datasets/v2_512_combined_v1/fields.npz` ve önceki `reports/physical_acceptance_followup_v1/scenario_evidence.csv`. OpenMC kaynak entropisi açıklaması: https://docs.openmc.org/en/stable/methods/eigenvalue.html','']
(O/'README.md').write_text('\n'.join(lines),encoding='utf-8')
print('top10',top[['experiment_id','boundary_change_50']].to_string(index=False))
print('quantiles',q)

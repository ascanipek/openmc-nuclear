"""Compare saved generation-wise k and entropy for the prior entropy top ten."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets/v2_512_combined_v1"
OUT = ROOT / "reports/entropy_keff_top10_v1"
OUT.mkdir(exist_ok=True)

manifest = json.loads((DATA / "dataset_manifest.json").read_text(encoding="utf-8"))
digest = hashlib.file_digest((DATA / "fields.npz").open("rb"), "sha256").hexdigest()
assert digest == manifest["output_sha256"]["fields.npz"]
scenarios = pd.read_csv(DATA / "scenarios.csv")
previous = pd.read_csv(ROOT / "reports/entropy_300_diagnostic_v1/entropy_boundary_diagnostics.csv")
top = previous.nlargest(10, "boundary_change_abs").copy()
assert len(top) == top.scenario_id.nunique() == 10
assert len(scenarios) == scenarios.scenario_id.nunique() == 512
row_by_id = pd.Series(scenarios.row.to_numpy(), index=scenarios.scenario_id)
indices = row_by_id.loc[top.scenario_id].to_numpy(dtype=int)
assert np.array_equal(scenarios.iloc[indices].scenario_id.to_numpy(), top.scenario_id.to_numpy())

with np.load(DATA / "fields.npz", allow_pickle=False) as fields:
    k = fields["k_generation"][indices]
    entropy = fields["shannon_entropy"][indices]
assert k.shape == entropy.shape == (10, 600)
assert np.isfinite(k).all() and np.isfinite(entropy).all()

top["k_mean_250_299"] = k[:, 250:300].mean(axis=1)
top["k_mean_300_349"] = k[:, 300:350].mean(axis=1)
top["k_change"] = top["k_mean_300_349"] - top["k_mean_250_299"]
top["k_change_abs"] = top.k_change.abs()
assert np.allclose(entropy[:, 250:300].mean(axis=1), top.entropy_before_250_299)
assert np.allclose(entropy[:, 300:350].mean(axis=1), top.entropy_after_300_349)

columns = ["scenario_id", "experiment_id", "insertion_percent", "entropy_before_250_299",
           "entropy_after_300_349", "boundary_change_50", "k_mean_250_299",
           "k_mean_300_349", "k_change", "k_change_abs"]
top[columns].to_csv(OUT / "top10_keff_entropy.csv", index=False, float_format="%.12g")

fig, axes = plt.subplots(5, 2, figsize=(15, 15), sharex=True, constrained_layout=True)
x = np.arange(200, 400)
for i, ax in enumerate(axes.flat):
    ax.plot(x, k[i, 200:400], color="tab:blue", lw=0.85, alpha=0.8)
    ax.plot([250, 299], [top.iloc[i].k_mean_250_299] * 2, color="tab:blue", lw=2.3)
    ax.plot([300, 349], [top.iloc[i].k_mean_300_349] * 2, color="tab:blue", lw=2.3)
    ax.axvline(300, color="0.4", lw=1, ls="--")
    other = ax.twinx()
    other.plot(x, entropy[i, 200:400], color="tab:orange", lw=0.85, alpha=0.7)
    ax.set_title(top.iloc[i].experiment_id, fontsize=10)
    ax.set_ylabel("Nesil k", color="tab:blue")
    other.set_ylabel("Shannon entropisi", color="tab:orange")
    ax.grid(alpha=0.2)
    if i >= 8:
        ax.set_xlabel("Nesil (0 tabanlı)")
fig.suptitle("Kayıtlı k ve Shannon entropisi: 300. nesil sınırı", fontsize=14)
fig.savefig(OUT / "top10_keff_entropy.png", dpi=160)
plt.close(fig)

same_direction = int(((top.k_change * top.boundary_change_50) > 0).sum())
lines = [
    "# Entropi sınırında k geçmişi — ilk 10 senaryo",
    "",
    "Kaynak: önceki `entropy_boundary_diagnostics.csv` dosyasında en büyük mutlak entropi değişimine sahip 10 senaryo; `v2_512_combined_v1/fields.npz` içindeki kayıtlı nesil geçmişleri. Nesiller **0 tabanlıdır**. Yeni transport hesabı yapılmadı.",
    "",
    "| Senaryo | k 250–299 | k 300–349 | Δk | Δentropi |",
    "|---|---:|---:|---:|---:|",
]
for r in top.itertuples():
    lines.append(f"| {r.experiment_id} | {r.k_mean_250_299:.6f} | {r.k_mean_300_349:.6f} | {r.k_change:+.6f} | {r.boundary_change_50:+.5f} |")
lines += [
    "",
    f"Entropi ve k pencere ortalaması {same_direction}/10 senaryoda aynı yönde, {10-same_direction}/10 senaryoda ters yönde değişti. "
    f"Mutlak Δk aralığı {top.k_change_abs.min():.6f}–{top.k_change_abs.max():.6f}; en büyük mutlak Δk "
    f"{top.loc[top.k_change_abs.idxmax(), 'experiment_id']} koşusunda görüldü. "
    "Dolayısıyla büyük entropi değişimleri, k ortalamasında tek yönlü ve tutarlı bir değişimle eşleşmiyor. "
    "Nesil bazındaki dalgalanma ve ardışık nesillerin bağımlılığı nedeniyle bu karşılaştırma istatistiksel anlamlılık veya kaynak yakınsaması testi değildir.",
    "",
    "![On senaryonun k ve entropi geçmişleri](top10_keff_entropy.png)",
    "",
    "Bu tanıdan otomatik fiziksel kabul veya ret kararı çıkarılmadı.",
]
(OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(top[["experiment_id", "k_change", "boundary_change_50"]].to_string(index=False))
print("same_direction", same_direction)

import pandas as pd
from pathlib import Path
import matplotlib;matplotlib.use("Agg")
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[2]/"reports/pinn_feasibility_and_experiment_v2"
d=pd.read_csv(R/"seed_metrics.csv")
fig,ax=plt.subplots(figsize=(7,4))
for method,group in d.groupby("method"):ax.plot(group.seed,group.validation_relative_l2,marker="o",label=method)
ax.set_yscale("log");ax.set(xlabel="seed",ylabel="Dense-grid relative L2 (log)",title="Five independent initializations")
ax.legend();fig.tight_layout();fig.savefig(R/"seed_stability_log.png",dpi=170);plt.close(fig)

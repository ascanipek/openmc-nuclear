"""Independent checks for new research artifacts; no transport."""
import json,numpy as np,pandas as pd
from pathlib import Path
R=Path(__file__).resolve().parents[2]
P=R/"reports/physical_error_analysis_v1"
N=R/"reports/pinn_feasibility_and_experiment_v2"
A=R/"reports/physical_validation_audit_v1"
case=pd.read_csv(P/"oof_case_metrics.csv")
assert case.groupby("branch").size().to_dict()=={"initial":208,"halton":336,"adaptive":336,"combined":464}
assert not case.duplicated(["branch","scenario_id"]).any()
assert np.array_equal(case.zero_fuel_voxels+case.low_signal_positive_voxels+case.strong_voxels,case.fuel_voxels)
n=pd.read_csv(N/"seed_metrics.csv")
assert len(n)==10 and n.groupby("method").size().to_dict()=={"MLP_residual_off":5,"PINN_residual_on":5}
assert n.optimizer_success.all()
assert n[n.method=="PINN_residual_on"].validation_relative_l2.mean()<n[n.method=="MLP_residual_off"].validation_relative_l2.mean()
assert n[n.method=="PINN_residual_on"].validation_pde_residual_rms.mean()<n[n.method=="MLP_residual_off"].validation_pde_residual_rms.mean()
d=json.loads((A/"audit_summary.json").read_text())
assert d["scenarios"]==512 and d["statepoint_direct_source_attempt_count"]==64 and d["statepoint_same_experiment_name_count"]==248
assert d["nuclear_index_comparison"]["logical_material_type_suffix_entries_equal"] is True
assert d["nuclear_index_comparison"]["hdf5_byte_equivalence"].startswith("NOT_ASSESSED")
print("research artifact checks: all checks passed")

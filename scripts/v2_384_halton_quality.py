"""Summarize fixed-mask signal coverage without granting physical acceptance."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_384_halton_v1"
OUT = ROOT / "reports/comparison_256_vs_384_halton_v1"


def main():
    if not OUT.is_dir():
        raise FileNotFoundError(OUT)
    scenarios = pd.read_csv(DATA / "scenarios.csv")
    q = pd.read_csv(DATA / "quality_report.csv")
    q = q[q.check == "structure_and_identity"].sort_values("row")
    if len(q) != 384 or not np.array_equal(q.row.to_numpy(), np.arange(384)):
        raise ValueError("Quality/scenario order mismatch")
    with np.load(DATA / "fields.npz", allow_pickle=False) as fields:
        fuel = fields["fuel_volume_fraction"] > 0
        kappa = fields["kappa_fission_mean"]
        fission = fields["fission_mean"]
        fission_se = fields["fission_std_dev"]
        low = fuel & ((fission == 0) | (fission < 5*fission_se) |
                      (fission < 1e-6*fission.max(axis=(1, 2, 3))[:, None, None, None]))
        zero = fuel & (kappa == 0)
        mean = kappa
        se = fields["kappa_fission_std_dev"]
        positive = fuel & (mean > 0)
        rel = np.divide(se, mean, out=np.full_like(mean, np.nan), where=positive)
    if not np.all(fuel.sum(axis=(1, 2, 3)) == 5280):
        raise ValueError("Unexpected geometric fuel voxel count")
    bands = pd.cut(scenarios.insertion_percent, [-1, 100/3, 200/3, 101],
                   labels=["low", "middle", "high"])
    entries = {}
    for label, mask in (("old_256", np.arange(384) < 256),
                        ("new_halton_128", np.arange(384) >= 256)):
        total = int(fuel[mask].sum())
        entries[label] = {
            "scenarios": int(mask.sum()), "fuel_voxels_total": total,
            "measured_zero_fuel_voxels": int(zero[mask].sum()),
            "measured_zero_fraction": float(zero[mask].sum()/total),
            "low_signal_fuel_voxels": int(low[mask].sum()),
            "low_signal_fraction": float(low[mask].sum()/total),
            "upper_four_fuel_voxels": int(fuel[mask, -4:].sum()),
            "upper_four_measured_zero": int(zero[mask, -4:].sum()),
            "upper_four_low_signal": int(low[mask, -4:].sum()),
            "positive_signal_relative_mc_error_median": float(np.nanmedian(rel[mask])),
            "positive_signal_relative_mc_error_p95": float(np.nanpercentile(rel[mask], 95)),
        }
    by_stage = {}
    for stage in ("halton_01", "halton_02", "halton_03", "halton_04"):
        mask = scenarios.stage.eq(stage).to_numpy()
        by_stage[stage] = {
            "scenarios": int(mask.sum()),
            "measured_zero_fuel_voxels": int(zero[mask].sum()),
            "low_signal_fuel_voxels": int(low[mask].sum()),
        }
    by_insertion = {}
    for label in ("low", "middle", "high"):
        mask = (bands == label).to_numpy() & (np.arange(384) >= 256)
        by_insertion[label] = {
            "scenarios": int(mask.sum()),
            "measured_zero_fraction": float(zero[mask].sum()/fuel[mask].sum()),
            "low_signal_fraction": float(low[mask].sum()/fuel[mask].sum()),
        }
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    summary = {
        "schema": "halton_384_signal_quality_review_v1",
        "scientific_status": "PROVISIONAL_EXPLORATORY; not physical/training acceptance",
        "mask": "fuel_volume_fraction > 0, fixed by geometry for each scenario",
        "low_signal_rule": "fuel and (fission_mean == 0 or fission_mean < 5*fission_std_dev or fission_mean < 1e-6 * max(fission_mean))",
        "zero_policy": "Measured zero is neither proven physical zero nor zero uncertainty",
        "groups": entries, "by_halton_stage": by_stage, "new_halton_by_insertion_band": by_insertion,
        "failed_attempts_not_used": manifest["failed_or_incomplete_attempts_not_used"],
        "nuclear_index_hash_counts": manifest["nuclear_index_hash_counts"],
        "statepoints": "lightweight ZIP omits them; 01/02 original local group outputs retain them, 03/04 require student source copies",
        "source_convergence": "not_assessed",
        "physical_validation": "not_assessed",
    }
    (OUT / "quality_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# 384 Halton branch: fixed-mask signal review", "",
             "PROVISIONAL / EXPLORATORY. Geometric fuel mask: fuel_volume_fraction > 0.",
             "Measured zeros are not interpreted as physical zero or zero uncertainty.",
             "", "| Group | Scenarios | Fuel voxels | Measured zero | Low signal | Upper 4 zero / fuel |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, x in entries.items():
        lines.append(f"| {label} | {x['scenarios']} | {x['fuel_voxels_total']} | "
                     f"{x['measured_zero_fuel_voxels']} ({x['measured_zero_fraction']:.1%}) | "
                     f"{x['low_signal_fuel_voxels']} ({x['low_signal_fraction']:.1%}) | "
                     f"{x['upper_four_measured_zero']} / {x['upper_four_fuel_voxels']} |")
    lines += ["", "Low signal uses the existing V2 fission tally diagnostic; this is a review flag, not a pass/fail threshold.",
              "Halton-03 case 0011 has two failed attempts and one completed attempt; only the completed one entered the dataset.",
              "Original 256 has 11 alternate nuclear-index hash cases. Byte equivalence remains unassessed.",
              "Source convergence and physical validation remain unassessed. The lightweight student ZIPs omit statepoints.",
              ""]
    (OUT / "quality_summary.md").write_text("\n".join(lines))
    print(json.dumps({"old": entries["old_256"], "new": entries["new_halton_128"]}))


if __name__ == "__main__":
    main()


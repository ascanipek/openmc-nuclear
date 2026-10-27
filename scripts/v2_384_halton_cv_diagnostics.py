"""Derived fold, rod-band, and Halton-only CV diagnostics; no refitting."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from v2_384_halton_repeated_cv import summarize

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/repeated_cv_256_vs_384_v1"
OLD = ROOT / "datasets/v2_256_preview_v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for name in ("fold_metrics.csv", "insertion_band_metrics.csv",
                 "halton_only_repeat_metrics.csv", "diagnostics_manifest.json"):
        if (REPORT / name).exists():
            raise FileExistsError(REPORT / name)
    oof_path = REPORT / "oof_predictions_and_metrics.csv"
    oof = pd.read_csv(oof_path)
    if len(oof) != 2970 or oof.duplicated(["repeat", "arm", "scenario_id"]).any():
        raise ValueError("OOF coverage mismatch")
    test_ids = set(json.loads((OLD / "splits.json").read_text())["test"])
    if test_ids & set(oof.scenario_id):
        raise ValueError("Original test scenario in CV")
    fold = []
    for (repeat, arm, fold_id), part in oof.groupby(["repeat", "arm", "fold"], sort=True):
        fold.append({"repeat": int(repeat), "arm": arm, "fold": int(fold_id),
                     **summarize(part)})
    fold_df = pd.DataFrame(fold)
    if len(fold_df) != 50:
        raise ValueError("Expected 50 arm/fold metric rows")
    oof["insertion_band"] = pd.cut(oof.insertion_percent,
                                    [-1, 100/3, 200/3, 101],
                                    labels=["low", "middle", "high"])
    scopes = []
    for repeat in range(1, 6):
        part = oof[oof.repeat == repeat]
        scopes += [
            ("A_common233", part[part.arm == "A_233"]),
            ("B_common233", part[(part.arm == "B_361") & (part.source == "initial_233")]),
            ("B_all361", part[part.arm == "B_361"]),
            ("B_halton128", part[(part.arm == "B_361") & (part.source == "halton_128")]),
        ]
    # Repeat is taken from each scope, so every row remains a distinct repeat-level diagnostic.
    bands, halton_rows = [], []
    for label, part in scopes:
        repeat = int(part.repeat.iloc[0])
        if label == "B_halton128":
            halton_rows.append({"repeat": repeat, **summarize(part)})
        for band_name, subset in part.groupby("insertion_band", observed=False):
            if len(subset):
                bands.append({"repeat": repeat, "evaluation": label,
                              "insertion_band": str(band_name), **summarize(subset)})
    bands_df = pd.DataFrame(bands)
    if len(bands_df) != 5*4*3 or len(halton_rows) != 5:
        raise ValueError("Incomplete insertion/repeat diagnostics")
    fold_df.to_csv(REPORT / "fold_metrics.csv", index=False)
    bands_df.to_csv(REPORT / "insertion_band_metrics.csv", index=False)
    pd.DataFrame(halton_rows).to_csv(REPORT / "halton_only_repeat_metrics.csv", index=False)
    fold_ranges = {}
    for evaluation, part in fold_df.groupby("arm"):
        fold_ranges[evaluation] = {
            "k_mae_min": float(part.k_mae.min()), "k_mae_max": float(part.k_mae.max()),
            "field_l2_min": float(part.field_relative_l2_mean.min()),
            "field_l2_max": float(part.field_relative_l2_mean.max()),
        }
    manifest = {
        "schema": "beavrs_v2_repeated_cv_diagnostics_v1",
        "source_oof_sha256": sha(oof_path),
        "source_main_cv_manifest_sha256": sha(REPORT / "reproducibility_manifest.json"),
        "fold_metric_rows": len(fold_df),
        "band_metric_rows": len(bands_df),
        "halton_only_repeats": 5,
        "fold_error_ranges": fold_ranges,
        "note": "Derived from saved OOF without model refitting; repeated predictions of a scenario are not independent observations",
        "output_sha256": {name: sha(REPORT / name) for name in (
            "fold_metrics.csv", "insertion_band_metrics.csv", "halton_only_repeat_metrics.csv")}
    }
    (REPORT / "diagnostics_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()


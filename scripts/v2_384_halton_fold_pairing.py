"""Check 25 matched validation folds on only the shared 233 scenarios."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from v2_384_halton_repeated_cv import summarize

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/repeated_cv_256_vs_384_v1"


def main():
    table_path = REPORT / "paired_fold_common233.csv"
    summary_path = REPORT / "paired_fold_common233_summary.json"
    if table_path.exists() or summary_path.exists():
        raise FileExistsError("Matched fold diagnostics already exist")
    source = REPORT / "oof_predictions_and_metrics.csv"
    oof = pd.read_csv(source)
    rows = []
    for repeat in range(1, 6):
        for fold in range(5):
            a = oof[(oof.repeat == repeat) & (oof.fold == fold) & (oof.arm == "A_233")]
            b = oof[(oof.repeat == repeat) & (oof.fold == fold) & (oof.arm == "B_361") &
                    (oof.source == "initial_233")]
            if len(a) not in (46, 47) or set(a.scenario_id) != set(b.scenario_id):
                raise ValueError("Matched validation scenario IDs differ")
            am, bm = summarize(a), summarize(b)
            rows.append({
                "repeat": repeat, "fold": fold, "shared_validation_count": len(a),
                **{f"A_{key}": value for key, value in am.items()},
                **{f"B_common_{key}": value for key, value in bm.items()},
                **{f"new_minus_old_{key}": bm[key]-am[key]
                   for key in ("k_mae", "k_rmse", "field_relative_l2_mean")},
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(table_path, index=False)
    summary = {
        "schema": "beavrs_v2_paired_fold_common233_v1",
        "source_oof_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "matched_fold_count": len(frame),
        "unit": "one validation fold of 46 or 47 common physical scenarios",
        "note": "Folds and repeated predictions are correlated; these 25 rows are not independent experiments",
        "metrics": {key: {
            "improved_folds": int((frame[f"new_minus_old_{key}"] < 0).sum()),
            "worsened_folds": int((frame[f"new_minus_old_{key}"] > 0).sum()),
            "mean_fold_difference": float(frame[f"new_minus_old_{key}"].mean()),
            "minimum_fold_difference": float(frame[f"new_minus_old_{key}"].min()),
            "maximum_fold_difference": float(frame[f"new_minus_old_{key}"].max()),
        } for key in ("k_mae", "k_rmse", "field_relative_l2_mean")},
        "table_sha256": hashlib.sha256(table_path.read_bytes()).hexdigest(),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()


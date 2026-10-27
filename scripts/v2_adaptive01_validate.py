"""Validate adaptive Sobol controls with the existing V2 physics guard; no transport."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reactor_pipeline import v2_students
from reactor_pipeline.parameter_space import resolve_proposed
from reactor_pipeline.beavrs3d import load_reference


def main(source: Path, target: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    space = v2_students.load_space(ROOT / "configs/v2_parameter_space_pilot_scope_v1.json")
    reference = load_reference()
    reference_sha = v2_students.digest(ROOT / space["reference_config"])
    valid, rejected = [], []
    for index, controls in enumerate(payload):
        try:
            resolve_proposed(controls, reference)
        except (ValueError, RuntimeError, UserWarning) as exc:
            rejected.append({"candidate_index": index, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        valid.append({"candidate_index": index, "scenario_id": v2_students.scenario_id(controls, reference_sha)})
    target.write_text(json.dumps({"reference_sha256": reference_sha, "valid": valid, "rejected": rejected},
                                 indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))

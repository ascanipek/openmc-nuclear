"""Frozen ADAPTIVE-01 selection provenance and package regression checks."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/adaptive_selection_v1"
SELECTED = ROOT / "scenarios/v2_adaptive128_v1/adaptive_01/selected_32.json"
PACKAGE = ROOT / "student_packages/v2_adaptive128_v1/adaptive_01/v2_adaptive_01_beavrs_v2_pilot_scope_v1"


class Adaptive01AuditTests(unittest.TestCase):
    def test_frozen_selection_has_no_source_leakage_or_duplicate(self):
        splits = json.loads((ROOT / "datasets/v2_256_preview_v1/splits.json").read_text())
        chosen = json.loads(SELECTED.read_text())["selected"]
        halton = json.loads((ROOT / "scenarios/v2_halton128_v1/catalogue_new_128.json").read_text())["scenarios"]
        report = json.loads((REPORT / "selection_report.json").read_text())
        with (REPORT / "training_only_oof_uncertainty.csv").open(newline="", encoding="utf-8") as source:
            oof = list(csv.DictReader(source))
        with (REPORT / "calibration_diagnostics.csv").open(newline="", encoding="utf-8") as source:
            calibration = list(csv.DictReader(source))
        chosen_ids = {x["scenario_id"] for x in chosen}
        self.assertEqual(len(chosen), len(chosen_ids))
        self.assertEqual(len(chosen), 32)
        self.assertFalse(chosen_ids & set().union(*map(set, splits.values())))
        self.assertFalse(chosen_ids & {x["scenario_id"] for x in halton})
        self.assertEqual({x["scenario_id"] for x in oof}, set(splits["train"]))
        self.assertEqual({x["scenario_id"] for x in calibration}, set(splits["calibration"]))
        self.assertTrue(report["data_firewall"]["excluded_test_count"] == 23)
        self.assertFalse(report["data_firewall"]["halton_outcomes_read"])
        self.assertFalse(report["data_firewall"]["full384_models_read"])

    def test_scores_bounds_and_manifest_are_exact(self):
        chosen = json.loads(SELECTED.read_text())["selected"]
        report = json.loads((REPORT / "selection_report.json").read_text())
        manifest = json.loads((PACKAGE / "manifest.json").read_text())
        bounds = report["candidate_generation"]["bounds"]
        self.assertEqual(report["scoring"]["weights"], {
            "k_uncertainty": .35, "field_uncertainty": .35,
            "sparsity": .20, "criticality": .10})
        self.assertEqual([x["scenario_id"] for x in chosen],
                         [x["scenario_id"] for x in manifest["experiments"]])
        self.assertEqual([x["calculation"]["seed"] for x in manifest["experiments"]],
                         list(range(73001, 73033)))
        self.assertEqual(manifest["group_runtime_budget_seconds"], 86400)
        scored = json.loads((REPORT / "selected_32.json").read_text())
        self.assertEqual([x["scenario_id"] for x in scored], [x["scenario_id"] for x in chosen])
        for row in scored:
            for name, value in row["controls"].items():
                self.assertTrue(bounds[name]["lower"] <= value <= bounds[name]["upper"])
            total = sum(row["component_weighted"].values())
            self.assertTrue(math.isclose(total, row["total_score"], abs_tol=1e-12))
        self.assertGreaterEqual(report["diversity"]["selected_pairwise_minimum"], .35)
        self.assertTrue(all(8 <= n <= 12 for n in report["diversity"]["selected_band_counts"].values()))


if __name__ == "__main__":
    unittest.main()



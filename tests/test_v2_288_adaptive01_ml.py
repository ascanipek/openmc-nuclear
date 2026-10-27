"""No-transport checks for the exploratory 256+ADAPTIVE-01 data and model report."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "datasets/v2_256_preview_v1"
DATA = ROOT / "datasets/v2_288_adaptive01_exploratory_v1"
REPORT = ROOT / "reports/adaptive01_vs_256_v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


class Adaptive01MLChecks(unittest.TestCase):
    def test_frozen_256_and_split(self):
        manifest = json.loads((DATA / "dataset_manifest.json").read_text())
        for name, expected in manifest["output_sha256"].items():
            self.assertEqual(digest(DATA / name), expected)
        old_split = json.loads((OLD / "splits.json").read_text())
        split = json.loads((DATA / "splits.json").read_text())
        original = rows(OLD / "scenarios.csv")
        combined = rows(DATA / "scenarios.csv")
        self.assertEqual(combined[:256], original)
        self.assertEqual(rows(DATA / "targets_keff.csv")[:256], rows(OLD / "targets_keff.csv"))
        self.assertEqual([x["scenario_id"] for x in combined[256:]], split["train"][208:])
        self.assertEqual(split["train"][:208], old_split["train"])
        self.assertEqual(split["calibration"], old_split["calibration"])
        self.assertEqual(split["test"], old_split["test"])
        self.assertEqual(len({x["scenario_id"] for x in combined}), 288)
        with np.load(OLD / "fields.npz", allow_pickle=False) as old, np.load(DATA / "fields.npz", allow_pickle=False) as new:
            for name in new.files:
                self.assertTrue(np.array_equal(new[name][:256], old[name]), name)
            self.assertEqual(new["target_normalized_kappa"].shape, (288,20,17,17))

    def test_cv_is_train_only_and_test_metrics_are_saved(self):
        split = json.loads((DATA / "splits.json").read_text())
        memberships = json.loads((REPORT / "cv_memberships.json").read_text())
        train = set(split["train"])
        banned = set(split["calibration"]) | set(split["test"])
        self.assertEqual(len(memberships), 5)
        validation = []
        for fold in memberships:
            fit, val = set(fold["fit_scenario_ids"]), set(fold["validation_scenario_ids"])
            self.assertFalse(fit & val)
            self.assertFalse((fit | val) & banned)
            self.assertEqual(fit | val, train)
            validation.extend(fold["validation_scenario_ids"])
        self.assertEqual(set(validation), train)
        self.assertEqual(len(validation), 240)
        report = json.loads((REPORT / "training_report.json").read_text())
        predictions = rows(REPORT / "test_per_scenario.csv")
        self.assertEqual({x["scenario_id"] for x in predictions}, set(split["test"]))
        self.assertEqual(len(predictions), 23)
        for label, expected in (("initial_256", 208), ("adaptive01_288", 240)):
            with np.load(REPORT / f"{label}_pca.npz", allow_pickle=False) as pca:
                self.assertEqual(len(pca["train_scenario_ids"]), expected)
                self.assertEqual(pca["basis"].shape, (12, 5780))
                self.assertFalse(set(pca["train_scenario_ids"].tolist()) & banned)
        self.assertEqual(report["scientific_status"].split(";")[0], "PROVISIONAL_EXPLORATORY")


if __name__ == "__main__":
    unittest.main()

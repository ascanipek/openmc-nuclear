"""Checks for the imported 256-scenario preview without transport."""
import csv
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v2_256_ml_dataset", ROOT / "scripts/v2_256_ml_dataset.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
CAT = ROOT / "scenarios/v2_students_portable_v1/catalogue_total_256.json"
IMP = ROOT / "deliveries/imported"
AUD = IMP / "central_256_audit.csv"
OUT = ROOT / "datasets/v2_256_preview_v1"


@contextmanager
def frozen_256_import_view():
    """Present the original audited deliveries despite later adaptive imports."""
    with AUD.open(encoding="utf-8") as stream:
        allowed = {row["package_id"] for row in csv.DictReader(stream)}
    original_glob = Path.glob

    def scoped_glob(path, pattern):
        found = original_glob(path, pattern)
        if path == IMP and pattern == "*/*/receipt.json":
            return (item for item in found if item.parent.parent.name in allowed)
        return found

    with patch.object(Path, "glob", scoped_glob):
        yield


class Imported256DatasetTests(unittest.TestCase):
    def test_catalogue_alignment_and_split(self):
        catalogue = mod.read(CAT)["scenarios"]
        with (OUT / "scenarios.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        with (OUT / "targets_keff.csv").open(encoding="utf-8") as stream:
            targets = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 256)
        self.assertEqual([x["scenario_id"] for x in rows], [x["scenario_id"] for x in catalogue])
        self.assertEqual([x["scenario_id"] for x in targets], [x["scenario_id"] for x in catalogue])
        self.assertEqual(len({x["scenario_id"] for x in rows}), 256)
        for row, source in zip(rows, catalogue):
            for key in mod.CONTROLS:
                self.assertEqual(float(row[key]), source["controls"][key])
        splits = mod.read(OUT / "splits.json")
        self.assertEqual([len(splits[x]) for x in ("train", "calibration", "test")], [208, 25, 23])
        self.assertEqual(len(set(splits["train"]) & set(splits["test"])), 0)
        self.assertEqual(len(set(splits["train"]) & set(splits["calibration"])), 0)
        self.assertEqual(len(set(splits["calibration"]) & set(splits["test"])), 0)

    def test_shapes_normalization_and_output_hashes(self):
        manifest = mod.read(OUT / "dataset_manifest.json")
        self.assertEqual(manifest["training_eligible_count"], 0)
        for filename, digest in manifest["output_sha256"].items():
            self.assertEqual(mod.sha(OUT / filename), digest)
        with np.load(OUT / "fields.npz", allow_pickle=False) as data:
            raw, target = data["kappa_fission_mean"], data["target_normalized_kappa"]
            fuel = data["fuel_volume_fraction"] > 0
            self.assertEqual(raw.shape, (256, 20, 17, 17))
            self.assertEqual(target.shape, raw.shape)
            self.assertTrue(np.allclose(target.sum(axis=(1, 2, 3)), 1, atol=1e-10, rtol=0))
            self.assertTrue(np.all(target[~fuel] == 0))
            sums = np.where(fuel, raw, 0).sum(axis=(1, 2, 3))
            self.assertTrue(np.allclose(target, raw * fuel / sums[:, None, None, None], atol=1e-12))
            for name in ("flux_mean", "flux_std_dev", "fission_mean", "fission_std_dev",
                         "kappa_fission_std_dev"):
                self.assertEqual(data[name].shape, raw.shape)

    def test_source_tampering_rejected(self):
        actual = mod.sha
        def bad_sha(path):
            if str(path).endswith("fields.npz"):
                return "0" * 64
            return actual(path)
        with frozen_256_import_view(), patch.object(mod, "sha", side_effect=bad_sha):
            with self.assertRaisesRegex(ValueError, "Source checksum mismatch"):
                mod.collect(CAT, IMP, AUD)

    def test_repeat_build_deterministic(self):
        with frozen_256_import_view(), tempfile.TemporaryDirectory() as temp:
            result = mod.build(CAT, IMP, AUD, Path(temp) / "dataset")
            self.assertEqual(result["scenarios"], 256)
            for filename in ("scenarios.csv", "targets_keff.csv", "quality_report.csv",
                             "fields.npz", "splits.json"):
                self.assertEqual(mod.sha(OUT / filename), mod.sha(Path(result["output"]) / filename))


if __name__ == "__main__":
    unittest.main()



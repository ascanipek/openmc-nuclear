"""Read-only identity and mocked launch checks for local Halton packages."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reactor_pipeline import notebook_content, v2_students, v2_student_runner

ROOT = v2_students.PROJECT
STAGES = tuple(f"halton_{i:02d}" for i in range(1, 5))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(stage):
    return ROOT / "student_packages/v2_halton128_v1" / stage / f"v2_{stage}_beavrs_v2_pilot_scope_v1"


class LocalHaltonPackages(unittest.TestCase):
    def test_frozen_physical_manifest_and_notebooks_with_local_approval(self):
        assignment = read(ROOT / "configs/v2_halton128_assignment_v1.json")
        self.assertEqual(len(assignment["packages"]), 4)
        self.assertEqual(len(assignment["scenarios"]), 128)
        for stage in STAGES:
            local = package(stage)
            frozen = ROOT / "kaggle/v2_128/project" / local.relative_to(ROOT)
            self.assertEqual((local / "manifest.json").read_bytes(),
                             (frozen / "manifest.json").read_bytes())
            for name in ("01_calistir.ipynb", "02_sonuclari_incele.ipynb"):
                self.assertEqual(notebook_content.content_digest(local / name),
                                 notebook_content.content_digest(frozen / name))
            info = v2_students.verify_package(local, require_approval=True)
            self.assertEqual(info["stage"], stage)
            self.assertEqual(read(local / "approval.json")["authorization"],
                             "local_v2_halton128_controlled_research_only")
            registry = assignment["packages"][info["package_id"]]
            manifest = read(local / "manifest.json")
            self.assertEqual(registry["package_sha256"], sha(local / "package.json"))
            self.assertEqual(registry["manifest_sha256"], sha(local / "manifest.json"))
            self.assertEqual(registry["scenario_ids"],
                             [case["scenario_id"] for case in manifest["experiments"]])

    def test_128_new_controls_indices_and_seeds_match_frozen_catalogue(self):
        old = read(ROOT / "scenarios/v2_students_portable_v1/catalogue_total_256.json")
        new = read(ROOT / "scenarios/v2_halton128_v1/catalogue_new_128.json")
        frozen = read(ROOT / "kaggle/v2_128/project/scenarios/v2_halton128_v1/catalogue_new_128.json")
        self.assertEqual(new, frozen)
        self.assertEqual(new["sampling_seed"], old["sampling_seed"])
        self.assertEqual(new["sampling_parameters"], old["sampling_parameters"])
        self.assertEqual([item["halton_index"] for item in new["scenarios"]], list(range(233, 361)))
        encode = lambda x: json.dumps(x["controls"], sort_keys=True)
        old_ids = {item["scenario_id"] for item in old["scenarios"]}
        old_controls = {encode(item) for item in old["scenarios"]}
        new_ids = {item["scenario_id"] for item in new["scenarios"]}
        new_controls = {encode(item) for item in new["scenarios"]}
        self.assertEqual(len(new_ids), 128)
        self.assertEqual(len(new_controls), 128)
        self.assertFalse(old_ids & new_ids)
        self.assertFalse(old_controls & new_controls)
        seeds = []
        reference = read(ROOT / "configs/v2_calculation_profile_256_students_80k_24h_research_v1.json")
        profile = read(ROOT / "configs/v2_calculation_profile_halton128_80k_24h_research_v1.json")
        self.assertEqual(profile["calculation"], reference["calculation"])
        for index, stage in enumerate(STAGES):
            catalogue = read(ROOT / "scenarios/v2_halton128_v1" / f"catalogue_{stage}.json")
            manifest = read(package(stage) / "manifest.json")
            self.assertEqual(catalogue["scenarios"], new["scenarios"][index * 32:(index + 1) * 32])
            self.assertEqual([(x["scenario_id"], x["controls"]) for x in manifest["experiments"]],
                             [(x["scenario_id"], x["controls"]) for x in catalogue["scenarios"]])
            self.assertEqual(manifest["group_runtime_budget_seconds"], 86400)
            for case in manifest["experiments"]:
                self.assertEqual({k: case["calculation"][k] for k in profile["calculation"]},
                                 profile["calculation"])
                seeds.append(case["calculation"]["seed"])
        self.assertEqual(seeds, list(range(72001, 72129)))

    def test_real_package_reaches_mocked_detached_launch_only(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(v2_student_runner, "GROUPS", Path(temp) / "groups"), \
                 patch.object(v2_student_runner, "preflight", return_value={"transport_started": False}), \
                 patch.object(v2_student_runner.subprocess, "Popen",
                              side_effect=RuntimeError("mock worker, no transport")) as spawn:
                with self.assertRaisesRegex(RuntimeError, "mock worker"):
                    v2_student_runner.launch(package("halton_01"))
                spawn.assert_called_once()
                status = read(Path(temp) / "groups/v2_halton_01_beavrs_v2_pilot_scope_v1/status.json")
                self.assertEqual(status["state"], "failed")

    def test_existing_lightweight_transfer_accepts_local_registry(self):
        import shutil
        from reactor_pipeline import v2_transfer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(v2_transfer, "GROUPS", root / "groups"):
                for stage in STAGES:
                    p = package(stage)
                    group = root / "groups" / p.name
                    group.mkdir(parents=True)
                    shutil.copy2(p / "manifest.json", group / "manifest.json")
                    (group / "status.json").write_text(json.dumps({
                        "state": "stopped", "group_id": p.name,
                        "completed_experiments": [], "physical_acceptance": "not_assessed"}))
                    delivery = root / f"{stage}.zip"
                    v2_transfer.export_package(p, delivery)
                    result = v2_transfer.import_zip(
                        delivery, output_root=root / "imports",
                        assignment_path=ROOT / "configs/v2_halton128_assignment_v1.json")
                    self.assertEqual(result["state"], "imported")
                    self.assertEqual(len(result["receipt"]["scenario_ids"]), 32)
                    self.assertEqual(result["receipt"]["completed_experiments"], [])

"""Startless integrity checks for the isolated 128-case Kaggle continuation."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE / "project"
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(PROJECT / "src")]
import kaggle_runner as kr
from reactor_pipeline import v2_students, v2_transfer, v2_student_runner

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Halton128Tests(unittest.TestCase):
    def test_128_continue_exactly_after_232_without_overlap(self):
        prior = read(REPO / "scenarios/v2_students_portable_v1/catalogue_total_256.json")
        new = read(PROJECT / "scenarios/v2_halton128_v1/catalogue_new_128.json")
        space = read(PROJECT / "configs/v2_parameter_space_pilot_scope_v1.json")
        self.assertEqual(sha(REPO / "scenarios/v2_students_portable_v1/catalogue_total_256.json"),
                         new["previous_catalogue_sha256"])
        self.assertEqual(new["sampling_parameters"], prior["sampling_parameters"])
        self.assertEqual(new["sampling_seed"], prior["sampling_seed"])
        self.assertEqual(prior["scenarios"][-1]["sampling_stratum"], "multiparameter_halton_232")
        self.assertEqual([x["halton_index"] for x in new["scenarios"]], list(range(233, 361)))
        old_ids = {x["scenario_id"] for x in prior["scenarios"]}
        old_controls = {json.dumps(x["controls"], sort_keys=True) for x in prior["scenarios"]}
        new_ids = {x["scenario_id"] for x in new["scenarios"]}
        new_controls = {json.dumps(x["controls"], sort_keys=True) for x in new["scenarios"]}
        self.assertEqual(len(new_ids), 128)
        self.assertEqual(len(new_controls), 128)
        self.assertFalse(old_ids & new_ids)
        self.assertFalse(old_controls & new_controls)
        for x in new["scenarios"]:
            self.assertEqual(x["scenario_id"],
                             v2_students.scenario_id(x["controls"], new["reference_config_sha256"]))
            for key, bound in space["ranges"].items():
                self.assertLessEqual(bound["lower"], x["controls"][key])
                self.assertLessEqual(x["controls"][key], bound["upper"])

    def test_halton_formula_matches_original_endpoint_and_new_points(self):
        from reactor_pipeline import v2_pilot
        old = read(REPO / "scenarios/v2_students_portable_v1/catalogue_total_256.json")
        new = read(PROJECT / "scenarios/v2_halton128_v1/catalogue_new_128.json")
        space = read(PROJECT / "configs/v2_parameter_space_pilot_scope_v1.json")
        sampling = old["sampling_parameters"]
        rng = random.Random(old["sampling_seed"])
        self.assertEqual([rng.random() for _ in range(8)], sampling["halton_shifts"])
        for index in (1, 232, 233, 360):
            controls = {}
            for dim, key in enumerate(sampling["control_order"]):
                bounds = space["ranges"][key]
                unit = (v2_pilot._radical_inverse(index, sampling["halton_bases"][dim])
                        + sampling["halton_shifts"][dim]) % 1.0
                controls[key] = bounds["lower"] + (bounds["upper"] - bounds["lower"]) * unit
            saved = old["scenarios"][23 + index] if index <= 232 else new["scenarios"][index - 233]
            self.assertEqual(saved["controls"], controls)

    def test_extracted_packages_verify_in_fresh_python_process(self):
        with zipfile.ZipFile(HERE / "v2_128_kod_dataset.zip") as archive, \
             tempfile.TemporaryDirectory() as tmp:
            archive.extractall(tmp)
            code = ("from reactor_pipeline import v2_students; from pathlib import Path; "
                    "p=Path('.').resolve(); "
                    "[v2_students.verify_package(p/'student_packages/v2_halton128_v1'/s/"
                    "('v2_'+s+'_beavrs_v2_pilot_scope_v1'),require_approval=True) "
                    "for s in ('halton_01','halton_02','halton_03','halton_04')]")
            project = Path(tmp) / "project"
            env = dict(os.environ, PYTHONPATH=str(project / "src"))
            result = subprocess.run([sys.executable, "-c", code], cwd=project,
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
    def test_four_pinned_packages_and_nonoverlapping_mc_seeds(self):
        assignment = read(PROJECT / "configs/v2_student_assignment_v1.json")
        profile = read(PROJECT / "configs/v2_calculation_profile_halton128_80k_24h_research_v1.json")
        self.assertEqual(profile["calculation"],
                         {"particles_per_generation": 80000, "batches": 600,
                          "inactive": 300, "generations_per_batch": 1, "threads": 6})
        self.assertEqual(profile["group_runtime_budget_seconds"], 86400)
        seen_ids, seeds = set(), set()
        for group, stage in enumerate(kr.STAGES):
            package = kr._package(PROJECT, stage)
            info = v2_students.verify_package(package, require_approval=True)
            manifest = read(package / "manifest.json")
            catalogue = read(PROJECT / "scenarios/v2_halton128_v1" / f"catalogue_{stage}.json")
            self.assertEqual(info["owner"], kr.OWNER)
            self.assertEqual(info["stage"], stage)
            self.assertEqual(len(manifest["experiments"]), 32)
            self.assertEqual(manifest["group_runtime_budget_seconds"], 86400)
            self.assertEqual([x["scenario_id"] for x in manifest["experiments"]],
                             [x["scenario_id"] for x in catalogue["scenarios"]])
            self.assertEqual([x["controls"] for x in manifest["experiments"]],
                             [x["controls"] for x in catalogue["scenarios"]])
            self.assertEqual([x["halton_index"] for x in catalogue["scenarios"]],
                             list(range(233 + 32*group, 265 + 32*group)))
            assigned = assignment["packages"][info["package_id"]]
            self.assertEqual(assigned["scenario_ids"],
                             [x["scenario_id"] for x in manifest["experiments"]])
            self.assertEqual(assigned["package_sha256"], sha(package / "package.json"))
            for case in manifest["experiments"]:
                self.assertNotIn(case["scenario_id"], seen_ids)
                self.assertNotIn(case["calculation"]["seed"], seeds)
                seen_ids.add(case["scenario_id"])
                seeds.add(case["calculation"]["seed"])
                self.assertEqual({k: case["calculation"][k] for k in profile["calculation"]},
                                 profile["calculation"])
        self.assertEqual(seeds, set(range(72001, 72129)))
        self.assertTrue(seeds.isdisjoint(set(range(71001, 71033))))
        self.assertEqual(len(seen_ids), 128)

    def test_reviewed_physics_code_matches_existing_kaggle_bundle(self):
        source = REPO / "kaggle/ogrenci_04"
        for relative, expected in read(source / "bundle_hashes.json")["files"].items():
            if relative.startswith("project/src/") or relative.startswith("project/scripts/"):
                self.assertEqual(sha(PROJECT / relative.removeprefix("project/")), expected)

    def test_custom_assignment_works_with_existing_central_status_table(self):
        assignment_path = PROJECT / "configs/v2_student_assignment_v1.json"
        assignment = read(assignment_path)
        self.assertEqual(len(assignment["scenarios"]), 128)
        with tempfile.TemporaryDirectory() as tmp:
            rows = v2_transfer.status_table(assignment_path=assignment_path,
                                            output_root=Path(tmp))
        self.assertEqual(len(rows), 128)
        self.assertEqual({row["state"] for row in rows}, {"missing"})
        self.assertEqual({row["stage"] for row in rows}, set(kr.STAGES))
    def test_single_notebook_selects_only_one_stage_and_parses(self):
        notebook = read(HERE / "01_kaggle_calistir.ipynb")
        codes = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
        self.assertEqual(len(codes), 4)
        for code in codes:
            ast.parse(code)
        self.assertIn('SELECTED_STAGE = "halton_01"', codes[0])
        self.assertIn("SESSION_BUDGET_SECONDS", codes[0])
        self.assertIn("kr.verify_bundle(code_root)", codes[1])
        self.assertIn("runner.preflight(package)", codes[2])
        self.assertNotIn("kr.run_stage", codes[2])
        self.assertIn("kr.run_stage(context, session_budget, session_started)", codes[3])
        self.assertEqual(codes[3].count("kr.run_stage("), 1)
        self.assertNotIn("wsl.exe", "".join(codes))

    def test_code_zip_matches_ledger_and_extracts(self):
        self.assertGreater(kr.verify_bundle(HERE), 50)
        ledger = read(HERE / "bundle_hashes.json")
        with zipfile.ZipFile(HERE / "v2_128_kod_dataset.zip") as archive:
            self.assertEqual(set(archive.namelist()), set(ledger["files"]) | {"bundle_hashes.json"})
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                self.assertEqual(kr.verify_bundle(tmp), len(ledger["files"]))

    def test_existing_transfer_contract_imports_all_four_without_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            assignment = PROJECT / "configs/v2_student_assignment_v1.json"
            with mock.patch.object(v2_transfer, "GROUPS", tmp / "groups"), \
                 mock.patch("openmc.Model.run", side_effect=AssertionError("transport forbidden")):
                for stage in kr.STAGES:
                    package = kr._package(PROJECT, stage)
                    manifest = read(package / "manifest.json")
                    group = tmp / "groups" / manifest["group_id"]
                    group.mkdir(parents=True)
                    shutil.copy2(package / "manifest.json", group / "manifest.json")
                    (group / "status.json").write_text(json.dumps({
                        "state": "stopped", "group_id": manifest["group_id"],
                        "completed_experiments": [], "physical_acceptance": "not_assessed"}))
                    delivery = tmp / f"{stage}.zip"
                    v2_transfer.export_package(package, delivery)
                    receipt = v2_transfer.import_zip(
                        delivery, output_root=tmp / "imports", assignment_path=assignment)
                    self.assertEqual(receipt["state"], "imported")
                    self.assertEqual(receipt["receipt"]["scenario_ids"],
                                     sorted(x["scenario_id"] for x in manifest["experiments"]))
                    self.assertEqual(receipt["receipt"]["completed_experiments"], [])
if __name__ == "__main__":
    unittest.main()




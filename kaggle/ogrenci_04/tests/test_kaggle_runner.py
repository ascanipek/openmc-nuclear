"""Startless checks for the separate Kaggle CPU handoff."""
from __future__ import annotations

from pathlib import Path
import ast
import sys
import tempfile
import time
import unittest
from unittest import mock
import json
import zipfile

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE / "project"
LOCAL_PROJECT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT / "src"))
import kaggle_runner as kr


class KaggleAdapterTests(unittest.TestCase):
    def test_final_upload_ledger(self):
        self.assertGreater(kr.verify_bundle(HERE), 50)

    def test_notebook_cells_parse_without_execution(self):
        notebook = kr._json(HERE / "01_kaggle_calistir.ipynb")
        codes = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
        for code in codes:
            ast.parse(code)
        self.assertEqual(len(codes), 4)
        self.assertIn("SESSION_BUDGET_SECONDS", codes[0])
        self.assertIn("SELECTED_STAGE = \"stage_32\"", codes[0])
        self.assertIn("micromamba-linux-64", codes[1])
        self.assertIn("micromamba_sha256", codes[1])
        self.assertIn("kr.verify_bundle(code_root)", codes[1])
        self.assertIn("runner.preflight(package)", codes[2])
        self.assertIn('case["controls"]', codes[2])
        self.assertNotIn("kr.run_stage", codes[2])
        self.assertIn("kr.prepare(data_root, code_root, stage)", codes[3])
        self.assertIn("kr.run_stage(context, session_budget, session_started)", codes[3])
        for code in codes[2:]:
            tree = ast.parse(code)
            embedded = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
            self.assertEqual(len(embedded), 1)
            ast.parse(embedded[0])

    def test_notebook_openmc_bridge_uses_pinned_child_python_without_launch(self):
        notebook = kr._json(HERE / "01_kaggle_calistir.ipynb")
        install = "".join(next(cell["source"] for cell in notebook["cells"] if cell.get("id") == "install"))
        definition = next(node for node in ast.parse(install).body
                          if isinstance(node, ast.FunctionDef) and node.name == "openmc_process")
        bridge = ast.Module(body=[definition], type_ignores=[])
        process = mock.Mock()
        context = {"openmc_python": Path("/tmp/openmc_016/bin/python"),
                   "code_root": Path("/kaggle/input/code"),
                   "child_env": {"MAMBA_ROOT_PREFIX": "/tmp/kaggle_micromamba_root"},
                   "subprocess": process}
        exec(compile(bridge, "notebook-bridge", "exec"), context)
        context["openmc_process"]("print('preflight')", "stage_128")
        args, kwargs = process.run.call_args
        self.assertEqual(args[0][:4], ["/tmp/openmc_016/bin/python", "-u", "-c", "print('preflight')"])
        self.assertEqual(args[0][4], "stage_128")
        self.assertEqual(kwargs["env"]["PYTHONPATH"], "/kaggle/input/code")
        self.assertTrue(kwargs["check"])

    def test_upload_zip_contains_exact_reviewed_files(self):
        zip_path = HERE.parent / "ogrenci_04_kod_dataset.zip"
        if not zip_path.is_file():
            self.skipTest("Upload ZIP has not been built yet")
        ledger = kr._json(HERE / "bundle_hashes.json")
        with zipfile.ZipFile(zip_path) as archive:
            self.assertEqual(set(archive.namelist()), set(ledger["files"]) | {"bundle_hashes.json"})
            for relative, expected in ledger["files"].items():
                import hashlib
                self.assertEqual(hashlib.sha256(archive.read(relative)).hexdigest(), expected)
            with tempfile.TemporaryDirectory() as tmp:
                archive.extractall(tmp)
                self.assertEqual(kr.verify_bundle(tmp), len(ledger["files"]))

    def test_only_assigned_scenarios_and_approved_packages(self):
        from reactor_pipeline import v2_students
        assignment = kr._json(PROJECT / "configs/v2_student_assignment_v1.json")
        all_ids = []
        for stage, count in (("stage_32", 8), ("stage_128", 24), ("stage_256", 32)):
            package = kr._package(PROJECT, stage)
            info = v2_students.verify_package(package, require_approval=True)
            manifest = kr._json(package / "manifest.json")
            registry = assignment["packages"][info["package_id"]]
            self.assertEqual(info["owner"], "ogrenci_04")
            self.assertEqual(info["stage"], stage)
            self.assertEqual(len(manifest["experiments"]), count)
            self.assertEqual([case["scenario_id"] for case in manifest["experiments"]], registry["scenario_ids"])
            self.assertEqual(kr._sha(package / "package.json"), registry["package_sha256"])
            self.assertEqual(kr._sha(package / "manifest.json"), registry["manifest_sha256"])
            source_catalogue = LOCAL_PROJECT / assignment["source_catalogues"][stage.split("_")[1]]
            if source_catalogue.is_file():
                catalogue = {item["scenario_id"]: item["controls"] for item in kr._json(source_catalogue)["scenarios"]}
                for case in manifest["experiments"]:
                    self.assertEqual(case["controls"], catalogue[case["scenario_id"]])
                local_package = LOCAL_PROJECT / registry["package_path"]
                self.assertEqual((package / "manifest.json").read_bytes(),
                                 (local_package / "manifest.json").read_bytes())
            all_ids.extend(registry["scenario_ids"])
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(len(all_ids), 64)

    def test_code_bundle_detects_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "code.py").write_text("original")
            kr._write(root / "bundle_hashes.json", {"schema": "kaggle_code_bundle_sha256_v1",
                     "files": {"code.py": kr._sha(root / "code.py")}})
            self.assertEqual(kr.verify_bundle(root), 1)
            (root / "code.py").write_text("changed")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                kr.verify_bundle(root)

    def test_saved_working_notebook_outputs_do_not_change_source_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input"
            source.mkdir()
            original = json.loads((HERE / "01_kaggle_calistir.ipynb").read_text())
            (source / "01_kaggle_calistir.ipynb").write_text(json.dumps(original))
            kr._write(source / "bundle_hashes.json", {"schema": "kaggle_code_bundle_sha256_v1",
                     "files": {"01_kaggle_calistir.ipynb": kr._sha(source / "01_kaggle_calistir.ipynb")}})
            working = root / "working.ipynb"
            original["cells"][1]["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["done"]}]
            original["cells"][1]["execution_count"] = 1
            working.write_text(json.dumps(original))
            self.assertEqual(kr.verify_bundle(source), 1)
            self.assertNotEqual(kr._sha(working), kr._sha(source / "01_kaggle_calistir.ipynb"))

    def test_nuclear_index_remaps_only_xml_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, working = root / "input", root / "working"
            (data / "lib").mkdir(parents=True)
            working.mkdir()
            (data / "lib" / "U235.h5").write_bytes(b"stub")
            (data / "cross_sections.xml").write_text(
                '<cross_sections><library materials="U235" type="neutron" path="/old/U235.h5" /></cross_sections>')
            result = kr.cross_sections_index(data, working)
            self.assertEqual(result["library_count"], 1)
            self.assertEqual(result["remapped_paths"], 1)
            self.assertEqual((data / "lib" / "U235.h5").read_bytes(), b"stub")
            self.assertIn(str(data / "lib" / "U235.h5"), (working / "cross_sections_kaggle.xml").read_text())
            (data / "other").mkdir()
            (data / "other" / "U235.h5").write_bytes(b"stub2")
            with self.assertRaisesRegex(ValueError, "uniquely"):
                kr.cross_sections_index(data, working)

    def test_abandoned_attempt_is_marked_only_in_writable_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input"
            target = root / "working"
            attempt = source / "experiments/e1/attempt_a"
            attempt.mkdir(parents=True)
            (attempt / "openmc.log").write_text("partial log")
            import shutil
            shutil.copytree(source, target)
            kr._normalize_interrupted(target, {"experiments": [{"experiment_id": "e1", "scenario_id": "s1"}]})
            self.assertFalse((attempt / "status.json").exists())
            self.assertEqual(kr._json(target / "experiments/e1/attempt_a/status.json")["state"], "stopped")
            self.assertEqual((target / "experiments/e1/attempt_a/openmc.log").read_text(), "partial log")

    def test_all_cases_can_run_when_budget_allows_and_completed_are_not_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp) / "working/v2_groups/group"
            group.mkdir(parents=True)
            cases = [{"experiment_id": f"e{i}", "scenario_id": f"s{i}",
                      "calculation": {"threads": 6, "batches": 600,
                                      "particles_per_generation": 80000, "generations_per_batch": 1}}
                     for i in range(3)]
            manifest = {"group_id": "group", "experiments": cases, "group_runtime_budget_seconds": 999999}
            kr._write(group / "status.json", {"state": "stopped", "completed_experiments": [],
                      "budget_consumed_seconds": 0.0})
            class Runner:
                def _comparison(self, *_):
                    pass
            class Transfer:
                def export_package(self, _, zip_path):
                    zip_path.write_bytes(b"mock delivery")
            context = {"group": group, "manifest": manifest, "package": Path(tmp) / "package",
                       "runner": Runner(), "transfer": Transfer(), "dataset": object(),
                       "runtime": {"resources": {"selected_threads": 6}, "observed_seconds_per_history": None}}
            completed = set()
            def execute(_context, case, _deadline, _kind):
                completed.add(case["experiment_id"])
            with mock.patch.object(kr, "_execute_case", side_effect=execute) as run, \
                 mock.patch.object(kr, "_validate_group", side_effect=lambda *_: set(completed)), \
                 mock.patch.object(kr, "runner_estimate", return_value=0):
                first = kr.run_stage(context, 999999)
                self.assertEqual(first["new_cases"], 3)
                self.assertEqual(first["pending"], 0)
                self.assertEqual(run.call_count, 3)
                self.assertGreater(context["runtime"]["observed_seconds_per_history"], 0)
                second = kr.run_stage(context, 999999)
                self.assertEqual(second["new_cases"], 0)
                self.assertEqual(run.call_count, 3)

    def test_budget_estimate_accounts_for_fewer_cpu_threads(self):
        class Runner:
            def _estimate_seconds(self, _):
                return 100
        context = {"runner": Runner(), "runtime": {"resources": {"selected_threads": 2},
                     "observed_seconds_per_history": None}}
        case = {"calculation": {"threads": 6, "batches": 10,
                               "particles_per_generation": 10, "generations_per_batch": 1}}
        self.assertEqual(kr.runner_estimate(context, case), 300)
        context["runtime"]["observed_seconds_per_history"] = 4
        self.assertEqual(kr.runner_estimate(context, case), 400)

    def test_session_budget_stops_before_next_case_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp) / "working/v2_groups/group"
            group.mkdir(parents=True)
            case = {"experiment_id": "e1", "scenario_id": "s1",
                    "calculation": {"threads": 6, "batches": 600,
                                    "particles_per_generation": 80000, "generations_per_batch": 1}}
            manifest = {"group_id": "group", "experiments": [case], "group_runtime_budget_seconds": 1000}
            kr._write(group / "status.json", {"state": "stopped", "completed_experiments": [],
                      "budget_consumed_seconds": 0.0})
            class Runner:
                def _comparison(self, *_):
                    pass
            class Transfer:
                def export_package(self, _, zip_path):
                    zip_path.write_bytes(b"mock delivery")
            context = {"group": group, "manifest": manifest, "package": Path(tmp) / "package",
                       "runner": Runner(), "transfer": Transfer(), "dataset": object(),
                       "runtime": {"resources": {"selected_threads": 6}, "observed_seconds_per_history": None}}
            with mock.patch.object(kr, "_validate_group", return_value=set()), \
                 mock.patch.object(kr, "runner_estimate", return_value=100), \
                 mock.patch.object(kr, "_execute_case") as run:
                result = kr.run_stage(context, 20)
            run.assert_not_called()
            self.assertEqual(result["state"], "stopped")
            self.assertEqual(result["new_cases"], 0)
            self.assertTrue(Path(result["delivery_zip"]).is_file())

    def test_first_observed_case_updates_next_case_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp) / "working/v2_groups/group"
            group.mkdir(parents=True)
            cases = [{"experiment_id": f"e{i}", "scenario_id": f"s{i}",
                      "calculation": {"threads": 6, "batches": n,
                                      "particles_per_generation": 1, "generations_per_batch": 1}}
                     for i, n in enumerate((1, 1000))]
            manifest = {"group_id": "group", "experiments": cases, "group_runtime_budget_seconds": 1000}
            kr._write(group / "status.json", {"state": "stopped", "completed_experiments": [],
                      "budget_consumed_seconds": 0.0})
            class Runner:
                def _comparison(self, *_):
                    pass
                def _estimate_seconds(self, _):
                    return 0
            class Transfer:
                def export_package(self, _, zip_path):
                    zip_path.write_bytes(b"mock")
            context = {"group": group, "manifest": manifest, "package": Path(tmp) / "package",
                       "runner": Runner(), "transfer": Transfer(), "dataset": object(),
                       "runtime": {"resources": {"selected_threads": 6}, "observed_seconds_per_history": None}}
            completed = set()
            def execute(_, case, _deadline, _kind):
                time.sleep(0.005)
                completed.add(case["experiment_id"])
            with mock.patch.object(kr, "_validate_group", side_effect=lambda *_: set(completed)), \
                 mock.patch.object(kr, "_execute_case", side_effect=execute) as run:
                result = kr.run_stage(context, 0.1)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(result["new_cases"], 1)
            self.assertEqual(result["state"], "stopped")
            self.assertGreater(result["observed_seconds_per_history"], 0)

    def test_budget_launcher_uses_pinned_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(kr.shutil, "which", return_value="/usr/bin/timeout"):
                launcher = kr._budget_launcher(Path(tmp), "/opt/conda/bin/openmc", 125)
            content = launcher.read_text()
            self.assertIn("125s /opt/conda/bin/openmc", content)
            self.assertIn("kaggle_budget_timeout.txt", content)
            self.assertTrue(launcher.stat().st_mode & 0o111)

    def test_central_lightweight_zip_contract(self):
        from reactor_pipeline import v2_transfer
        package = kr._package(PROJECT, "stage_32")
        manifest = kr._json(package / "manifest.json")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = root / "v2_groups" / manifest["group_id"]
            group.mkdir(parents=True)
            (group / "manifest.json").write_bytes((package / "manifest.json").read_bytes())
            kr._write(group / "status.json", {"state": "stopped", "group_id": manifest["group_id"],
                      "completed_experiments": []})
            with mock.patch.object(v2_transfer, "GROUPS", root / "v2_groups"):
                delivered = v2_transfer.export_package(package, root / "delivery.zip")
                receipt = v2_transfer.import_zip(root / "delivery.zip", output_root=root / "imported",
                          assignment_path=PROJECT / "configs/v2_student_assignment_v1.json")
            self.assertEqual(delivered["cases_completed"], 0)
            self.assertEqual(receipt["state"], "imported")
            self.assertEqual(receipt["receipt"]["owner"], "ogrenci_04")


if __name__ == "__main__":
    unittest.main()

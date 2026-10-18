import json
import io
import shutil
from contextlib import redirect_stdout
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from reactor_pipeline import experiments as exp
from reactor_pipeline.beavrs3d import build_model, extract_3d, validate_3d_outputs


class ExperimentWorkflowTests(unittest.TestCase):
    def test_prepared_manifests_preflight_without_transport(self):
        with patch.object(exp, "_spawn", side_effect=AssertionError("transport spawned")):
            for name in ("beavrs3d_d2_budget_v1.json", "beavrs3d_d3_seeds_v1.json",
                         "beavrs3d_d4_positions_v1.json"):
                with self.subTest(name=name):
                    info = exp.preflight(exp.MANIFESTS / name)
                    self.assertFalse(info["transport_started"])
                    self.assertEqual(len(info["experiments"]), 3)
                    self.assertTrue(all(row["active_histories"] > 0 for row in info["experiments"]))

    def test_d2_fixed_budget_and_history_counts(self):
        info = exp.preflight(exp.MANIFESTS / "beavrs3d_d2_budget_v1.json")
        self.assertEqual(info["group_runtime_budget_seconds"], 14400)
        self.assertFalse(info["estimate_is_guarantee"])
        self.assertLess(info["initial_group_estimated_seconds"], 14400)
        for row, particles, seed in zip(info["experiments"], (20000, 80000, 320000),
                                        (31001, 41001, 51001)):
            self.assertEqual(row["insertion_percent"], 50)
            self.assertEqual((row["batches"], row["inactive"], row["active_batches"]),
                             (600, 300, 300))
            self.assertEqual((row["generations_per_batch"], row["threads"], row["seed"]),
                             (1, 6, seed))
            self.assertEqual(row["particles_per_generation"], particles)
            self.assertEqual(row["total_histories"], 600 * particles)
            self.assertEqual(row["active_histories"], 300 * particles)

    def test_budget_deadline_signals_worker_process_group(self):
        exp.BUDGET_EXPIRED = False
        exp.STOP_FLAG = False
        with patch.object(exp.os, "killpg") as kill:
            exp._expire_budget()
            kill.assert_called_once_with(exp.os.getpid(), exp.signal.SIGTERM)
        self.assertTrue(exp.BUDGET_EXPIRED)
        self.assertTrue(exp.STOP_FLAG)
        exp.BUDGET_EXPIRED = False
        exp.STOP_FLAG = False
    def test_budget_gate_refuses_new_case_without_transport(self):
        manifest = exp.MANIFESTS / "beavrs3d_d2_budget_v1.json"
        with tempfile.TemporaryDirectory() as temp, patch.object(exp, "GROUPS", Path(temp)):
            with patch.object(exp, "_spawn", return_value={"pid": 12345}):
                exp.launch(manifest)
            folder = Path(temp) / "beavrs3d_d2_budget_v1"
            with patch.object(exp.threading, "Timer") as timer, \
                 patch.object(exp, "_estimate_case_seconds", return_value=20000), \
                 patch.object(exp, "run_case", side_effect=AssertionError("transport started")):
                exp.worker(folder)
                timer.assert_called_once()
                timer.return_value.start.assert_called_once()
                timer.return_value.cancel.assert_called_once()
            status = json.loads((folder / "status.json").read_text())
            self.assertEqual(status["state"], "budget_exhausted")
            self.assertEqual(status["budget_reason"], "estimated_next_case_exceeds_remaining")
            self.assertEqual(status["next_experiment"], "D2-B1")
            with patch.object(exp, "process_alive", return_value=False):
                with self.assertRaises(RuntimeError):
                    exp.resume("beavrs3d_d2_budget_v1")
    def test_launch_is_detached_and_duplicate_group_is_rejected(self):
        manifest = exp.MANIFESTS / "beavrs3d_d2_budget_v1.json"
        with tempfile.TemporaryDirectory() as temp, patch.object(exp, "GROUPS", Path(temp)):
            with patch.object(exp, "_spawn", return_value={"pid": 12345}) as spawn:
                result = exp.launch(manifest)
                self.assertEqual(result["pid"], 12345)
                spawn.assert_called_once()
                folder = Path(temp) / "beavrs3d_d2_budget_v1"
                self.assertEqual((folder / "manifest.json").read_bytes(), manifest.read_bytes())
                self.assertEqual(json.loads((folder / "status.json").read_text())["state"], "queued")
                self.assertTrue((folder / "comparison.csv").is_file())
                self.assertTrue((folder / "comparison.html").is_file())
                with self.assertRaises(FileExistsError):
                    exp.launch(manifest)
                self.assertEqual(spawn.call_count, 1)

    def test_resume_preserves_group_and_requires_idle_worker(self):
        manifest = exp.MANIFESTS / "beavrs3d_d2_budget_v1.json"
        with tempfile.TemporaryDirectory() as temp, patch.object(exp, "GROUPS", Path(temp)):
            with patch.object(exp, "_spawn", return_value={"pid": 12345}):
                exp.launch(manifest)
            group_id = "beavrs3d_d2_budget_v1"
            with patch.object(exp, "process_alive", return_value=True):
                with self.assertRaises(RuntimeError):
                    exp.resume(group_id)
            status_file = Path(temp) / group_id / "status.json"
            status = json.loads(status_file.read_text())
            status["state"] = "failed"
            exp.write_json(status_file, status)
            with patch.object(exp, "process_alive", return_value=False), \
                 patch.object(exp, "_spawn", return_value={"pid": 12346}) as spawn:
                result = exp.resume(group_id)
                self.assertEqual(result["pid"], 12346)
                spawn.assert_called_once()
            self.assertEqual((Path(temp) / group_id / "manifest.json").read_bytes(), manifest.read_bytes())

    def test_dependency_requires_explicit_review_marker(self):
        manifest = exp.MANIFESTS / "beavrs3d_d3_seeds_v1.json"
        _, data, _ = exp.load_manifest(manifest)
        with tempfile.TemporaryDirectory() as temp, patch.object(exp, "GROUPS", Path(temp)):
            with self.assertRaises(FileNotFoundError):
                exp._check_dependencies(data)
            parent = Path(temp) / "beavrs3d_d2_budget_v1"
            parent.mkdir()
            source = exp.MANIFESTS / "beavrs3d_d2_budget_v1.json"
            (parent / "manifest.json").write_bytes(source.read_bytes())
            exp.write_json(parent / "status.json", {
                "state": "completed", "manifest_sha256": exp.sha_file(source)})
            with self.assertRaises(RuntimeError):
                exp._check_dependencies(data)
            exp.write_json(parent / "review.json", {"operator_acknowledged": False})
            with self.assertRaises(RuntimeError):
                exp._check_dependencies(data)
            exp.write_json(parent / "review.json", {"operator_acknowledged": True})
            exp._check_dependencies(data)

    def test_reporting_schema_from_saved_integration_statepoint(self):
        source = (exp.PROJECT / "runs/beavrs_3d/integration_50pct_20261017T103026Z_98e3515a"
                  / "statepoint.100.h5")
        if not source.is_file():
            self.skipTest("saved integration statepoint unavailable")
        cfg = exp.load_reference()
        assembly = build_model(cfg, 50)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            result = extract_3d(source, assembly, folder, 1.0, {}, purpose="schema_test_no_transport")
            validate_3d_outputs(folder)
            with np.load(folder / "beavrs_3d_arrays.npz", allow_pickle=False) as fields:
                self.assertEqual(fields["array_order"].tolist(), ["z", "y", "x"])
                self.assertEqual(fields["relative_error_reporting_mask"].shape, (20, 17, 17))
                for name in ("fission", "kappa_fission", "flux"):
                    self.assertEqual(fields[f"{name}_mean"].shape, (20, 17, 17))
                    self.assertEqual(fields[f"{name}_std_dev"].shape, (20, 17, 17))
            case = {"experiment_id": "SCHEMA-TEST", "insertion_percent": 50,
                    "calculation": {"batches": 100, "inactive": 50,
                                    "particles_per_generation": 10000, "generations_per_batch": 1,
                                    "threads": 6, "seed": 41001}}
            exp.write_json(folder / "resolved_config.json", {"reference_config": cfg})
            status = {"state": "completed", "run_id": "test-run", "scenario_id": "test-scenario",
                      "elapsed_seconds": 1.0, "statepoint": source.name, "error": None}
            summary = exp._summary_for(folder, case, result, status)
            self.assertEqual(summary["quality_message"], "inceleme gerekli")
            self.assertEqual(summary["physical_acceptance"], "not_assessed")
            exp.render_case_report(folder, status, summary)
            html = (folder / "report.html").read_text(encoding="utf-8")
            self.assertIn("Fiziksel koşul ve hesap bütçesi", html)
            self.assertIn("Tamamlanma fiziksel doğrulama değildir", html)
    def test_resume_skip_requires_matching_identity_and_complete_outputs(self):
        source = exp.PROJECT / "runs/beavrs_3d/integration_50pct_20261017T103026Z_98e3515a"
        if not (source / "statepoint.100.h5").is_file():
            self.skipTest("saved integration statepoint unavailable")
        with tempfile.TemporaryDirectory() as temp:
            attempt = Path(temp) / "experiments/TEST/attempt_1"
            attempt.mkdir(parents=True)
            for name in ("result.json", "beavrs_3d_arrays.npz", "statepoint.100.h5"):
                shutil.copy2(source / name, attempt / name)
            shutil.copy2(source / "beavrs_3d_arrays.npz", attempt / "fields.npz")
            exp.write_json(attempt / "status.json", {"state": "completed", "run_id": "current"})
            exp.write_json(attempt / "summary.json", {"run_id": "current"})
            exp.write_json(attempt / "resolved_config.json", {"run_id": "current"})
            (attempt / "openmc.log").write_text("saved output")
            (attempt / "report.html").write_text("saved report")
            self.assertEqual(exp._completed_attempt(Path(temp), "TEST", "current"), attempt)
            self.assertIsNone(exp._completed_attempt(Path(temp), "TEST", "changed"))
            (attempt / "report.html").write_text("")
            self.assertIsNone(exp._completed_attempt(Path(temp), "TEST", "current"))
    def test_general_notebook_is_read_only_directory(self):
        notebook = json.loads((exp.PROJECT / 'notebooks/01_deney_calistir.ipynb').read_text())
        sources = [''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code']
        joined = chr(10).join(sources)
        for forbidden in ('launch(', 'resume(', 'approve(', 'preflight(', '.run('):
            self.assertNotIn(forbidden, joined)
        with tempfile.TemporaryDirectory() as temp, patch.object(exp, 'launch', side_effect=AssertionError('started')):
            for source in sources:
                compile(source, '01_deney_calistir.ipynb', 'exec')

    def test_results_notebook_only_reads_saved_results(self):
        name = "02_sonuclari_incele.ipynb"
        notebook = json.loads((exp.PROJECT / "notebooks" / name).read_text(encoding="utf-8"))
        sources = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
        joined = "\n".join(sources)
        self.assertNotIn("launch(", joined)
        self.assertNotIn("resume(", joined)
        self.assertNotIn(".run(", joined)
        namespace = {}
        with patch.object(exp, "launch", side_effect=AssertionError("transport started")), \
             redirect_stdout(io.StringIO()):
            for source in sources:
                exec(compile(source, name, "exec"), namespace)

if __name__ == "__main__":
    unittest.main()









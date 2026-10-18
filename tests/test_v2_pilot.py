"""Pilot proposal checks use temporary folders and never start transport."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reactor_pipeline import v2_pilot, v2_scenarios, v2_runner


class PilotPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogues = v2_pilot.nested_catalogues()

    def test_nested_unique_ids_preserve_all_eight_existing_controls(self):
        old = v2_scenarios._read(v2_pilot.LEGACY_CATALOGUE)["scenarios"]
        a, b, c = (self.catalogues[n]["scenarios"] for n in (32, 128, 256))
        self.assertEqual([(x["scenario_id"], x["controls"]) for x in a[:8]],
                         [(x["scenario_id"], x["controls"]) for x in old])
        self.assertEqual(a, b[:32])
        self.assertEqual(b, c[:128])
        self.assertEqual(len({r["scenario_id"] for r in c}), 256)
        self.assertEqual(sum(r["sampling_stratum"].startswith("one_at_a_time") for r in a), 16)
        self.assertEqual(sum(r["sampling_stratum"].startswith("multiparameter") for r in a), 8)

    def test_stage_packages_are_disjoint_draft_and_output_save_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "stages"
            result = v2_pilot.prepare(output)
            self.assertEqual([result[x]["new"] for x in ("stage_32", "stage_128", "stage_256")],
                             [32, 96, 128])
            seen = set()
            for stage in ("stage_32", "stage_128", "stage_256"):
                folders = list((output / stage / "packages").iterdir())
                self.assertEqual(len(folders), 4)
                for folder in folders:
                    info = v2_scenarios.verify_package(folder, require_approval=False)
                    self.assertEqual(info["state"], "draft_unapproved")
                    cases = v2_scenarios._read(folder / "manifest.json")["experiments"]
                    ids = {case["scenario_id"] for case in cases}
                    self.assertFalse(seen & ids)
                    seen.update(ids)
                    with patch.object(v2_runner.subprocess, "Popen",
                                      side_effect=AssertionError("transport started")) as spawn:
                        with self.assertRaises((ValueError, FileNotFoundError)):
                            v2_runner.launch(folder)
                        spawn.assert_not_called()
            self.assertEqual(len(seen), 256)
            book = next((output / "stage_32" / "packages").iterdir()) / "01_calistir.ipynb"
            original = book.read_text()
            obj = json.loads(original)
            self.assertTrue(all(cell.get("id") for cell in obj["cells"]))
            obj["cells"][-1]["outputs"] = [{"output_type": "stream", "name": "stdout",
                                              "text": ["Saved output"]}]
            obj["cells"][-1]["execution_count"] = 1
            book.write_text(json.dumps(obj))
            v2_scenarios.verify_package(book.parent, require_approval=False)
            obj["cells"][-1]["source"].append("raise RuntimeError('changed launch')\n")
            book.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                v2_scenarios.verify_package(book.parent, require_approval=False)
            book.write_text(original)
            obj = json.loads(original)
            self.assertTrue(all(cell.get("id") for cell in obj["cells"]))
            obj["cells"][0]["source"].append("New instruction\n")
            book.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                v2_scenarios.verify_package(book.parent, require_approval=False)

            book.write_text(original)
            obj = json.loads(original)
            self.assertTrue(all(cell.get("id") for cell in obj["cells"]))
            obj["cells"][0], obj["cells"][1] = obj["cells"][1], obj["cells"][0]
            book.write_text(json.dumps(obj))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                v2_scenarios.verify_package(book.parent, require_approval=False)
            book.write_text(original)
            original_digest = v2_scenarios.digest
            def changed_config_hash(path):
                return "changed-config" if Path(path) == v2_pilot.SPACE else original_digest(path)
            with patch.object(v2_scenarios, "digest", side_effect=changed_config_hash):
                with self.assertRaisesRegex(ValueError, "config mismatch"):
                    v2_scenarios.verify_package(book.parent, require_approval=False)

    def test_pilot_package_saved_numeric_export_contract(self):
        import numpy as np
        from reactor_pipeline import parameter_space, v2_dataset
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared = root / "prepared"
            v2_pilot.prepare(prepared)
            package = next((prepared / "stage_32" / "packages").iterdir())
            case = v2_scenarios._read(package / "manifest.json")["experiments"][1]
            sid, calc = case["scenario_id"], case["calculation"]
            groups = root / "groups"
            group = groups / package.name
            attempt = group / "experiments" / case["experiment_id"] / "attempt_synthetic"
            attempt.mkdir(parents=True)
            (group / "manifest.json").write_text(json.dumps({
                "group_id": package.name, "model": parameter_space.MODEL_ID,
                "experiments": [case]}))
            cfg, _ = parameter_space.resolve_proposed(case["controls"])
            ref_sha = v2_scenarios.digest(v2_scenarios.PROJECT / "configs/beavrs_derived_3d_reference.json")
            rid = v2_scenarios.identity({"scenario_id": sid, "calculation": calc,
                "model": parameter_space.MODEL_ID, "reference_config_sha256": ref_sha,
                "package_ledger_sha256": "synthetic", "cross_sections_xml_sha256": "synthetic"})
            resolved = {"model": parameter_space.MODEL_ID, "scenario_id": sid, "run_id": rid,
                "controls": case["controls"], "calculation": calc, "resolved_config": cfg,
                "reference_config_sha256": ref_sha, "package_ledger_sha256": "synthetic",
                "nuclear_data": {"cross_sections_xml_sha256": "synthetic"}}
            summary = {"model": parameter_space.MODEL_ID, "scenario_id": sid, "run_id": rid,
                "completion_state": "completed", "array_order": ["z", "y", "x"],
                "mesh_shape_zyx": [20, 17, 17], "field_units": v2_dataset.UNITS,
                "k_effective": {"mean": 0.9, "mc_standard_error": 0.002, "unit": "dimensionless"}}
            for name, value in (("resolved_config.json", resolved), ("summary.json", summary),
                                ("status.json", {"state": "completed", "scenario_id": sid, "run_id": rid})):
                (attempt / name).write_text(json.dumps(value))
            shape = (20, 17, 17)
            zero = np.zeros(shape)
            fuel = zero.copy(); fuel[0, 0, 0] = 1; fuel[0, 0, 1] = 1
            mean = zero.copy(); mean[0, 0, 0] = 1; mean[0, 0, 1] = 3
            np.savez_compressed(attempt / "fields.npz",
                fission_mean=mean, fission_std_dev=zero,
                kappa_fission_mean=mean, kappa_fission_std_dev=zero,
                flux_mean=mean, flux_std_dev=zero,
                fuel_volume_fraction=fuel, aic_volume_fraction=zero,
                b4c_volume_fraction=zero, fission_expected_zero=(fuel == 0),
                kappa_fission_expected_zero=(fuel == 0),
                relative_error_reporting_mask=(fuel > 0),
                x_edges_cm=np.linspace(-cfg["geometry"]["assembly_pitch_cm"]/2, cfg["geometry"]["assembly_pitch_cm"]/2, 18),
                y_edges_cm=np.linspace(-cfg["geometry"]["assembly_pitch_cm"]/2, cfg["geometry"]["assembly_pitch_cm"]/2, 18),
                z_edges_cm=np.linspace(cfg["geometry"]["fuel_bottom_cm"], cfg["geometry"]["fuel_top_cm"], 21), k_generation=np.zeros(600),
                shannon_entropy=np.zeros(600), array_order=np.array(["z", "y", "x"]))
            with patch.object(v2_dataset, "GROUPS", groups):
                self.assertEqual(v2_dataset.export([package.name], root / "preview",
                                                   preview=True)["sample_count"], 1)
                self.assertEqual(v2_dataset.export([package.name], root / "accepted")["sample_count"], 0)
            index = json.loads((root / "preview/index.json").read_text())
            sample = index["samples"][0]
            self.assertEqual(sample["physical_controls"], case["controls"])
            self.assertEqual(sample["resolved_water_density_g_cm3"],
                             cfg["materials"]["water"]["density_g_cm3"])
            self.assertEqual(sample["selected_run_id"], rid)
            self.assertEqual(sample["derived_inputs"]["water_solution_density_g_cm3"],
                             cfg["materials"]["water"]["density_g_cm3"])
            with np.load(root / "preview/samples.npz") as data:
                target = data["sample_00000_target_normalized_kappa"]
                self.assertEqual(target.shape, shape)
                self.assertAlmostEqual(float(target.sum()), 1.0)
                self.assertAlmostEqual(float(target[0, 0, 1]), 0.75)
                self.assertTrue(np.array_equal(data["sample_00000_kappa_fission_mean"], mean))
            second = next(row for row in self.catalogues[32]["scenarios"]
                          if row["sampling_stratum"] == "one_at_a_time_pin_pitch_cm_lower")
            controls2, sid2 = second["controls"], second["scenario_id"]
            cfg2, _ = parameter_space.resolve_proposed(controls2)
            rid2 = v2_scenarios.identity({"scenario_id": sid2, "calculation": calc,
                "model": parameter_space.MODEL_ID, "reference_config_sha256": ref_sha,
                "package_ledger_sha256": "synthetic", "cross_sections_xml_sha256": "synthetic"})
            group2 = groups / "v2_pitch_second"
            attempt2 = group2 / "experiments" / "PITCH" / "attempt_synthetic"
            attempt2.mkdir(parents=True)
            (group2 / "manifest.json").write_text(json.dumps({
                "group_id": group2.name, "model": parameter_space.MODEL_ID,
                "experiments": [{"experiment_id": "PITCH", "scenario_id": sid2}]}))
            for name, value in (
                ("resolved_config.json", dict(resolved, scenario_id=sid2, run_id=rid2,
                                              controls=controls2, resolved_config=cfg2)),
                ("summary.json", dict(summary, scenario_id=sid2, run_id=rid2)),
                ("status.json", {"state": "completed", "scenario_id": sid2, "run_id": rid2}),
            ):
                (attempt2 / name).write_text(json.dumps(value))
            with np.load(attempt / "fields.npz", allow_pickle=False) as data:
                second_fields = {key: data[key].copy() for key in data.files}
            half2 = cfg2["geometry"]["assembly_pitch_cm"] / 2
            second_fields["x_edges_cm"] = np.linspace(-half2, half2, 18)
            second_fields["y_edges_cm"] = np.linspace(-half2, half2, 18)
            np.savez_compressed(attempt2 / "fields.npz", **second_fields)
            with patch.object(v2_dataset, "GROUPS", groups):
                result = v2_dataset.export([package.name, group2.name], root / "mixed_pitch",
                                           preview=True)
                self.assertEqual(result["sample_count"], 2)
                second_fields["x_edges_cm"] += 0.01
                np.savez_compressed(attempt2 / "fields.npz", **second_fields)
                with self.assertRaisesRegex(ValueError, "mesh coordinates"):
                    v2_dataset.export([package.name, group2.name], root / "bad_pitch",
                                      preview=True)
    def test_joint_bounds_resolve_and_data_temperature_covered(self):
        from reactor_pipeline.parameter_space import build_proposed
        from reactor_pipeline.beavrs3d import nuclear_data_precheck
        space = v2_scenarios.load_space(v2_pilot.SPACE)
        for fuel in (556.0, 576.0):
            for water in (556.0, 576.0):
                for pressure in (15.0, 16.0):
                    controls = dict(space["nominal"], fuel_temperature_K=fuel,
                                    moderator_temperature_K=water,
                                    coolant_pressure_MPa=pressure)
                    assembly = build_proposed(controls, check_nuclear_data=False)
                    check = nuclear_data_precheck(assembly.materials, assembly.config)
                    self.assertEqual(check["temperature_method"], "interpolation")


if __name__ == "__main__":
    unittest.main()








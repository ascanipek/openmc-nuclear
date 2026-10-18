"""V2 preparation tests; all launch paths use mocks and never run OpenMC transport."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import openmc

from reactor_pipeline import parameter_space as physics, v2_scenarios as scenarios
from reactor_pipeline import v2_runner as runner, v2_dataset as dataset


class V2ProductionPreparationTests(unittest.TestCase):
    def nominal(self):
        return scenarios.load_space()["nominal"]

    def test_all_eight_controls_change_actual_model_inputs(self):
        nominal = self.nominal()
        base = physics.build_proposed(nominal, check_nuclear_data=False)
        def changed(**values):
            return physics.build_proposed(dict(nominal, **values), check_nuclear_data=False)
        fuel = changed(u235_enrichment_wt_percent=2.4)
        self.assertNotEqual(base.materials["fuel"].get_nuclide_atom_densities()["U235"],
                            fuel.materials["fuel"].get_nuclide_atom_densities()["U235"])
        self.assertEqual(changed(fuel_temperature_K=600).materials["fuel"].temperature, 600)
        hot_water = changed(moderator_temperature_K=570)
        self.assertEqual(hot_water.materials["water"].temperature, 570)
        self.assertNotEqual(base.config["materials"]["water"]["density_g_cm3"],
                            hot_water.config["materials"]["water"]["density_g_cm3"])
        high_pressure = changed(coolant_pressure_MPa=16)
        self.assertEqual(high_pressure.config["coolant_pressure_MPa"], 16)
        self.assertNotEqual(base.config["materials"]["water"]["density_g_cm3"],
                            high_pressure.config["materials"]["water"]["density_g_cm3"])
        deborated = changed(elemental_boron_ppm=0)
        self.assertEqual(deborated.materials["water"].get_nuclide_atom_densities()["B10"], 0)
        self.assertNotEqual(base.config["geometry"]["assembly_pitch_cm"],
                            changed(pin_pitch_cm=1.27).config["geometry"]["assembly_pitch_cm"])
        self.assertNotEqual(base.config["geometry"]["pellet_radius_cm"],
                            changed(pellet_radius_cm=0.39).config["geometry"]["pellet_radius_cm"])
        self.assertLess(changed(insertion_percent=75).rod_tip, base.rod_tip)
        self.assertEqual(base.model.settings.source[0].constraints, {"fissionable": True})
        self.assertEqual(base.mesh.dimension, (17, 17, 20))

    def test_joint_physics_constraints_reject_invalid(self):
        nominal = self.nominal()
        for control, value in (("pellet_radius_cm", 0.41), ("pin_pitch_cm", 1.1),
                               ("insertion_percent", 101)):
            with self.subTest(control=control), self.assertRaises(ValueError):
                physics.resolve_proposed(dict(nominal, **{control: value}))
        with self.assertRaises((ValueError, UserWarning)):
            physics.resolve_proposed(dict(nominal, moderator_temperature_K=623.15,
                                          coolant_pressure_MPa=0.1))

    def test_deterministic_draft_catalogue_unique_packages_and_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = scenarios.generate(5, 20261018, root / "first.json")
            second = scenarios.generate(5, 20261018, root / "second.json")
            self.assertEqual(first, second)
            self.assertEqual(first["state"], "draft_unapproved")
            self.assertEqual(len({x["scenario_id"] for x in first["scenarios"]}), 5)
            packages = scenarios.allocate(root / "first.json", ["ali", "ayse"], root / "packages")
            all_ids = []
            for folder in packages.iterdir():
                info = scenarios.verify_package(folder, require_approval=False)
                self.assertEqual(info["state"], "draft_unapproved")
                with self.assertRaises((ValueError, FileNotFoundError)):
                    scenarios.verify_package(folder, require_approval=True)
                with patch.object(runner.subprocess, "Popen", side_effect=AssertionError("worker started")) as spawn:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        runner.launch(folder)
                    spawn.assert_not_called()
                manifest = scenarios._read(folder / "manifest.json")
                all_ids.extend(c["scenario_id"] for c in manifest["experiments"])
                self.assertEqual(len(list(folder.glob("*.ipynb"))), 2)
                book = scenarios._read(folder / "01_calistir.ipynb")
                self.assertEqual(book["metadata"]["kernelspec"]["name"], "openmc-proje")
                code = ["".join(c["source"]) for c in book["cells"] if c["cell_type"] == "code"]
                self.assertIn("v2_runner.launch", code[-1])
                self.assertNotIn("v2_runner.launch", "\n".join(code[:-1]))
                for cell in code:
                    compile(cell, "student notebook", "exec")
                previous = Path.cwd()
                try:
                    os.chdir(folder)
                    namespace = {}
                    with contextlib.redirect_stdout(io.StringIO()):
                        exec(code[0], namespace)
                    self.assertEqual(namespace["PACKAGE"], folder.resolve())
                finally:
                    os.chdir(previous)
                result = scenarios._read(folder / "02_sonuclari_incele.ipynb")
                self.assertNotIn("launch(", json.dumps(result))
            self.assertEqual(len(all_ids), len(set(all_ids)))
            self.assertEqual(set(all_ids), {x["scenario_id"] for x in first["scenarios"]})

    def test_invalid_candidates_are_rejected_with_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            space = scenarios.load_space()
            space["ranges"]["pin_pitch_cm"]["lower"] = 1.0
            space["ranges"]["pin_pitch_cm"]["upper"] = space["nominal"]["pin_pitch_cm"]
            path = root / "space.json"
            path.write_text(json.dumps(space))
            catalogue = scenarios.generate(4, 20261018, root / "catalogue.json", space_path=path)
            self.assertEqual(catalogue["generation_status"], "complete")
            self.assertTrue(catalogue["rejected"])
            self.assertTrue(any("overlap" in row["reason"] for row in catalogue["rejected"]))
    def test_manifest_mutation_and_mocked_detached_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenarios.generate(1, 1, root / "list.json")
            package = next(scenarios.allocate(root / "list.json", ["ali"], root / "packages").iterdir())
            with patch.object(runner, "GROUPS", root / "groups"), \
                 patch.object(runner, "verify_package", return_value={"state": "production_ready"}), \
                 patch.object(runner, "preflight", return_value={"transport_started": False}), \
                 patch.object(runner, "process_alive", return_value=True), \
                 patch.object(runner.subprocess, "Popen", return_value=Mock(pid=24680)) as spawn:
                # The draft has no approved runtime budget. Mocked approved manifest supplies one.
                original = runner._manifest
                def approved_manifest(_):
                    return dict(original(package), group_runtime_budget_seconds=3600)
                with patch.object(runner, "_manifest", side_effect=approved_manifest):
                    started = runner.launch(package)
                    self.assertEqual(started["pid"], 24680)
                    spawn.assert_called_once()
                    self.assertTrue(spawn.call_args.kwargs["start_new_session"])
                    with self.assertRaises(FileExistsError):
                        runner.launch(package)
                self.assertEqual(runner.status(package)["state"], "queued")
            manifest = package / "manifest.json"
            manifest.write_text(manifest.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                scenarios.verify_package(package, require_approval=False)

    def test_v2_export_groups_repeated_runs_and_requires_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group_id = "v2_synthetic"
            group = root / group_id
            case_dir = group / "experiments" / "V2-1"
            case_dir.mkdir(parents=True)
            controls = self.nominal()
            ref_sha = scenarios.digest(scenarios.PROJECT / "configs/beavrs_derived_3d_reference.json")
            sid = scenarios.scenario_id(controls, ref_sha)
            (group / "manifest.json").write_text(json.dumps({"group_id": group_id,
                "model": physics.MODEL_ID, "experiments": [{"experiment_id": "V2-1", "scenario_id": sid}]}))
            shape = (20, 17, 17)
            for i, particles in enumerate((1000, 2000)):
                attempt = case_dir / f"attempt_{i}"
                attempt.mkdir()
                calc = {"particles_per_generation": particles, "batches": 10, "inactive": 5,
                        "generations_per_batch": 1, "threads": 6, "seed": i+1}
                rid = scenarios.identity({"scenario_id": sid, "calculation": calc,
                    "model": physics.MODEL_ID, "reference_config_sha256": ref_sha,
                    "package_ledger_sha256": "synthetic", "cross_sections_xml_sha256": "synthetic_xml"})
                cfg, _ = physics.resolve_proposed(controls)
                resolved = {"model": physics.MODEL_ID, "scenario_id": sid, "run_id": rid,
                    "controls": controls, "calculation": calc, "resolved_config": cfg,
                    "reference_config_sha256": ref_sha, "package_ledger_sha256": "synthetic",
                    "nuclear_data": {"cross_sections_xml_sha256": "synthetic_xml"}}
                summary = {"model": physics.MODEL_ID, "scenario_id": sid, "run_id": rid,
                    "completion_state": "completed", "array_order": ["z", "y", "x"],
                    "mesh_shape_zyx": list(shape), "field_units": dataset.UNITS,
                    "k_effective": {"mean": 1.1, "mc_standard_error": 0.001, "unit": "dimensionless"}}
                (attempt / "resolved_config.json").write_text(json.dumps(resolved))
                (attempt / "summary.json").write_text(json.dumps(summary))
                (attempt / "status.json").write_text(json.dumps({"state": "completed", "scenario_id": sid, "run_id": rid}))
                zero = np.zeros(shape)
                fuel = zero.copy(); fuel[0, 0, 0] = 1
                field = zero.copy(); field[0, 0, 0] = i+1
                np.savez_compressed(attempt / "fields.npz", fission_mean=field, fission_std_dev=zero,
                    kappa_fission_mean=field, kappa_fission_std_dev=zero, flux_mean=field,
                    flux_std_dev=zero, fuel_volume_fraction=fuel, aic_volume_fraction=zero,
                    b4c_volume_fraction=zero, fission_expected_zero=(fuel == 0),
                    kappa_fission_expected_zero=(fuel == 0), relative_error_reporting_mask=(fuel > 0),
                    x_edges_cm=np.linspace(-cfg["geometry"]["assembly_pitch_cm"]/2, cfg["geometry"]["assembly_pitch_cm"]/2, 18),
                    y_edges_cm=np.linspace(-cfg["geometry"]["assembly_pitch_cm"]/2, cfg["geometry"]["assembly_pitch_cm"]/2, 18),
                    z_edges_cm=np.linspace(cfg["geometry"]["fuel_bottom_cm"], cfg["geometry"]["fuel_top_cm"], 21),
                    k_generation=np.zeros(10), shannon_entropy=np.zeros(10), array_order=np.array(["z", "y", "x"]))
            with patch.object(dataset, "GROUPS", root):
                preview = dataset.export([group_id], root / "preview", preview=True)
                self.assertEqual(preview["sample_count"], 1)
                index = json.loads((root / "preview/index.json").read_text())
                self.assertEqual(len(index["samples"][0]["all_source_runs"]), 2)
                self.assertEqual(index["samples"][0]["active_histories"], 10000)
                production = dataset.export([group_id], root / "production")
                self.assertEqual(production["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()


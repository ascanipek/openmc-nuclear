import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import openmc

from reactor_pipeline import dataset, parameter_space, student_package, fuel_states
from reactor_pipeline.beavrs3d import build_model, load_reference, leaf_material, volume_fractions


class ProposedControlsTests(unittest.TestCase):
    def setUp(self):
        self.ref = load_reference()
        self.c = {"u235_enrichment_wt_percent": 1.6, "fuel_temperature_K": 566.483,
                  "moderator_temperature_K": 566.483, "coolant_pressure_MPa": 15.5,
                  "elemental_boron_ppm": 975, "pin_pitch_cm": 1.25984,
                  "pellet_radius_cm": 0.39218, "insertion_percent": 50}

    def test_missing_or_invalid_controls_rejected(self):
        with self.assertRaises(ValueError):
            parameter_space.resolve_proposed({k: v for k, v in self.c.items() if k != "coolant_pressure_MPa"})
        for key, bad in (("pin_pitch_cm", 1.1), ("pellet_radius_cm", .401),
                         ("insertion_percent", 101), ("elemental_boron_ppm", -1),
                         ("moderator_temperature_K", 700), ("u235_enrichment_wt_percent", 8)):
            changed = dict(self.c, **{key: bad})
            with self.subTest(key=key), self.assertRaises(ValueError):
                parameter_space.resolve_proposed(changed)
        with self.assertRaises(Warning):
            parameter_space.resolve_proposed(dict(self.c, coolant_pressure_MPa=.1))

    def test_density_boron_and_enrichment_mass_balance(self):
        c = dict(self.c, u235_enrichment_wt_percent=2.4, elemental_boron_ppm=500)
        cfg, p = parameter_space.resolve_proposed(c)
        self.assertEqual(p, 50)
        self.assertEqual(cfg["model"], parameter_space.MODEL_ID)
        baseline, _ = parameter_space.resolve_proposed(self.c)
        self.assertEqual(baseline["materials"]["fuel"]["atom_density_atom_b_cm"],
                         self.ref["materials"]["fuel"]["atom_density_atom_b_cm"])
        higher_pressure, _ = parameter_space.resolve_proposed(dict(c, coolant_pressure_MPa=16.0))
        self.assertGreater(higher_pressure["materials"]["water"]["density_g_cm3"],
                           cfg["materials"]["water"]["density_g_cm3"])
        self.assertAlmostEqual(cfg["materials"]["water"]["density_g_cm3"],
                               openmc.data.water_density(566.483, 15.5)/(1-500e-6), places=10)
        fuel = cfg["materials"]["fuel"]["atom_density_atom_b_cm"]
        uranium_mass = sum(fuel[k]*openmc.data.atomic_mass(k) for k in ("U234", "U235", "U238"))
        self.assertAlmostEqual(100*fuel["U235"]*openmc.data.atomic_mass("U235")/uranium_mass, 2.4, places=10)
        self.assertAlmostEqual(sum(fuel[k] for k in ("O16", "O17", "O18"))/sum(fuel[k] for k in ("U234", "U235", "U238")), 2, places=10)
        water = cfg["materials"]["water"]["atom_density_atom_b_cm"]
        total_mass = sum(v*openmc.data.atomic_mass(k) for k, v in water.items())
        ppm = 1e6*sum(water[k]*openmc.data.atomic_mass(k) for k in ("B10", "B11"))/total_mass
        self.assertAlmostEqual(ppm, 500, places=7)
        original_b = self.ref["materials"]["water"]["atom_density_atom_b_cm"]
        self.assertAlmostEqual(water["B10"]/water["B11"], original_b["B10"]/original_b["B11"], places=10)
        self.assertNotEqual(cfg["materials"]["fuel"]["temperature_K"], cfg["materials"]["water"]["temperature_K"]+1)

    def test_geometry_and_temperature_links(self):
        c = dict(self.c, pin_pitch_cm=1.27, pellet_radius_cm=.39,
                 fuel_temperature_K=600, moderator_temperature_K=550)
        assembly = parameter_space.build_proposed(c, check_nuclear_data=False)
        self.assertAlmostEqual(assembly.pin_pitch, 1.27)
        self.assertAlmostEqual(assembly.rod_tip, (assembly.top+assembly.bottom)/2)
        self.assertEqual(assembly.materials["fuel"].temperature, 600)
        self.assertEqual(assembly.materials["water"].temperature, 550)
        self.assertEqual(assembly.materials["zircaloy"].temperature, 550)
        x, y, z = 1.27+.395, 0, (assembly.bottom+assembly.top)/2
        self.assertEqual(leaf_material(assembly.model, x, y, z), "helium")
        fractions = volume_fractions(assembly)
        self.assertTrue(np.any((fractions["aic"] > 0) & (fractions["aic"] < 1)))


class NewManifestTests(unittest.TestCase):
    def test_b1_matched_d3_d4(self):
        root = student_package.PROJECT/"manifests"
        b1 = json.loads((root/"beavrs3d_d2_budget_v1.json").read_text())["experiments"][0]
        d3 = json.loads((root/"beavrs3d_d3_b1_repeats_v1.json").read_text())
        d4 = json.loads((root/"beavrs3d_d4_b1_positions_v1.json").read_text())
        self.assertEqual(d3["depends_on"], ["beavrs3d_d2_budget_v1"])
        self.assertEqual(d4["depends_on"], [d3["group_id"]])
        self.assertEqual([x["calculation"]["seed"] for x in d3["experiments"]], [32001, 33001])
        self.assertEqual([x["insertion_percent"] for x in d3["experiments"]], [50, 50])
        self.assertEqual([x["insertion_percent"] for x in d4["experiments"]], [0, 100])
        for manifest in (d3, d4):
            self.assertEqual(manifest["model"], "beavrs_derived_3d_assembly_v1")
            self.assertEqual(manifest["group_runtime_budget_seconds"], 14400)
            for case in manifest["experiments"]:
                calculation = dict(case["calculation"])
                calculation.pop("seed")
                expected = dict(b1["calculation"])
                expected.pop("seed")
                self.assertEqual(calculation, expected)

class DatasetContractTests(unittest.TestCase):
    def test_normalization_and_asymmetric_axes(self):
        raw = np.zeros(dataset.SHAPE)
        fuel = np.zeros(dataset.SHAPE)
        raw[1, 2, 3], raw[4, 5, 6] = 2, 6
        fuel[1, 2, 3], fuel[4, 5, 6] = .25, 1
        target, mask = dataset.normalized_kappa(raw, fuel)
        self.assertAlmostEqual(target.sum(), 1)
        self.assertAlmostEqual(target[1, 2, 3], .25)
        self.assertAlmostEqual(target[4, 5, 6], .75)
        self.assertFalse(mask[3, 2, 1])
        with self.assertRaises(ValueError):
            dataset.normalized_kappa(raw.transpose(2, 1, 0), fuel)
        raw[0, 0, 0] = 2
        with self.assertRaises(ValueError):
            dataset.normalized_kappa(raw, fuel)

    def test_recorded_d2_is_one_preview_sample_and_no_accepted_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = dataset.build_dataset(["beavrs3d_d2_budget_v1"], root/"preview", preview=True)
            accepted = dataset.build_dataset(["beavrs3d_d2_budget_v1"], root/"accepted")
            self.assertEqual(preview["sample_count"], 1)
            self.assertEqual(accepted["sample_count"], 0)
            index = json.loads((root/"preview/index.json").read_text())
            self.assertEqual(len(index["samples"][0]["all_source_runs"]), 3)
            self.assertEqual(index["samples"][0]["quality"], "preview_not_accepted")
    def test_same_scenario_same_split(self):
        self.assertEqual(dataset.split_for("one"), dataset.split_for("one"))
        with self.assertRaises(ValueError):
            dataset.split_for("one", "changed")


class PackageTests(unittest.TestCase):
    def test_draft_hash_and_approval_gate(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(student_package, "PACKAGES", Path(tmp)):
            folder = student_package.create_draft(student_package.PROJECT/"manifests/beavrs3d_d2_budget_v1.json", "test_package")
            self.assertEqual(student_package.verify(folder, require_approval=False)["approval_status"], "draft_unapproved")
            with self.assertRaises(FileNotFoundError):
                student_package.verify(folder)
            copied = folder/"src/reactor_pipeline/beavrs3d.py"
            copied.write_text(copied.read_text()+"\n# altered\n")
            with self.assertRaises(ValueError):
                student_package.verify(folder, require_approval=False)

    def test_fuel_state_rejects_missing_or_incompatible_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"fuel_state.json"
            state = {key: None for key in fuel_states.REQUIRED}
            state.update(state_id="s1", model="m", source_chain_sha256="abc",
                         source_cross_sections_sha256="def", initial_u235_enrichment_wt_percent=1.6,
                         burnup_MWd_per_kgU=10, history_id="h1", power_history=[1],
                         temperature_history=[1], control_history=[1], fuel_volume_cm3=1,
                         nuclide_atom_density_atom_b_cm={"I135": 1, "Xe135": 1},
                         contains_I135_Xe135=True, validation_status="accepted")
            path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                fuel_states.load_fuel_state(path, enrichment=2.4, burnup_MWd_per_kgU=10, history_id="h1", model="m")
            with self.assertRaises(ValueError):
                fuel_states.load_fuel_state(path, enrichment=1.6, burnup_MWd_per_kgU=11,
                                            history_id="h1", model="m")
            state["contains_I135_Xe135"] = False
            path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                fuel_states.load_fuel_state(path, enrichment=1.6, burnup_MWd_per_kgU=10, history_id="h1", model="m")

    def test_d4_package_points_to_d4_fixed_manifest(self):
        folder = student_package.PACKAGES/"beavrs3d_d4_b1_positions_v1"
        info = json.loads((folder/'package.json').read_text())
        self.assertEqual(info["group_id"], "beavrs3d_d4_b1_positions_v1")
        nb = json.loads((folder/"notebooks/01_D4_calistir.ipynb").read_text())
        source = chr(10).join("".join(c["source"]) for c in nb["cells"])
        self.assertIn("beavrs3d_d4_b1_positions_v1", source)
        self.assertNotIn("beavrs3d_d3_b1_repeats_v1", source)
        directory = json.loads((folder/"notebooks/01_deney_calistir.ipynb").read_text())
        self.assertNotIn("launch(", chr(10).join("".join(c["source"]) for c in directory["cells"]))
    def test_general_notebook_is_syntactically_valid_and_read_only(self):
        nb = json.loads((student_package.PROJECT/'notebooks/01_deney_calistir.ipynb').read_text())
        source = chr(10).join(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code')
        compile(source, '<notebook>', 'exec')
        for forbidden in ('launch(', 'resume(', 'verify(', 'wsl.exe'):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()









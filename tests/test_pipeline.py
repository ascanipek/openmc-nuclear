import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import openmc.examples

from reactor_pipeline.config import Calculation, Physics, Scenario, load_scenarios, MODEL_ID, digest
from reactor_pipeline.geometry import fuel_mask, xy_bounds
from reactor_pipeline.materials import BORON, mass_fractions_for_ppm, set_boron, water_material
from reactor_pipeline.measurements import mesh_to_yx
from reactor_pipeline.results import validate_outputs
from reactor_pipeline.runner import completed_run

ROOT = Path(__file__).resolve().parents[1]

class ConfigTests(unittest.TestCase):
    def test_scenarios_and_identity(self):
        scenario = load_scenarios(ROOT / "configs/pilot_assembly.json")[0]
        self.assertEqual(len(load_scenarios(ROOT / "scenarios/pilot_boron_sweep.json")), 3)
        changed = Scenario(scenario.name, scenario.physics,
                           Calculation(150, 60, 20000, 999, 6))
        self.assertEqual(scenario.scenario_id, changed.scenario_id)
        self.assertNotEqual(digest(scenario.definition()), digest(changed.definition()))

    def test_strict_validation(self):
        data = json.loads((ROOT / "configs/pilot_assembly.json").read_text())
        for key, value in (("boron_ppm_mass", -1), ("water_density_g_cm3", 0),
                           ("temperature_K", 200)):
            bad = json.loads(json.dumps(data))
            bad["physics"][key] = value
            with self.assertRaises(ValueError):
                Scenario.parse(bad)
        bad = json.loads(json.dumps(data))
        bad["physics"]["burnup"] = 1
        with self.assertRaises(ValueError):
            Scenario.parse(bad)
        bad = json.loads(json.dumps(data))
        bad["calculation"]["inactive"] = bad["calculation"]["batches"]
        with self.assertRaises(ValueError):
            Scenario.parse(bad)
        bad = json.loads(json.dumps(data))
        bad["physics"]["model"] = "beavrs_validated"
        with self.assertRaises(ValueError):
            Scenario.parse(bad)
        bad = json.loads(json.dumps(data))
        bad["calculation"]["particles"] = True
        with self.assertRaises(ValueError):
            Scenario.parse(bad)

class PhysicsTests(unittest.TestCase):
    def test_boron_and_density(self):
        model = openmc.examples.pwr_assembly()
        water = water_material(model)
        before_density = float(water.get_mass_density())
        before = {n: float(water.get_mass_density(n) / before_density) for n in water.get_nuclides()}
        reference_boron = sum(before[n] for n in BORON)
        target = reference_boron * 1e6 * 0.8
        converted = mass_fractions_for_ppm(water, target)
        self.assertAlmostEqual(sum(converted.values()), 1.0, places=10)
        self.assertAlmostEqual(converted["B10"] / converted["B11"], before["B10"] / before["B11"], places=10)
        nonboron = [n for n in before if n not in BORON]
        self.assertAlmostEqual(converted[nonboron[0]] / converted[nonboron[1]],
                               before[nonboron[0]] / before[nonboron[1]], places=10)
        changed, actual = set_boron(model, target, before_density)
        self.assertAlmostEqual(changed.get_mass_density(), before_density, places=10)
        self.assertAlmostEqual(actual, target, places=5)

    def test_geometry_mask(self):
        model = openmc.examples.pwr_assembly()
        lower, upper = xy_bounds(model)
        mask = fuel_mask(model, lower, upper)
        self.assertEqual(mask.shape, (17, 17))
        self.assertEqual(int(mask.sum()), 264)

    def test_xy_orientation(self):
        n = 3
        indices = [(ix, iy) for ix in range(1, n + 1) for iy in range(1, n + 1)]
        values = [100 * ix + iy for ix, iy in indices]
        array = mesh_to_yx(values, indices, n)
        self.assertEqual(array[0, 2], 301)
        self.assertEqual(array[2, 0], 103)
        self.assertNotEqual(array[0, 2], array[2, 0])

class ResumeTests(unittest.TestCase):
    def fixture(self, folder, state="completed"):
        definition = {"scenario": {"physics": {"boron_ppm_mass": 1000}}, "seed": 5}
        run_id = digest(definition)
        run = folder / f"{run_id}_sample"
        run.mkdir()
        (run / "status.json").write_text(json.dumps({"state": state, "statepoint": "statepoint.h5", "run_id": run_id}))
        (run / "run_definition.json").write_text(json.dumps(definition))
        for name in ("model.xml", "openmc.log", "scenario.json", "model_summary.json", "statepoint.h5"):
            (run / name).write_bytes(b"ok")
        mask = np.zeros((17, 17), dtype=bool)
        mask.flat[:264] = True
        raw = np.ones((17, 17))
        relative = np.where(mask, 1.0, np.nan)
        np.savez_compressed(run / "fission_data.npz", raw_mean=raw,
                            raw_std_dev=np.zeros_like(raw), fuel_mask=mask,
                            relative_fission=relative,
                            lower_left_cm=np.array([-1., -1.]),
                            upper_right_cm=np.array([1., 1.]))
        (run / "result.json").write_text(json.dumps({"source_convergence": "not_assessed",
                                                       "fuel_positions": 264,
                                                       "k_mean": 1.1, "k_mc_standard_error": 0.01}))
        return run_id, definition, run

    def test_resume_only_completed_intact_matching(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id, definition, run = self.fixture(root)
            self.assertIsNone(completed_run(root, run_id, definition))  # corrupt statepoint
            class FakeStatePoint:
                keff = type("K", (), {"nominal_value": 1.1, "std_dev": 0.01})()
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def get_tally(self, name):
                    if name != "pin_fission":
                        raise KeyError(name)
            with patch("reactor_pipeline.runner.openmc.StatePoint", return_value=FakeStatePoint()):
                self.assertEqual(completed_run(root, run_id, definition), run)
                self.assertIsNone(completed_run(root, run_id, {"different": True}))
                (run / "fission_data.npz").unlink()
                self.assertIsNone(completed_run(root, run_id, definition))

    def test_partial_not_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id, definition, _ = self.fixture(root, "running")
            self.assertIsNone(completed_run(root, run_id, definition))

if __name__ == "__main__":
    unittest.main()



import unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
import openmc

from reactor_pipeline.config import Calculation, Scenario, load_scenarios, digest
from reactor_pipeline.measurements import mesh_to_yx, normalize_on_fuel
from reactor_pipeline.runner import run_definition

ROOT = Path(__file__).resolve().parents[1]

class MeasurementTests(unittest.TestCase):
    def test_actual_openmc_mesh_index_order_is_yx(self):
        mesh = openmc.RegularMesh()
        mesh.dimension = (3, 3)
        mesh.lower_left = (-1.0, -1.0)
        mesh.upper_right = (1.0, 1.0)
        indices = list(mesh.indices)
        values = [10 * ix + iy for ix, iy in indices]
        result = mesh_to_yx(values, indices, n=3)
        self.assertEqual(result[0, 2], 31)
        self.assertEqual(result[2, 0], 13)

    def test_normalization_uses_fuel_only(self):
        mask = np.zeros((17, 17), dtype=bool)
        mask.flat[:264] = True
        raw = np.full((17, 17), 1000.0)
        raw[mask] = np.arange(1, 265, dtype=float)
        relative, average = normalize_on_fuel(raw, mask)
        self.assertAlmostEqual(average, 132.5)
        self.assertAlmostEqual(float(np.mean(relative[mask])), 1.0)
        self.assertTrue(np.all(np.isnan(relative[~mask])))
        self.assertNotAlmostEqual(average, float(raw.mean()))

class IdentityTests(unittest.TestCase):
    def test_run_id_changes_with_computation_or_nuclear_source(self):
        scenario = load_scenarios(ROOT / "configs/pilot_assembly.json")[0]
        source = {"xml_path": "/data/cross_sections.xml", "xml_sha256": "a"}
        first = digest(run_definition(scenario, source))
        for field in ("batches", "inactive", "particles", "seed", "threads"):
            changed_calc = replace(scenario.calculation, **{field: getattr(scenario.calculation, field) + 1})
            changed = Scenario(scenario.name, scenario.physics, changed_calc)
            self.assertEqual(scenario.scenario_id, changed.scenario_id)
            self.assertNotEqual(first, digest(run_definition(changed, source)), field)
        for field, delta in (("boron_ppm_mass", 1), ("water_density_g_cm3", 0.01), ("temperature_K", 10)):
            changed_physics = replace(scenario.physics, **{field: getattr(scenario.physics, field) + delta})
            changed = Scenario(scenario.name, changed_physics, scenario.calculation)
            self.assertNotEqual(scenario.scenario_id, changed.scenario_id)
            self.assertNotEqual(first, digest(run_definition(changed, source)), field)
        self.assertNotEqual(first, digest(run_definition(scenario, {**source, "xml_sha256": "b"})))

if __name__ == "__main__":
    unittest.main()




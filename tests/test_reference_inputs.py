"""Compare physical input objects against the preserved legacy reference."""
import json
import os
from pathlib import Path
import unittest
import warnings

import numpy as np
import openmc
from openmc.mixin import IDWarning

from reactor_pipeline.config import load_scenarios
from reactor_pipeline.geometry import fuel_mask, xy_bounds
from reactor_pipeline.runner import build_model

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "runs/boron_sensitivity_jw2nca39/referans"

def material_signature(model):
    answer = {}
    for material in model.geometry.get_all_materials().values():
        answer[material.name] = {
            "density": round(float(material.get_mass_density()), 12),
            "nuclide_mass_density": {n: round(float(material.get_mass_density(n)), 12)
                                     for n in material.get_nuclides()},
            "sab": tuple(sorted((name, round(fraction, 12)) for name, fraction in material._sab)),
        }
    return answer

def geometry_signature(model):
    surfaces = sorted((type(surface).__name__, surface.boundary_type,
                       tuple(sorted((key, round(float(value), 12))
                                    for key, value in surface.coefficients.items())))
                      for surface in model.geometry.get_all_surfaces().values())
    cells = sorted((cell.name, cell.fill_type,
                    cell.fill.name if cell.fill_type == "material" else
                    (cell.fill.name if cell.fill_type == "lattice" else None),
                    cell.temperature)
                   for cell in model.geometry.get_all_cells().values())
    lattices = []
    for lattice in model.geometry.get_all_lattices().values():
        universes = np.asarray(lattice.universes)
        pattern = tuple(tuple(tuple(sorted(cell.name for cell in universe.get_all_cells().values()))
                              for universe in row) for row in universes)
        lattices.append((lattice.name, tuple(lattice.pitch), tuple(lattice.lower_left),
                         universes.shape, pattern))
    return surfaces, cells, sorted(lattices)

def source_signature(model):
    sources = []
    for source in model.settings.source:
        space = source.space
        sources.append((type(source).__name__, str(source.particle), float(source.strength),
                        tuple(sorted(source.constraints.items())), type(space).__name__,
                        tuple(space.lower_left), tuple(space.upper_right)))
    return sources

def tally_signature(model):
    return sorted((tally.name, tuple(tally.scores), tally.estimator,
                   tuple((type(filter_).__name__, tuple(filter_.mesh.dimension),
                          tuple(filter_.mesh.lower_left), tuple(filter_.mesh.upper_right))
                         for filter_ in tally.filters))
                  for tally in model.tallies)

class ReferenceInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (LEGACY / "model.xml").is_file():
            raise unittest.SkipTest("Preserved legacy model.xml unavailable")
        cls.scenario = load_scenarios(ROOT / "configs/reference_regression.json")[0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", IDWarning)  # both models reuse harmless IDs
            warnings.filterwarnings("ignore", category=DeprecationWarning, module="openmc.lattice")
            cls.legacy = openmc.Model.from_model_xml(LEGACY / "model.xml")
            cls.current, cls.mesh, cls.mask, cls.lower, cls.upper, _ = build_model(cls.scenario)

    def test_record_and_calculation(self):
        info = json.loads((LEGACY / "run_info.json").read_text())
        physics = self.scenario.physics
        calc = self.scenario.calculation
        self.assertAlmostEqual(info["boron_ppm"], physics.boron_ppm_mass, places=7)
        self.assertEqual(info["water_density_g_cm3"], physics.water_density_g_cm3)
        self.assertEqual(info["temperature_K"], physics.temperature_K)
        self.assertEqual(info["temperature_method"], physics.temperature_method)
        for name in ("batches", "inactive", "particles", "seed", "threads"):
            self.assertEqual(info[name], getattr(calc, name))
        self.assertEqual(info["openmc_version"], openmc.__version__)
        self.assertEqual(info["cross_sections"], os.environ["OPENMC_CROSS_SECTIONS"])

    def test_materials_and_temperature(self):
        self.assertEqual(material_signature(self.legacy), material_signature(self.current))
        self.assertEqual(self.legacy.settings.temperature, self.current.settings.temperature)

    def test_geometry_boundaries_and_fuel_mask(self):
        self.assertEqual(geometry_signature(self.legacy), geometry_signature(self.current))
        old_lower, old_upper = xy_bounds(self.legacy)
        np.testing.assert_array_equal(old_lower, self.lower)
        np.testing.assert_array_equal(old_upper, self.upper)
        np.testing.assert_array_equal(fuel_mask(self.legacy, old_lower, old_upper), self.mask)
        self.assertEqual(int(self.mask.sum()), 264)

    def test_source_tally_and_settings(self):
        self.assertEqual(source_signature(self.legacy), source_signature(self.current))
        self.assertEqual(tally_signature(self.legacy), tally_signature(self.current))
        for name in ("run_mode", "particles", "batches", "inactive", "seed"):
            self.assertEqual(getattr(self.legacy.settings, name), getattr(self.current.settings, name))

if __name__ == "__main__":
    unittest.main()



import math
import unittest

import numpy as np

from reactor_pipeline.beavrs3d import (
    build_model, leaf_material, load_reference, materials_from_reference,
    mesh_to_zyx, nuclear_data_precheck, point_checks, volume_fractions,
)


class Beavrs3DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = load_reference()

    def test_source_geometry_and_materials(self):
        cfg = self.reference
        g = cfg["geometry"]
        guides = {tuple(p) for p in g["guide_positions_yx_one_based"]}
        self.assertEqual(len(guides), 24)
        self.assertNotIn(tuple(g["center_instrument_position_yx_one_based"]), guides)
        self.assertTrue(math.isclose(g["fuel_top_cm"]-g["fuel_bottom_cm"], 365.76))
        mats = materials_from_reference(cfg)
        self.assertEqual(set(mats), {"fuel", "water", "helium", "zircaloy", "ss304", "aic", "b4c"})
        for key, material in mats.items():
            self.assertEqual(material.temperature, cfg["materials"][key]["temperature_K"])
            self.assertTrue(math.isclose(
                material.get_mass_density(), cfg["materials"][key]["density_g_cm3"], rel_tol=1e-12))
        water = mats["water"]
        ppm = 1e6*sum(water.get_mass_density(n) for n in ("B10", "B11"))/water.get_mass_density()
        self.assertTrue(math.isclose(ppm, 975.0, abs_tol=0.02))  # rounded atom densities

    def test_insertion_geometry_and_points(self):
        for insertion in (0, 50, 100):
            with self.subTest(insertion=insertion):
                a = build_model(self.reference, insertion)
                self.assertTrue(math.isclose(
                    a.rod_tip, a.top-insertion/100*(a.top-a.bottom), abs_tol=1e-9))
                checks = point_checks(a)
                self.assertGreaterEqual(checks["sampled_pin_centers"], 17*17*4)
                cx, cy = -3*a.pin_pitch, 6*a.pin_pitch  # row 3, column 6
                if insertion:
                    self.assertEqual(leaf_material(a.model, cx, cy, a.rod_tip+1), "aic")
                else:
                    self.assertEqual(leaf_material(a.model, cx, cy, (a.bottom+a.top)/2), "water")
                self.assertEqual(leaf_material(a.model, 0, 0, (a.bottom+a.top)/2), "water")

    def test_three_insertion_axial_material_intervals(self):
        g = self.reference["geometry"]
        x, y = -3*g["pin_pitch_cm"], 6*g["pin_pitch_cm"]
        expected = {
            0: [(100, "water"), (250, "water"), (400, "water")],
            50: [(100, "water"), (250, "aic"), (350, "b4c")],
            100: [(100, "aic"), (250, "b4c"), (400, "water")],
        }
        for percent, probes in expected.items():
            with self.subTest(percent=percent):
                a = build_model(self.reference, percent)
                self.assertEqual(a.mesh.dimension, (17, 17, 20))
                self.assertAlmostEqual(a.aic_top-a.rod_tip, 101.6)
                self.assertAlmostEqual(a.b4c_top-a.aic_top, 259.08)
                for z, material in probes:
                    self.assertEqual(leaf_material(a.model, x, y, z), material)
                    self.assertEqual(leaf_material(a.model, -8*a.pin_pitch, 8*a.pin_pitch, z), "fuel")
                fractions = volume_fractions(a)
                self.assertEqual(fractions["z_edges_cm"][0], 36.748)
                self.assertEqual(fractions["z_edges_cm"][-1], 402.508)
                if percent == 100:
                    self.assertTrue(np.any(fractions["b4c"][-1] > 0))
                    self.assertTrue(np.all(fractions["b4c"][-1] < 1))
    def test_mesh_order_and_partial_rod_slices(self):
        a = build_model(self.reference, 50)
        order = mesh_to_zyx(np.arange(1, 17*17*20+1), a.mesh.indices, a.mesh.dimension)
        self.assertEqual(order.shape, (20, 17, 17))
        self.assertEqual(order[0, 0, 0], 1)
        self.assertEqual(order[0, 0, 1], 2)
        self.assertEqual(order[1, 0, 0], 17*17+1)
        fractions = volume_fractions(a)
        self.assertEqual(fractions["fuel"].shape, (20, 17, 17))
        self.assertTrue(np.all(fractions["fuel"] >= 0))
        self.assertTrue(np.any((fractions["aic"] > 0) & (fractions["aic"] < 1)))
        self.assertTrue(np.any((fractions["b4c"] > 0) & (fractions["b4c"] < 1)))
        z = fractions["z_edges_cm"]
        self.assertEqual(z[0], a.bottom)
        self.assertEqual(z[-1], a.top)
        self.assertTrue(np.any((z[:-1] < a.aic_top) & (z[1:] > a.aic_top)))
        i = int(np.searchsorted(z, a.aic_top)-1)
        self.assertTrue(0 < fractions["aic"][i].max() < fractions["aic"][i-1].max())

    def test_nuclear_data_temperature_coverage(self):
        a = build_model(self.reference, 50)
        check = nuclear_data_precheck(a.materials, self.reference)
        self.assertIn("c_H_in_H2O", check["required_libraries"])
        self.assertEqual(check["temperature_method"], "interpolation")
        self.assertTrue(550 < self.reference["operating_temperature_K"] < 574)
        self.assertGreaterEqual(len(check["required_libraries"]), 7)


if __name__ == "__main__":
    unittest.main()



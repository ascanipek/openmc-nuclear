import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reactor_pipeline import student_package, v2_integration


class DecisionAndV2Tests(unittest.TestCase):
    def test_pinned_pressure_and_conversion(self):
        source = student_package.PROJECT / 'docs/sources/beavrs_1ccae04/specifications.tex'
        self.assertIn('Operating Pressure & 2250 psia', source.read_text().splitlines()[83])
        manifest = v2_integration.load_prepared()
        self.assertEqual(manifest['pressure_original']['kind'], 'absolute')
        self.assertAlmostEqual(2250 * manifest['psi_to_MPa'], 15.51320325, places=10)
        self.assertEqual(manifest['controls']['coolant_pressure_MPa'], 15.51320325)

    def test_nominal_comparison_finds_water_difference(self):
        result = v2_integration.nominal_comparison()
        for field in ('geometry_config_equal', 'external_boundaries_equal',
                      'source_equal', 'tallies_equal', 'temperature_method_equal'):
            self.assertTrue(result[field], field)
        water = result['materials']['water']
        self.assertAlmostEqual(water['old_density_g_cm3'], 0.740582068)
        self.assertLess(water['density_difference_g_cm3'], 0)
        self.assertLess(water['total_atom_density_difference_atom_b_cm'], 0)
        self.assertAlmostEqual(water['density_difference_g_cm3'], -1.2077387032682907e-6, places=12)
        for name, material in result['materials'].items():
            self.assertEqual(material['old_temperature_K'], material['new_temperature_K'])
            if name != 'water':
                self.assertEqual(material['density_difference_g_cm3'], 0)
                self.assertEqual(material['max_abs_atom_density_difference_atom_b_cm'], 0)

    def test_v2_preflight_no_transport_and_fixed_budget(self):
        with patch('openmc.Model.run', side_effect=AssertionError('transport started')):
            check = v2_integration.preflight()
        self.assertFalse(check['transport_started'])
        self.assertEqual(check['calculation']['batches'], 100)
        self.assertEqual(check['calculation']['particles_per_generation'], 10000)
        self.assertEqual(check['nuclear_data']['temperature_method'], 'interpolation')

    def test_v2_launch_guard_without_starting_worker(self):
        class FakeProcess:
            pid = 24680
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(v2_integration, 'ROOT', Path(tmp) / 'beavrs3d_v2_nominal_integration_v1'), \
             patch.object(v2_integration, 'preflight', return_value={'manifest_sha256': 'test'}), \
             patch.object(v2_integration.subprocess, 'Popen', return_value=FakeProcess()), \
             patch.object(v2_integration, 'process_alive', return_value=False):
            first = v2_integration.launch()
            self.assertEqual(first['state'], 'queued')
            self.assertEqual(first['pid'], 24680)
            with self.assertRaises(FileExistsError):
                v2_integration.launch()

    def test_notebook_is_explicit_and_compiles_without_running(self):
        nb = json.loads((student_package.PROJECT / 'notebooks/03_v2_nominal_entegrasyon.ipynb').read_text())
        self.assertIn('Run All', ''.join(nb['cells'][0]['source']))
        for cell in nb['cells']:
            if cell['cell_type'] == 'code':
                compile(''.join(cell['source']), '<v2 notebook>', 'exec')
        self.assertIn('launch()', ''.join(nb['cells'][-1]['source']))
        self.assertNotIn('wsl.exe', ''.join(nb['cells'][-1]['source']))

    def test_legacy_approvals_are_preserved_and_new_versions_unapproved(self):
        root = student_package.PACKAGES
        for group in ('beavrs3d_d3_b1_repeats_v1','beavrs3d_d4_b1_positions_v1'):
            old = root / group
            original = json.loads((old/'approval.json').read_text())
            self.assertEqual(original['hashes_sha256'],student_package.digest(old/'SHA256SUMS.json'))
            self.assertEqual(original['package_sha256'],student_package.digest(old/'package.json'))
            new = root / (group + '_integrity_v2')
            self.assertEqual(student_package.verify(new,require_approval=False)['notebook_integrity_schema'],
                             'notebook-inputs-v1')
            with self.assertRaises(FileNotFoundError):
                student_package.verify(new,require_approval=True)
        self.assertFalse((student_package.PROJECT / 'docs/scope_approval.json').exists())


if __name__ == '__main__':
    unittest.main()

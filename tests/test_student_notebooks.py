"""Static and mocked checks; never starts Monte Carlo transport."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use('Agg')
import openmc

from reactor_pipeline import experiments as exp, research_results as rr, student_package

ROOT = student_package.PROJECT
PACKAGES = student_package.PACKAGES
CASES = (('D3', 'beavrs3d_d3_b1_repeats_v1'), ('D4', 'beavrs3d_d4_b1_positions_v1'))


def notebook_sources(package_id, filename):
    path = PACKAGES / package_id / 'notebooks' / filename
    book = json.loads(path.read_text(encoding='utf-8'))
    return book, [''.join(c['source']) for c in book['cells'] if c['cell_type'] == 'code']


class StudentNotebookTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = Path.cwd()
        os.chdir(ROOT)

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_four_notebooks_compile_and_hash_pinned(self):
        for phase, group_id in CASES:
            info = json.loads((PACKAGES / group_id / 'package.json').read_text())
            self.assertEqual(info['group_id'], group_id)
            hashes = json.loads((PACKAGES / group_id / 'SHA256SUMS.json').read_text())
            for filename in (f'01_{phase}_calistir.ipynb', f'02_{phase}_sonuclari_incele.ipynb'):
                self.assertIn(f'notebooks/{filename}', hashes)
                book, sources = notebook_sources(group_id, filename)
                self.assertEqual(book['metadata']['kernelspec']['display_name'], 'Python (OpenMC Proje)')
                for source in sources:
                    compile(source, filename, 'exec')
            self.assertIn('README.md', hashes)
            self.assertIn('src/reactor_pipeline/research_results.py', hashes)

    def test_launch_cell_does_not_start_when_approval_or_preflight_fails(self):
        for phase, group_id in CASES:
            book, cells = notebook_sources(group_id, f'01_{phase}_calistir.ipynb')
            launch_source = ''.join(next(c for c in book['cells'] if c.get('id')=='launch_commands')['source'])
            early = [s for s in cells if s != launch_source]
            self.assertNotIn('/home/ascanipek', '\n'.join(cells))
            self.assertNotIn('wsl.exe', '\n'.join(cells))
            self.assertNotIn('ipywidgets', '\n'.join(cells))
            self.assertNotIn('launch(', '\n'.join(early))
            namespace = {}
            with contextlib.redirect_stdout(io.StringIO()):
                with patch.object(student_package, 'verify', return_value={'group_id': group_id, 'manifest': f'manifests/{group_id}.json'}):
                    exec(cells[0], namespace)
            namespace['group_status'] = Mock(side_effect=FileNotFoundError())
            with patch.object(exp, 'launch', side_effect=AssertionError('transport started')) as launch:
                namespace['verify'] = Mock(side_effect=ValueError('approval invalid'))
                with self.assertRaisesRegex(ValueError, 'approval invalid'):
                    exec(launch_source, namespace)
                launch.assert_not_called()
                namespace['verify'] = Mock(return_value={})
                namespace['preflight'] = Mock(side_effect=ValueError('nuclear preflight failed'))
                with self.assertRaisesRegex(ValueError, 'preflight failed'):
                    exec(launch_source, namespace)
                launch.assert_not_called()

    def test_success_is_single_mocked_launch_and_existing_group_never_restarts(self):
        for phase, group_id in CASES:
            book, cells = notebook_sources(group_id, f'01_{phase}_calistir.ipynb')
            launch_source = ''.join(next(c for c in book['cells'] if c.get('id')=='launch_commands')['source'])
            namespace = {}
            with contextlib.redirect_stdout(io.StringIO()):
                with patch.object(student_package, 'verify', return_value={'group_id': group_id, 'manifest': f'manifests/{group_id}.json'}):
                    exec(cells[0], namespace)
            namespace['group_status'] = Mock(side_effect=FileNotFoundError())
            namespace['verify'] = Mock(return_value={})
            namespace['preflight'] = Mock(return_value={'group_id': group_id, 'transport_started': False})
            fake = {'pid': 12345, 'group_log': '/tmp/group.log', 'status_file': '/tmp/status.json', 'group_dir': '/tmp/group'}
            with patch.object(exp, 'launch', return_value=fake) as launch, contextlib.redirect_stdout(io.StringIO()):
                exec(launch_source, namespace)
                launch.assert_called_once_with(namespace['SELECTED_MANIFEST'])
            existing = {'group_id': group_id, 'state': 'running', 'pid': 12345, 'process_alive': True,
                        'group_log': '/tmp/group.log', 'status_file': '/tmp/status.json', 'group_dir': '/tmp/group'}
            namespace['group_status'] = Mock(return_value=existing)
            namespace['verify'] = Mock(side_effect=AssertionError('should not verify an existing run'))
            with patch.object(exp, 'launch', side_effect=AssertionError('duplicate transport')) as launch, contextlib.redirect_stdout(io.StringIO()):
                exec(launch_source, namespace)
                launch.assert_not_called()
            for state in ('completed', 'failed', 'stopped', 'budget_exhausted'):
                namespace['group_status'] = Mock(return_value=dict(existing, state=state, process_alive=False))
                with patch.object(exp, 'launch', side_effect=AssertionError('restart')) as launch, contextlib.redirect_stdout(io.StringIO()):
                    exec(launch_source, namespace)
                    launch.assert_not_called()

    def test_result_notebooks_read_only_and_handle_unstarted_groups(self):
        for phase, group_id in CASES:
            _, cells = notebook_sources(group_id, f'02_{phase}_sonuclari_incele.ipynb')
            joined = '\n'.join(cells)
            for prohibited in ('launch(', 'resume(', '.run(', 'subprocess', 'wsl.exe', '/home/ascanipek'):
                self.assertNotIn(prohibited, joined)
            namespace = {}
            saved_reference = rr.reference_b1()
            original_saved_group = rr.saved_group
            def fixture_group(package_id):
                return {'state':'not_started','cases':{}} if package_id == group_id else original_saved_group(package_id)
            with patch.object(rr, 'saved_group', side_effect=fixture_group), \
                 patch.object(openmc.Model, 'run', side_effect=AssertionError('transport started')), \
                 patch.object(exp, 'launch', side_effect=AssertionError('group started')), \
                 contextlib.redirect_stdout(io.StringIO()):
                for source in cells:
                    exec(source, namespace)
            self.assertEqual(namespace['group']['state'], 'not_started')
            self.assertEqual(namespace['reference']['summary']['experiment_id'], 'D2-B1')

    def test_reference_identity_and_common_geometry_mask(self):
        ref = rr.reference_b1()
        self.assertTrue(rr.validate_comparison(ref, ref))
        stats = rr.comparison_stats(ref, ref)
        self.assertGreater(stats['common_geometry_voxels'], 0)
        self.assertEqual(stats['fission']['mean_signed_raw_difference'], 0)
        self.assertEqual(rr.case_row('D2-B1', ref)['sıfır_fisyon_voxel'],
                         int(((ref['fields']['fuel_volume_fraction'] > 0) &
                              (ref['fields']['fission_mean'] == 0)).sum()))
        wrong = dict(ref, resolved=dict(ref['resolved'], reference_config_sha256='wrong'))
        with self.assertRaisesRegex(ValueError, 'reference_config_sha256'):
            rr.validate_comparison(ref, wrong)

    def test_partial_group_exposes_completed_case_without_waiting(self):
        source = Path(rr.reference_b1()["attempt"])
        original_json = rr._json
        def renamed_case(path):
            value = original_json(path)
            if Path(path).parent == source and Path(path).name in ("resolved_config.json", "summary.json", "status.json"):
                value = dict(value, experiment_id="D3-S32001")
            return value
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(rr, "read_group", return_value=(Path(temp), rr._manifest(rr.D3_ID), {"state": "running"})), \
             patch.object(rr, "_completed_attempt", side_effect=[source, None]), \
             patch.object(rr, "_json", side_effect=renamed_case):
            group = rr.saved_group(rr.D3_ID)
        self.assertEqual(group["state"], "running")
        self.assertEqual(group["cases"]["D3-S32001"]["state"], "completed")
        self.assertEqual(group["cases"]["D3-S33001"]["state"], "not_started")
        self.assertIsNotNone(rr.case_row("D3-S32001", group["cases"]["D3-S32001"])["k"])
    def test_d3_approval_record_and_d4_gate_without_local_state_assumptions(self):
        d3 = PACKAGES / CASES[0][1]
        approval = json.loads((d3 / 'approval.json').read_text())
        self.assertEqual(approval['authorization'], 'd3_research_repeats_only')
        self.assertEqual(approval['hashes_sha256'], student_package.digest(d3 / 'SHA256SUMS.json'))
        self.assertEqual(approval['package_sha256'], student_package.digest(d3 / 'package.json'))
        group_id = CASES[1][1]
        manifest = ROOT / 'manifests' / f'{group_id}.json'
        with tempfile.TemporaryDirectory() as temp, patch.object(exp, 'GROUPS', Path(temp)),              patch.object(exp, 'preflight', return_value={}),              patch.object(exp, '_spawn', side_effect=AssertionError('worker started')):
            with self.assertRaises((ValueError, FileNotFoundError)):
                exp.launch(manifest)
            self.assertFalse((Path(temp) / group_id).exists())


if __name__ == '__main__':
    unittest.main()

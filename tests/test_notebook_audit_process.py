import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reactor_pipeline import experiments, notebook_audit

ROOT = Path('/home/ascanipek/openmc-proje')


class NotebookAuditAndProcessTests(unittest.TestCase):
    def test_saved_outputs_and_metadata_do_not_change_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            source = {'cells': [{'cell_type': 'code', 'source': ['x = 1'], 'outputs': [],
                                 'execution_count': None}], 'metadata': {'version': 1}}
            old, current = Path(temp)/'approved.ipynb', Path(temp)/'saved.ipynb'
            old.write_text(json.dumps(source))
            edited = json.loads(old.read_text())
            edited['cells'][0]['outputs'] = [{'output_type': 'stream', 'text': ['1']}]
            edited['cells'][0]['execution_count'] = 1
            edited['metadata']['version'] = 2
            current.write_text(json.dumps(edited))
            result = notebook_audit.audit(current, old, notebook_audit.sha256(old))
            self.assertTrue(result['inputs_equal'])
            self.assertFalse(result['raw_sha256_equal'])
            self.assertEqual(result['outputs_or_execution_counts_changed'], [0])
            self.assertTrue(result['notebook_metadata_changed'])
            edited['cells'][0]['source'] = ['x = 2']
            current.write_text(json.dumps(edited))
            self.assertFalse(notebook_audit.audit(current, old, notebook_audit.sha256(old))['inputs_equal'])
            edited['cells'][0]['source'] = ['x = 1']
            edited['cells'].append({'cell_type': 'code', 'source': ['print(x)']})
            current.write_text(json.dumps(edited))
            self.assertEqual(len(notebook_audit.audit(current, old, notebook_audit.sha256(old))['added_input_cells']), 1)
            with self.assertRaisesRegex(ValueError, 'snapshot'):
                notebook_audit.audit(current, old, 'wrong')

    def test_d3_original_approved_snapshot_and_added_status_cell(self):
        folder = ROOT/'student_packages/beavrs3d_d3_b1_repeats_v1'
        current = folder/'notebooks/01_D3_calistir.ipynb'
        snapshot = folder/'notebooks/.ipynb_checkpoints/01_D3_calistir-checkpoint.ipynb'
        hashes = json.loads((folder/'SHA256SUMS.json').read_text())
        result = notebook_audit.audit(current, snapshot, hashes['notebooks/01_D3_calistir.ipynb'])
        self.assertFalse(result['inputs_equal'])
        self.assertTrue(result['added_input_cells'])

    def test_history_table_includes_generations_per_batch(self):
        calc = {'batches':4, 'inactive':1, 'generations_per_batch':3,
                'particles_per_generation':10}
        for phase, group in [('D3','beavrs3d_d3_b1_repeats_v1'),('D4','beavrs3d_d4_b1_positions_v1')]:
            path = ROOT/'student_packages'/group/'notebooks'/f'01_{phase}_calistir.ipynb'
            book = json.loads(path.read_text())
            source = ''.join(next(c for c in book['cells'] if c.get('id')=='manifest')['source'])
            tree = ast.parse(source)
            row = next(node.args[0] for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and isinstance(node.func, ast.Attribute) and node.func.attr == 'append'
                       and node.args and isinstance(node.args[0], ast.Dict))
            values = {key.value: value for key, value in zip(row.keys, row.values)
                      if isinstance(key, ast.Constant)}
            total = eval(compile(ast.Expression(values['toplam_geçmiş']), '<table>', 'eval'), {'c':calc})
            active = eval(compile(ast.Expression(values['aktif_geçmiş']), '<table>', 'eval'), {'c':calc})
            self.assertEqual((total,active),(120,90))

    def test_pid_reuse_never_counts_as_worker_or_receives_signal(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            process = {'pid': 12345, 'start_ticks': 88,
                       'launcher': str(experiments.SCRIPT.resolve()),
                       'worker_folder': str(folder.resolve())}
            (folder/'process.json').write_text(json.dumps(process))
            with patch.object(experiments, '_proc_start_ticks', return_value=89),                  patch.object(experiments, 'read_group', return_value=(folder, {}, {})),                  patch.object(experiments.os, 'killpg') as kill:
                self.assertFalse(experiments.process_alive(12345, process, folder))
                self.assertFalse(experiments.stop('test')['signal_sent'])
                kill.assert_not_called()

    def test_group_status_reads_without_touching_saved_records(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            process = folder/'process.json'
            process.write_text(json.dumps({'pid':12345,'started_at':'old'}))
            before = process.read_bytes()
            with patch.object(experiments, 'read_group', return_value=(folder, {'phase':'D3','group_runtime_budget_seconds':14400}, {'state':'completed','budget_consumed_seconds':0})):
                state = experiments.group_status('fixture')
            self.assertFalse(state['process_alive'])
            self.assertIn('observed_at_utc',state)
            self.assertEqual(process.read_bytes(),before)
            self.assertEqual(sorted(p.name for p in folder.iterdir()),['process.json'])

    def test_result_figures_are_displayed_once_and_closed(self):
        for phase, group in [('D3','beavrs3d_d3_b1_repeats_v1'),('D4','beavrs3d_d4_b1_positions_v1')]:
            path = ROOT/'student_packages'/group/'notebooks'/f'02_{phase}_sonuclari_incele.ipynb'
            book = json.loads(path.read_text())
            source = ''.join(next(c for c in book['cells'] if c.get('id')=='plots')['source'])
            class Graphs:
                profile_plot = staticmethod(lambda records: plt.figure())
                history_plot = staticmethod(lambda records: plt.figure())
            shown = []
            reference = object()
            exec(source, {'rr': Graphs, 'records': {'ref':reference}, 'reference':reference,
                          'display':shown.append})
            self.assertEqual(len(shown), 2)
            self.assertEqual(plt.get_fignums(), [])


if __name__ == '__main__':
    unittest.main()

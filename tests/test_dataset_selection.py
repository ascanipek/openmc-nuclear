import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from reactor_pipeline import dataset


class DatasetSelectionTests(unittest.TestCase):
    def test_one_scenario_uses_highest_history_run_without_averaging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            group = root/'groups'/'fixture'
            for name in ('A','B','C'):
                (group/'experiments'/name/'attempt_1').mkdir(parents=True)
            (group/'manifest.json').write_text(json.dumps({
                'model': dataset.MODEL_ID,
                'experiments': [{'experiment_id': name} for name in ('A','B','C')]}))
            edges = np.array([0.0,1.0])
            base_config = {'elemental_boron_ppm': 900, 'materials': {
                'water': {'density_g_cm3': .7, 'temperature_K': 500},
                'fuel': {'density_g_cm3': 10, 'temperature_K': 600}},
                'geometry': {'pin_pitch_cm': 1.2, 'pellet_radius_cm': .4}}
            def record(attempt, preview):
                name = attempt.parent.name
                histories = {'A': 30, 'B': 90, 'C': 50}[name]
                return {'scenario_id':'same_physics', 'run_id':name, 'attempt':str(attempt),
                        'active_histories':histories,
                        'target':np.array([[[float(histories)]]]),
                        'fuel_mask':np.ones((1,1,1),dtype=bool),
                        'fields':{**{f'{axis}_edges_cm':edges for axis in ('x','y','z')},
                                  'fission_mean':np.ones((1,1,1)),
                                  'kappa_fission_mean':np.ones((1,1,1))},
                        'summary':{'k_effective':{'mean':histories/100,'mc_standard_error':.01}},
                        'resolved':{'insertion_percent':50,'reference_config':base_config,
                                    'reference_config_sha256':'ref'}}
            with patch.object(dataset, 'GROUPS', root/'groups'),                  patch.object(dataset, '_read_attempt', side_effect=record):
                result = dataset.build_dataset(['fixture'],root/'export',preview=True)
            self.assertEqual(result['sample_count'],1)
            sample = json.loads((root/'export/index.json').read_text())['samples'][0]
            self.assertEqual(sample['selected_run_id'],'B')
            self.assertEqual(sample['active_histories'],90)
            self.assertEqual(len(sample['all_source_runs']),3)
            self.assertEqual(sample['k_mean'],.9)
            with np.load(root/'export/samples.npz') as arrays:
                self.assertEqual(float(arrays['sample_00000_target_normalized_kappa'][0,0,0]),90)


if __name__ == '__main__':
    unittest.main()

"""Notebook content gate tests use temporary packages and mocked transport only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reactor_pipeline import experiments, notebook_content, student_package

D3 = 'beavrs3d_d3_b1_repeats_v1'
D4 = 'beavrs3d_d4_b1_positions_v1'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


def fixture(root, group=D3):
    project = Path(root)
    packages = project/'student_packages'
    folder = packages/(group+'_integrity_v2')
    folder.mkdir(parents=True)
    scope = project/'docs/scope.md'
    scope.parent.mkdir(parents=True)
    scope.write_text('scope')
    phase = 'D3' if group == D3 else 'D4'
    launch_name = f'notebooks/01_{phase}_calistir.ipynb'
    result_name = f'notebooks/02_{phase}_sonuclari_incele.ipynb'
    book = {'nbformat':4, 'nbformat_minor':5,
            'metadata':{'kernelspec':{'name':'openmc-proje','display_name':'OpenMC'},
                        'language_info':{'name':'python','version':'3.12.0'},
                        'launch_policy':'fixed manifest only'},
            'cells':[{'id':'first','cell_type':'markdown','source':['# Heading'], 'metadata':{}},
                     {'id':'second','cell_type':'code','source':['x = 1'],
                      'outputs':[], 'execution_count':None, 'metadata':{}},
                     {'id':'third','cell_type':'raw','source':['raw text'], 'metadata':{'tags':['keep']}}]}
    for rel in (launch_name,result_name):
        write_json(folder/rel, book)
    notebook_hashes = {rel:notebook_content.content_digest(folder/rel)
                       for rel in (launch_name,result_name)}
    write_json(folder/'NOTEBOOK_CONTENT_SHA256.json',
               {'schema':notebook_content.SCHEMA,'notebooks':notebook_hashes})
    hashes = {'README.md':None,'NOTEBOOK_CONTENT_SHA256.json':None}
    (folder/'README.md').write_text('technical draft')
    for rel in ('src/reactor_pipeline/research_results.py',
                'src/reactor_pipeline/notebook_content.py',
                'src/reactor_pipeline/experiments.py',
                'configs/profile.json','manifests/fixed.json'):
        local, shared = folder/rel, project/rel
        local.parent.mkdir(parents=True,exist_ok=True)
        shared.parent.mkdir(parents=True,exist_ok=True)
        local.write_text(rel)
        shared.write_text(rel)
        hashes[rel] = student_package.digest(local)
    for rel in ('README.md','NOTEBOOK_CONTENT_SHA256.json'):
        hashes[rel] = student_package.digest(folder/rel)
    write_json(folder/'SHA256SUMS.json',hashes)
    info = {'schema_version':2,'notebook_integrity_schema':notebook_content.SCHEMA,
            'package_id':folder.name,'group_id':group,'model':'beavrs_derived_3d_assembly_v1',
            'manifest':'manifests/fixed.json','scope_proposal_sha256':student_package.digest(scope)}
    write_json(folder/'package.json',info)
    approval = {'status':'approved','authorization':
                'd3_research_repeats_only' if group == D3 else 'd4_research_after_d3_review',
                'package_sha256':student_package.digest(folder/'package.json'),
                'hashes_sha256':student_package.digest(folder/'SHA256SUMS.json')}
    if group == D4:
        review = project/'runs/beavrs_3d/groups'/D3/'review.json'
        write_json(review,{'operator_acknowledged':True})
        approval['d3_review_sha256'] = student_package.digest(review)
    write_json(folder/'approval.json',approval)
    return project, packages, folder, scope, folder/launch_name


class NotebookIntegrityV2Tests(unittest.TestCase):
    def test_output_only_save_passes_real_gate_but_input_changes_block_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            project,packages,folder,scope,notebook = fixture(temp)
            original = json.loads(notebook.read_text())
            with patch.object(student_package,'PROJECT',project),                  patch.object(student_package,'PACKAGES',packages),                  patch.object(student_package,'SCOPE',scope),                  patch.object(student_package,'load_manifest',
                              return_value=(project/'manifests/fixed.json',{'group_id':D3},None)),                  patch.object(student_package,'preflight',return_value={'group_id':D3}),                  patch.object(student_package,'launch',return_value={'pid':123}) as launch:
                edited = copy.deepcopy(original)
                edited['cells'][1]['outputs'] = [{'output_type':'stream','text':['done']}]
                edited['cells'][1]['execution_count'] = 4
                edited['cells'][1]['metadata']['execution'] = {'iopub.execute_input':'later'}
                edited['metadata']['language_info']['version'] = '3.12.15'
                edited['metadata']['kernelspec']['display_name'] = 'New display name'
                edited['cells'][1]['source'] = ['x ', '= 1']
                write_json(notebook,edited)
                self.assertEqual(student_package.launch_approved(folder),{'pid':123})
                launch.assert_called_once()
                launch.reset_mock()
                mutations = [
                    lambda n:n['cells'][1].update(source=['x = 2']),
                    lambda n:n['cells'][0].update(source=['# Changed']),
                    lambda n:n['cells'][2].update(source=['changed raw']),
                    lambda n:n['cells'].append(copy.deepcopy(n['cells'][1])),
                    lambda n:n['cells'].pop(),
                    lambda n:n['cells'].reverse(),
                    lambda n:n['cells'][1].update(cell_type='markdown'),
                    lambda n:n['cells'][1].update(id='different'),
                    lambda n:n['cells'][1]['metadata'].update(tags=['skip-execution']),
                    lambda n:n['metadata']['kernelspec'].update(name='other'),
                    lambda n:n['metadata']['language_info'].update(name='other'),
                    lambda n:n['metadata'].update(launch_policy='different'),
                ]
                for mutate in mutations:
                    changed = copy.deepcopy(original)
                    mutate(changed)
                    write_json(notebook,changed)
                    with self.assertRaisesRegex(ValueError,'Notebook input hash mismatch'):
                        student_package.launch_approved(folder)
                    launch.assert_not_called()
                write_json(notebook,original)
                code = project/'src/reactor_pipeline/experiments.py'
                code.write_text('changed physics or execution code')
                with self.assertRaisesRegex(ValueError,'Package hash mismatch'):
                    student_package.launch_approved(folder)
                launch.assert_not_called()
                code.write_text('src/reactor_pipeline/experiments.py')
                profile = project/'configs/profile.json'
                profile.write_text('changed calculation profile')
                with self.assertRaisesRegex(ValueError,'Package hash mismatch'):
                    student_package.launch_approved(folder)
                launch.assert_not_called()
                profile.write_text('configs/profile.json')
                manifest = project/'manifests/fixed.json'
                manifest.write_text('changed manifest')
                with self.assertRaisesRegex(ValueError,'Package hash mismatch'):
                    student_package.launch_approved(folder)
                launch.assert_not_called()
                manifest.write_text('manifests/fixed.json')
                changed = copy.deepcopy(original)
                changed['cells'][1]['source'] = ['x = 2']
                write_json(notebook,changed)
                notebook_file = folder/'NOTEBOOK_CONTENT_SHA256.json'
                content = json.loads(notebook_file.read_text())
                rel = str(notebook.relative_to(folder))
                content['notebooks'][rel] = notebook_content.content_digest(notebook)
                write_json(notebook_file,content)
                ledger_file = folder/'SHA256SUMS.json'
                ledger = json.loads(ledger_file.read_text())
                ledger['NOTEBOOK_CONTENT_SHA256.json'] = student_package.digest(notebook_file)
                write_json(ledger_file,ledger)
                with self.assertRaisesRegex(ValueError,'Package lacks matching advisor approval'):
                    student_package.launch_approved(folder)
                launch.assert_not_called()

    def test_d4_still_requires_d3_review_link(self):
        with tempfile.TemporaryDirectory() as temp:
            project,packages,folder,scope,notebook = fixture(temp,D4)
            with patch.object(student_package,'PROJECT',project),                  patch.object(student_package,'PACKAGES',packages),                  patch.object(student_package,'SCOPE',scope),                  patch.object(student_package,'load_manifest',
                              return_value=(project/'manifests/fixed.json',{'group_id':D4},None)),                  patch.object(experiments,'read_group',
                              return_value=(None,None,{'state':'completed'})):
                self.assertEqual(student_package.verify(folder)['group_id'],D4)
                review = project/'runs/beavrs_3d/groups'/D3/'review.json'
                write_json(review,{'operator_acknowledged':False})
                with self.assertRaisesRegex(ValueError,'D4 requires completed D3'):
                    student_package.verify(folder)
                write_json(review,{'operator_acknowledged':True})
                with patch.object(experiments,'read_group',
                                  return_value=(None,None,{'state':'failed'})):
                    with self.assertRaisesRegex(ValueError,'D4 requires completed D3'):
                        student_package.verify(folder)


if __name__ == '__main__':
    unittest.main()

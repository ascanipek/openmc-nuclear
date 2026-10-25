import csv,hashlib,io,json,zipfile
from pathlib import Path
root=Path('/home/ascanipek/openmc-proje')
p=root/'kaggle/ml_keff_v1'
zpath=p/'openmc_keff_256_provisional_v1.zip'
with zipfile.ZipFile(zpath) as z:
    names=z.namelist();print('ZIP_FILES',names)
    files={n:z.read(n) for n in names}
    ledger=json.loads(files['bundle_hashes.json'])
    assert set(ledger['files'])==set(files)-{'bundle_hashes.json'}
    for n,h in ledger['files'].items(): assert hashlib.sha256(files[n]).hexdigest()==h,n
    rows=list(csv.DictReader(io.StringIO(files['ml_keff.csv'].decode())))
    splits=json.loads(files['splits.json'])
    assert len(rows)==256 and len({r['scenario_id'] for r in rows})==256
    assert {k:len(splits[k]) for k in ('train','calibration','test')}=={'train':208,'calibration':25,'test':23}
    assert all(r['scenario_id'] in splits[r['split']] for r in rows)
    source=(root/'datasets/v2_256_preview_v1/splits.json').read_bytes()
    assert files['splits.json']==source
    print('ROWS',len(rows),'SPLITS',[(k,len(splits[k])) for k in ('train','calibration','test')])
    print('ZIP_SHA256',hashlib.sha256(zpath.read_bytes()).hexdigest())
nb=json.loads((p/'01_keff_kaggle_egitim.ipynb').read_text())
for i,c in enumerate(nb['cells']):
    if c['cell_type']=='code':
        code=''.join(c['source'])
        compile(code,f'cell_{i}','exec')
        assert not c['outputs'] and c['execution_count'] is None
        assert '/kaggle/input' in ''.join(''.join(x['source']) for x in nb['cells'])
print('NOTEBOOK_CELLS',len(nb['cells']),'CODE_SYNTAX_OK')

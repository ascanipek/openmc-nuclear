"""Build unapproved notebook-content-v1 review packages; never launch transport."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path('/home/ascanipek/openmc-proje')
PACKAGES = ROOT / 'student_packages'
REVIEW = ROOT / 'technical_reviews/notebook_integrity_v2'
SCHEMA = 'notebook-inputs-v1'
GROUPS = ('beavrs3d_d3_b1_repeats_v1', 'beavrs3d_d4_b1_positions_v1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(group):
    if group not in GROUPS:
        raise ValueError('Unsupported review group')
    from reactor_pipeline.notebook_content import content_digest
    source = PACKAGES / group
    dest = PACKAGES / (group + '_integrity_v2')
    dest.mkdir(parents=True, exist_ok=False)
    old = json.loads((source / 'package.json').read_text())
    old_hashes = json.loads((source / 'SHA256SUMS.json').read_text())
    protected = {}
    notebooks = {}
    for rel in old_hashes:
        if rel == 'README.md' or rel.startswith('notebooks/'):
            original = ROOT / rel if rel in ('notebooks/01_deney_calistir.ipynb', 'notebooks/02_sonuclari_incele.ipynb') else source / rel
        else:
            original = ROOT / rel
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        if rel.startswith('notebooks/'):
            book = json.loads(target.read_text(encoding='utf-8'))
            for cell in book['cells']:
                if cell['cell_type'] == 'code':
                    cell['outputs'] = []
                    cell['execution_count'] = None
                text = ''.join(cell.get('source', []))
                if rel not in ('notebooks/01_deney_calistir.ipynb', 'notebooks/02_sonuclari_incele.ipynb'):
                    if "PACKAGE_ID = '" + group + "'" in text:
                        text = text.replace("PACKAGE_ID = '" + group + "'",
                                            "PACKAGE_ID = '" + dest.name + "'" + chr(10) + "GROUP_ID = '" + group + "'")
                    text = text.replace("package_info['group_id'] == PACKAGE_ID", "package_info['group_id'] == GROUP_ID")
                    text = text.replace("check['group_id'] == PACKAGE_ID", "check['group_id'] == GROUP_ID")
                    text = text.replace("final_check['group_id'] == PACKAGE_ID", "final_check['group_id'] == GROUP_ID")
                    text = text.replace('group_status(PACKAGE_ID)', 'group_status(GROUP_ID)')
                    text = text.replace('rr.saved_group(PACKAGE_ID)', 'rr.saved_group(GROUP_ID)')
                    text = text.replace('rr._manifest(PACKAGE_ID)', 'rr._manifest(GROUP_ID)')
                cell['source'] = text.splitlines(True)
            if rel.endswith('01_D3_calistir.ipynb'):
                book['cells'] = book['cells'][:next(i for i,c in enumerate(book['cells']) if c.get('id') == 'launch_commands')+1]
            target.write_text(json.dumps(book, ensure_ascii=False, indent=1) + chr(10))
            notebooks[rel] = content_digest(target)
        elif rel != 'README.md':
            protected[rel] = sha(target)
    for rel in ('src/reactor_pipeline/notebook_content.py',):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
        protected[rel] = sha(target)
    readme = dest / 'README.md'
    readme.write_text('''# Technical review package, not approved

This version pins notebook inputs with notebook-inputs-v1. No advisor approval is bundled. Do not Run All until a new approval.json is issued and verified. The original D3/D4 packages, approvals, manifests, and completed results remain separate. Once approved, open the dedicated 01 notebook in the OpenMC Proje WSL kernel; the dedicated 02 notebook only reads results. A completed group is never restarted by Run All.
''')
    protected['README.md'] = sha(readme)
    review_copy = dest / 'TECHNICAL_REVIEW.md'
    shutil.copy2(REVIEW / 'review.md', review_copy)
    protected['TECHNICAL_REVIEW.md'] = sha(review_copy)
    notebook_file = dest / 'NOTEBOOK_CONTENT_SHA256.json'
    notebook_file.write_text(json.dumps({'schema': SCHEMA, 'notebooks': notebooks}, ensure_ascii=False, indent=2) + chr(10))
    protected[notebook_file.name] = sha(notebook_file)
    (dest / 'SHA256SUMS.json').write_text(json.dumps(protected, ensure_ascii=False, indent=2) + chr(10))
    info = dict(old)
    info.update(schema_version=2, notebook_integrity_schema=SCHEMA, package_id=dest.name,
                approval_status='technical_review_ready_unapproved',
                purpose='Notebook content integrity v2 technical review only; no new advisor approval')
    (dest / 'package.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + chr(10))
    return dest


if __name__ == '__main__':
    for group in GROUPS:
        print(build(group))

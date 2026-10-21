"""Rebuild the upload inventory after reviewing a Kaggle-only change."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
files = {}
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or "__pycache__" in path.parts or path.name == "bundle_hashes.json":
        continue
    relative = path.relative_to(ROOT).as_posix()
    files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
ledger = {"schema": "kaggle_code_bundle_sha256_v1", "owner": "ogrenci_04",
          "stages": {"stage_32": 8, "stage_128": 24, "stage_256": 32}, "files": files}
(ROOT / "bundle_hashes.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
print(f"Frozen {len(files)} files")

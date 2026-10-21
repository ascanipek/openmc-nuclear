"""Create the single Kaggle code Dataset ZIP from the reviewed hash inventory."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT.parent / "ogrenci_04_kod_dataset.zip"
ledger = json.loads((ROOT / "bundle_hashes.json").read_text(encoding="utf-8"))
files = ledger["files"]
for relative, expected in files.items():
    path = ROOT / relative
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Reviewed bundle changed: {relative}")
temporary = TARGET.with_suffix(".zip.partial")
if temporary.exists():
    raise FileExistsError(temporary)
try:
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(ROOT / "bundle_hashes.json", "bundle_hashes.json")
        for relative in sorted(files):
            archive.write(ROOT / relative, relative)
    temporary.replace(TARGET)
except BaseException:
    temporary.unlink(missing_ok=True)
    raise
print(TARGET)
print("sha256", hashlib.sha256(TARGET.read_bytes()).hexdigest())

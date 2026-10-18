from pathlib import Path
from datetime import datetime
import json
import os
import tempfile
import time

import openmc
import openmc.examples

project = Path.home() / "openmc-proje"
run_dir = Path(tempfile.mkdtemp(
    prefix="pincell_check_",
    dir=project / "runs"
))

# Resmî örnek: geometri ve malzemeler değiştirilmez.
model = openmc.examples.pwr_pin_cell()

# Yalnızca başlangıç çalışırlık testi için hesap ayarları.
model.settings.batches = 60
model.settings.inactive = 20
model.settings.particles = 10_000
model.settings.seed = 12345

metadata = {
    "purpose": "installation_check_not_training_data",
    "model": "openmc.examples.pwr_pin_cell",
    "openmc_version": openmc.__version__,
    "created_at": datetime.now().astimezone().isoformat(),
    "cross_sections": os.environ["OPENMC_CROSS_SECTIONS"],
    "batches": model.settings.batches,
    "inactive_batches": model.settings.inactive,
    "particles_per_generation": model.settings.particles,
    "seed": model.settings.seed,
    "requested_threads": 6,
}

metadata_path = run_dir / "run_info.json"
metadata_path.write_text(
    json.dumps(metadata, indent=2), encoding="utf-8"
)

print(f"\nÇalışma klasörü: {run_dir}", flush=True)

start = time.perf_counter()
statepoint_path = model.run(cwd=run_dir, threads=6)
elapsed = time.perf_counter() - start

with openmc.StatePoint(statepoint_path) as sp:
    result = sp.keff
    metadata["multiplication_factor"] = float(result.nominal_value)
    metadata["mc_standard_deviation"] = float(result.std_dev)

metadata["elapsed_seconds"] = elapsed
metadata["statepoint"] = str(statepoint_path)
metadata_path.write_text(
    json.dumps(metadata, indent=2), encoding="utf-8"
)

print("\n--- İLK HESAP TAMAMLANDI ---")
print(f"Çoğalma faktörü: {result}")
print(f"Geçen süre: {elapsed:.1f} saniye")
print(f"Sonuç dosyası: {statepoint_path}")
print(f"Hesap kaydı: {metadata_path}")

from pathlib import Path
import json
import os
import tempfile
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import openmc
import openmc.examples

project = Path.home() / "openmc-proje"
run_dir = Path(tempfile.mkdtemp(
    prefix="pincell_map_", dir=project / "runs"
))

model = openmc.examples.pwr_pin_cell()
model.settings.batches = 80
model.settings.inactive = 30
model.settings.particles = 20_000
model.settings.seed = 12345

# Ölçüm sınırlarını doğrudan model geometrisinden alıyoruz.
bounds = model.geometry.bounding_box
lower = np.asarray(bounds.lower_left[:2], dtype=float)
upper = np.asarray(bounds.upper_right[:2], dtype=float)
assert np.all(np.isfinite([lower, upper]))

# Model eksen boyunca değişmediği için x-y ölçüm ağı kullanılır.
# Bu ölçüm, sonlu kalınlıklı bir 3D dilim değildir.
n = 32
mesh = openmc.RegularMesh(name="xy_measurement_grid")
mesh.dimension = (n, n)
mesh.lower_left = lower
mesh.upper_right = upper

tally = openmc.Tally(name="xy_flux")
tally.filters = [openmc.MeshFilter(mesh)]
tally.scores = ["flux"]
tally.estimator = "tracklength"
model.tallies = openmc.Tallies([tally])

info = {
    "purpose": "pilot_flux_map_not_validated_training_data",
    "model": "openmc.examples.pwr_pin_cell",
    "openmc_version": openmc.__version__,
    "cross_sections": os.environ["OPENMC_CROSS_SECTIONS"],
    "batches": 80,
    "inactive_batches": 30,
    "particles_per_generation": 20000,
    "seed": 12345,
    "requested_threads": 6,
    "mesh_shape_yx": [n, n],
    "lower_left_cm": lower.tolist(),
    "upper_right_cm": upper.tolist(),
    "array_order": "row=y, column=x",
    "measurement": "2D xy tally, no axial restriction",
    "raw_unit": "particle-cm per source particle",
    "display_normalization": "raw mean divided by spatial mean",
}
(run_dir / "run_info.json").write_text(
    json.dumps(info, indent=2), encoding="utf-8"
)

print(f"Çalışma klasörü: {run_dir}", flush=True)
start = time.perf_counter()
statepoint_path = model.run(cwd=run_dir, threads=6)
info["elapsed_seconds"] = time.perf_counter() - start

with openmc.StatePoint(statepoint_path) as sp:
    result = sp.get_tally(name="xy_flux")
    values = result.mean.ravel()
    errors = result.std_dev.ravel()

    # OpenMC hücre indekslerini açıkça y,x matrisine yerleştiriyoruz.
    mean = np.zeros((n, n))
    std = np.zeros((n, n))
    for index, (ix, iy) in enumerate(mesh.indices):
        mean[iy - 1, ix - 1] = values[index]
        std[iy - 1, ix - 1] = errors[index]

    info["multiplication_factor"] = float(sp.keff.nominal_value)
    info["mc_standard_deviation"] = float(sp.keff.std_dev)

assert np.all(np.isfinite(mean)) and mean.mean() > 0
relative = mean / mean.mean()
relative_error = np.divide(
    std, mean, out=np.full_like(std, np.nan), where=mean > 0
)

# Asıl veri: renkli görüntü değil, bu sayısal dizilerdir.
np.savez_compressed(
    run_dir / "flux_data.npz",
    raw_mean=mean,
    raw_std_dev=std,
    relative_flux=relative,
    mc_relative_error=relative_error,
    lower_left_cm=lower,
    upper_right_cm=upper,
)
np.savetxt(run_dir / "flux_raw_mean.csv", mean, delimiter=",")
np.savetxt(run_dir / "flux_raw_std.csv", std, delimiter=",")

info["statepoint"] = str(statepoint_path)
info["normalization_value"] = float(mean.mean())
info["median_cell_relative_error_percent"] = float(
    100 * np.nanmedian(relative_error)
)
(run_dir / "run_info.json").write_text(
    json.dumps(info, indent=2), encoding="utf-8"
)

extent = [lower[0], upper[0], lower[1], upper[1]]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)

plots = [
    (relative, "Relative flux — spatial mean = 1", "viridis", "Relative value"),
    (100 * relative_error, "Monte Carlo relative standard error",
     "magma", "Percent (%)"),
]

for ax, (data, title, cmap, label) in zip(axes, plots):
    image = ax.imshow(
        data, origin="lower", extent=extent,
        interpolation="nearest", cmap=cmap
    )
    ax.set_title(title)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    fig.colorbar(image, ax=ax, label=label)

fig.savefig(run_dir / "flux_maps.png", dpi=180)
plt.close(fig)

print("\n--- AKI HARİTASI TAMAMLANDI ---")
print("Matris boyutu:", mean.shape)
print(f"Süre: {info['elapsed_seconds']:.1f} saniye")
print(
    "Medyan hücre bağıl standart hatası: "
    f"%{info['median_cell_relative_error_percent']:.2f}"
)
print("Görsel:", run_dir / "flux_maps.png")
print("Sayısal veri:", run_dir / "flux_data.npz")
print("Klasör:", run_dir)

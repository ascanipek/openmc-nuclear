"""Extract and validate numeric results; plotting is separate."""
import json
from pathlib import Path
import numpy as np
import openmc
from .measurements import mesh_to_yx, normalize_on_fuel

ARRAYS_FILE = "fission_data.npz"
RESULT_FILE = "result.json"

def extract(statepoint_path, mesh, mask, lower, upper, output_dir):
    with openmc.StatePoint(statepoint_path) as sp:
        tally = sp.get_tally(name="pin_fission")
        raw = mesh_to_yx(tally.mean, mesh.indices)
        std = mesh_to_yx(tally.std_dev, mesh.indices)
        if not np.all(std >= 0):
            raise ValueError("Negative tally standard error")
        relative, fuel_average = normalize_on_fuel(raw, mask)
        k_mean = float(sp.keff.nominal_value)
        k_std = float(sp.keff.std_dev)
        history = None
        try:
            generations = np.asarray(sp.k_generation, dtype=float).ravel()
            if generations.size and np.all(np.isfinite(generations)):
                history = generations.tolist()
        except (AttributeError, ValueError, KeyError):
            pass
    if not np.isfinite(k_mean) or not np.isfinite(k_std) or k_std < 0:
        raise ValueError("Invalid k estimate")
    folder = Path(output_dir)
    np.savez_compressed(folder / ARRAYS_FILE, raw_mean=raw, raw_std_dev=std,
                        fuel_mask=mask, relative_fission=relative,
                        lower_left_cm=lower, upper_right_cm=upper)
    result = {
        "k_mean": k_mean, "k_mc_standard_error": k_std,
        "k_generation_history": history, "source_convergence": "not_assessed",
        "array_order": "row=y, column=x", "mesh_shape_yx": [17, 17],
        "mesh_lower_left_cm": lower.tolist(), "mesh_upper_right_cm": upper.tolist(),
        "raw_fission_unit": "reactions per source particle",
        "raw_std_dev_meaning": "Monte Carlo standard error of raw tally mean",
        "relative_fission_unit": "dimensionless",
        "relative_fission_uncertainty": "not_estimated",
        "normalization": "raw mean at each fuel position divided by arithmetic mean over fuel positions only",
        "fuel_mean_raw": fuel_average, "fuel_positions": int(mask.sum()),
        "axial_restriction": None,
        "physical_validation": "not_assessed",
    }
    (folder / RESULT_FILE).write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    validate_outputs(folder)
    return result

def validate_outputs(folder):
    folder = Path(folder)
    result = json.loads((folder / RESULT_FILE).read_text(encoding="utf-8"))
    with np.load(folder / ARRAYS_FILE, allow_pickle=False) as arrays:
        raw = arrays["raw_mean"]
        std = arrays["raw_std_dev"]
        mask = arrays["fuel_mask"]
        relative = arrays["relative_fission"]
        lower = arrays["lower_left_cm"]
        upper = arrays["upper_right_cm"]
        if any(a.shape != (17, 17) for a in (raw, std, mask, relative)):
            raise ValueError("Invalid result array shape")
        if lower.shape != (2,) or upper.shape != (2,) or not np.all(upper > lower):
            raise ValueError("Invalid mesh bounds")
        if mask.dtype != bool or mask.sum() != 264 or not np.all(raw[mask] > 0):
            raise ValueError("Invalid fuel measurements")
        if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(std)) or not np.all(std >= 0):
            raise ValueError("Invalid raw tally")
        expected, _ = normalize_on_fuel(raw, mask)
        if not np.allclose(relative[mask], expected[mask]) or not np.all(np.isnan(relative[~mask])):
            raise ValueError("Invalid normalization")
    if result["source_convergence"] != "not_assessed" or result["fuel_positions"] != 264:
        raise ValueError("Invalid result metadata")
    return result

def plot_results(folders, output_path=None):
    """Regenerate maps with one shared scale from saved arrays."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    paths = [Path(p) for p in folders]
    if not paths:
        raise ValueError("At least one result folder is required")
    maps = []
    for path in paths:
        validate_outputs(path)
        with np.load(path / ARRAYS_FILE, allow_pickle=False) as arrays:
            maps.append(arrays["relative_fission"].copy())
    vmin = min(float(np.nanmin(a)) for a in maps)
    vmax = max(float(np.nanmax(a)) for a in maps)
    fig, axes = plt.subplots(1, len(maps), figsize=(5 * len(maps), 5), squeeze=False, constrained_layout=True)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("lightgray")
    for ax, path, values in zip(axes[0], paths, maps):
        image = ax.imshow(values, origin="lower", interpolation="nearest", cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(path.name)
        ax.set_xlabel("x mesh column")
        ax.set_ylabel("y mesh row")
    fig.colorbar(image, ax=axes[0].tolist(), label="Relative fission; fuel mean = 1")
    destination = Path(output_path) if output_path else paths[0] / "relative_fission.png"
    fig.savefig(destination, dpi=180)
    plt.close(fig)
    return destination


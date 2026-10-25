"""17x17 tracklength fission tally and explicit XY indexing."""
import numpy as np
import openmc

def attach_fission_tally(model, lower, upper, n=17):
    mesh = openmc.RegularMesh(name="pin_positions")
    mesh.dimension = (n, n)
    mesh.lower_left = lower
    mesh.upper_right = upper
    tally = openmc.Tally(name="pin_fission")
    tally.filters = [openmc.MeshFilter(mesh)]
    tally.scores = ["fission"]
    tally.estimator = "tracklength"
    model.tallies = openmc.Tallies([tally])
    return mesh

def mesh_to_yx(values, indices, n=17):
    values = np.asarray(values, dtype=float).ravel()
    result = np.full((n, n), np.nan)
    count = 0
    for count, (ix, iy) in enumerate(indices, 1):
        result[iy - 1, ix - 1] = values[count - 1]
    if count != n * n or values.size != n * n or not np.all(np.isfinite(result)):
        raise ValueError("Invalid or incomplete XY mesh tally")
    return result

def normalize_on_fuel(raw, mask):
    if raw.shape != mask.shape or not np.all(np.isfinite(raw)) or not np.all(raw[mask] > 0):
        raise ValueError("Fuel measurements must be finite and positive")
    average = float(np.mean(raw[mask]))
    relative = np.full(raw.shape, np.nan)
    relative[mask] = raw[mask] / average
    return relative, average


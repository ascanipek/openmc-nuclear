"""Geometry-derived bounds and fuel positions; row=y, column=x."""
import numpy as np
import openmc

N = 17

def xy_bounds(model):
    bounds = model.geometry.bounding_box
    lower = np.asarray(bounds.lower_left[:2], dtype=float)
    upper = np.asarray(bounds.upper_right[:2], dtype=float)
    if not np.all(np.isfinite([lower, upper])) or not np.all(upper > lower):
        raise ValueError("Assembly XY bounds must be finite and nonempty")
    return lower, upper

def fuel_mask(model, lower, upper, n=N):
    mask = np.zeros((n, n), dtype=bool)
    spacing = (upper - lower) / n
    for iy in range(n):
        for ix in range(n):
            x, y = lower + (np.array([ix, iy]) + 0.5) * spacing
            cells = [item for item in model.geometry.find((float(x), float(y), 0.0)) if isinstance(item, openmc.Cell)]
            if not cells:
                raise ValueError(f"No cell at mesh position {(ix, iy)}")
            material = cells[-1].fill
            mask[iy, ix] = isinstance(material, openmc.Material) and "U235" in material.get_nuclides()
    if n == N and int(mask.sum()) != 264:
        raise ValueError(f"Expected 264 fuel positions, found {mask.sum()}")
    return mask

def summary(model, mask, lower, upper):
    materials = model.geometry.get_all_materials().values()
    return {"model": "openmc_example_pwr_assembly_pilot",
            "xy_lower_left_cm": lower.tolist(), "xy_upper_right_cm": upper.tolist(),
            "axial_restriction": None, "lateral_boundary": "reflective (OpenMC example)",
            "mesh_shape_yx": list(mask.shape), "fuel_positions": int(mask.sum()),
            "materials": [{"id": m.id, "name": m.name, "density": m.density,
                           "density_units": m.density_units, "temperature_K": m.temperature}
                          for m in materials]}


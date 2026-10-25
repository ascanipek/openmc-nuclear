"""Finite-height BEAVRS-derived idealized assembly, separate from the 2D pilot."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid
import xml.etree.ElementTree as ET

import h5py
import numpy as np
import openmc

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "beavrs_derived_3d_reference.json"
MODEL_ID = "beavrs_derived_3d_assembly_v1"


def load_reference(path=DEFAULT_CONFIG):
    cfg = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if cfg["model"] != MODEL_ID or cfg["schema_version"] != 1:
        raise ValueError("Unsupported 3D reference configuration")
    g = cfg["geometry"]
    if not math.isclose(g["fuel_top_cm"] - g["fuel_bottom_cm"], 365.76, abs_tol=1e-8):
        raise ValueError("Active height differs from pinned source")
    if len(g["guide_positions_yx_one_based"]) != 24:
        raise ValueError("Expected 24 control guides")
    for m in cfg["materials"].values():
        if not m["atom_density_atom_b_cm"] or m["temperature_K"] is None:
            raise ValueError("Material composition/temperature missing")
    if cfg["temperature_method"] != "interpolation":
        raise ValueError("This model requires explicit temperature interpolation")
    return cfg


def materials_from_reference(cfg):
    materials = {}
    for key, definition in cfg["materials"].items():
        material = openmc.Material(name=key)
        material.set_density("g/cm3", definition["density_g_cm3"])
        for nuclide, atom_density in definition["atom_density_atom_b_cm"].items():
            material.add_nuclide(nuclide, atom_density, "ao")
        material.temperature = definition["temperature_K"]
        if key == "water":
            material.add_s_alpha_beta("c_H_in_H2O")
        materials[key] = material
    return materials


def _temperature_labels(group):
    return sorted(float(key[:-1]) for key in group["kTs"] if key.endswith("K"))


def nuclear_data_precheck(materials, cfg, xml_path=None):
    """Inspect small HDF5 metadata only. No transport or bulk data loading."""
    raw = xml_path or os.environ.get("OPENMC_CROSS_SECTIONS")
    if not raw:
        raise RuntimeError("OPENMC_CROSS_SECTIONS is unset")
    path = Path(raw).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    libraries = {}
    for lib in ET.parse(path).getroot().findall("library"):
        for name in lib.get("materials", "").split():
            libraries[name] = lib
    required = sorted({n for m in materials.values() for n in m.get_nuclides()} |
                      {sab[0] for m in materials.values() for sab in m._sab})
    temperatures = {}
    missing = []
    unbracketed = []
    for name in required:
        lib = libraries.get(name)
        if lib is None:
            missing.append(name)
            continue
        h5_path = (path.parent / lib.get("path")).resolve()
        if not h5_path.is_file():
            missing.append(f"{name}: {h5_path}")
            continue
        with h5py.File(h5_path, "r") as data:
            if name not in data or "kTs" not in data[name]:
                missing.append(f"{name}: no temperature metadata")
                continue
            available = _temperature_labels(data[name])
        temperatures[name] = available
        used_by = [m for m in materials.values()
                   if name in m.get_nuclides() or name in [s[0] for s in m._sab]]
        for material in used_by:
            target = float(material.temperature)
            if not available or not (available[0] <= target <= available[-1]):
                unbracketed.append(f"{name} in {material.name}: {target} K outside {available}")
    if missing or unbracketed:
        raise RuntimeError(f"Nuclear data precheck failed: missing={missing}; temperatures={unbracketed}")
    return {
        "cross_sections_xml": str(path),
        "cross_sections_xml_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "required_libraries": required,
        "temperature_grid_K": temperatures,
        "requested_material_temperature_K": {k: m.temperature for k, m in materials.items()},
        "temperature_method": cfg["temperature_method"],
        "thermal_scattering": ["c_H_in_H2O"],
        "coverage_result": "all required library temperatures bracket requested material temperatures",
        "scope": "HDF5 temperature metadata and file existence; OpenMC transport still required",
    }


@dataclass
class Assembly3D:
    model: openmc.Model
    config: dict
    insertion_percent: float
    materials: dict
    pin_pitch: float
    half_pitch: float
    bottom: float
    top: float
    rod_tip: float
    aic_top: float
    b4c_top: float
    mesh: openmc.RegularMesh


def _pin_universes(g, mats, rod_tip, aic_top, b4c_top):
    fuel_r = openmc.ZCylinder(r=g["pellet_radius_cm"])
    ci = openmc.ZCylinder(r=g["clad_inner_radius_cm"])
    co = openmc.ZCylinder(r=g["clad_outer_radius_cm"])
    fuel = openmc.Universe(name="active fuel pin")
    fuel.add_cells([
        openmc.Cell(name="fuel pellet", fill=mats["fuel"], region=-fuel_r),
        openmc.Cell(name="fuel helium gap", fill=mats["helium"], region=+fuel_r & -ci),
        openmc.Cell(name="fuel Zircaloy clad", fill=mats["zircaloy"], region=+ci & -co),
        openmc.Cell(name="fuel-pin water", fill=mats["water"], region=+co),
    ])
    guide = openmc.Universe(name="control guide with finite rod")
    dash_plane = openmc.ZPlane(z0=g["dashpot_top_cm"])
    gi = openmc.ZCylinder(r=g["guide_inner_radius_cm"])
    go = openmc.ZCylinder(r=g["guide_outer_radius_cm"])
    di = openmc.ZCylinder(r=g["dashpot_inner_radius_cm"])
    do = openmc.ZCylinder(r=g["dashpot_outer_radius_cm"])
    guide.add_cells([
        openmc.Cell(name="dashpot Zircaloy", fill=mats["zircaloy"], region=+di & -do & -dash_plane),
        openmc.Cell(name="normal guide Zircaloy", fill=mats["zircaloy"], region=+gi & -go & +dash_plane),
    ])
    ar = openmc.ZCylinder(r=g["aic_radius_cm"])
    br = openmc.ZCylinder(r=g["b4c_radius_cm"])
    he = openmc.ZCylinder(r=g["rod_helium_outer_radius_cm"])
    ss = openmc.ZCylinder(r=g["rod_ss_outer_radius_cm"])
    z_tip = openmc.ZPlane(z0=rod_tip)
    z_aic = openmc.ZPlane(z0=aic_top)
    z_b4c = openmc.ZPlane(z0=b4c_top)
    aic_zone = +z_tip & -z_aic
    b4c_zone = +z_aic & -z_b4c
    rod_region = -ss & (aic_zone | b4c_zone)
    guide.add_cells([
        openmc.Cell(name="Ag-In-Cd absorber", fill=mats["aic"], region=-ar & aic_zone),
        openmc.Cell(name="B4C absorber", fill=mats["b4c"], region=-br & b4c_zone),
        openmc.Cell(name="Ag-In-Cd helium annulus", fill=mats["helium"], region=+ar & -he & aic_zone),
        openmc.Cell(name="B4C helium annulus", fill=mats["helium"], region=+br & -he & b4c_zone),
        openmc.Cell(name="SS304 rod sleeve", fill=mats["ss304"], region=+he & -ss & (aic_zone | b4c_zone)),
        openmc.Cell(name="dashpot water", fill=mats["water"],
                    region=-di & -dash_plane & ~rod_region),
        openmc.Cell(name="normal guide water", fill=mats["water"],
                    region=-gi & +dash_plane & ~rod_region),
        openmc.Cell(name="outside dashpot water", fill=mats["water"], region=+do & -dash_plane),
        openmc.Cell(name="outside guide water", fill=mats["water"], region=+go & +dash_plane),
    ])
    center = openmc.Universe(name="idealized water-filled center; instrument tube omitted")
    center.add_cell(openmc.Cell(name="center water", fill=mats["water"]))
    outer = openmc.Universe(name="assembly-edge water")
    outer.add_cell(openmc.Cell(name="edge water", fill=mats["water"]))
    return fuel, guide, center, outer


def build_model(cfg, insertion_percent, *, batches=100, inactive=50,
                particles=10000, seed=41001):
    if not isinstance(insertion_percent, (int, float)) or not math.isfinite(insertion_percent) or not 0 <= insertion_percent <= 100:
        raise ValueError("insertion_percent must be within [0, 100]")
    g = cfg["geometry"]
    bottom, top = g["fuel_bottom_cm"], g["fuel_top_cm"]
    rod_tip = top - float(insertion_percent) / 100.0 * (top - bottom)
    aic_top = rod_tip + g["aic_length_cm"]
    b4c_top = aic_top + g["b4c_length_cm"]
    mats = materials_from_reference(cfg)
    fuel, guide, center, outer = _pin_universes(g, mats, rod_tip, aic_top, b4c_top)
    positions = {tuple(p) for p in g["guide_positions_yx_one_based"]}
    lattice = openmc.RectLattice(name="17x17 BEAVRS-derived active assembly")
    lattice.lower_left = (-g["n"] * g["pin_pitch_cm"] / 2,) * 2
    lattice.pitch = (g["pin_pitch_cm"],) * 2
    lattice.universes = [[center if (row, col) == (9, 9) else
                          guide if (row, col) in positions else fuel
                          for col in range(1, 18)] for row in range(1, 18)]
    lattice.outer = outer
    half = g["assembly_pitch_cm"] / 2
    xmin = openmc.XPlane(x0=-half, boundary_type="reflective")
    xmax = openmc.XPlane(x0=half, boundary_type="reflective")
    ymin = openmc.YPlane(y0=-half, boundary_type="reflective")
    ymax = openmc.YPlane(y0=half, boundary_type="reflective")
    zmin = openmc.ZPlane(z0=bottom, boundary_type="vacuum")
    zmax = openmc.ZPlane(z0=top, boundary_type="vacuum")
    root = openmc.Cell(name="bounded active assembly", fill=lattice,
                       region=+xmin & -xmax & +ymin & -ymax & +zmin & -zmax)
    model = openmc.Model()
    model.geometry = openmc.Geometry([root])
    model.materials = openmc.Materials(list(mats.values()))
    settings = openmc.Settings()
    settings.run_mode = "eigenvalue"
    settings.batches = batches
    settings.inactive = inactive
    settings.particles = particles
    settings.generations_per_batch = 1
    settings.seed = seed
    settings.temperature = {"default": cfg["operating_temperature_K"],
                            "method": cfg["temperature_method"]}
    settings.source = openmc.IndependentSource(
        space=openmc.stats.Box((-half, -half, bottom), (half, half, top)),
        constraints={"fissionable": True})
    mesh = openmc.RegularMesh(name="assembly_xyz")
    mesh.dimension = tuple(cfg["mesh_dimension_xyz"])
    mesh.lower_left = (-half, -half, bottom)
    mesh.upper_right = (half, half, top)
    settings.entropy_mesh = mesh
    model.settings = settings
    tally = openmc.Tally(name="assembly_3d")
    tally.filters = [openmc.MeshFilter(mesh)]
    tally.scores = ["fission", "kappa-fission", "flux"]
    tally.estimator = "tracklength"
    model.tallies = openmc.Tallies([tally])
    return Assembly3D(model, cfg, float(insertion_percent), mats, g["pin_pitch_cm"],
                      half, bottom, top, rod_tip, aic_top, b4c_top, mesh)


def leaf_material(model, x, y, z):
    cells = [item for item in model.geometry.find((float(x), float(y), float(z)))
             if isinstance(item, openmc.Cell)]
    if not cells or not isinstance(cells[-1].fill, openmc.Material):
        raise ValueError(f"Undefined material at {(x, y, z)}")
    return cells[-1].fill.name


def point_checks(assembly):
    g = assembly.config["geometry"]
    p = assembly.pin_pitch
    mid = (assembly.bottom + assembly.top) / 2
    fuel_x, fuel_y = -8*p, 8*p
    guide_x, guide_y = -3*p, 6*p  # row 3, column 6
    probes = {
        "fuel": (fuel_x, fuel_y, mid, "fuel"),
        "fuel_gap": (fuel_x + (g["pellet_radius_cm"] + g["clad_inner_radius_cm"])/2, fuel_y, mid, "helium"),
        "fuel_clad": (fuel_x + (g["clad_inner_radius_cm"] + g["clad_outer_radius_cm"])/2, fuel_y, mid, "zircaloy"),
        "moderator": (fuel_x + 0.7, fuel_y, mid, "water"),
        "guide_wall": (guide_x + 0.58, guide_y, mid, "zircaloy"),
        "center": (0, 0, mid, "water"),
    }
    if assembly.insertion_percent:
        z = min(assembly.top - 1e-3, assembly.rod_tip + 1)
        probes["rod_aic"] = (guide_x, guide_y, z, "aic")
        probes["rod_sleeve"] = (guide_x + 0.43, guide_y, z, "ss304")
        probes["rod_water"] = (guide_x + 0.494, guide_y, z, "water")
    else:
        probes["empty_guide"] = (guide_x, guide_y, mid, "water")
    checked = {}
    for key, (x, y, z, expected) in probes.items():
        actual = leaf_material(assembly.model, x, y, z)
        if actual != expected:
            raise AssertionError(f"{key}: expected {expected}, got {actual}")
        checked[key] = {"xyz_cm": [x, y, z], "material": actual}
    # Probe interiors over all pin types and several axial planes, including around the rod and dashpot.
    zs = sorted({assembly.bottom + 1e-3, min(assembly.top - 1e-3, g["dashpot_top_cm"] + 1e-3),
                 mid, assembly.top - 1e-3,
                 max(assembly.bottom + 1e-3, min(assembly.top - 1e-3, assembly.rod_tip + 1e-3)),
                 max(assembly.bottom + 1e-3, min(assembly.top - 1e-3, assembly.aic_top + 1e-3))})
    for z in zs:
        for row in range(1, 18):
            for col in range(1, 18):
                leaf_material(assembly.model, (col-9)*p, (9-row)*p, z)
    checked["sampled_pin_centers"] = len(zs)*17*17
    return checked


def plot_sections(assembly, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    mid = (assembly.bottom + assembly.top)/2
    plots = openmc.Plots()
    for basis, origin, width, pixels in [
        ("xy", (0, 0, assembly.bottom + 0.75*(assembly.top-assembly.bottom)), (2*assembly.half_pitch, 2*assembly.half_pitch), (750, 750)),
        ("xz", (0, 6*assembly.pin_pitch, mid),
         (2*assembly.half_pitch, assembly.top-assembly.bottom), (520, 1000)),
    ]:
        plot = openmc.Plot()
        plot.filename = f"{basis}_{int(assembly.insertion_percent)}pct"
        plot.basis = basis
        plot.origin = origin
        plot.width = width
        plot.pixels = pixels
        plot.color_by = "material"
        plots.append(plot)
    assembly.model.plots = plots
    assembly.model.plot_geometry(cwd=folder, output=False)
    return sorted(str(p) for p in folder.glob("*.png"))


def _circle_area_in_rectangle(cx, cy, radius, x0, x1, y0, y1):
    """Deterministic area integral; exact zero classification uses min-distance."""
    dx = max(x0-cx, 0.0, cx-x1)
    dy = max(y0-cy, 0.0, cy-y1)
    if dx*dx + dy*dy >= radius*radius:
        return 0.0
    if max(math.hypot(x-cx, y-cy) for x in (x0, x1) for y in (y0, y1)) <= radius:
        return (x1-x0)*(y1-y0)
    left, right = max(x0, cx-radius), min(x1, cx+radius)
    nodes, weights = np.polynomial.legendre.leggauss(96)
    xs = (right-left)*nodes/2 + (right+left)/2
    half_chord = np.sqrt(np.maximum(0.0, radius*radius-(xs-cx)**2))
    heights = np.maximum(0.0, np.minimum(y1, cy+half_chord)-np.maximum(y0, cy-half_chord))
    return float((right-left)/2 * np.dot(weights, heights))


def volume_fractions(assembly):
    """[z,y,x] cell fractions; rod boundary z overlaps are never rounded to a full slice."""
    g = assembly.config["geometry"]
    n_x, n_y, n_z = assembly.mesh.dimension
    x_edges = np.linspace(-assembly.half_pitch, assembly.half_pitch, n_x+1)
    y_edges = np.linspace(-assembly.half_pitch, assembly.half_pitch, n_y+1)
    z_edges = np.linspace(assembly.bottom, assembly.top, n_z+1)
    voxel_xy = (x_edges[1]-x_edges[0])*(y_edges[1]-y_edges[0])
    fuel_xy = np.zeros((n_y, n_x))
    aic_xy = np.zeros_like(fuel_xy)
    b4c_xy = np.zeros_like(fuel_xy)
    guide_positions = {tuple(p) for p in g["guide_positions_yx_one_based"]}
    for row in range(1, 18):
        for col in range(1, 18):
            if (row, col) == (9, 9):
                continue
            cx, cy = (col-9)*assembly.pin_pitch, (9-row)*assembly.pin_pitch
            radii = ([(g["aic_radius_cm"], aic_xy), (g["b4c_radius_cm"], b4c_xy)]
                     if (row, col) in guide_positions else
                     [(g["pellet_radius_cm"], fuel_xy)])
            for radius, plane in radii:
                ix0 = max(0, int(np.searchsorted(x_edges, cx-radius, side="right")-1))
                ix1 = min(n_x-1, int(np.searchsorted(x_edges, cx+radius, side="left")))
                iy0 = max(0, int(np.searchsorted(y_edges, cy-radius, side="right")-1))
                iy1 = min(n_y-1, int(np.searchsorted(y_edges, cy+radius, side="left")))
                for iy in range(iy0, iy1+1):
                    for ix in range(ix0, ix1+1):
                        area = _circle_area_in_rectangle(
                            cx, cy, radius, x_edges[ix], x_edges[ix+1],
                            y_edges[iy], y_edges[iy+1])
                        plane[iy, ix] += area/voxel_xy
    dz = np.diff(z_edges)
    def axial_fraction(start, stop):
        return np.maximum(0, np.minimum(z_edges[1:], stop)-np.maximum(z_edges[:-1], start))/dz
    fuel = np.broadcast_to(fuel_xy, (n_z, n_y, n_x)).copy()
    aic = axial_fraction(assembly.rod_tip, assembly.aic_top)[:, None, None]*aic_xy
    b4c = axial_fraction(assembly.aic_top, assembly.b4c_top)[:, None, None]*b4c_xy
    for name, arr in (("fuel", fuel), ("aic", aic), ("b4c", b4c)):
        if np.any(arr < -1e-12) or np.any(arr > 1+1e-8):
            raise ValueError(f"Invalid {name} volume fractions")
    return {
        "fuel": fuel,
        "aic": aic,
        "b4c": b4c,
        "x_edges_cm": x_edges,
        "y_edges_cm": y_edges,
        "z_edges_cm": z_edges,
    }


def mesh_to_zyx(values, indices, dimension_xyz):
    nx, ny, nz = dimension_xyz
    flat = np.asarray(values, dtype=float).reshape(-1)
    result = np.full((nz, ny, nx), np.nan)
    indices = list(indices)
    if len(indices) != nx*ny*nz or len(flat) != len(indices):
        raise ValueError("Incomplete 3D mesh tally")
    for value, (ix, iy, iz) in zip(flat, indices):
        result[iz-1, iy-1, ix-1] = value
    if not np.all(np.isfinite(result)):
        raise ValueError("Non-finite or misindexed 3D tally")
    return result


def extract_3d(statepoint_path, assembly, output_dir, elapsed_seconds, precheck, purpose="single_50pct_integration_and_initial_timing_not_convergence"):
    output_dir = Path(output_dir)
    fractions = volume_fractions(assembly)
    arrays = {f"{name}_volume_fraction": fractions[name] for name in ("fuel", "aic", "b4c")}
    arrays.update({key: fractions[key] for key in ("x_edges_cm", "y_edges_cm", "z_edges_cm")})
    arrays["fission_expected_zero"] = fractions["fuel"] <= 0
    arrays["kappa_fission_expected_zero"] = fractions["fuel"] <= 0
    with openmc.StatePoint(statepoint_path) as sp:
        tally = sp.get_tally(name="assembly_3d")
        for score in ("fission", "kappa-fission", "flux"):
            label = score.replace("-", "_")
            arrays[f"{label}_mean"] = mesh_to_zyx(
                tally.get_values(scores=[score], value="mean"), assembly.mesh.indices,
                assembly.mesh.dimension)
            arrays[f"{label}_std_dev"] = mesh_to_zyx(
                tally.get_values(scores=[score], value="std_dev"), assembly.mesh.indices,
                assembly.mesh.dimension)
        k = float(sp.keff.nominal_value)
        k_err = float(sp.keff.std_dev)
        k_generation = np.asarray(sp.k_generation, dtype=float).reshape(-1)
        entropy = np.asarray(sp.entropy, dtype=float).reshape(-1)
        globals_record = {}
        for value in sp.global_tallies:
            name = value['name'].decode()
            globals_record[name] = {'mean': float(value['mean']), 'std_dev': float(value['std_dev'])}
    if not all(np.all(np.isfinite(arr)) for arr in arrays.values()):
        raise ValueError("Non-finite 3D output")
    if not np.isfinite(k) or not np.isfinite(k_err) or k_err < 0:
        raise ValueError("Invalid k result")
    if entropy.size != assembly.model.settings.batches or k_generation.size != assembly.model.settings.batches:
        raise ValueError("Incomplete generation history")
    if "leakage" not in globals_record:
        raise ValueError("Global leakage tally missing")
    arrays["k_generation"] = k_generation
    arrays["shannon_entropy"] = entropy
    array_path = output_dir / "beavrs_3d_arrays.npz"
    fuel = arrays["fuel_volume_fraction"]
    raw = arrays["fission_mean"]
    std = arrays["fission_std_dev"]
    # This reporting mask avoids tiny partial-volume bins and near-zero, noise-only means.
    # It is descriptive, not an acceptance criterion.
    max_mean = float(np.max(raw))
    report_mask = ((fuel > 0.20) & (raw > 0) &
                   (raw >= 5*std) & (raw >= 1e-6*max_mean))
    arrays["relative_error_reporting_mask"] = report_mask
    arrays["array_order"] = np.asarray(["z", "y", "x"])
    np.savez_compressed(array_path, **arrays)
    relative = np.divide(std, raw, out=np.full_like(std, np.nan), where=report_mask)
    stats = None
    if np.any(report_mask):
        selected = relative[report_mask]
        stats = {"median": float(np.median(selected)),
                 "p95": float(np.percentile(selected, 95)),
                 "maximum": float(np.max(selected))}
    z_fission = np.sum(arrays["fission_mean"], axis=(1, 2))
    z_kappa = np.sum(arrays["kappa_fission_mean"], axis=(1, 2))
    result = {
        "model": assembly.config["model"],
        "source_commit": assembly.config["beavrs_source_commit"],
        "purpose": purpose,
        "calculation": {"batches": assembly.model.settings.batches,
                        "inactive": assembly.model.settings.inactive,
                        "particles_per_generation": assembly.model.settings.particles,
                        "generations_per_batch": assembly.model.settings.generations_per_batch,
                        "seed": assembly.model.settings.seed},
        "physical_validation": "not_assessed",
        "insertion_percent": assembly.insertion_percent,
        "rod_tip_cm": assembly.rod_tip,
        "aic_top_cm": assembly.aic_top,
        "b4c_top_cm": assembly.b4c_top,
        "array_order": ["z", "y", "x"],
        "mesh_dimension_xyz": list(assembly.mesh.dimension),
        "mesh_shape_zyx": [20, 17, 17],
        "k_mean": k,
        "k_mc_standard_error": k_err,
        "global_tallies": globals_record,
        "elapsed_seconds": elapsed_seconds,
        "relative_error_reporting_mask": {
            "fuel_volume_fraction_gt": 0.20,
            "raw_fission_mean_ge_5_times_standard_error": True,
            "raw_fission_mean_ge_fraction_of_maximum": 1e-6,
            "included_voxels": int(np.sum(report_mask)),
            "fuel_intersecting_voxels": int(np.sum(fuel > 0)),
            "excluded_voxels": int(raw.size-np.sum(report_mask)),
            "meaning": "descriptive reliability filter; not an acceptance threshold",
        },
        "active_fission_relative_mc_error": stats,
        "axial_fission_raw_profile": z_fission.tolist(),
        "axial_kappa_fission_raw_profile": z_kappa.tolist(),
        "axial_z_edges_cm": fractions["z_edges_cm"].tolist(),
        "k_generation_history": k_generation.tolist(),
        "shannon_entropy_history": entropy.tolist(),
        "raw_units": {
            "fission": "reactions/source particle",
            "kappa_fission": "eV/source particle; fission energy generation approximation, not total local heat deposition",
            "flux": "particle-cm/source particle",
            "std_dev": "Monte Carlo standard error of raw mean",
        },
        "nuclear_data": precheck,
        "result_arrays": array_path.name,
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result


def run_integration(config_path=DEFAULT_CONFIG, root="runs/beavrs_3d"):
    cfg = load_reference(config_path)
    assembly = build_model(cfg, 50, batches=100, inactive=50, particles=10000, seed=41001)
    precheck = nuclear_data_precheck(assembly.materials, cfg)
    checks = point_checks(assembly)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / f"integration_50pct_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    status = {"state": "pending", "purpose": "single_50pct_integration_and_initial_timing_not_convergence",
              "physical_validation": "not_assessed", "seed": 41001,
              "calculation": {"batches": 100, "inactive": 50, "particles_per_generation": 10000,
                              "generations_per_batch": 1, "threads": 6}}
    (folder / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (folder / "configuration.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (folder / "geometry_checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    (folder / "nuclear_data_precheck.json").write_text(json.dumps(precheck, indent=2), encoding="utf-8")
    start = time.perf_counter()
    try:
        assembly.model.export_to_xml(directory=folder)
        status["state"] = "running"
        (folder / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        statepoint = assembly.model.run(cwd=folder, threads=6, geometry_debug=True, output=True)
        statepoint = Path(statepoint)
        if not statepoint.is_file() or statepoint.stat().st_size == 0:
            raise RuntimeError("Missing statepoint")
        result = extract_3d(statepoint, assembly, folder, time.perf_counter()-start, precheck)
        validate_3d_outputs(folder)
        status.update(state="completed", elapsed_seconds=result["elapsed_seconds"],
                      k_mean=result["k_mean"], k_mc_standard_error=result["k_mc_standard_error"],
                      statepoint=statepoint.name)
        (folder / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        return folder, result
    except Exception as exc:
        status.update(state="failed", elapsed_seconds=time.perf_counter()-start,
                      error=f"{type(exc).__name__}: {exc}")
        (folder / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        raise





def geometry_check_suite(config_path=DEFAULT_CONFIG, root="runs/beavrs_3d"):
    cfg = load_reference(config_path)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / f"geometry_checks_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    record = {"model": MODEL_ID, "source_commit": cfg["beavrs_source_commit"],
              "physical_validation": "not_assessed", "geometry_states": {}}
    try:
        for percent in (0, 50, 100):
            assembly = build_model(cfg, percent)
            checks = point_checks(assembly)
            fractions = volume_fractions(assembly)
            plots = plot_sections(assembly, folder / f"{percent}pct")
            record["geometry_states"][str(percent)] = {
                "rod_tip_cm": assembly.rod_tip,
                "aic_top_cm": assembly.aic_top,
                "b4c_top_cm": assembly.b4c_top,
                "selected_point_checks": checks,
                "sampled_fuel_intersecting_voxels": int(np.sum(fractions["fuel"] > 0)),
                "partly_occupied_aic_voxels": int(np.sum((fractions["aic"] > 0) &
                                                       (fractions["aic"] < 1))),
                "partly_occupied_b4c_voxels": int(np.sum((fractions["b4c"] > 0) &
                                                       (fractions["b4c"] < 1))),
                "plots": plots,
            }
        nuclear = nuclear_data_precheck(build_model(cfg, 50).materials, cfg)
        record["nuclear_data_precheck"] = nuclear
        record["state"] = "passed"
    except Exception as exc:
        record["state"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (folder / "checks.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return folder, record


def plot_integration_results(folder):
    """Plots saved results only; never invokes neutron transport."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder = Path(folder)
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    with np.load(folder / result["result_arrays"], allow_pickle=False) as data:
        z_edges = data["z_edges_cm"]
        z = (z_edges[:-1] + z_edges[1:])/2
        fission = np.sum(data["fission_mean"], axis=(1, 2))
        kappa = np.sum(data["kappa_fission_mean"], axis=(1, 2))
        k_history = data["k_generation"]
        entropy = data["shannon_entropy"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].step(z, fission, where="mid", color="tab:blue")
    axes[0].axvline(result["rod_tip_cm"], color="black", ls="--", lw=1, label="absorber tip")
    axes[0].axvline(result["aic_top_cm"], color="tab:red", ls=":", lw=1, label="AIC/B4C")
    axes[0].set(xlabel="z (cm)", ylabel="raw fission (reactions/source particle)",
                title="Axial fission profile")
    axes[0].legend()
    axes[1].step(z, kappa, where="mid", color="tab:orange")
    axes[1].axvline(result["rod_tip_cm"], color="black", ls="--", lw=1)
    axes[1].axvline(result["aic_top_cm"], color="tab:red", ls=":", lw=1)
    axes[1].set(xlabel="z (cm)", ylabel="raw kappa-fission (eV/source particle)",
                title="Fission-energy generation proxy")
    profile_path = folder / "axial_profiles.png"
    fig.savefig(profile_path, dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, constrained_layout=True)
    batches = np.arange(1, k_history.size+1)
    axes[0].plot(batches, k_history, lw=0.8, color="tab:blue")
    axes[0].axhline(result["k_mean"], color="black", ls=":", lw=1)
    axes[0].set_ylabel("generation k")
    axes[1].plot(batches, entropy, lw=0.8, color="tab:green")
    axes[1].set(xlabel="batch / generation", ylabel="source Shannon entropy")
    inactive = result.get("calculation", {}).get("inactive", 50)
    for ax in axes:
        ax.axvspan(1, inactive, color="gray", alpha=0.15, label="inactive")
        ax.axvline(inactive+0.5, color="gray", ls="--", lw=1)
    history_path = folder / "history.png"
    fig.savefig(history_path, dpi=160)
    plt.close(fig)
    return profile_path, history_path


def validate_3d_outputs(folder, expected_model=MODEL_ID):
    folder = Path(folder)
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    if result["model"] != expected_model or result["array_order"] != ["z", "y", "x"]:
        raise ValueError("Invalid 3D model metadata")
    expected = tuple(result["mesh_shape_zyx"])
    with np.load(folder / result["result_arrays"], allow_pickle=False) as data:
        if "array_order" in data and data["array_order"].tolist() != ["z", "y", "x"]:
            raise ValueError("Invalid NPZ axis order")
        if "relative_error_reporting_mask" in data and data["relative_error_reporting_mask"].shape != expected:
            raise ValueError("Invalid relative-error mask shape")
        for score in ("fission", "kappa_fission", "flux"):
            mean, error = data[f"{score}_mean"], data[f"{score}_std_dev"]
            if mean.shape != expected or error.shape != expected:
                raise ValueError(f"Invalid {score} shape")
            if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(error)) or np.any(error < 0):
                raise ValueError(f"Invalid {score} measurements")
        for name in ("fuel", "aic", "b4c"):
            fraction = data[f"{name}_volume_fraction"]
            if fraction.shape != expected or np.any(fraction < 0) or np.any(fraction > 1+1e-8):
                raise ValueError(f"Invalid {name} geometry mask")
        zero = data["fission_expected_zero"]
        if zero.shape != expected or not np.array_equal(zero, data["fuel_volume_fraction"] <= 0):
            raise ValueError("Invalid geometry-based fission zero mask")
        if not np.array_equal(zero, data["kappa_fission_expected_zero"]):
            raise ValueError("Invalid kappa-fission zero mask")
        if np.any(data["fission_mean"][zero] != 0) or np.any(data["kappa_fission_mean"][zero] != 0):
            raise ValueError("Nonzero fission outside fuel")
        if data["z_edges_cm"].shape != (expected[0]+1,) or not np.all(np.diff(data["z_edges_cm"]) > 0):
            raise ValueError("Invalid axial coordinates")
        expected_batches = result.get("calculation", {}).get("batches", len(result["k_generation_history"]))
        if data["k_generation"].size != expected_batches or data["shannon_entropy"].size != expected_batches:
            raise ValueError("Incomplete generation data")
    if not (math.isfinite(result["k_mean"]) and math.isfinite(result["k_mc_standard_error"])
            and result["k_mc_standard_error"] >= 0):
        raise ValueError("Invalid k")
    return result







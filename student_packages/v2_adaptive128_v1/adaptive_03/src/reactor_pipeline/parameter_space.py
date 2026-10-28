"""Proposed, isolated v2 parameter links. Never relabel recorded v1 runs."""
from __future__ import annotations

from copy import deepcopy
import math
import warnings

import openmc

from .beavrs3d import build_model, load_reference, nuclear_data_precheck

MODEL_ID = "beavrs_derived_3d_assembly_v2_proposed"
CONTROLS = {"u235_enrichment_wt_percent", "fuel_temperature_K", "moderator_temperature_K",
            "coolant_pressure_MPa", "elemental_boron_ppm", "pin_pitch_cm",
            "pellet_radius_cm", "insertion_percent"}


def _number(controls, name, low, high):
    value = controls[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    if not low <= value <= high:
        raise ValueError(f"{name} outside proposed/physical guard [{low}, {high}]")
    return float(value)


def _atom_mass(name):
    return openmc.data.atomic_mass(name)


def _density_to_atoms(mass_density, atom_ratios):
    denominator = sum(v * _atom_mass(k) for k, v in atom_ratios.items())
    factor = mass_density * openmc.data.AVOGADRO * 1e-24 / denominator
    return {k: v * factor for k, v in atom_ratios.items()}


def resolve_proposed(controls, reference=None):
    """Resolve explicit controls; no inferred pressure or silent defaults."""
    if set(controls) != CONTROLS:
        raise ValueError(f"Exactly these controls are required: {sorted(CONTROLS)}")
    ref = load_reference() if reference is None else deepcopy(reference)
    cfg = deepcopy(ref)
    cfg["model"] = MODEL_ID
    e = _number(controls, "u235_enrichment_wt_percent", 1.6, 3.1)
    tf = _number(controls, "fuel_temperature_K", 273.15, float("inf"))
    tw = _number(controls, "moderator_temperature_K", 273.15, 623.15)
    pressure = _number(controls, "coolant_pressure_MPa", 0.001, 100)
    boron = _number(controls, "elemental_boron_ppm", 0, 975)
    pitch = _number(controls, "pin_pitch_cm", 0.01, 100)
    pellet = _number(controls, "pellet_radius_cm", 0.001, 100)
    insertion = _number(controls, "insertion_percent", 0, 100)
    if pellet >= ref["geometry"]["clad_inner_radius_cm"]:
        raise ValueError("Pellet overlaps fixed gap/cladding interface")
    if pitch <= 2 * max(ref["geometry"]["guide_outer_radius_cm"],
                        ref["geometry"]["clad_outer_radius_cm"]):
        raise ValueError("Neighboring pin/guide envelopes overlap")
    if ref["geometry"]["assembly_pitch_cm"] <= 17 * ref["geometry"]["pin_pitch_cm"]:
        raise ValueError("Reference assembly edge-water clearance invalid")
    cfg["geometry"]["pin_pitch_cm"] = pitch
    cfg["geometry"]["assembly_pitch_cm"] = (17 * pitch + ref["geometry"]["assembly_pitch_cm"]
                                             - 17 * ref["geometry"]["pin_pitch_cm"])
    cfg["geometry"]["pellet_radius_cm"] = pellet
    fuel_ref = ref["materials"]["fuel"]
    original = fuel_ref["atom_density_atom_b_cm"]
    uranium = {k: original[k] for k in ("U234", "U235", "U238")}
    wt235 = uranium["U235"] * _atom_mass("U235") / sum(v * _atom_mass(k) for k, v in uranium.items())
    # U234/U235 mass ratio follows the pinned 1.6% table; U238 is remainder.
    ratio234 = uranium["U234"] * _atom_mass("U234") / (uranium["U235"] * _atom_mass("U235"))
    w235 = e / 100
    w234 = w235 * ratio234
    w238 = 1 - w235 - w234
    if w238 <= 0:
        raise ValueError("Invalid uranium isotope balance")
    u_atoms = {k: w / _atom_mass(k) for k, w in
               (("U234", w234), ("U235", w235), ("U238", w238))}
    u_sum = sum(u_atoms.values())
    atom_ratios = {k: v / u_sum for k, v in u_atoms.items()}
    oxygen = {k: original[k] for k in ("O16", "O17", "O18")}
    o_sum = sum(oxygen.values())
    atom_ratios.update({k: 2 * v / o_sum for k, v in oxygen.items()})
    cfg["materials"]["fuel"]["atom_density_atom_b_cm"] = _density_to_atoms(
        fuel_ref["density_g_cm3"], atom_ratios)
    if e == 1.6:
        # The source table is nominally 1.6 wt%; retain its rounded atoms exactly.
        cfg["materials"]["fuel"]["atom_density_atom_b_cm"] = deepcopy(original)
    cfg["materials"]["fuel"]["temperature_K"] = tf
    cfg["materials"]["fuel"]["composition_rule"] = (
        "U235 mass fraction of uranium; U234/U235 mass ratio pinned to BEAVRS 1.6% table; "
        "U238 balance; UO2 stoichiometry; fixed bulk fuel density; proposed interpolation, not source validated")
    # IF97 region 1: fail closed outside compressed-liquid region. OpenMC raises for invalid state.
    with warnings.catch_warnings():
        warnings.simplefilter('error', UserWarning)
        pure_density = openmc.data.water_density(tw, pressure)
    solution_density = pure_density / (1 - boron * 1e-6)
    base_water = ref["materials"]["water"]["atom_density_atom_b_cm"]
    h = {k: base_water[k] for k in ("H1", "H2")}
    o = {k: base_water[k] for k in ("O16", "O17", "O18")}
    b = {k: base_water[k] for k in ("B10", "B11")}
    ratios = {k: 2 * v / sum(h.values()) for k, v in h.items()}
    ratios.update({k: v / sum(o.values()) for k, v in o.items()})
    boron_atomic_mass = sum(v * _atom_mass(k) for k, v in b.items()) / sum(b.values())
    water_molar_mass = sum(ratios[k] * _atom_mass(k) for k in (*h, *o))
    boron_atoms_per_water = ((boron * 1e-6) / (1 - boron * 1e-6)
                             * water_molar_mass / boron_atomic_mass)
    ratios.update({k: boron_atoms_per_water * v / sum(b.values()) for k, v in b.items()})
    cfg["materials"]["water"]["density_g_cm3"] = solution_density
    cfg["materials"]["water"]["atom_density_atom_b_cm"] = _density_to_atoms(
        solution_density, ratios)
    cfg["materials"]["water"]["temperature_K"] = tw
    for name in ("helium", "zircaloy", "ss304", "aic", "b4c"):
        cfg["materials"][name]["temperature_K"] = tw
    cfg["operating_temperature_K"] = tw
    cfg["resolved_controls"] = dict(controls)
    cfg["coolant_pressure_MPa"] = pressure
    cfg["water_density_method"] = "OpenMC 0.16 IAPWS-IF97 region 1 pure water; solution mass density = pure/(1-B mass fraction)"
    cfg["structural_temperature_rule"] = "equal to moderator temperature; proposed uniform-temperature assumption"
    cfg["reference_u235_mass_fraction_of_uranium"] = wt235
    return cfg, insertion


def build_proposed(controls, reference=None, *, check_nuclear_data=True, **model_settings):
    cfg, insertion = resolve_proposed(controls, reference)
    assembly = build_model(cfg, insertion, **model_settings)
    if check_nuclear_data:
        nuclear_data_precheck(assembly.materials, cfg)
    return assembly





"""Mass fraction changes for the example assembly's borated water."""
import math

BORON = ("B10", "B11")

def water_material(model):
    candidates = [m for m in model.geometry.get_all_materials().values()
                  if "water" in m.name.lower() and set(BORON).intersection(m.get_nuclides())]
    if len(candidates) != 1:
        raise ValueError(f"Expected one borated water material, found {len(candidates)}")
    return candidates[0]

def mass_fractions_for_ppm(original, target_ppm):
    """Keep boron isotope ratio and non-boron ratios at fixed total mass density."""
    if not math.isfinite(target_ppm) or not 0 <= target_ppm < 1e6:
        raise ValueError("Invalid elemental boron ppm")
    total = original.get_mass_density()
    fractions = {n: original.get_mass_density(n) / total for n in original.get_nuclides()}
    old_b = sum(fractions.get(n, 0) for n in BORON)
    if not 0 < old_b < 1:
        raise ValueError("Reference water needs boron and non-boron nuclides")
    new_b = target_ppm / 1e6
    return {n: f * (new_b / old_b if n in BORON else (1 - new_b) / (1 - old_b))
            for n, f in fractions.items()}

def set_boron(model, target_ppm, density_g_cm3):
    water = water_material(model)
    fractions = mass_fractions_for_ppm(water, target_ppm)
    for nuclide in list(water.get_nuclides()):
        water.remove_nuclide(nuclide)
    for nuclide, fraction in fractions.items():
        if fraction > 0:
            water.add_nuclide(nuclide, fraction, percent_type="wo")
    water.set_density("g/cm3", density_g_cm3)
    actual = 1e6 * sum(water.get_mass_density(n) for n in BORON if n in water.get_nuclides()) / water.get_mass_density()
    if not math.isclose(actual, target_ppm, abs_tol=1e-5):
        raise ValueError(f"Boron conversion failed: {actual} != {target_ppm}")
    return water, actual


"""Sequential OpenMC execution with preserved run states and safe resume."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import uuid

import openmc
import openmc.examples

from . import __version__
from .config import digest
from .geometry import fuel_mask, summary, xy_bounds
from .materials import set_boron
from .measurements import attach_fission_tally
from .results import validate_outputs, extract

def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def cross_sections_source():
    raw = os.environ.get("OPENMC_CROSS_SECTIONS")
    if not raw:
        raise RuntimeError("OPENMC_CROSS_SECTIONS is unset")
    path = Path(raw).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"xml_path": str(path), "xml_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "hash_scope": "cross_sections.xml only; not the entire nuclear data library"}

def run_definition(scenario, source):
    return {"scenario": scenario.definition(), "nuclear_data": source,
            "openmc_version": openmc.__version__, "pipeline_version": __version__}

def completed_run(root, run_id, definition):
    """Return only an exact completed, intact run; leave partial runs untouched."""
    for folder in sorted(Path(root).glob(f"{run_id}_*")):
        try:
            status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
            saved = json.loads((folder / "run_definition.json").read_text(encoding="utf-8"))
            if status["state"] != "completed" or status["run_id"] != run_id or saved != definition:
                continue
            statepoint = folder / status["statepoint"]
            if not statepoint.is_file() or statepoint.stat().st_size == 0:
                continue
            for required in ("model.xml", "openmc.log", "scenario.json", "model_summary.json"):
                if not (folder / required).is_file():
                    break
            else:
                result = validate_outputs(folder)
                with openmc.StatePoint(statepoint) as sp:
                    sp.get_tally(name="pin_fission")
                    if not (abs(float(sp.keff.nominal_value) - result["k_mean"]) < 1e-10
                            and abs(float(sp.keff.std_dev) - result["k_mc_standard_error"]) < 1e-10):
                        continue
                return folder
        except (OSError, ValueError, KeyError, TypeError, FileNotFoundError):
            continue
    return None

def build_model(scenario):
    model = openmc.examples.pwr_assembly()
    physics = scenario.physics
    calculation = scenario.calculation
    water, measured_ppm = set_boron(model, physics.boron_ppm_mass, physics.water_density_g_cm3)
    for cell in model.geometry.get_all_cells().values():
        if cell.fill_type == "material":
            cell.temperature = physics.temperature_K
    model.settings.temperature = {"default": physics.temperature_K, "method": physics.temperature_method}
    model.settings.batches = calculation.batches
    model.settings.inactive = calculation.inactive
    model.settings.particles = calculation.particles
    model.settings.seed = calculation.seed
    lower, upper = xy_bounds(model)
    mask = fuel_mask(model, lower, upper)
    mesh = attach_fission_tally(model, lower, upper)
    details = summary(model, mask, lower, upper)
    details["borated_water"] = {"material_id": water.id, "name": water.name,
                                "measured_boron_ppm_mass": measured_ppm,
                                "total_density_g_cm3": float(water.get_mass_density()),
                                "nuclide_mass_fractions": {n: float(water.get_mass_density(n) / water.get_mass_density())
                                                           for n in water.get_nuclides()}}
    return model, mesh, mask, lower, upper, details

def run_one(scenario, root, resume=True, purpose="pilot_not_validated_training_data"):
    source = cross_sections_source()
    definition = run_definition(scenario, source)
    run_id = digest(definition)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if resume:
        found = completed_run(root, run_id, definition)
        if found:
            return {"action": "skipped", "run_id": run_id, "folder": str(found)}
    folder = root / f"{run_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    status = {"state": "pending", "run_id": run_id, "scenario_id": scenario.scenario_id,
              "folder": str(folder), "purpose": purpose, "created_at": utc_now(),
              "physical_validation": "not_assessed"}
    write_json(folder / "status.json", status)
    write_json(folder / "scenario.json", scenario.definition())
    write_json(folder / "run_definition.json", definition)
    write_json(folder / "versions.json", {"python": sys.version, "openmc": openmc.__version__,
                                          "pipeline": __version__, "platform": platform.platform()})
    started = time.perf_counter()
    try:
        status.update(state="running", started_at=utc_now())
        write_json(folder / "status.json", status)
        model, mesh, mask, lower, upper, details = build_model(scenario)
        write_json(folder / "model_summary.json", details)
        model.export_to_xml(directory=folder)
        with (folder / "openmc.log").open("w", encoding="utf-8") as log:
            with redirect_stdout(log), redirect_stderr(log):
                statepoint = model.run(cwd=folder, threads=scenario.calculation.threads, output=True)
        statepoint = Path(statepoint)
        if not statepoint.is_file() or statepoint.stat().st_size == 0:
            raise RuntimeError("OpenMC returned no valid statepoint")
        result = extract(statepoint, mesh, mask, lower, upper, folder)
        status.update(state="completed", completed_at=utc_now(), elapsed_seconds=time.perf_counter() - started,
                      statepoint=statepoint.name, k_mean=result["k_mean"],
                      k_mc_standard_error=result["k_mc_standard_error"])
        write_json(folder / "status.json", status)
        return {"action": "completed", "run_id": run_id, "folder": str(folder),
                "k_mean": result["k_mean"], "k_mc_standard_error": result["k_mc_standard_error"]}
    except Exception as exc:
        status.update(state="failed", failed_at=utc_now(), elapsed_seconds=time.perf_counter() - started,
                      error=f"{type(exc).__name__}: {exc}")
        write_json(folder / "status.json", status)
        raise RuntimeError(f"Run failed in {folder}: {exc}") from exc



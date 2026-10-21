"""Read-only nominal v2 check and explicit, detached single-case launcher."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .beavrs3d import build_model, extract_3d, load_reference, nuclear_data_precheck, plot_integration_results, point_checks, validate_3d_outputs
from .experiments import PROJECT, _html_document, _html_table, _proc_start_ticks, process_alive, sha_file, write_json
from .parameter_space import MODEL_ID, build_proposed, resolve_proposed

MANIFEST = PROJECT / "manifests/beavrs3d_v2_nominal_integration_v1.json"
ROOT = PROJECT / "runs/beavrs_3d/v2_integration/beavrs3d_v2_nominal_integration_v1"
SCRIPT = PROJECT / "scripts/v2_integration.py"
EXPECTED_CONTROLS = {"u235_enrichment_wt_percent": 1.6, "fuel_temperature_K": 566.483,
                     "moderator_temperature_K": 566.483, "coolant_pressure_MPa": 15.51320325,
                     "elemental_boron_ppm": 975, "pin_pitch_cm": 1.25984,
                     "pellet_radius_cm": 0.39218, "insertion_percent": 50}
EXPECTED_CALC = {"batches": 100, "inactive": 50, "particles_per_generation": 10000,
                 "generations_per_batch": 1, "threads": 6, "seed": 61001}


def _now():
    return datetime.now(timezone.utc).isoformat()


def load_prepared():
    raw = MANIFEST.read_bytes()
    manifest = json.loads(raw.decode("utf-8-sig"))
    if manifest["group_id"] != ROOT.name or manifest["model"] != MODEL_ID:
        raise ValueError("Unexpected v2 integration identity")
    if (manifest["calculation"] != EXPECTED_CALC or manifest["controls"] != EXPECTED_CONTROLS or
            manifest["physical_acceptance"] != "not_assessed" or manifest["convergence"] != "review_required" or
            manifest["purpose"] != "single_small_code_integration_not_physical_acceptance"):
        raise ValueError("Integration budget/purpose changed")
    if manifest["reference_config"] != "configs/beavrs_derived_3d_reference.json" or sha_file(PROJECT / manifest["reference_config"]) != manifest["reference_config_sha256"]:
        raise ValueError("Pinned v1 reference changed")
    if manifest["beavrs_source_commit"] != "1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22":
        raise ValueError("Pinned source changed")
    if manifest["pressure_original"] != {"value": 2250, "unit": "psia", "kind": "absolute"} or manifest["psi_to_MPa"] != 0.006894757:
        raise ValueError("Pressure provenance changed")
    if abs(manifest["controls"]["coolant_pressure_MPa"] - 2250 * manifest["psi_to_MPa"]) > 1e-10:
        raise ValueError("Pressure conversion mismatch")
    return manifest


def _surfaces(assembly):
    return sorted((type(s).__name__, s.boundary_type, round(float(s.x0 if hasattr(s, "x0") else s.y0 if hasattr(s, "y0") else s.z0), 9))
                  for s in assembly.model.geometry.get_all_surfaces().values()
                  if s.boundary_type in ("reflective", "vacuum"))


def nominal_comparison(manifest=None):
    manifest = load_prepared() if manifest is None else manifest
    ref = load_reference(PROJECT / manifest["reference_config"])
    cfg, insertion = resolve_proposed(manifest["controls"], ref)
    calc = manifest["calculation"]
    kwargs = {"batches": calc["batches"], "inactive": calc["inactive"],
              "particles": calc["particles_per_generation"], "seed": calc["seed"]}
    old, new = build_model(ref, insertion, **kwargs), build_model(cfg, insertion, **kwargs)
    materials = {}
    for name, original in ref["materials"].items():
        proposed = cfg["materials"][name]
        # OpenMC treats the configured "ao" values as ratios and normalizes them
        # to the material mass density. Compare the actual generated atom densities.
        old_atoms = {k: float(v) for k, v in old.materials[name].get_nuclide_atom_densities().items()}
        new_atoms = {k: float(v) for k, v in new.materials[name].get_nuclide_atom_densities().items()}
        all_nuclides = sorted(set(old_atoms) | set(new_atoms))
        differences = {n: new_atoms.get(n, 0) - old_atoms.get(n, 0) for n in all_nuclides}
        materials[name] = {"old_density_g_cm3": original["density_g_cm3"],
                           "new_density_g_cm3": proposed["density_g_cm3"],
                           "density_difference_g_cm3": proposed["density_g_cm3"] - original["density_g_cm3"],
                           "density_relative_difference_percent": 100 * (proposed["density_g_cm3"] / original["density_g_cm3"] - 1),
                           "old_total_atom_density_atom_b_cm": sum(old_atoms.values()),
                           "new_total_atom_density_atom_b_cm": sum(new_atoms.values()),
                           "total_atom_density_difference_atom_b_cm": sum(differences.values()),
                           "old_temperature_K": original["temperature_K"],
                           "new_temperature_K": proposed["temperature_K"],
                           "source_table_atom_density_atom_b_cm": original["atom_density_atom_b_cm"],
                           "v2_resolved_atom_ratio_input": proposed["atom_density_atom_b_cm"],
                           "old_generated_atom_density_atom_b_cm": old_atoms,
                           "new_generated_atom_density_atom_b_cm": new_atoms,
                           "atom_density_difference_atom_b_cm": differences,
                           "max_abs_atom_density_difference_atom_b_cm": max(map(abs, differences.values()))}
    a, b = old.model.settings.source[0], new.model.settings.source[0]
    source_equal = (type(a.space) is type(b.space) and
                    list(a.space.lower_left) == list(b.space.lower_left) and
                    list(a.space.upper_right) == list(b.space.upper_right) and
                    a.constraints == b.constraints)
    ta, tb = old.model.tallies[0], new.model.tallies[0]
    tallies_equal = (ta.scores == tb.scores and ta.estimator == tb.estimator and
                     list(old.mesh.dimension) == list(new.mesh.dimension) and
                     list(old.mesh.lower_left) == list(new.mesh.lower_left) and
                     list(old.mesh.upper_right) == list(new.mesh.upper_right))
    return {"model_v1": ref["model"], "model_v2": cfg["model"],
            "pressure_psia_absolute": 2250, "pressure_MPa_absolute": manifest["controls"]["coolant_pressure_MPa"],
            "materials": materials,
            "geometry_config_equal": ref["geometry"] == cfg["geometry"],
            "external_boundaries_equal": _surfaces(old) == _surfaces(new),
            "external_boundaries": _surfaces(new),
            "source_equal": source_equal, "tallies_equal": tallies_equal,
            "temperature_method_equal": ref["temperature_method"] == cfg["temperature_method"],
            "water_density_method": cfg["water_density_method"],
            "interpretation": "v1 source-table composition versus v2 pressure-derived borated solution; equal control labels do not imply identical physical inputs"}


def preflight():
    manifest = load_prepared()
    comparison = nominal_comparison(manifest)
    if not all(comparison[key] for key in ("geometry_config_equal", "external_boundaries_equal", "source_equal", "tallies_equal", "temperature_method_equal")):
        raise ValueError("Unexpected v2/v1 geometry, source or tally mismatch")
    calc = manifest["calculation"]
    assembly = build_proposed(manifest["controls"], batches=calc["batches"], inactive=calc["inactive"],
                              particles=calc["particles_per_generation"], seed=calc["seed"])
    return {"manifest": str(MANIFEST), "manifest_sha256": sha_file(MANIFEST),
            "model": MODEL_ID, "calculation": calc, "controls": manifest["controls"],
            "comparison": comparison, "point_checks": point_checks(assembly),
            "nuclear_data": nuclear_data_precheck(assembly.materials, assembly.config),
            "transport_started": False}


def status():
    path = ROOT / "status.json"
    if not path.is_file():
        return {"state": "not_started", "folder": str(ROOT)}
    value = json.loads(path.read_text())
    process_path = ROOT / "process.json"
    process = json.loads(process_path.read_text()) if process_path.is_file() else {}
    return {**value, "pid": process.get("pid"), "process_alive": process_alive(process.get("pid"), process, ROOT, SCRIPT),
            "folder": str(ROOT), "log": str(ROOT / "openmc.log"), "status_file": str(path)}


def launch():
    check = preflight()
    ROOT.parent.mkdir(parents=True, exist_ok=True)
    ROOT.mkdir(exist_ok=False)  # atomic duplicate/completed/failed guard: no implicit resume
    with (ROOT / "manifest.json").open("xb") as out:
        out.write(MANIFEST.read_bytes())
    os.chmod(ROOT / "manifest.json", 0o444)
    write_json(ROOT / "preflight.json", check)
    write_json(ROOT / "status.json", {"state": "queued", "purpose": "code_integration_only",
                                      "manifest_sha256": sha_file(ROOT / "manifest.json"),
                                      "physical_acceptance": "not_assessed", "convergence": "review_required",
                                      "created_at": _now(), "error": None})
    with (ROOT / "openmc.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(SCRIPT), "worker"], cwd=PROJECT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True, close_fds=True)
    write_json(ROOT / "process.json", {"pid": process.pid, "started_at": _now(),
                                          "start_ticks": _proc_start_ticks(process.pid),
                                          "launcher": str(SCRIPT.resolve()),
                                          "worker_folder": str(ROOT.resolve())})
    return status()


def worker():
    saved = json.loads((ROOT / "manifest.json").read_text())
    if sha_file(ROOT / "manifest.json") != status()["manifest_sha256"] or saved != load_prepared():
        raise ValueError("Immutable v2 manifest mismatch")
    check = json.loads((ROOT / "preflight.json").read_text())
    calc = saved["calculation"]
    assembly = build_proposed(saved["controls"], batches=calc["batches"], inactive=calc["inactive"],
                              particles=calc["particles_per_generation"], seed=calc["seed"])
    record = status()
    record.update(state="running", started_at=_now())
    write_json(ROOT / "status.json", {k: v for k, v in record.items() if k not in ("pid", "process_alive", "folder", "log", "status_file")})
    start = time.perf_counter()
    try:
        write_json(ROOT / "resolved_config.json", {"model": MODEL_ID, "config": assembly.config,
                                                    "calculation": calc, "manifest_sha256": sha_file(ROOT / "manifest.json"),
                                                    "nuclear_data": check["nuclear_data"]})
        assembly.model.export_to_xml(directory=ROOT)
        with (ROOT / "openmc.log").open("a", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
            statepoint = Path(assembly.model.run(cwd=ROOT, threads=calc["threads"], geometry_debug=True, output=True))
        if not statepoint.is_file() or not statepoint.stat().st_size:
            raise RuntimeError("Missing statepoint")
        result = extract_3d(statepoint, assembly, ROOT, time.perf_counter()-start,
                            check["nuclear_data"], purpose=saved["purpose"])
        validate_3d_outputs(ROOT, expected_model=MODEL_ID)
        shutil.copy2(ROOT / result["result_arrays"], ROOT / "fields.npz")
        plot_integration_results(ROOT)
        summary = {"model": MODEL_ID, "completion_state": "completed",
                   "physical_acceptance": "not_assessed", "convergence": "review_required",
                   "k_effective": {"mean": result["k_mean"], "mc_standard_error": result["k_mc_standard_error"], "unit": "dimensionless"},
                   "duration": {"value": result["elapsed_seconds"], "unit": "s"},
                   "water_density": {"value": assembly.config["materials"]["water"]["density_g_cm3"], "unit": "g/cm3"},
                   "array_order": ["z", "y", "x"], "fields": "fields.npz", "statepoint": statepoint.name,
                   "quality_message": "integration complete; physical/statistical review required"}
        write_json(ROOT / "summary.json", summary)
        rows = [("Model", MODEL_ID), ("Amaç", saved["purpose"]), ("Durum", "completed; fiziksel kabul yok"),
                ("Yakınsama", "inceleme gerekli"), ("Süre (s)", result["elapsed_seconds"]),
                ("k ± MC hata", f"{result['k_mean']:.6f} ± {result['k_mc_standard_error']:.6f}"),
                ("Su yoğunluğu (g/cm³)", summary["water_density"]["value"])]
        body = _html_table(("Alan", "Değer"), rows)
        body += "<p>MC standart hata fiziksel doğruluk yüzdesi değildir. V2 çözeltisi v1 kaynak tablosuyla aynı yoğunlukta değildir.</p>"
        body += "<img src='axial_profiles.png' alt='Eksenel profil'><img src='history.png' alt='k ve entropi geçmişi'>"
        (ROOT / "report.html").write_text(_html_document("V2 nominal entegrasyon", body), encoding="utf-8")
        record.update(state="completed", completed_at=_now(), elapsed_seconds=result["elapsed_seconds"],
                      statepoint=statepoint.name)
        write_json(ROOT / "status.json", {k: v for k, v in record.items() if k not in ("pid", "process_alive", "folder", "log", "status_file")})
    except Exception as exc:
        record.update(state="failed", error=f"{type(exc).__name__}: {exc}", elapsed_seconds=time.perf_counter()-start)
        write_json(ROOT / "status.json", {k: v for k, v in record.items() if k not in ("pid", "process_alive", "folder", "log", "status_file")})
        raise

"""User-operated detached WSL runner for approved v2 packages.

Only explicit launch() starts transport. No automatic resume is provided.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import csv
import fcntl
import html
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

import openmc
import numpy as np

from .beavrs3d import extract_3d, nuclear_data_precheck, plot_integration_results, point_checks, validate_3d_outputs
from .experiments import _html_document, _html_table, PILOT_SECONDS_PER_HISTORY, ESTIMATE_FACTOR, _proc_start_ticks, process_alive
from .parameter_space import MODEL_ID, build_proposed, resolve_proposed
from .v2_students import PROJECT, digest, identity, verify_package, _read

GROUPS = PROJECT / "runs/beavrs_3d/v2_groups"
SCRIPT = PROJECT / "scripts/v2_student_production.py"
# Measured D2-B2: 600 x 80,000 histories in 1041.67823256 s. A 1.5x planning
# factor is descriptive only; the 4 h timer is the actual hard group ceiling.
D2_B2_MEASURED_SECONDS = 1041.6782325600016
D2_B2_HISTORIES = 600 * 80000


def _estimate_seconds(calc):
    if (calc["batches"], calc["inactive"], calc["particles_per_generation"],
            calc["generations_per_batch"], calc["threads"]) == (600, 300, 80000, 1, 6):
        return D2_B2_MEASURED_SECONDS * ESTIMATE_FACTOR
    return (calc["batches"] * calc["particles_per_generation"] *
            calc["generations_per_batch"] * PILOT_SECONDS_PER_HISTORY * ESTIMATE_FACTOR)


def _relative_stats(mean, std, selector):
    valid = selector & (mean > 0) & np.isfinite(mean) & np.isfinite(std)
    values = std[valid] / mean[valid]
    return {"voxels": int(np.count_nonzero(selector)), "positive_mean_voxels": int(values.size),
            "zero_mean_voxels": int(np.count_nonzero(selector & (mean == 0))),
            "undefined_relative_error_voxels": int(np.count_nonzero(selector) - values.size),
            "median": float(np.median(values)) if values.size else None,
            "p95": float(np.percentile(values, 95)) if values.size else None,
            "maximum": float(np.max(values)) if values.size else None}


def _pilot_diagnostics(fields_path, elapsed_seconds, estimate_seconds, inactive_batches):
    with np.load(fields_path, allow_pickle=False) as a:
        fuel = a["fuel_volume_fraction"] > 0  # fixed geometry, independent of score
        fission, fse = a["fission_mean"], a["fission_std_dev"]
        energy, ese = a["kappa_fission_mean"], a["kappa_fission_std_dev"]
        maximum = float(np.max(fission))
        low = fuel & ((fission == 0) | (fission < 5 * fse) |
                      (fission < 1e-6 * maximum))
        positive = np.sort(fission[fuel][fission[fuel] > 0])[::-1]
        cutoff = 0.0
        if positive.size and positive.sum() > 0:
            cutoff = float(positive[min(int(np.searchsorted(np.cumsum(positive),
                                          .95 * positive.sum())), positive.size-1)])
        important = fuel & (fission >= cutoff) & (fission > 0)
        old_filter = a["relative_error_reporting_mask"]
        axial_f = fission.sum(axis=(1, 2))
        axial_e = energy.sum(axis=(1, 2))
        def shares(x):
            total = float(x.sum())
            return (x / total).tolist() if total > 0 else None
        return {
            "definition": "descriptive fixed-geometric-mask pilot diagnostics, not physical acceptance",
            "fuel_intersecting_voxels": int(fuel.sum()),
            "zero_fission_mean_voxels": int(np.count_nonzero(fuel & (fission == 0))),
            "zero_kappa_fission_mean_voxels": int(np.count_nonzero(fuel & (energy == 0))),
            "zero_mean_interpretation": "No recorded tally is not proof of zero production or zero uncertainty",
            "low_signal_definition": "within fuel: fission mean=0 or mean<5*MC SE or mean<1e-6 of maximum",
            "low_signal_voxels": int(low.sum()),
            "previous_reliability_filter_voxels": int(old_filter.sum()),
            "important_definition": "positive-mean voxels contributing first 95% of measured total fission; descriptive",
            "important_voxels": int(important.sum()),
            "low_signal_fission_share": float(fission[low].sum() / fission[fuel].sum()) if fission[fuel].sum() > 0 else None,
            "low_signal_kappa_share": float(energy[low].sum() / energy[fuel].sum()) if energy[fuel].sum() > 0 else None,
            "important_fission_share": float(fission[important].sum() / fission[fuel].sum()) if fission[fuel].sum() > 0 else None,
            "fission_relative_mc_error": {"all_geometric_fuel": _relative_stats(fission, fse, fuel),
                                         "low_signal": _relative_stats(fission, fse, low),
                                         "important_95pct": _relative_stats(fission, fse, important),
                                         "outside_previous_filter": _relative_stats(fission, fse, fuel & ~old_filter)},
            "kappa_fission_relative_mc_error": {"all_geometric_fuel": _relative_stats(energy, ese, fuel),
                                               "low_signal": _relative_stats(energy, ese, low),
                                               "important_95pct": _relative_stats(energy, ese, important),
                                               "outside_previous_filter": _relative_stats(energy, ese, fuel & ~old_filter)},
            "axial_fission_share": shares(axial_f),
            "axial_kappa_fission_share": shares(axial_e),
            "z_edges_cm": a["z_edges_cm"].tolist(),
            "k_generation": a["k_generation"].tolist(),
            "shannon_entropy": a["shannon_entropy"].tolist(),
            "inactive_batches": int(inactive_batches),
            "duration_estimate_seconds": float(estimate_seconds),
            "duration_actual_seconds": float(elapsed_seconds),
            "duration_minus_estimate_seconds": float(elapsed_seconds - estimate_seconds),
            "estimate_basis": "D2-B2 measured 1041.67823256 s x 1.5; not a guarantee",
        }



def _write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def _manifest(package):
    verify_package(package, require_approval=False)
    return _read(Path(package) / "manifest.json")


def _group(package):
    return GROUPS / Path(package).resolve().name


def preflight(package):
    manifest = _manifest(package)
    cases = []
    for case in manifest["experiments"]:
        cfg, insertion = resolve_proposed(case["controls"])
        calc = case["calculation"]
        if (calc["generations_per_batch"] != 1 or calc["inactive"] >= calc["batches"] or
                calc["threads"] < 1 or calc["particles_per_generation"] < 1):
            raise ValueError("Invalid v2 calculation profile")
        assembly = build_proposed(case["controls"], batches=calc["batches"],
                                  inactive=calc["inactive"], particles=calc["particles_per_generation"],
                                  seed=calc["seed"])
        cases.append({"experiment_id": case["experiment_id"], "scenario_id": case["scenario_id"],
                      "geometry_checks": len(point_checks(assembly)),
                      "water_density_g_cm3": cfg["materials"]["water"]["density_g_cm3"],
                      "nuclear_data": nuclear_data_precheck(assembly.materials, cfg)["coverage_result"],
                      "calculation": calc})
    return {"group_id": manifest["group_id"], "cases": cases,
            "production_gate": manifest["production_gate"], "transport_started": False}


def status(package):
    group = _group(package)
    path = group / "status.json"
    if not path.is_file():
        return {"state": "not_started", "group_dir": str(group),
                "status_file": str(path), "group_log": str(group / "group.log")}
    record = _read(path)
    process_path = group / "process.json"
    process = _read(process_path) if process_path.is_file() else {}
    return {**record, "pid": process.get("pid"), "process_alive": process_alive(process.get("pid"), process, group, SCRIPT),
            "group_dir": str(group), "status_file": str(path), "group_log": str(group / "group.log")}


def launch(package):
    package = Path(package).resolve()
    verify_package(package, require_approval=True)
    check = preflight(package)
    manifest = _manifest(package)
    if manifest["group_runtime_budget_seconds"] is None:
        raise ValueError("Production budget has not been approved")
    GROUPS.mkdir(parents=True, exist_ok=True)
    group = _group(package)
    group.mkdir(exist_ok=False)  # atomic guard; completed/failed/stopped never restart here
    try:
        shutil.copy2(package / "manifest.json", group / "manifest.json")
        os.chmod(group / "manifest.json", 0o444)
        _write(group / "preflight.json", check)
        _write(group / "status.json", {"state": "queued", "group_id": manifest["group_id"],
               "manifest_sha256": digest(group / "manifest.json"),
               "physical_acceptance": "not_assessed", "quality_status": "review_required",
               "completed_experiments": [], "budget_consumed_seconds": 0.0, "error": None})
        _comparison(group, manifest)
        with (group / "group.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(SCRIPT), "worker", str(package)],
                         cwd=PROJECT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True, close_fds=True)
        _write(group / "process.json", {"pid": process.pid, "launcher": str(SCRIPT.resolve()),
                                               "worker_folder": str(group.resolve()),
                                               "start_ticks": _proc_start_ticks(process.pid)})
        return status(package)
    except Exception as exc:
        if (group / "status.json").is_file():
            record = _read(group / "status.json")
            record.update(state="failed", error=f"{type(exc).__name__}: {exc}")
            _write(group / "status.json", record)
        raise


def _case_record(group, case):
    case_dir = group / "experiments" / case["experiment_id"]
    if not case_dir.is_dir():
        return "not_started", None, None
    attempts = sorted(case_dir.glob("attempt_*"))
    if not attempts:
        return "not_started", None, None
    attempt = attempts[-1]
    st = _read(attempt / "status.json")
    summary_path = attempt / "summary.json"
    return st["state"], _read(summary_path) if summary_path.is_file() else None, attempt


def _comparison(group, manifest):
    rows = []
    for case in manifest["experiments"]:
        state, summary, attempt = _case_record(group, case)
        calc = case["calculation"]
        rows.append({"experiment_id": case["experiment_id"], "scenario_id": case["scenario_id"],
                     "state": state, "attempt": str(attempt) if attempt else "",
                     "seed": calc["seed"], "batches": calc["batches"], "inactive": calc["inactive"],
                     "particles_per_generation": calc["particles_per_generation"],
                     "k_mean": summary.get("k_effective", {}).get("mean") if summary else None,
                     "k_mc_standard_error": summary.get("k_effective", {}).get("mc_standard_error") if summary else None,
                     "physical_acceptance": "not_assessed", "quality_status": "review_required"})
    with (group / "comparison.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    body = "<p>Completed means outputs exist; physical and convergence review remain required.</p>"
    body += _html_table(list(rows[0]), ([row[k] for k in rows[0]] for row in rows))
    (group / "comparison.html").write_text(_html_document(manifest["group_id"], body), encoding="utf-8")


def saved_results(package):
    manifest = _manifest(package)
    group = _group(package)
    return {"group": status(package), "cases": [
        {"experiment_id": case["experiment_id"], "scenario_id": case["scenario_id"],
         "state": state, "summary": summary, "attempt": str(attempt) if attempt else None,
         "physical_acceptance": "not_assessed", "statistical_convergence": "review_required"}
        for case in manifest["experiments"]
        for state, summary, attempt in [_case_record(group, case)]]}


def _run_case(group, manifest, case, package_ledger_sha256):
    case_dir = group / "experiments" / case["experiment_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    attempt = case_dir / ("attempt_" + uuid.uuid4().hex)
    attempt.mkdir()
    (attempt / "openmc.log").touch()
    calc = case["calculation"]
    cfg, insertion = resolve_proposed(case["controls"])
    assembly = build_proposed(case["controls"], batches=calc["batches"], inactive=calc["inactive"],
                              particles=calc["particles_per_generation"], seed=calc["seed"])
    nuclear = nuclear_data_precheck(assembly.materials, cfg)
    run_id = identity({"scenario_id": case["scenario_id"], "calculation": calc,
                       "model": MODEL_ID, "reference_config_sha256": manifest["reference_config_sha256"],
                       "package_ledger_sha256": package_ledger_sha256,
                       "cross_sections_xml_sha256": nuclear["cross_sections_xml_sha256"]})
    resolved = {"model": MODEL_ID, "scenario_id": case["scenario_id"], "run_id": run_id,
                "group_id": manifest["group_id"], "experiment_id": case["experiment_id"],
                "controls": case["controls"], "resolved_config": cfg, "calculation": calc,
                "reference_config_sha256": manifest["reference_config_sha256"],
                "nuclear_data": nuclear, "package_ledger_sha256": package_ledger_sha256,
                "temperature_method": cfg["temperature_method"],
                "openmc_version": openmc.__version__, "python_executable": sys.executable}
    _write(attempt / "resolved_config.json", resolved)
    record = {"state": "running", "scenario_id": case["scenario_id"], "run_id": run_id,
              "experiment_id": case["experiment_id"], "physical_acceptance": "not_assessed",
              "quality_status": "review_required", "error": None}
    _write(attempt / "status.json", record)
    start = time.monotonic()
    try:
        point_checks(assembly)
        assembly.model.export_to_model_xml(path=attempt / "model.xml")
        with (attempt / "openmc.log").open("a", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
            statepoint = Path(assembly.model.run(cwd=attempt, threads=calc["threads"], output=True, export_model_xml=True))
        if not statepoint.is_file() or statepoint.stat().st_size == 0:
            raise RuntimeError("Missing or empty statepoint")
        result = extract_3d(statepoint, assembly, attempt, time.monotonic()-start, nuclear,
                            purpose="controlled_v2_pilot_research_subject_to_review")
        validate_3d_outputs(attempt, expected_model=MODEL_ID)
        shutil.copy2(attempt / result["result_arrays"], attempt / "fields.npz")
        plot_integration_results(attempt)
        diagnostics = _pilot_diagnostics(attempt / "fields.npz", result["elapsed_seconds"],
                                         _estimate_seconds(calc), calc["inactive"])
        summary = {"model": MODEL_ID, "scenario_id": case["scenario_id"], "run_id": run_id,
                   "experiment_id": case["experiment_id"], "completion_state": "completed",
                   "physical_acceptance": "not_assessed", "quality_status": "review_required",
                   "statistical_convergence": "review_required",
                   "k_effective": {"mean": result["k_mean"], "mc_standard_error": result["k_mc_standard_error"],
                                   "unit": "dimensionless"},
                   "duration": {"value": result["elapsed_seconds"], "unit": "s"},
                   "array_order": ["z", "y", "x"], "mesh_shape_zyx": list(result["mesh_shape_zyx"]),
                   "field_units": result["raw_units"], "statepoint": statepoint.name,
                   "pilot_diagnostics": diagnostics}
        _write(attempt / "summary.json", summary)
        body = _html_table(("field", "value"), [("experiment", case["experiment_id"]),
                ("k", summary["k_effective"]["mean"]), ("MC standard error", summary["k_effective"]["mc_standard_error"]),
                ("seconds", result["elapsed_seconds"]), ("acceptance", "not_assessed"),
                ("convergence", "review_required")])
        body += "<p>Completed is output integrity only; physical and statistical review required. " \
                "Zero tallies do not prove zero production or zero uncertainty.</p>"
        body += _html_table(("diagnostic", "value"), [
            ("geometric fuel voxels", diagnostics["fuel_intersecting_voxels"]),
            ("zero fission tally voxels", diagnostics["zero_fission_mean_voxels"]),
            ("low signal fuel voxels", diagnostics["low_signal_voxels"]),
            ("low signal fission share", diagnostics["low_signal_fission_share"]),
            ("low signal kappa share", diagnostics["low_signal_kappa_share"]),
            ("important fission share", diagnostics["important_fission_share"]),
            ("previous filter included", diagnostics["previous_reliability_filter_voxels"]),
            ("duration estimate s", diagnostics["duration_estimate_seconds"]),
            ("actual minus estimate s", diagnostics["duration_minus_estimate_seconds"]),
        ])
        for score in ("fission", "kappa_fission"):
            body += _html_table((score + " relative MC error", "statistics"), [
                (name, json.dumps(stats)) for name, stats in
                diagnostics[score + "_relative_mc_error"].items()])
        body += _html_table(("axial bin", "fission share", "kappa-fission share"), [
            (i+1, diagnostics["axial_fission_share"][i], diagnostics["axial_kappa_fission_share"][i])
            for i in range(len(diagnostics["axial_fission_share"]))])
        body += "<p>Histories include the inactive-to-active transition at batch 300. " \
                "kappa-fission approximates fission energy production, not total heat deposition.</p>"
        body += "<img src='axial_profiles.png'><img src='history.png'>"
        (attempt / "report.html").write_text(_html_document(case["experiment_id"], body), encoding="utf-8")
        required = ["model.xml", "resolved_config.json", "summary.json", "fields.npz", "openmc.log",
                    "report.html", statepoint.name]
        if not all((attempt / x).is_file() and (attempt / x).stat().st_size for x in required):
            raise RuntimeError("Incomplete output bundle")
        record.update(state="completed", elapsed_seconds=result["elapsed_seconds"], statepoint=statepoint.name)
        _write(attempt / "status.json", record)
        return record
    except BaseException as exc:
        record.update(state="failed", error=f"{type(exc).__name__}: {exc}",
                      elapsed_seconds=time.monotonic()-start)
        _write(attempt / "status.json", record)
        raise


def _worker_locked(package):
    package = Path(package).resolve()
    verify_package(package, require_approval=True)
    group = _group(package)
    manifest = _manifest(package)
    record = _read(group / "status.json")
    if digest(group / "manifest.json") != record["manifest_sha256"] or _read(group / "manifest.json") != manifest:
        raise ValueError("Saved manifest differs from approved package")
    if record["state"] != "queued":
        raise RuntimeError("Worker may start only once from queued state")
    budget = manifest["group_runtime_budget_seconds"] - record.get("budget_consumed_seconds", 0.0)
    if not isinstance(budget, (int, float)) or budget <= 0:
        raise ValueError("Missing approved runtime budget")
    start = time.monotonic()
    expired = threading.Event()
    def stop_budget():
        expired.set()
        try:
            os.killpg(os.getpid(), signal.SIGTERM)
        except ProcessLookupError:
            pass
    def on_term(signum, frame):
        raise InterruptedError("Worker process group stopped")
    signal.signal(signal.SIGTERM, on_term)
    timer = threading.Timer(budget, stop_budget)
    timer.daemon = True
    timer.start()
    record["state"] = "running"
    _write(group / "status.json", record)
    try:
        for case in manifest["experiments"]:
            if case["experiment_id"] in record["completed_experiments"]:
                continue
            calc = case["calculation"]
            estimate = _estimate_seconds(calc)
            if estimate > budget - (time.monotonic() - start):
                record.update(state="budget_exhausted", error="Next case estimate exceeds remaining group budget; estimate is not a guarantee")
                break
            _run_case(group, manifest, case, digest(package / "SHA256SUMS.json"))
            record["completed_experiments"].append(case["experiment_id"])
            _write(group / "status.json", record)
            _comparison(group, manifest)
        else:
            record["state"] = "completed"
        if expired.is_set():
            record.update(state="budget_exhausted", error="Group runtime budget interrupted active case")
    except BaseException as exc:
        record.update(state="budget_exhausted" if expired.is_set() else "stopped" if (group / "stop.requested").exists() else "failed",
                      error=f"{type(exc).__name__}: {exc}")
    finally:
        timer.cancel()
        record["elapsed_seconds"] = time.monotonic() - start
        record["budget_consumed_seconds"] = record.get("budget_consumed_seconds", 0.0) + record["elapsed_seconds"]
        _write(group / "status.json", record)
        _comparison(group, manifest)


def resume(package):
    """Explicit operator action; never called by notebooks on Run All."""
    package = Path(package).resolve()
    verify_package(package, require_approval=True)
    group = _group(package)
    with (group / "dispatch.lock").open("a+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        current = status(package)
        if current["state"] not in ("failed", "stopped") or current["process_alive"]:
            raise RuntimeError("Only idle failed/stopped v2 group can be resumed explicitly")
        manifest = _manifest(package)
        if digest(group / "manifest.json") != current["manifest_sha256"]:
            raise ValueError("Saved manifest changed")
        if current.get("budget_consumed_seconds", 0.0) >= manifest["group_runtime_budget_seconds"]:
            raise RuntimeError("Group runtime budget exhausted")
        (group / "stop.requested").unlink(missing_ok=True)
        record = _read(group / "status.json")
        record.update(state="queued", error=None)
        _write(group / "status.json", record)
        with (group / "group.log").open("a", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, str(SCRIPT), "worker", str(package)],
                         cwd=PROJECT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True, close_fds=True)
        _write(group / "process.json", {"pid": process.pid, "launcher": str(SCRIPT.resolve()),
                                               "worker_folder": str(group.resolve()),
                                               "start_ticks": _proc_start_ticks(process.pid)})
        return status(package)


def stop(package):
    """Explicitly terminate only the verified v2 worker process group."""
    current = status(package)
    pid = current.get("pid")
    group = _group(package)
    if not pid or not current.get("process_alive"):
        return {"signal_sent": False, "state": current["state"]}
    cmdline = Path(f"/proc/{pid}/cmdline")
    if not cmdline.is_file() or str(Path(package).resolve()).encode() not in cmdline.read_bytes():
        raise RuntimeError("Worker PID identity not verified")
    if os.getpgid(pid) != pid:
        raise RuntimeError("Worker is not the process group leader")
    (group / "stop.requested").touch()
    os.killpg(pid, signal.SIGTERM)
    return {"signal_sent": True, "pid": pid, "status_file": current["status_file"]}



def worker(package):
    group = _group(package)
    with (group / 'group.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another v2 worker owns this group') from exc
        return _worker_locked(package)





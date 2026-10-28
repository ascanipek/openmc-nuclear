"""User-operated, detached manifest runner for BEAVRS-derived 3D experiments.

No command other than explicit 'launch' or 'resume' starts transport.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import threading
import uuid

import openmc

from .beavrs3d import (
    MODEL_ID, build_model, extract_3d, load_reference,
    nuclear_data_precheck, plot_integration_results, point_checks,
    validate_3d_outputs,
)

PROJECT = Path(__file__).resolve().parents[2]
MANIFESTS = PROJECT / "manifests"
GROUPS = PROJECT / "runs" / "beavrs_3d" / "groups"
SCRIPT = PROJECT / "scripts" / "experiments.py"
STOP_FLAG = False
BUDGET_EXPIRED = False
PILOT_SECONDS_PER_HISTORY = 34.430837549998614 / 1_000_000
ESTIMATE_FACTOR = 1.5
CALC_KEYS = {"batches", "inactive", "particles_per_generation",
             "generations_per_batch", "threads", "seed"}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(Path(path).read_bytes())


def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def load_manifest(path):
    path = Path(path).resolve()
    if path.parent != MANIFESTS.resolve() or path.suffix != ".json":
        raise ValueError("Only prepared JSON files in manifests/ are accepted")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    expected = {"schema_version", "model", "reference_config", "reference_config_sha256",
                "physical_acceptance", "group_id", "phase", "title", "depends_on", "experiments",
                "group_runtime_budget_seconds"}
    if set(data) != expected or data["schema_version"] != 1 or data["model"] != MODEL_ID:
        raise ValueError("Unsupported or noncanonical experiment manifest")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", data["group_id"]):
        raise ValueError("Invalid group ID")
    if data["phase"] not in ("D2", "D3", "D4") or data["physical_acceptance"] != "review_required":
        raise ValueError("Invalid phase/quality declaration")
    if type(data["group_runtime_budget_seconds"]) is not int or data["group_runtime_budget_seconds"] != 14400:
        raise ValueError("Prepared group runtime budget must be 14400 seconds")
    if not isinstance(data["depends_on"], list) or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", item)
            for item in data["depends_on"]):
        raise ValueError("Invalid dependency list")
    if not isinstance(data["experiments"], list) or not 1 <= len(data["experiments"]) <= 12:
        raise ValueError("Expected 1–12 prepared experiments")
    ref_rel = Path(data["reference_config"])
    if ref_rel != Path("configs/beavrs_derived_3d_reference.json"):
        raise ValueError("Reference configuration path is not pinned")
    ref_path = PROJECT / ref_rel
    if sha_file(ref_path) != data["reference_config_sha256"]:
        raise ValueError("Reference config hash differs from prepared manifest")
    cfg = load_reference(ref_path)
    if cfg["model"] != data["model"]:
        raise ValueError("Reference model mismatch")
    ids = set()
    for case in data["experiments"]:
        if set(case) != {"experiment_id", "insertion_percent", "calculation"}:
            raise ValueError("Invalid experiment keys")
        case_id = case["experiment_id"]
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9-]*", case_id) or case_id in ids:
            raise ValueError("Invalid or duplicate experiment ID")
        ids.add(case_id)
        insertion = case["insertion_percent"]
        if isinstance(insertion, bool) or insertion not in (0, 50, 100):
            raise ValueError("Only prepared 0, 50 and 100 percent cases are supported")
        calc = case["calculation"]
        if set(calc) != CALC_KEYS:
            raise ValueError("Invalid calculation keys")
        if any(type(calc[key]) is not int or calc[key] < 1 for key in CALC_KEYS-{"inactive"}):
            raise ValueError("Invalid positive integer calculation value")
        if type(calc["inactive"]) is not int or not 0 <= calc["inactive"] < calc["batches"]:
            raise ValueError("Invalid inactive batches")
        if calc["generations_per_batch"] != 1 or calc["threads"] != 6:
            raise ValueError("This prepared runner fixes one generation and six threads")
    return path, data, cfg


def preflight(manifest_path):
    path, manifest, cfg = load_manifest(manifest_path)
    insertions = sorted({case["insertion_percent"] for case in manifest["experiments"]})
    checks = {}
    for insertion in insertions:
        checks[str(insertion)] = point_checks(build_model(cfg, insertion))
    nuclear = nuclear_data_precheck(build_model(cfg, insertions[0]).materials, cfg)
    rows = []
    for case in manifest["experiments"]:
        calc = case["calculation"]
        rows.append({
            "group_id": manifest["group_id"], "phase": manifest["phase"],
            "experiment_id": case["experiment_id"],
            "model": MODEL_ID, "insertion_percent": case["insertion_percent"],
            "boron_ppm": cfg["elemental_boron_ppm"],
            "water_density_g_cm3": cfg["materials"]["water"]["density_g_cm3"],
            "fuel_density_g_cm3": cfg["materials"]["fuel"]["density_g_cm3"],
            "temperature_K": cfg["operating_temperature_K"],
            **calc,
            "active_batches": calc["batches"]-calc["inactive"],
            "active_histories": (calc["batches"]-calc["inactive"]) *
                                calc["particles_per_generation"],
            "total_histories": calc["batches"] * calc["particles_per_generation"],
            "estimated_seconds_from_pilot_with_factor_1p5": (
                calc["batches"] * calc["particles_per_generation"] *
                PILOT_SECONDS_PER_HISTORY * ESTIMATE_FACTOR),
        })
    return {"manifest_path": str(path), "group_id": manifest["group_id"],
            "phase": manifest["phase"], "depends_on": manifest["depends_on"],
            "reference_config_sha256": manifest["reference_config_sha256"],
            "group_runtime_budget_seconds": manifest["group_runtime_budget_seconds"],
            "initial_group_estimated_seconds": sum(
                row["estimated_seconds_from_pilot_with_factor_1p5"] for row in rows),
            "estimate_is_guarantee": False,
            "geometry_point_checks": {k: len(v) for k, v in checks.items()},
            "nuclear_data": nuclear, "experiments": rows,
            "transport_started": False}


def group_dir(group_id):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", group_id):
        raise ValueError("Invalid group ID")
    return GROUPS / group_id


def read_group(group_id):
    folder = group_dir(group_id)
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Group not found: {folder}")
    manifest_bytes = manifest_path.read_bytes()
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    if sha_bytes(manifest_bytes) != status["manifest_sha256"]:
        raise ValueError("Immutable group manifest checksum mismatch")
    manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    return folder, manifest, status


def _proc_start_ticks(pid):
    """Linux /proc field 22; independent of wall-clock time and PID reuse."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = raw.rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return int(fields[19])
    except (OSError, IndexError, ValueError):
        return None


def process_alive(pid, process=None, folder=None, script=None):
    """Require saved worker identity, start ticks, command and process group."""
    if not isinstance(pid, int) or pid < 1 or not isinstance(process, dict) or folder is None:
        return False
    expected = process.get("start_ticks")
    launcher = str(Path(script or SCRIPT).resolve())
    if not isinstance(expected, int) or expected < 1 or process.get("launcher") != launcher:
        return False
    if process.get("worker_folder") != str(Path(folder).resolve()):
        return False
    if _proc_start_ticks(pid) != expected:
        return False
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        if (launcher.encode() not in args or b"worker" not in args or
                str(Path(folder).resolve()).encode() not in args or os.getpgid(pid) != pid):
            return False
        os.killpg(pid, 0)
    except (OSError, ValueError):
        return False
    return True

def _budget_used_seconds(status, include_active=False):
    used = float(status.get("budget_consumed_seconds", 0.0))
    started = status.get("active_session_started_at")
    if include_active and started:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()
        used += max(0.0, elapsed)
    return used


def _checkpoint_budget(status):
    status["budget_consumed_seconds"] = _budget_used_seconds(status, True)
    status["active_session_started_at"] = now()


def _estimate_case_seconds(folder, manifest, case):
    # Pilot is the saved 100-batch, 10k-particle integration; a heuristic, not a guarantee.
    rates = [PILOT_SECONDS_PER_HISTORY]
    for prior in manifest["experiments"]:
        attempt = _completed_attempt(folder, prior["experiment_id"])
        if attempt is None:
            continue
        try:
            summary = json.loads((attempt / "summary.json").read_text(encoding="utf-8"))
            total = prior["calculation"]["batches"] * prior["calculation"]["particles_per_generation"]
            duration = float(summary["duration"]["value"])
            if total > 0 and duration > 0:
                rates.append(duration / total)
        except (OSError, KeyError, TypeError, ValueError):
            continue
    histories = case["calculation"]["batches"] * case["calculation"]["particles_per_generation"]
    return histories * max(rates) * ESTIMATE_FACTOR

def group_status(group_id):
    folder, manifest, status = read_group(group_id)
    process = folder / "process.json"
    proc = json.loads(process.read_text(encoding="utf-8")) if process.is_file() else {}
    pid = proc.get("pid")
    return {
        "group_id": group_id, "state": status["state"],
        "phase": manifest["phase"], "pid": pid, "process_alive": process_alive(pid, proc, folder),
        "observed_at_utc": now(),
        "group_dir": str(folder), "group_log": str(folder / "group.log"),
        "status_file": str(folder / "status.json"),
        "comparison_csv": str(folder / "comparison.csv"),
        "comparison_html": str(folder / "comparison.html"),
        "group_runtime_budget_seconds": manifest["group_runtime_budget_seconds"],
        "budget_consumed_seconds": _budget_used_seconds(status, status["state"] == "running"),
        "budget_remaining_seconds": max(0.0, manifest["group_runtime_budget_seconds"] -
                                        _budget_used_seconds(status, status["state"] == "running")),
        "budget_reason": status.get("budget_reason"),
        "current_experiment": status.get("current_experiment"),
        "completed_experiments": status.get("completed_experiments", []),
        "error": status.get("error"),
        "physical_acceptance": "not_assessed",
        "quality_status": "review_required",
    }


def _check_dependencies(manifest):
    for parent in manifest["depends_on"]:
        folder, _, status = read_group(parent)
        review_path = folder / "review.json"
        review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
        if status["state"] != "completed" or review.get("operator_acknowledged") is not True:
            raise RuntimeError(f"Dependency {parent} needs completion and explicit review acknowledgement")


def _spawn(folder):
    with (folder / "group.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "worker", str(folder)],
            cwd=PROJECT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True)
    write_json(folder / "process.json", {"pid": process.pid, "started_at": now(),
                                         "start_ticks": _proc_start_ticks(process.pid),
                                         "launcher": str(SCRIPT.resolve()),
                                         "worker_folder": str(folder.resolve()),
                                         "session_leader": True})
    return {"pid": process.pid, "group_log": str(folder / "group.log"),
            "status_file": str(folder / "status.json"), "group_dir": str(folder)}


def launch(manifest_path):
    info = preflight(manifest_path)
    path, manifest, _ = load_manifest(manifest_path)
    if manifest["phase"] in ("D3", "D4"):
        from .student_package import verify
        verify(PROJECT / "student_packages" / manifest["group_id"], require_approval=True)
    _check_dependencies(manifest)
    GROUPS.mkdir(parents=True, exist_ok=True)
    folder = group_dir(manifest["group_id"])
    folder.mkdir(exist_ok=False)  # atomic duplicate-group guard
    try:
        with (folder / "manifest.json").open("xb") as out:
            out.write(path.read_bytes())
        os.chmod(folder / "manifest.json", 0o444)
        write_json(folder / "status.json", {
            "state": "queued", "group_id": manifest["group_id"],
            "manifest_sha256": sha_file(folder / "manifest.json"),
            "created_at": now(), "completed_experiments": [],
            "group_runtime_budget_seconds": manifest["group_runtime_budget_seconds"],
            "budget_consumed_seconds": 0.0, "active_session_started_at": None,
            "physical_acceptance": "not_assessed", "quality_status": "review_required"})
        render_comparison(folder, manifest)
        return _spawn(folder)
    except Exception as exc:
        status_path = folder / "status.json"
        if status_path.is_file():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status.update(state="failed", error=f"{type(exc).__name__}: {exc}")
            write_json(status_path, status)
        raise


def resume(group_id):
    folder, _, _ = read_group(group_id)
    with (folder / "dispatch.lock").open("a+") as guard:
        fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        folder, manifest, status = read_group(group_id)
        proc = folder / "process.json"
        process = json.loads(proc.read_text(encoding="utf-8")) if proc.is_file() else {}
        pid = process.get("pid")
        if process_alive(pid, process, folder):
            raise RuntimeError(f"Group {group_id} is still running with PID {pid}")
        if status["state"] not in ("failed", "interrupted", "stopped"):
            raise RuntimeError("Completed or budget-exhausted group cannot be restarted")
        if manifest["phase"] in ("D3", "D4"):
            from .student_package import verify
            verify(PROJECT / "student_packages" / manifest["group_id"], require_approval=True)
        _check_dependencies(manifest)
        cfg_path = PROJECT / manifest["reference_config"]
        if sha_file(cfg_path) != manifest["reference_config_sha256"]:
            raise RuntimeError("Reference config changed; cannot resume pinned group")
        (folder / "stop.requested").unlink(missing_ok=True)
        status.update(state="queued", resumed_at=now(), current_experiment=None)
        write_json(folder / "status.json", status)
        return _spawn(folder)


def stop(group_id):
    folder, _, _ = read_group(group_id)
    proc = folder / "process.json"
    process = json.loads(proc.read_text(encoding="utf-8")) if proc.is_file() else {}
    pid = process.get("pid")
    if not process_alive(pid, process, folder):
        return {"group_id": group_id, "signal_sent": False, "reason": "no live process group"}
    cmdline = Path(f"/proc/{pid}/cmdline")
    if not cmdline.is_file() or str(folder).encode() not in cmdline.read_bytes():
        raise RuntimeError("PID identity could not be verified; refusing to signal")
    if os.getpgid(pid) != pid:
        raise RuntimeError("Worker is not its own process-group leader")
    (folder / "stop.requested").touch()
    os.killpg(pid, signal.SIGTERM)
    return {"group_id": group_id, "pid": pid, "signal_sent": True,
            "status_file": str(folder / "status.json")}


def acknowledge_review(group_id):
    folder, _, status = read_group(group_id)
    if status["state"] != "completed":
        raise RuntimeError("Only a completed group can be acknowledged for the next stage")
    target = folder / "review.json"
    if target.exists():
        raise FileExistsError(target)
    write_json(target, {
        "reviewed_at": now(),
        "operator_acknowledged": True,
        "meaning": "operator acknowledged saved outputs before launching dependent group",
        "statistical_convergence": "review_required",
        "physical_acceptance": "not_assessed",
    })
    return target


def _identities(manifest, case, nuclear):
    scenario_id = sha_bytes(canonical({
        "reference_sha256": manifest["reference_config_sha256"],
        "insertion_percent": case["insertion_percent"],
        "model": MODEL_ID}).encode())[:16]
    code_sha = sha_bytes((sha_file(PROJECT / "src/reactor_pipeline/beavrs3d.py") +
                          sha_file(PROJECT / "src/reactor_pipeline/experiments.py")).encode())
    run_id = sha_bytes(canonical({
        "scenario_id": scenario_id, "calculation": case["calculation"],
        "nuclear_data_xml_sha256": nuclear["cross_sections_xml_sha256"],
        "openmc_version": openmc.__version__, "code_sha256": code_sha}).encode())[:16]
    return scenario_id, run_id, code_sha

def _case_attempts(folder, case_id):
    root = folder / "experiments" / case_id
    return sorted(root.glob("attempt_*")) if root.is_dir() else []


def _completed_attempt(folder, case_id, expected_run_id=None):
    for attempt in reversed(_case_attempts(folder, case_id)):
        try:
            status = json.loads((attempt / "status.json").read_text(encoding="utf-8"))
            if status.get("state") != "completed":
                continue
            resolved = json.loads((attempt / "resolved_config.json").read_text(encoding="utf-8"))
            summary = json.loads((attempt / "summary.json").read_text(encoding="utf-8"))
            if expected_run_id is not None and (status.get("run_id") != expected_run_id or
                                                 resolved.get("run_id") != expected_run_id or
                                                 summary.get("run_id") != expected_run_id):
                continue
            validate_3d_outputs(attempt)
            required = ("resolved_config.json", "status.json", "summary.json",
                        "fields.npz", "openmc.log", "report.html")
            statepoints = list(attempt.glob("statepoint.*.h5"))
            if all((attempt / name).is_file() and (attempt / name).stat().st_size > 0
                   for name in required) and any(path.stat().st_size > 0 for path in statepoints):
                return attempt
        except (OSError, ValueError, KeyError, FileNotFoundError):
            continue
    return None


def _summary_for(attempt, case, result, status):
    resolved = json.loads((attempt / "resolved_config.json").read_text(encoding="utf-8"))
    cfg = resolved["reference_config"]
    leakage = result.get("global_tallies", {}).get("leakage", {})
    return {
        "experiment_id": case["experiment_id"],
        "run_id": status["run_id"], "scenario_id": status["scenario_id"],
        "completion_state": status["state"],
        "physical_acceptance": "not_assessed",
        "quality_status": "review_required",
        "quality_message": "inceleme gerekli",
        "statistical_convergence": "inceleme gerekli",
        "meaning": "completed means output integrity, not physics validation",
        "insertion_percent": case["insertion_percent"],
        "conditions": {
            "elemental_boron": {"value": cfg["elemental_boron_ppm"], "unit": "ppm by mass"},
            "water_density": {"value": cfg["materials"]["water"]["density_g_cm3"], "unit": "g/cm3"},
            "fuel_density": {"value": cfg["materials"]["fuel"]["density_g_cm3"], "unit": "g/cm3"},
            "temperature": {"value": cfg["operating_temperature_K"], "unit": "K"},
            "calculation": case["calculation"],
        },
        "duration": {"value": status["elapsed_seconds"], "unit": "s"},
        "k_effective": {"mean": result["k_mean"],
                        "mc_standard_error": result["k_mc_standard_error"],
                        "unit": "dimensionless"},
        "global_leakage_fraction": {
            "mean": leakage.get("mean"), "mc_standard_error": leakage.get("std_dev"),
            "unit": "fraction of source neutrons"},
        "local_fission_relative_mc_error": result["active_fission_relative_mc_error"],
        "local_error_reporting_mask": result["relative_error_reporting_mask"],
        "field_units": result["raw_units"],
        "array_order": result["array_order"],
        "mesh_shape_zyx": result["mesh_shape_zyx"],
        "z_edges_cm": result["axial_z_edges_cm"],
        "statepoint": status["statepoint"],
        "fields": "fields.npz",
        "openmc_log": "openmc.log",
        "error": None,
    }


def _html_table(headers, rows):
    head = "".join(f"<th>{html.escape(str(x))}</th>" for x in headers)
    body = "".join("<tr>" + "".join(
        f"<td>{html.escape('' if value is None else str(value))}</td>" for value in row
    ) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _html_document(title, body):
    return (
        "<!doctype html><html lang='tr'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #bbb;padding:.45rem;text-align:left}"
        "th{background:#eee}img{max-width:100%}code{background:#eee;padding:.15rem}"
        ".note{background:#fff3d6;padding:.8rem;border-left:4px solid #c77800}</style>"
        f"<body><h1>{html.escape(title)}</h1>{body}</body></html>"
    )


def render_case_report(attempt, status, summary):
    conditions = [
        ("Model", MODEL_ID),
        ("Deney", summary["experiment_id"]),
        ("Giriş (%)", summary["insertion_percent"]),
        ("Durum", status["state"]),
        ("Fiziksel kabul", "değerlendirilmedi"),
        ("Yakınsama", "inceleme gerekli"),
        ("Süre (s)", summary.get("duration", {}).get("value")),
        ("k ± MC standart hata", (
            f"{summary['k_effective']['mean']:.6f} ± "
            f"{summary['k_effective']['mc_standard_error']:.6f}"
            if summary.get("k_effective") else None)),
        ("Kaçak kesri ± MC standart hata", (
            f"{summary['global_leakage_fraction']['mean']:.6f} ± "
            f"{summary['global_leakage_fraction']['mc_standard_error']:.6f}"
            if summary.get("global_leakage_fraction") and
               summary["global_leakage_fraction"]["mean"] is not None else None)),
        ("Hata", status.get("error")),
    ]
    body = "<div class='note'>Tamamlanma fiziksel doğrulama değildir. MC standart hata fiziksel doğruluk yüzdesi değildir.</div>"
    body += _html_table(("Alan", "Değer"), conditions)
    if summary.get("conditions"):
        cond = summary["conditions"]
        body += "<h2>Fiziksel koşul ve hesap bütçesi</h2>"
        body += _html_table(("Alan", "Değer"), [
            ("Elementel bor", f"{cond['elemental_boron']['value']} {cond['elemental_boron']['unit']}"),
            ("Su yoğunluğu", f"{cond['water_density']['value']} {cond['water_density']['unit']}"),
            ("Yakıt yoğunluğu", f"{cond['fuel_density']['value']} {cond['fuel_density']['unit']}"),
            ("Sıcaklık", f"{cond['temperature']['value']} {cond['temperature']['unit']}"),
            *[(key, value) for key, value in cond["calculation"].items()],
        ])
    for image, caption in (("axial_profiles.png", "Eksenel fisyon ve kappa-fission"),
                           ("history.png", "Nesil k ve Shannon entropisi")):
        if (attempt / image).is_file():
            body += f"<h2>{html.escape(caption)}</h2><img src='{image}' alt='{html.escape(caption)}'>"
    body += "<p>Ham alanlar ve standart hatalar <code>fields.npz</code>; fiziksel koordinatlar ve eksen sırası aynı dosyadadır.</p>"
    (attempt / "report.html").write_text(
        _html_document(f"BEAVRS kaynaklı 3B koşu — {summary['experiment_id']}", body),
        encoding="utf-8")


def render_comparison(folder, manifest):
    rows = []
    for case in manifest["experiments"]:
        attempts = _case_attempts(folder, case["experiment_id"])
        attempt = _completed_attempt(folder, case["experiment_id"])
        if attempt is None and attempts:
            attempt = attempts[-1]
        state, summary, error = "queued", {}, None
        if attempt is not None:
            state_data = json.loads((attempt / "status.json").read_text(encoding="utf-8"))
            state, error = state_data.get("state", "unknown"), state_data.get("error")
            summary_path = attempt / "summary.json"
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
        calc = case["calculation"]
        rows.append({
            "group_id": manifest["group_id"], "phase": manifest["phase"],
            "experiment_id": case["experiment_id"], "attempt": str(attempt.relative_to(folder)) if attempt else "",
            "state": state, "insertion_percent": case["insertion_percent"],
            "batches": calc["batches"], "inactive": calc["inactive"],
            "active_batches": calc["batches"] - calc["inactive"],
            "particles_per_generation": calc["particles_per_generation"],
            "total_histories": calc["batches"] * calc["particles_per_generation"],
            "active_histories": (calc["batches"] - calc["inactive"]) * calc["particles_per_generation"],
            "seed": calc["seed"],
            "k_mean": summary.get("k_effective", {}).get("mean"),
            "k_mc_standard_error": summary.get("k_effective", {}).get("mc_standard_error"),
            "leakage_fraction": summary.get("global_leakage_fraction", {}).get("mean"),
            "elapsed_seconds": summary.get("duration", {}).get("value"),
            "quality_status": summary.get("quality_status", "review_required"),
            "physical_acceptance": summary.get("physical_acceptance", "not_assessed"),
            "error": error,
        })
    headers = list(rows[0])
    with (folder / "comparison.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    table = _html_table(headers, ([row[key] for key in headers] for row in rows))
    body = "<div class='note'>Yalnızca kaydedilmiş sonuçlar. Tamamlanma fiziksel kabul değildir; yakınsama inceleme gerektirir.</div>"
    body += table
    body += "<p>Her koşunun ayrıntıları kendi <code>report.html</code> dosyasındadır.</p>"
    (folder / "comparison.html").write_text(
        _html_document(f"Deney grubu — {manifest['group_id']}", body), encoding="utf-8")
    return rows


def run_case(folder, manifest, cfg, case, nuclear):
    case_dir = folder / "experiments" / case["experiment_id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    attempt = case_dir / f"attempt_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    attempt.mkdir()
    (attempt / "openmc.log").touch()
    calc = case["calculation"]
    scenario_id, run_id, code_sha = _identities(manifest, case, nuclear)

    resolved = {
        "model": MODEL_ID, "beavrs_source_commit": cfg["beavrs_source_commit"],
        "group_id": manifest["group_id"], "experiment_id": case["experiment_id"],
        "scenario_id": scenario_id, "run_id": run_id,
        "reference_config_sha256": manifest["reference_config_sha256"],
        "reference_config": cfg, "insertion_percent": case["insertion_percent"],
        "calculation": calc, "nuclear_data": nuclear,
        "group_runtime_budget_seconds": manifest["group_runtime_budget_seconds"],
        "runtime_estimate_policy": "max(saved-pilot, completed-case-seconds-per-history) x 1.5; not a guarantee",
        "temperature_method": cfg["temperature_method"],
        "python_executable": sys.executable, "openmc_version": openmc.__version__,
        "pipeline_code_sha256": code_sha,
        "model_scope": "idealized isolated assembly; not full-core BEAVRS validation",
    }
    write_json(attempt / "resolved_config.json", resolved)
    status = {"state": "pending", "group_id": manifest["group_id"],
              "experiment_id": case["experiment_id"], "scenario_id": scenario_id,
              "run_id": run_id, "started_at": now(),
              "physical_acceptance": "not_assessed", "quality_status": "review_required",
              "error": None}
    write_json(attempt / "status.json", status)
    start = time.perf_counter()
    try:
        assembly = build_model(cfg, case["insertion_percent"],
                               batches=calc["batches"], inactive=calc["inactive"],
                               particles=calc["particles_per_generation"], seed=calc["seed"])
        point_checks(assembly)
        assembly.model.export_to_xml(directory=attempt)
        status["state"] = "running"
        write_json(attempt / "status.json", status)
        with (attempt / "openmc.log").open("a", encoding="utf-8") as log:
            with redirect_stdout(log), redirect_stderr(log):
                statepoint = assembly.model.run(cwd=attempt, threads=calc["threads"], output=True)
        statepoint = Path(statepoint)
        if not statepoint.is_file() or statepoint.stat().st_size == 0:
            raise RuntimeError("OpenMC did not produce a nonempty statepoint")
        result = extract_3d(statepoint, assembly, attempt, time.perf_counter()-start, nuclear,
                            purpose="user_started_controlled_experiment_not_physical_validation")
        validate_3d_outputs(attempt)
        shutil.copy2(attempt / "beavrs_3d_arrays.npz", attempt / "fields.npz")
        plot_integration_results(attempt)
        status.update(state="completed", completed_at=now(),
                      elapsed_seconds=time.perf_counter()-start,
                      statepoint=statepoint.name, error=None)
        summary = _summary_for(attempt, case, result, status)
        write_json(attempt / "summary.json", summary)
        render_case_report(attempt, status, summary)
        required = ("resolved_config.json", "status.json", "summary.json",
                    "fields.npz", "openmc.log", "report.html", statepoint.name)
        if not all((attempt / name).is_file() and (attempt / name).stat().st_size > 0
                   for name in required):
            raise RuntimeError("Required output is missing or empty")
        write_json(attempt / "status.json", status)
        return attempt, status
    except BaseException as exc:
        interrupted = STOP_FLAG or (folder / "stop.requested").exists()
        status.update(state="interrupted" if interrupted else "failed",
                      ended_at=now(), elapsed_seconds=time.perf_counter()-start,
                      error=f"{type(exc).__name__}: {exc}")
        write_json(attempt / "status.json", status)
        summary = {
            "experiment_id": case["experiment_id"], "run_id": run_id,
            "scenario_id": scenario_id, "completion_state": status["state"],
            "physical_acceptance": "not_assessed", "quality_status": "review_required",
            "quality_message": "inceleme gerekli",
            "statistical_convergence": "inceleme gerekli",
            "duration": {"value": status["elapsed_seconds"], "unit": "s"},
            "error": status["error"], "insertion_percent": case["insertion_percent"],
        }
        write_json(attempt / "summary.json", summary)
        render_case_report(attempt, status, summary)
        return attempt, status


def _on_term(signum, frame):
    global STOP_FLAG
    STOP_FLAG = True


def _expire_budget():
    global BUDGET_EXPIRED, STOP_FLAG
    BUDGET_EXPIRED = True
    STOP_FLAG = True
    try:
        os.killpg(os.getpid(), signal.SIGTERM)
    except ProcessLookupError:
        pass


def worker(folder):
    global STOP_FLAG, BUDGET_EXPIRED
    STOP_FLAG = False
    BUDGET_EXPIRED = False
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    folder = Path(folder).resolve()
    if folder.parent != GROUPS.resolve():
        raise ValueError("Worker folder is outside managed groups")
    with (folder / "group.lock").open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another worker owns this experiment group") from exc
        manifest_bytes = (folder / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
        status_path = folder / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if sha_bytes(manifest_bytes) != status["manifest_sha256"]:
            raise ValueError("Group manifest changed")
        if sha_file(PROJECT / manifest["reference_config"]) != manifest["reference_config_sha256"]:
            raise ValueError("Reference configuration changed")
        budget = manifest["group_runtime_budget_seconds"]
        consumed = _budget_used_seconds(status, bool(status.get("active_session_started_at")))
        if consumed >= budget:
            status.update(state="budget_exhausted", budget_consumed_seconds=consumed,
                          active_session_started_at=None, budget_reason="no_time_remaining",
                          current_experiment=None)
            write_json(status_path, status)
            return
        status.update(state="running", worker_pid=os.getpid(), started_at=now(),
                      active_session_started_at=now(), budget_consumed_seconds=consumed,
                      error=None, current_experiment=None)
        write_json(status_path, status)
        timer = threading.Timer(budget-consumed, _expire_budget)
        timer.daemon = True
        timer.start()
        try:
            cfg = load_reference(PROJECT / manifest["reference_config"])
            nuclear = nuclear_data_precheck(build_model(cfg, 50).materials, cfg)
            completed = set(status.get("completed_experiments", []))
            for case in manifest["experiments"]:
                case_id = case["experiment_id"]
                if _completed_attempt(folder, case_id, _identities(manifest, case, nuclear)[1]):
                    completed.add(case_id)
                    continue
                if BUDGET_EXPIRED:
                    status.update(state="budget_exhausted", budget_reason="runtime_limit_reached",
                                  current_experiment=None, completed_experiments=sorted(completed))
                    write_json(status_path, status)
                    render_comparison(folder, manifest)
                    return
                if STOP_FLAG or (folder / "stop.requested").exists():
                    status.update(state="stopped", stopped_at=now(), current_experiment=None,
                                  completed_experiments=sorted(completed))
                    write_json(status_path, status)
                    render_comparison(folder, manifest)
                    return
                remaining = budget - _budget_used_seconds(status, True)
                estimate = _estimate_case_seconds(folder, manifest, case)
                if estimate > remaining:
                    status.update(state="budget_exhausted", budget_reason="estimated_next_case_exceeds_remaining",
                                  next_experiment=case_id, next_experiment_estimated_seconds=estimate,
                                  budget_remaining_seconds=max(0.0, remaining),
                                  current_experiment=None, completed_experiments=sorted(completed))
                    write_json(status_path, status)
                    render_comparison(folder, manifest)
                    return
                status.update(current_experiment=case_id,
                              next_experiment_estimated_seconds=estimate,
                              completed_experiments=sorted(completed))
                write_json(status_path, status)
                attempt, case_status = run_case(folder, manifest, cfg, case, nuclear)
                render_comparison(folder, manifest)
                _checkpoint_budget(status)
                if case_status["state"] == "completed":
                    completed.add(case_id)
                    status["completed_experiments"] = sorted(completed)
                    if BUDGET_EXPIRED:
                        status.update(state="budget_exhausted", budget_reason="runtime_limit_reached",
                                      current_experiment=None)
                        write_json(status_path, status)
                        return
                    write_json(status_path, status)
                    continue
                group_state = "budget_exhausted" if BUDGET_EXPIRED else (
                    "stopped" if case_status["state"] == "interrupted" else "failed")
                status.update(state=group_state, current_experiment=None,
                              budget_reason="runtime_limit_reached" if BUDGET_EXPIRED else None,
                              stopped_at=now() if group_state == "stopped" else None,
                              failed_at=now() if group_state == "failed" else None,
                              error=case_status["error"], completed_experiments=sorted(completed),
                              last_attempt=str(attempt.relative_to(folder)))
                write_json(status_path, status)
                return
            final_state = "budget_exhausted" if BUDGET_EXPIRED else "completed"
            status.update(state=final_state, completed_at=now(), current_experiment=None,
                          budget_reason="runtime_limit_reached" if BUDGET_EXPIRED else None,
                          completed_experiments=sorted(completed), error=None)
            write_json(status_path, status)
            render_comparison(folder, manifest)
        finally:
            timer.cancel()
            latest = json.loads(status_path.read_text(encoding="utf-8"))
            if latest.get("worker_pid") == os.getpid() and latest.get("active_session_started_at"):
                _checkpoint_budget(latest)
                latest["active_session_started_at"] = None
                write_json(status_path, latest)

def worker_entry(folder):
    try:
        worker(folder)
    except BaseException as exc:
        folder = Path(folder)
        process = folder / "process.json"
        try:
            recorded_pid = json.loads(process.read_text(encoding="utf-8")).get("pid") if process.is_file() else None
            if recorded_pid in (None, os.getpid()):
                status_path = folder / "status.json"
                if status_path.is_file():
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    if status.get("state") != "completed":
                        status.update(state="failed", failed_at=now(),
                                      error=f"{type(exc).__name__}: {exc}")
                        write_json(status_path, status)
        except (OSError, ValueError, KeyError):
            pass
        raise

def inspect_saved(group_id):
    folder, manifest, status = read_group(group_id)
    rows = render_comparison(folder, manifest)
    return {"group": group_status(group_id), "rows": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="beavrs-experiments")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list prepared manifests; never starts transport")
    pre = sub.add_parser("preflight", help="validate one prepared manifest without transport")
    pre.add_argument("manifest", type=Path)
    launch_p = sub.add_parser("launch", help="explicitly start a detached WSL worker")
    launch_p.add_argument("manifest", type=Path)
    for name in ("status", "stop", "resume", "review", "inspect"):
        command = sub.add_parser(name)
        command.add_argument("group_id")
    work = sub.add_parser("worker", help=argparse.SUPPRESS)
    work.add_argument("group_dir", type=Path)
    args = parser.parse_args(argv)
    if args.command == "list":
        rows = []
        for path in sorted(MANIFESTS.glob("*.json")):
            _, manifest, _ = load_manifest(path)
            rows.append({"group_id": manifest["group_id"], "phase": manifest["phase"],
                         "manifest": str(path), "experiments": len(manifest["experiments"]),
                         "depends_on": manifest["depends_on"]})
        result = rows
    elif args.command == "preflight":
        result = preflight(args.manifest)
    elif args.command == "launch":
        result = launch(args.manifest)
    elif args.command == "status":
        result = group_status(args.group_id)
    elif args.command == "stop":
        result = stop(args.group_id)
    elif args.command == "resume":
        result = resume(args.group_id)
    elif args.command == "review":
        result = {"review_file": str(acknowledge_review(args.group_id))}
    elif args.command == "inspect":
        result = inspect_saved(args.group_id)
    else:
        worker_entry(args.group_dir)
        return
    print(json.dumps(result, indent=2, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()

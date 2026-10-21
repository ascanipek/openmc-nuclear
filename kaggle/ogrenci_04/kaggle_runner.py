"""Kaggle CPU adapter for the existing approved ogrenci_04 V2 packages.

The physics and output writer live in the unchanged bundled reactor_pipeline.
Nothing in this module starts transport until run_stage() is called explicitly.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

STAGES = ("stage_32", "stage_128", "stage_256")
OWNER = "ogrenci_04"


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _under(path, root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def verify_bundle(code_root):
    root = Path(code_root).resolve()
    ledger = _json(root / "bundle_hashes.json")
    if ledger.get("schema") != "kaggle_code_bundle_sha256_v1":
        raise ValueError("Unsupported code bundle ledger")
    for relative, expected in ledger["files"].items():
        path = root / relative
        if not _under(path, root) or not path.is_file() or _sha(path) != expected:
            raise ValueError(f"Code Dataset file mismatch: {relative}")
    return len(ledger["files"])


def _cpu_quota():
    path = Path("/sys/fs/cgroup/cpu.max")
    if path.is_file():
        quota, period = path.read_text().split()[:2]
        if quota != "max":
            return max(1, math.floor(int(quota) / int(period)))
    return None


def resources():
    affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    quota = _cpu_quota()
    visible = max(1, min(affinity, quota)) if quota is not None else max(1, affinity)
    mem_limit = None
    path = Path("/sys/fs/cgroup/memory.max")
    if path.is_file():
        value = path.read_text().strip()
        if value != "max":
            mem_limit = int(value)
    if mem_limit is None:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_limit = int(line.split()[1]) * 1024
                break
    return {"cpu_affinity_count": affinity, "cpu_quota_count": quota,
            "visible_cpu_count": visible, "memory_limit_bytes": mem_limit,
            "selected_threads": min(6, visible)}


def ensure_openmc():
    """Use OpenMC's documented conda-forge distribution in this kernel prefix."""
    if sys.version_info < (3, 12):
        raise RuntimeError("OpenMC 0.16.0 requires Python 3.12 or newer; choose a compatible Kaggle kernel")
    prefix = Path(sys.prefix).resolve()
    executable = prefix / "bin" / "openmc"
    try:
        import openmc
        installed = openmc.__version__ == "0.16.0" and executable.is_file()
    except ImportError:
        installed = False
    if not installed:
        conda = shutil.which("conda")
        if conda is None:
            raise RuntimeError("Conda is unavailable in this kernel; OpenMC was not installed")
        subprocess.run([conda, "install", "-y", "--override-channels", "-c", "conda-forge",
                        "-p", str(prefix), "openmc=0.16.0", "numpy", "h5py", "matplotlib", "pandas"], check=True)
        importlib.invalidate_caches()
    import openmc
    if openmc.__version__ != "0.16.0" or not executable.is_file() or not _under(openmc.__file__, prefix):
        raise RuntimeError("OpenMC Python API and executable are not from the pinned kernel environment")
    version = subprocess.check_output([str(executable), "--version"], text=True).strip()
    if "0.16.0" not in version:
        raise RuntimeError(f"OpenMC executable version differs: {version}")
    return {"python": sys.executable, "openmc_python": openmc.__file__,
            "openmc_executable": str(executable), "openmc_version": version}


def cross_sections_index(data_root, working_root):
    """Build only a tiny XML index; every HDF5 file remains under input/."""
    data_root = Path(data_root).resolve()
    indices = list(data_root.rglob("cross_sections.xml"))
    if len(indices) != 1:
        raise ValueError(f"Expected one cross_sections.xml under {data_root}; found {len(indices)}")
    original = indices[0]
    tree = ET.parse(original)
    libraries = tree.getroot().findall("library")
    if not libraries:
        raise ValueError("No libraries in cross_sections.xml")
    candidates = {}
    remapped = 0
    for library in libraries:
        raw = library.get("path")
        if not raw:
            raise ValueError("Library path is missing")
        source = Path(raw)
        target = (original.parent / source).resolve()
        if not target.is_file() or not _under(target, data_root):
            if not candidates:
                for item in data_root.rglob("*"):
                    if item.is_file() and item.suffix in (".h5", ".hdf5"):
                        candidates.setdefault(item.name, []).append(item.resolve())
            matches = candidates.get(source.name, [])
            if len(matches) != 1:
                raise ValueError(f"Cannot uniquely map nuclear data file: {raw}")
            target = matches[0]
        if not _under(target, data_root):
            raise ValueError(f"Nuclear data escaped Dataset root: {target}")
        if raw != str(target):
            remapped += 1
        library.set("path", str(target))
    index = Path(working_root) / "cross_sections_kaggle.xml"
    tree.write(index, encoding="utf-8", xml_declaration=True)
    os.environ["OPENMC_CROSS_SECTIONS"] = str(index)
    return {"original_index": str(original), "original_sha256": _sha(original),
            "working_index": str(index), "working_sha256": _sha(index),
            "library_count": len(libraries), "remapped_paths": remapped}


def _modules(project):
    src = str(Path(project).resolve() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from reactor_pipeline import v2_students, v2_student_runner, v2_transfer, v2_dataset
    if v2_students.PROJECT.resolve() != Path(project).resolve():
        raise RuntimeError("A different reactor_pipeline package was imported")
    return v2_students, v2_student_runner, v2_transfer, v2_dataset


def _package(project, stage):
    if stage not in STAGES:
        raise ValueError(f"Stage must be one of {STAGES}")
    package_id = f"v2_{stage}_{OWNER}_beavrs_v2_pilot_scope_v1"
    return Path(project) / "student_packages/v2_students_portable_v1" / stage / OWNER / package_id


def _validate_group(group, package, manifest, dataset_module):
    if _json(group / "manifest.json") != manifest:
        raise ValueError("Saved group manifest differs from approved package")
    status = _json(group / "status.json")
    if status.get("group_id") != manifest["group_id"]:
        raise ValueError("Saved group identity differs")
    known = {case["experiment_id"]: case for case in manifest["experiments"]}
    experiments = group / "experiments"
    if experiments.is_dir() and any(p.name not in known for p in experiments.iterdir()):
        raise ValueError("Unexpected experiment in prior output")
    completed = set()
    for case_id, case in known.items():
        for attempt in sorted((experiments / case_id).glob("attempt_*")):
            if not (attempt / "status.json").is_file():
                raise ValueError(f"Attempt has no status record: {attempt}")
            record = _json(attempt / "status.json")
            if record.get("scenario_id") != case["scenario_id"]:
                raise ValueError(f"Scenario mismatch in {attempt}")
            if record.get("state") != "completed":
                continue
            for name in ("model.xml", "fields.npz", "openmc.log", "report.html", "summary.json", "resolved_config.json"):
                if not (attempt / name).is_file():
                    raise ValueError(f"Incomplete completed attempt: {attempt / name}")
            item = dataset_module._attempt(attempt, preview=True)
            if item["resolved"]["controls"] != case["controls"] or item["resolved"]["calculation"] != case["calculation"]:
                raise ValueError(f"Inputs changed in prior result: {attempt}")
            statepoint = attempt / item["summary"]["statepoint"]
            if not statepoint.is_file() or statepoint.stat().st_size == 0:
                raise ValueError(f"Statepoint missing from saved Kaggle output: {attempt}")
            completed.add(case_id)
    if not set(status.get("completed_experiments", [])).issubset(completed):
        raise ValueError("Group claims a completed case without valid output")
    return completed


def _normalize_interrupted(group, manifest):
    """Mark abandoned attempts in the writable copy, preserving all their files."""
    for case in manifest["experiments"]:
        case_dir = group / "experiments" / case["experiment_id"]
        for attempt in case_dir.glob("attempt_*"):
            path = attempt / "status.json"
            if not path.is_file():
                _write(path, {"state": "stopped", "scenario_id": case["scenario_id"],
                              "experiment_id": case["experiment_id"],
                              "error": "Previous Kaggle session ended before attempt status was saved"})
            else:
                record = _json(path)
                if record.get("state") == "running":
                    record.update(state="stopped", error="Previous Kaggle session ended during this attempt")
                    _write(path, record)


def _make_writable(root):
    """Input Datasets are read-only; a restored working copy must be writable."""
    for directory, subdirs, files in os.walk(root):
        os.chmod(directory, 0o755)
        for name in files:
            os.chmod(Path(directory) / name, 0o644)


def _find_previous(input_root, group_id, current):
    candidates = []
    for dataset in Path(input_root).iterdir():
        if dataset.is_dir():
            candidate = dataset / "v2_groups" / group_id
            if candidate.is_dir() and candidate.resolve() != current.resolve():
                candidates.append(candidate)
    if len(candidates) > 1:
        raise ValueError(f"Multiple previous-output Datasets for {group_id}; attach only one")
    return candidates[0] if candidates else None


def _progress(manifest, completed):
    return [{"experiment_id": x["experiment_id"], "scenario_id": x["scenario_id"],
             "state": "completed" if x["experiment_id"] in completed else "pending"}
            for x in manifest["experiments"]]


def prepare(data_root, code_root, stage, *, kaggle_root="/kaggle"):
    kaggle_root = Path(kaggle_root).resolve()
    input_root = kaggle_root / "input"
    working = kaggle_root / "working"
    data_root, code_root = Path(data_root).resolve(), Path(code_root).resolve()
    if not _under(data_root, input_root) or not (_under(code_root, input_root) or _under(code_root, working)):
        raise ValueError("Nuclear data must be under input/; verified code may be under input/ or extracted into working/")
    if not data_root.is_dir() or not code_root.is_dir():
        raise FileNotFoundError("Dataset root is missing")
    working.mkdir(parents=True, exist_ok=True)
    bundle_count = verify_bundle(code_root)
    environment = ensure_openmc()
    if shutil.which("timeout") is None:
        raise RuntimeError("GNU timeout is unavailable; approved group budget cannot be enforced")
    project = code_root / "project"
    students, runner, transfer, dataset = _modules(project)
    package = _package(project, stage)
    info = students.verify_package(package, require_approval=True)
    manifest = _json(package / "manifest.json")
    assignment = _json(project / "configs/v2_student_assignment_v1.json")
    registry = assignment["packages"].get(info["package_id"])
    if (info.get("owner") != OWNER or info.get("stage") != stage or
            registry is None or registry.get("owner") != OWNER or registry.get("stage") != stage or
            registry.get("scenario_ids") != [x["scenario_id"] for x in manifest["experiments"]] or
            registry.get("package_sha256") != _sha(package / "package.json") or
            registry.get("manifest_sha256") != _sha(package / "manifest.json")):
        raise ValueError("Central assignment or Kaggle package mismatch")
    if len(manifest["experiments"]) != {"stage_32": 8, "stage_128": 24, "stage_256": 32}[stage]:
        raise ValueError("Unexpected assigned case count")
    index = cross_sections_index(data_root, working)
    checks = runner.preflight(package)
    if len(checks["cases"]) != len(manifest["experiments"]):
        raise ValueError("Incomplete preflight")
    runner.GROUPS = working / "v2_groups"
    transfer.GROUPS = runner.GROUPS
    group = runner.GROUPS / info["package_id"]
    previous = _find_previous(input_root, info["package_id"], group)
    if group.exists() and previous is not None:
        raise ValueError("Current and previous group both exist; refusing ambiguous merge")
    if previous is not None:
        if _json(previous / "manifest.json") != manifest:
            raise ValueError("Previous group manifest differs from approved package")
        group.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(previous, group)
        _make_writable(group)
        _normalize_interrupted(group, manifest)
    if not group.exists():
        group.mkdir(parents=True)
        shutil.copy2(package / "manifest.json", group / "manifest.json")
        _write(group / "status.json", {"state": "stopped", "group_id": info["package_id"],
               "manifest_sha256": _sha(group / "manifest.json"),
               "physical_acceptance": "not_assessed", "quality_status": "review_required",
               "completed_experiments": [], "budget_consumed_seconds": 0.0, "error": None})
        _write(group / "preflight.json", checks)
    else:
        _normalize_interrupted(group, manifest)
    completed = _validate_group(group, package, manifest, dataset)
    status = _json(group / "status.json")
    status["completed_experiments"] = [x["experiment_id"] for x in manifest["experiments"]
                                       if x["experiment_id"] in completed]
    if status["state"] in ("running", "queued"):
        status.update(state="stopped", error="Previous Kaggle session ended; valid completed cases were retained")
    _write(group / "status.json", status)
    runner._comparison(group, manifest)
    capacity = resources()
    previous_runtime = _json(group / "kaggle_environment.json") if (group / "kaggle_environment.json").is_file() else {}
    observed_rate = previous_runtime.get("observed_seconds_per_history")
    if not isinstance(observed_rate, (int, float)) or not math.isfinite(observed_rate) or observed_rate <= 0:
        observed_rate = None
    runtime = {"selected_stage": stage, "package": str(package), "group": str(group),
               "code_bundle_files_verified": bundle_count, "nuclear_data": index,
               "resources": capacity, "openmc_environment": environment,
               "observed_seconds_per_history": observed_rate,
               "approved_group_budget_seconds": manifest["group_runtime_budget_seconds"]}
    _write(group / "kaggle_environment.json", runtime)
    return {"package": package, "manifest": manifest, "group": group,
            "runner": runner, "transfer": transfer, "dataset": dataset,
            "runtime": runtime, "completed": completed,
            "progress": _progress(manifest, completed)}


def _budget_launcher(group, executable, seconds):
    timeout = shutil.which("timeout")
    if timeout is None:
        raise RuntimeError("GNU timeout is required to enforce the approved group budget")
    launcher = group / "openmc_budget.sh"
    launcher.write_text("#!/bin/sh\n"
        + f"{shlex.quote(timeout)} --signal=TERM --kill-after=30s {seconds}s "
        + f"{shlex.quote(str(executable))} \"$@\"\n"
        + "result=$?\n"
        + "if [ \"$result\" -eq 124 ]; then printf 'group time budget exhausted\\n' > kaggle_budget_timeout.txt; fi\n"
        + "exit \"$result\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def _execute_case(context, case, deadline, limit_kind):
    """Retain the approved run identity; explicitly record the CPU thread override."""
    import openmc
    runner = context["runner"]
    used = context["runtime"]["resources"]["selected_threads"]
    approved = case["calculation"]["threads"]
    execution = {"platform": "kaggle_cpu", "approved_threads": approved,
                 "actual_openmc_threads": used, "visible_cpu_count": context["runtime"]["resources"]["visible_cpu_count"],
                 "memory_limit_bytes": context["runtime"]["resources"]["memory_limit_bytes"],
                 "note": "calculation is the immutable approved profile; actual thread count is recorded here"}
    before = set((context["group"] / "experiments" / case["experiment_id"]).glob("attempt_*"))
    original_run = openmc.Model.run
    def model_run(model, *args, **kwargs):
        seconds = math.floor(deadline - time.monotonic())
        if seconds < 1:
            raise TimeoutError(f"{limit_kind} time budget expired before OpenMC started")
        launcher = _budget_launcher(context["group"],
                                    context["runtime"]["openmc_environment"]["openmc_executable"], seconds)
        kwargs["threads"] = used
        kwargs["openmc_exec"] = str(launcher)
        return original_run(model, *args, **kwargs)
    openmc.Model.run = model_run
    try:
        record = runner._run_case(context["group"], context["manifest"], case,
                                  runner.digest(context["package"] / "SHA256SUMS.json"))
    except BaseException as exc:
        created = set((context["group"] / "experiments" / case["experiment_id"]).glob("attempt_*")) - before
        if len(created) == 1:
            attempt = next(iter(created))
            path = attempt / "status.json"
            if path.is_file():
                stopped = _json(path)
                stopped["execution_environment"] = execution
                if (attempt / "kaggle_budget_timeout.txt").is_file():
                    stopped.update(state="stopped", error=f"{limit_kind} time budget exhausted during OpenMC")
                _write(path, stopped)
            if (attempt / "kaggle_budget_timeout.txt").is_file():
                raise TimeoutError(f"{limit_kind} time budget exhausted during OpenMC") from exc
        raise
    finally:
        openmc.Model.run = original_run
    created = set((context["group"] / "experiments" / case["experiment_id"]).glob("attempt_*")) - before
    if len(created) != 1 or record["state"] != "completed":
        raise RuntimeError("One completed attempt was expected")
    attempt = created.pop()
    for name in ("resolved_config.json", "summary.json", "status.json"):
        path = attempt / name
        value = _json(path)
        value["execution_environment"] = execution
        _write(path, value)
    context["dataset"]._attempt(attempt, preview=True)
    return record


def _histories(case):
    calc = case["calculation"]
    return calc["batches"] * calc["particles_per_generation"] * calc["generations_per_batch"]


def _delivery(context, completed_count):
    deliveries = context["group"].parents[1] / "deliveries"
    deliveries.mkdir(parents=True, exist_ok=True)
    zip_path = deliveries / f"{context['manifest']['group_id']}_after_{completed_count:02d}.zip"
    if not zip_path.exists():
        context["transfer"].export_package(context["package"], zip_path)
    return zip_path


def run_stage(context, session_budget_seconds, session_started_monotonic=None):
    """Run pending cases synchronously while both approved and session budgets permit."""
    if not isinstance(session_budget_seconds, (int, float)) or not math.isfinite(session_budget_seconds) or session_budget_seconds <= 0:
        raise ValueError("SESSION_BUDGET_SECONDS must be a positive finite number")
    session_started = time.monotonic() if session_started_monotonic is None else session_started_monotonic
    session_deadline = session_started + session_budget_seconds
    manifest, group = context["manifest"], context["group"]
    completed = _validate_group(group, context["package"], manifest, context["dataset"])
    status = _json(group / "status.json")
    budget = manifest["group_runtime_budget_seconds"]
    if status["state"] == "completed" and len(completed) != len(manifest["experiments"]):
        raise ValueError("Group claims completion but valid results are missing")
    if len(completed) == len(manifest["experiments"]):
        return {"state": "completed", "completed": len(completed), "pending": 0,
                "new_cases": 0, "progress": _progress(manifest, completed),
                "full_outputs": str(group), "delivery_zip": str(_delivery(context, len(completed))),
                "session_remaining_seconds": max(0, session_deadline - time.monotonic())}
    if status["state"] in ("failed", "budget_exhausted"):
        raise RuntimeError(f"Group is {status['state']}; review before explicit continuation")
    if status["state"] not in ("stopped", "not_started"):
        raise RuntimeError(f"Group cannot start from {status['state']}")
    new_cases = 0
    started = time.monotonic()
    limit_kind = None
    status["state"] = "running"
    status["session_budget_seconds"] = session_budget_seconds
    _write(group / "status.json", status)
    try:
        for case in manifest["experiments"]:
            if case["experiment_id"] in completed:
                continue
            now = time.monotonic()
            group_remaining = budget - status.get("budget_consumed_seconds", 0.0) - (now - started)
            session_remaining = session_deadline - now
            estimate = runner_estimate(context, case)
            if estimate > group_remaining:
                status.update(state="budget_exhausted", error="Next case estimate exceeds remaining approved group budget; estimate is not a guarantee")
                break
            if estimate > session_remaining:
                status.update(state="stopped", error="Next case estimate exceeds remaining configured session budget; estimate is not a guarantee")
                break
            limit_kind = "group" if group_remaining <= session_remaining else "session"
            case_started = time.monotonic()
            _execute_case(context, case, case_started + min(group_remaining, session_remaining), limit_kind)
            observed_seconds = time.monotonic() - case_started
            rate = observed_seconds / _histories(case)
            previous_rate = context["runtime"].get("observed_seconds_per_history")
            context["runtime"]["observed_seconds_per_history"] = max(rate, previous_rate or 0)
            context["runtime"]["last_observed_case_seconds"] = observed_seconds
            context["runtime"]["last_observed_case_id"] = case["experiment_id"]
            _write(group / "kaggle_environment.json", context["runtime"])
            completed.add(case["experiment_id"])
            new_cases += 1
            status["completed_experiments"] = [x["experiment_id"] for x in manifest["experiments"]
                                               if x["experiment_id"] in completed]
            status["budget_consumed_seconds"] += time.monotonic() - started
            started = time.monotonic()
            _write(group / "status.json", status)
            context["runner"]._comparison(group, manifest)
        if status["state"] == "running":
            status["state"] = "completed" if len(completed) == len(manifest["experiments"]) else "stopped"
    except TimeoutError as exc:
        status["budget_consumed_seconds"] += time.monotonic() - started
        status.update(state="budget_exhausted" if limit_kind == "group" else "stopped",
                      error=f"{type(exc).__name__}: {exc}")
    except BaseException as exc:
        status["budget_consumed_seconds"] += time.monotonic() - started
        status.update(state="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        _write(group / "status.json", status)
        context["runner"]._comparison(group, manifest)
    zip_path = _delivery(context, len(completed))
    return {"state": status["state"], "completed": len(completed),
            "pending": len(manifest["experiments"]) - len(completed),
            "new_cases": new_cases, "delivery_zip": str(zip_path),
            "full_outputs": str(group), "progress": _progress(manifest, completed),
            "stop_reason": status.get("error"),
            "session_remaining_seconds": max(0, session_deadline - time.monotonic()),
            "observed_seconds_per_history": context["runtime"].get("observed_seconds_per_history")}


def runner_estimate(context, case):
    baseline = context["runner"]._estimate_seconds(case["calculation"])
    approved = case["calculation"]["threads"]
    actual = context["runtime"]["resources"]["selected_threads"]
    cpu_scaled = baseline * max(1.0, approved / actual)
    observed_rate = context["runtime"].get("observed_seconds_per_history")
    observed = observed_rate * _histories(case) if observed_rate else 0
    return max(cpu_scaled, observed)

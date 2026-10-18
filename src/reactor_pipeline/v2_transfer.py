"""Checksum-validated, read-only V2 handoff; never starts transport or grants acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

from .parameter_space import MODEL_ID
from . import v2_dataset, v2_scenarios, v2_students

PROJECT = Path(__file__).resolve().parents[2]
ASSIGNMENT = PROJECT / "configs/v2_student_assignment_v1.json"
IMPORTS = PROJECT / "deliveries/imported"
GROUPS = PROJECT / "runs/beavrs_3d/v2_groups"
SCHEMA = "beavrs_v2_handoff_v1"
CASE_FILES = ("status.json", "summary.json", "resolved_config.json", "fields.npz",
              "openmc.log", "report.html", "result.json", "model.xml",
              "axial_profiles.png", "history.png", "acceptance.json")
GROUP_FILES = ("status.json", "process.json", "preflight.json", "comparison.csv",
               "comparison.html", "group.log", "manifest.json")
PACKAGE_FILES = ("manifest.json", "package.json", "SHA256SUMS.json", "approval.json")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _validate_member(name):
    if not name or "\\" in name or name.startswith("/") or ":" in name:
        raise ValueError(f"Unsafe ZIP path: {name}")
    parts = PurePosixPath(name).parts
    if any(part in ("", ".", "..") for part in parts) or str(PurePosixPath(name)) != name:
        raise ValueError(f"Unsafe ZIP path: {name}")
    if parts[0] not in ("package", "group") and name not in ("transfer.json", "checksums.json"):
        raise ValueError(f"Unexpected ZIP path: {name}")


def _package_verifier(folder):
    info = _read(Path(folder) / "package.json")
    return (v2_students if info.get("project_root") == "." else v2_scenarios).verify_package


def export_package(package, output_zip):
    package = Path(package).resolve()
    _package_verifier(package)(package, require_approval=False)
    info = _read(package / "package.json")
    manifest = _read(package / "manifest.json")
    group = GROUPS / info["package_id"]
    if not (group / "status.json").is_file():
        raise ValueError("No saved group status; no results to deliver")
    if _read(group / "manifest.json") != manifest:
        raise ValueError("Saved and package manifests differ")
    files = {}
    for filename in PACKAGE_FILES:
        path = package / filename
        if path.is_file(): files[f"package/{filename}"] = path
    for filename in GROUP_FILES:
        path = group / filename
        if path.is_file(): files[f"group/{filename}"] = path
    statepoints = []
    case_ids = {c["experiment_id"] for c in manifest["experiments"]}
    completed = set()
    experiments = group / "experiments"
    for case_dir in sorted(experiments.iterdir()) if experiments.is_dir() else ():
        if not case_dir.is_dir() or case_dir.name not in case_ids:
            raise ValueError(f"Unexpected experiment: {case_dir}")
        for attempt in sorted(case_dir.glob("attempt_*")):
            if not attempt.is_dir() or not (attempt / "status.json").is_file():
                raise ValueError(f"Incomplete attempt record: {attempt}")
            status = _read(attempt / "status.json")
            if status.get("state") == "completed":
                v2_dataset._attempt(attempt, preview=True)
                completed.add(case_dir.name)
                required = ("summary.json", "resolved_config.json", "fields.npz", "openmc.log", "report.html")
                if any(not (attempt / f).is_file() for f in required):
                    raise ValueError(f"Completed attempt misses output: {attempt}")
            for filename in CASE_FILES:
                path = attempt / filename
                if path.is_file():
                    files[f"group/experiments/{case_dir.name}/{attempt.name}/{filename}"] = path
            for statepoint in sorted(attempt.glob("statepoint.*.h5")):
                statepoints.append({"relative_path": f"group/experiments/{case_dir.name}/{attempt.name}/{statepoint.name}",
                                    "bytes": statepoint.stat().st_size, "sha256": _digest(statepoint),
                                    "retention": "source_machine; transfer separately on request"})
    group_status = _read(group / "status.json")
    if group_status.get("state") == "completed" and completed != case_ids:
        raise ValueError("Group completed but one or more completed attempt outputs are missing")
    metadata = {"schema": SCHEMA, "package_id": info["package_id"], "model": MODEL_ID,
                "manifest_sha256": _digest(package / "manifest.json"),
                "package_sha256": _digest(package / "package.json"),
                "hashes_sha256": _digest(package / "SHA256SUMS.json"),
                "statepoint_policy": "omitted_from_lightweight_zip; retain on source machine",
                "omitted_statepoints": statepoints,
                "physical_acceptance": "not_assessed_by_transfer", "training_acceptance": "not_granted"}
    out = Path(output_zip)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(out.name + ".partial")
    if temporary.exists(): raise FileExistsError(temporary)
    checksums = {name: _digest(path) for name, path in files.items()}
    transfer_bytes = (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode()
    checksums["transfer.json"] = hashlib.sha256(transfer_bytes).hexdigest()
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, path in sorted(files.items()): archive.write(path, name)
            archive.writestr("transfer.json", transfer_bytes)
            archive.writestr("checksums.json", json.dumps(checksums, sort_keys=True, indent=2) + "\n")
        temporary.rename(out)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return {"zip": str(out), "cases_completed": len(completed), "statepoints_omitted": len(statepoints),
            "statepoint_bytes_retained_on_source": sum(x["bytes"] for x in statepoints), "zip_sha256": _digest(out)}


def _inspect_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "checksums.json" not in names or "transfer.json" not in names:
            raise ValueError("Duplicate or missing ZIP entries")
        if len(names) > 10000:
            raise ValueError("Too many ZIP entries")
        if sum(entry.file_size for entry in archive.infolist()) > 2 * 1024 * 1024 * 1024:
            raise ValueError("ZIP uncompressed size exceeds 2 GiB")
        for entry in archive.infolist():
            _validate_member(entry.filename)
            parts = PurePosixPath(entry.filename).parts
            if parts[0] == "package" and (len(parts) != 2 or parts[1] not in PACKAGE_FILES):
                raise ValueError("Unexpected package entry")
            if parts[0] == "group" and not (len(parts) == 2 and parts[1] in GROUP_FILES or
                    len(parts) == 5 and parts[1] == "experiments" and parts[3].startswith("attempt_") and parts[4] in CASE_FILES):
                raise ValueError("Unexpected group entry")
            if entry.is_dir() or (entry.external_attr >> 16) & 0o170000 == 0o120000 or entry.flag_bits & 1:
                raise ValueError("Directory, symlink, or encrypted ZIP entry not allowed")
            if entry.file_size > 512 * 1024 * 1024:
                raise ValueError("Oversized ZIP entry")
        checksums = json.loads(archive.read("checksums.json"))
        if set(checksums) != set(names) - {"checksums.json"}:
            raise ValueError("ZIP checksum list mismatch")
        for name, expected in checksums.items():
            h = hashlib.sha256()
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            if h.hexdigest() != expected:
                raise ValueError(f"Checksum mismatch: {name}")
        metadata = json.loads(archive.read("transfer.json"))
        if metadata.get("schema") != SCHEMA or metadata.get("model") != MODEL_ID:
            raise ValueError("Transfer schema/model mismatch")
        return metadata, names


def _semantic_validate(folder, metadata, assignment):
    package = folder / "package"
    group = folder / "group"
    manifest = _read(package / "manifest.json")
    saved_manifest = _read(group / "manifest.json")
    package_info = _read(package / "package.json")
    if (manifest != saved_manifest or manifest.get("group_id") != metadata["package_id"] or
            manifest.get("model") != MODEL_ID or package_info.get("package_id") != metadata["package_id"]):
        raise ValueError("Manifest/model/group conflict")
    for filename, key in (("manifest.json", "manifest_sha256"), ("package.json", "package_sha256"),
                          ("SHA256SUMS.json", "hashes_sha256")):
        if _digest(package / filename) != metadata[key]:
            raise ValueError(f"Package identity mismatch: {filename}")
    registry = assignment["packages"].get(metadata["package_id"])
    if not registry or registry["package_sha256"] != metadata["package_sha256"] or registry["manifest_sha256"] != metadata["manifest_sha256"]:
        raise ValueError("Package not in pinned student assignment registry")
    expected = set(registry["scenario_ids"])
    cases = manifest["experiments"]
    if {case["scenario_id"] for case in cases} != expected or len(cases) != len(expected):
        raise ValueError("Scenario assignment mismatch")
    completed = set()
    runs = []
    for case in cases:
        if v2_scenarios.scenario_id(case["controls"], manifest["reference_config_sha256"]) != case["scenario_id"]:
            raise ValueError("Scenario identity mismatch")
        attempts = sorted((group / "experiments" / case["experiment_id"]).glob("attempt_*"))
        for attempt in attempts:
            status = _read(attempt / "status.json")
            if status.get("scenario_id") != case["scenario_id"]:
                raise ValueError("Conflicting scenario in attempt")
            if status.get("state") == "completed":
                required = ("summary.json", "resolved_config.json", "fields.npz", "openmc.log", "report.html", "model.xml")
                if any(not (attempt / name).is_file() for name in required):
                    raise ValueError("Completed attempt missing required outputs")
                item = v2_dataset._attempt(attempt, preview=True)
                if item["resolved"]["controls"] != case["controls"] or item["resolved"]["calculation"] != case["calculation"]:
                    raise ValueError("Conflicting physical input or budget")
                completed.add(case["experiment_id"])
                runs.append({"scenario_id":case["scenario_id"],"run_id":status["run_id"],
                             "attempt_sha256":hashlib.sha256(json.dumps({name:_digest(attempt/name) for name in
                                 ("status.json","summary.json","resolved_config.json","fields.npz")},sort_keys=True).encode()).hexdigest(),
                             "state":"completed"})
            else:
                runs.append({"scenario_id":case["scenario_id"],"run_id":status.get("run_id"),
                             "attempt_sha256":_digest(attempt/"status.json"),"state":status.get("state")})
    group_status = _read(group / "status.json")
    if group_status.get("state") == "completed" and completed != {case["experiment_id"] for case in cases}:
        raise ValueError("Incomplete completed group")
    return {"package_id":metadata["package_id"],"package_sha256":metadata["package_sha256"],
            "manifest_sha256":metadata["manifest_sha256"],"owner":registry["owner"],"stage":registry["stage"],
            "scenario_ids":sorted(expected),"completed_experiments":sorted(completed),"runs":runs,
            "group_state":group_status.get("state"),"physical_acceptance":"not_assessed_by_import",
            "training_acceptance":"not_granted"}


def import_zip(zip_path, output_root=IMPORTS, assignment_path=ASSIGNMENT):
    zip_path, output_root = Path(zip_path), Path(output_root)
    metadata, names = _inspect_zip(zip_path)
    assignment = _read(assignment_path)
    if assignment.get("schema") != "v2_student_assignment_v1":
        raise ValueError("Unsupported assignment version")
    zhash = _digest(zip_path)
    dest = output_root / metadata["package_id"] / zhash
    if dest.is_dir():
        receipt = _read(dest / "receipt.json")
        return {"state":"duplicate","path":str(dest),"receipt":receipt}
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v2_import_",dir=output_root) as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path) as archive:
            for name in names:
                if name == "checksums.json": continue
                target = tmp_path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            (tmp_path / "checksums.json").write_bytes(archive.read("checksums.json"))
        receipt = _semantic_validate(tmp_path, metadata, assignment)
        receipt["zip_sha256"] = zhash
        for prior in output_root.glob("*/*/receipt.json"):
            old = _read(prior)
            if (old["package_id"] == receipt["package_id"] and
                    (old.get("package_sha256") != receipt["package_sha256"] or
                     old.get("manifest_sha256") != receipt["manifest_sha256"])):
                raise ValueError("Conflicting package identity across deliveries")
            existing = {r["run_id"]:r["attempt_sha256"] for r in old["runs"] if r.get("run_id")}
            for run in receipt["runs"]:
                rid = run.get("run_id")
                if rid in existing and existing[rid] != run["attempt_sha256"]:
                    raise ValueError(f"Conflicting delivery for run_id {rid}")
        (tmp_path / "receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists(): raise FileExistsError(dest)
        tmp_path.rename(dest)
    return {"state":"imported","path":str(dest),"receipt":receipt}


def status_table(assignment_path=ASSIGNMENT, output_root=IMPORTS):
    assignment=_read(assignment_path)
    runs={}
    for path in Path(output_root).glob("*/*/receipt.json"):
        for record in _read(path)["runs"]:
            runs.setdefault(record["scenario_id"],{})[record.get("run_id")] = record["state"]
    pilot = GROUPS / "v2_advisor_pilot8_beavrs_v2_pilot_scope_v1"
    if (pilot / "status.json").is_file():
        for case in _read(pilot / "manifest.json")["experiments"]:
            attempts = sorted((pilot / "experiments" / case["experiment_id"]).glob("attempt_*"))
            for attempt in attempts:
                st=_read(attempt/"status.json")
                runs.setdefault(case["scenario_id"],{})[st.get("run_id")] = st.get("state")
    rows=[]
    for sid, record in assignment["scenarios"].items():
        states=list(runs.get(sid,{}).values())
        rows.append({"stage":record["stage"],"owner":record["owner"],"scenario_id":sid,
                     "state":"completed" if "completed" in states else "failed" if "failed" in states else "missing",
                     "distinct_runs":len(states),"physical_acceptance":"not_assessed",
                     "statistical_acceptance":"review_required"})
    return rows


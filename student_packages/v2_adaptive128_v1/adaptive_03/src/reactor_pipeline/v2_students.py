"""Versioned v2 scenario catalogue and immutable, advisor-gated student packages.

No function in this module starts OpenMC transport.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import re

from .parameter_space import CONTROLS, MODEL_ID, resolve_proposed
from .notebook_content import content_digest

PROJECT = Path(__file__).resolve().parents[2]
SPACE = PROJECT / "configs/v2_parameter_space_pilot_scope_v1.json"
PROFILE = PROJECT / "configs/v2_calculation_profile_pilot_80k_4h_v1.json"
SOURCE_FILES = (
    "src/reactor_pipeline/beavrs3d.py",
    "src/reactor_pipeline/parameter_space.py",
    "src/reactor_pipeline/v2_students.py",
    "src/reactor_pipeline/notebook_content.py",
    "src/reactor_pipeline/v2_student_runner.py",
    "src/reactor_pipeline/v2_integration.py",
    "src/reactor_pipeline/v2_dataset.py",
    "src/reactor_pipeline/dataset.py",
    "scripts/v2_student_production.py",
    "scripts/v2_transfer.py",
    "src/reactor_pipeline/v2_transfer.py",
    "src/reactor_pipeline/experiments.py",
    "configs/beavrs_derived_3d_reference.json",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False)
        out.write("\n")


def load_space(path=SPACE):
    path = Path(path)
    space = _read(path)
    if space.get("schema_version") != 1 or space.get("model") != MODEL_ID:
        raise ValueError("Unsupported v2 parameter-space version/model")
    if set(space["nominal"]) != CONTROLS or set(space["ranges"]) != CONTROLS:
        raise ValueError("Exactly eight v2 controls/ranges are required")
    if space["beavrs_source_commit"] != "1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22":
        raise ValueError("BEAVRS source revision changed")
    ref = PROJECT / space["reference_config"]
    if ref.resolve() != (PROJECT / "configs/beavrs_derived_3d_reference.json").resolve():
        raise ValueError("Unexpected reference configuration")
    for name, bounds in space["ranges"].items():
        lo, hi = bounds["lower"], bounds["upper"]
        if (lo is None) != (hi is None) or (lo is not None and not lo <= space["nominal"][name] <= hi):
            raise ValueError(f"Invalid range/nominal for {name}")
    resolve_proposed(space["nominal"])
    return space


def load_profile(path=PROFILE):
    profile = _read(path)
    calc = profile.get("calculation", {})
    required = {"particles_per_generation", "batches", "inactive", "generations_per_batch", "threads"}
    if profile.get("schema_version") != 1 or set(calc) != required:
        raise ValueError("Unsupported calculation profile")
    if any(type(calc[k]) is not int or calc[k] < 1 for k in required - {"inactive"}):
        raise ValueError("Calculation settings must be positive integers")
    if type(calc["inactive"]) is not int or not 0 <= calc["inactive"] < calc["batches"]:
        raise ValueError("Invalid inactive batches")
    if type(profile.get("seed_base")) is not int or profile["seed_base"] < 1:
        raise ValueError("Invalid seed base")
    budget = profile.get("group_runtime_budget_seconds")
    if budget is not None and (type(budget) is not int or budget <= 0):
        raise ValueError("Invalid group budget")
    return profile


def _approved(document, path):
    approval_path = Path(str(path) + ".approval.json")
    if not approval_path.is_file():
        return False
    approval = _read(approval_path)
    return (approval.get("status") == "approved" and
            approval.get("document_sha256") == digest(path) and
            bool(approval.get("reviewer")))

def production_ready(space=None, profile=None, space_path=SPACE, profile_path=PROFILE):
    space = load_space(space_path) if space is None else space
    profile = load_profile(profile_path) if profile is None else profile
    return (space.get("status") == "approved" and profile.get("status") == "approved" and
            all(v["lower"] is not None for v in space["ranges"].values()) and
            profile.get("group_runtime_budget_seconds") is not None and
            _approved(space, space_path) and _approved(profile, profile_path))


def scenario_id(controls, reference_sha):
    return identity({"model": MODEL_ID, "reference_config_sha256": reference_sha,
                     "controls": controls})


def generate(count, seed, output, *, space_path=SPACE, profile_path=PROFILE):
    if type(count) is not int or count < 1 or type(seed) is not int or seed < 0:
        raise ValueError("count must be positive and seed nonnegative integers")
    space_path, profile_path = Path(space_path), Path(profile_path)
    space, profile = load_space(space_path), load_profile(profile_path)
    ref_sha = digest(PROJECT / space["reference_config"])
    rng = random.Random(seed)
    records, rejected, seen = [], [], set()
    for attempt in range(max(100, count * 100)):
        if len(records) == count:
            break
        controls = deepcopy(space["nominal"]) if attempt == 0 else {
            key: (bounds["lower"] + (bounds["upper"] - bounds["lower"]) * rng.random()
                  if bounds["lower"] is not None else space["nominal"][key])
            for key, bounds in space["ranges"].items()
        }
        try:
            resolve_proposed(controls)
            sid = scenario_id(controls, ref_sha)
            if sid in seen:
                raise ValueError("duplicate physical scenario")
        except (ValueError, RuntimeError, UserWarning) as exc:
            rejected.append({"candidate_index": attempt, "controls": controls,
                             "reason": f"{type(exc).__name__}: {exc}"})
            continue
        seen.add(sid)
        records.append({"scenario_id": sid, "controls": controls})
    catalogue = {
        "schema": "beavrs_v2_scenario_list_v1", "state": "production_ready" if
            production_ready(space, profile, space_path, profile_path) and len(records) == count else "draft_unapproved",
        "model": MODEL_ID, "space_id": space["space_id"], "space_sha256": digest(space_path),
        "profile_id": profile["profile_id"], "profile_sha256": digest(profile_path),
        "reference_config_sha256": ref_sha, "sampling_seed": seed,
        "requested_count": count, "scenario_count": len(records),
        "generation_status": "complete" if len(records) == count else "incomplete_rejected",
        "scenarios": records, "rejected": rejected,
        "calculation_profile_separate": True,
    }
    _write_new(output, catalogue)
    return catalogue


def _notebook(markdown, cells):
    return {"cells": [{"cell_type": "markdown", "id": "intro", "metadata": {}, "source": [markdown + "\n"]}] +
            [{"cell_type": "code", "id": f"code-{index:02d}", "execution_count": None, "metadata": {}, "outputs": [],
              "source": code.splitlines(keepends=True)} for index, code in enumerate(cells, start=1)],
            "metadata": {"kernelspec": {"display_name": "Python (OpenMC Proje)",
                                        "language": "python", "name": "openmc-proje"},
                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


def _make_notebooks(package):
    start = '''import sys, os, json
from pathlib import Path
assert sys.platform == "linux" and "openmc-proje" in sys.executable, "WSL openmc-proje kernelini secin"
PACKAGE = Path.cwd().resolve()
assert PACKAGE.name == "__PACKAGE__", "Notebook paket dizininden acilmali"
PROJECT = next(p for p in (PACKAGE, *PACKAGE.parents) if (p / "src/reactor_pipeline/v2_students.py").is_file())
assert (PROJECT / "src/reactor_pipeline/v2_students.py").is_file()
sys.path.insert(0, str(PROJECT / "src"))
import openmc
from reactor_pipeline import v2_students, v2_student_runner
print("OpenMC", openmc.__version__, "| veri", os.environ.get("OPENMC_CROSS_SECTIONS"))
assert os.environ.get("OPENMC_CROSS_SECTIONS") and Path(os.environ["OPENMC_CROSS_SECTIONS"]).is_file()
info = v2_students.verify_package(PACKAGE, require_approval=False)
manifest = v2_students._read(PACKAGE / "manifest.json")
print("Grup", manifest["group_id"], "| durum", info["state"])
for case in manifest["experiments"]:
    print(case["experiment_id"], case["scenario_id"], case["controls"], case["calculation"])
'''.replace("__PACKAGE__", package)
    pre = '''check = v2_student_runner.preflight(PACKAGE)
print("On kontrol:", check)
'''
    launch = '''current = v2_student_runner.status(PACKAGE)
if current["state"] == "not_started":
    v2_students.verify_package(PACKAGE, require_approval=True)
    current = v2_student_runner.launch(PACKAGE)
print("Durum", current["state"], "PID", current.get("pid"))
print("Log", current.get("group_log"), "durum", current.get("status_file"), "sonuclar", current.get("group_dir"))
'''
    read = '''from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display
import json, sys
PACKAGE = Path.cwd().resolve()
PROJECT = next(p for p in (PACKAGE, *PACKAGE.parents) if (p / "src/reactor_pipeline/v2_students.py").is_file())
sys.path.insert(0, str(PROJECT / "src"))
from reactor_pipeline import v2_student_runner, v2_students
assert PACKAGE.name == "__PACKAGE__"
info = v2_students.verify_package(PACKAGE, require_approval=False)
saved = v2_student_runner.saved_results(PACKAGE)
print("Grup:", saved["group"]["state"], "| completed fiziksel kabul degildir")
rows = []
for case in saved["cases"]:
    summary = case["summary"] or {}
    k = summary.get("k_effective", {})
    manifest_case = next(x for x in v2_students._read(PACKAGE / "manifest.json")["experiments"]
                         if x["experiment_id"] == case["experiment_id"])
    rows.append({"experiment_id": case["experiment_id"],
                 "scenario_id": case["scenario_id"], "state": case["state"],
                 "controls": manifest_case["controls"], "calculation": manifest_case["calculation"],
                 "k": k.get("mean"), "MC_standard_error": k.get("mc_standard_error"),
                 "duration_s": summary.get("duration", {}).get("value"),
                 "fields_npz": str(Path(case["attempt"]) / "fields.npz") if case["attempt"] else None,
                 "summary_json": str(Path(case["attempt"]) / "summary.json") if case["attempt"] else None,
                 "physical_acceptance": case["physical_acceptance"],
                 "statistical_convergence": case["statistical_convergence"]})
display(pd.DataFrame(rows))
for case in saved["cases"]:
    if case["state"] != "completed":
        continue
    with np.load(Path(case["attempt"]) / "fields.npz", allow_pickle=False) as fields:
        z = fields["z_edges_cm"]
        axial = fields["kappa_fission_mean"].sum(axis=(1, 2))
        k_history = fields["k_generation"].copy()
        entropy = fields["shannon_entropy"].copy()
    fig, axes = plt.subplots(1, 3, figsize=(13, 3))
    axes[0].step((z[:-1]+z[1:])/2, axial, where="mid")
    axes[0].set_title("kappa-fission eksenel")
    axes[1].plot(k_history); axes[1].set_title("k gecmisi")
    axes[2].plot(entropy); axes[2].set_title("Shannon entropisi")
    fig.suptitle(case["experiment_id"] + " — inceleme gerekli")
    display(fig)
    plt.close(fig)
'''.replace("__PACKAGE__", package)
    return (_notebook("# V2 atanmis deneyler — Run All yalniz onayli paketi baslatir; taslak paket baslatilmaz.",
                      [start, pre, launch]),
            _notebook("# V2 kayitli sonuclar — salt okuma; completed fiziksel kabul degildir.", [read]))


def allocate(catalogue_path, student_ids, output_root, *, space_path=SPACE, profile_path=PROFILE):
    catalogue = _read(catalogue_path)
    space, profile = load_space(space_path), load_profile(profile_path)
    if (catalogue.get("schema") != "beavrs_v2_scenario_list_v1" or
            catalogue.get("generation_status") != "complete" or not catalogue["scenarios"]):
        raise ValueError("Invalid scenario catalogue")
    if (catalogue["space_sha256"] != digest(space_path) or
            catalogue["profile_sha256"] != digest(profile_path) or
            catalogue["reference_config_sha256"] != digest(PROJECT / space["reference_config"])):
        raise ValueError("Scenario catalogue configuration changed")
    ids = list(student_ids)
    if not ids or len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", x) for x in ids):
        raise ValueError("Unique simple student IDs required")
    output_root = Path(output_root)
    if output_root.exists():
        raise FileExistsError(output_root)
    sids = [row["scenario_id"] for row in catalogue["scenarios"]]
    if len(sids) != len(set(sids)) or any(
            scenario_id(row["controls"], catalogue["reference_config_sha256"]) != row["scenario_id"]
            for row in catalogue["scenarios"]):
        raise ValueError("Duplicate or invalid scenario catalogue identity")
    chunks = {student: [] for student in ids}
    for index, row in enumerate(catalogue["scenarios"]):
        chunks[ids[index % len(ids)]].append(row)
    output_root.mkdir(parents=True)
    for student, rows in chunks.items():
        if not rows:
            continue
        package_id = f"v2_{student}_{catalogue['space_id']}"
        folder = output_root / package_id
        folder.mkdir()
        cases = []
        for index, row in enumerate(rows):
            calc = dict(profile["calculation"], seed=profile["seed_base"] +
                        catalogue["scenarios"].index(row))
            cases.append({"experiment_id": f"V2-{student.upper()}-{index+1:04d}",
                          "scenario_id": row["scenario_id"], "controls": row["controls"],
                          "calculation": calc})
        manifest = {"schema_version": 1, "group_id": package_id, "model": MODEL_ID,
                    "space_id": space["space_id"], "profile_id": profile["profile_id"],
                    "space_sha256": catalogue["space_sha256"],
                    "profile_sha256": catalogue["profile_sha256"],
                    "reference_config_sha256": catalogue["reference_config_sha256"],
                    "production_gate": catalogue["state"],
                    "group_runtime_budget_seconds": profile["group_runtime_budget_seconds"],
                    "experiments": cases}
        _write_new(folder / "manifest.json", manifest)
        run_nb, read_nb = _make_notebooks(package_id)
        _write_new(folder / "01_calistir.ipynb", run_nb)
        _write_new(folder / "02_sonuclari_incele.ipynb", read_nb)
        for filename in ("01_calistir.ipynb", "02_sonuclari_incele.ipynb"):
            nb_path = folder / filename
            nb = _read(nb_path)
            nb["cells"].append({"cell_type": "markdown", "id": "delivery-instructions", "metadata": {},
                                "source": ["## Teslim — hesap başlatmaz\n",
                                           "Tamamlanan koşular için WSL terminalinde: `python scripts/v2_transfer.py export " +
                                           str(folder.relative_to(PROJECT)) + " deliveries/" + package_id +
                                           ".zip`. Durum `completed` olmadan teslim tam sayılmaz; varsayılan ZIP statepoint içermez.\n"]})
            nb_path.write_text(json.dumps(nb, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (folder / "README.md").write_text(
            f"# {package_id}\n\nAtanmis senaryo: {len(cases)}. "
            "01_calistir.ipynb Run All onaydan sonra bagimsiz WSL iscisini baslatir. "
            "02_sonuclari_incele.ipynb salt okur. Taslak paket uretim icin kapalidir.\n",
            encoding="utf-8")
        hashes = {name: digest(folder / name) for name in
                  ("manifest.json", "01_calistir.ipynb", "02_sonuclari_incele.ipynb", "README.md")}
        for name in ("01_calistir.ipynb", "02_sonuclari_incele.ipynb"):
            hashes[name] = content_digest(folder / name)
        hashes.update({name: digest(PROJECT / name) for name in SOURCE_FILES})
        _write_new(folder / "SHA256SUMS.json", hashes)
        _write_new(folder / "package.json", {"package_id": package_id,
                   "model": MODEL_ID, "state": catalogue["state"],
                   "project_root": ".", "package_path": str(folder.resolve().relative_to(PROJECT)),
                   "space_config": str(space_path.resolve().relative_to(PROJECT)),
                   "profile_config": str(profile_path.resolve().relative_to(PROJECT)),
                   "notebook_hash_schema": "notebook-inputs-v1",
                   "space_id": space["space_id"], "profile_id": profile["profile_id"],
                   "reference_config_sha256": catalogue["reference_config_sha256"],
                   "manifest_sha256": digest(folder / "manifest.json"),
                   "hashes_sha256": digest(folder / "SHA256SUMS.json")})
    return output_root


def verify_package(folder, *, require_approval=True, space_path=SPACE, profile_path=PROFILE):
    folder = Path(folder).resolve()
    info = _read(folder / "package.json")
    hashes = _read(folder / "SHA256SUMS.json")
    if info.get("distribution_config"):
        distribution_path = PROJECT / info["distribution_config"]
        if (distribution_path.resolve().parent != (PROJECT / "configs").resolve() or
                digest(distribution_path) != info.get("distribution_sha256")):
            raise ValueError("Package student-distribution config mismatch")
    if info.get("space_config"):
        space_path = PROJECT / info["space_config"]
        profile_path = PROJECT / info["profile_config"]
        if (space_path.resolve().parent != (PROJECT / "configs").resolve() or
                profile_path.resolve().parent != (PROJECT / "configs").resolve()):
            raise ValueError("Package configuration path outside project configs")
    if folder.name != info["package_id"] or info.get("project_root") != "." or folder != (PROJECT / info.get("package_path", "")).resolve() or set(hashes) != set(SOURCE_FILES) | {
            "manifest.json", "01_calistir.ipynb", "02_sonuclari_incele.ipynb", "README.md"}:
        raise ValueError("Package identity/file list mismatch")
    for rel, expected in hashes.items():
        path = PROJECT / rel if rel in SOURCE_FILES else folder / rel
        actual = (content_digest(path) if info.get("notebook_hash_schema") == "notebook-inputs-v1"
                  and rel.endswith(".ipynb") else digest(path)) if path.is_file() else None
        if actual != expected:
            raise ValueError(f"Package hash mismatch: {path}")
    manifest = _read(folder / "manifest.json")
    if (manifest["group_id"] != folder.name or manifest["model"] != MODEL_ID or
            digest(folder / "manifest.json") != info["manifest_sha256"] or
            digest(folder / "SHA256SUMS.json") != info["hashes_sha256"] or
            manifest["space_sha256"] != digest(space_path) or
            manifest["profile_sha256"] != digest(profile_path)):
        raise ValueError("Package manifest/config mismatch")
    if len({x["scenario_id"] for x in manifest["experiments"]}) != len(manifest["experiments"]):
        raise ValueError("Duplicate physical scenario in package")
    for case in manifest["experiments"]:
        if scenario_id(case["controls"], manifest["reference_config_sha256"]) != case["scenario_id"]:
            raise ValueError("Scenario ID mismatch")
    if require_approval:
        if not production_ready(space_path=space_path, profile_path=profile_path):
            raise ValueError("Parameter space or calculation profile lacks production approval")
        approval = _read(folder / "approval.json")
        if (info["state"] != "production_ready" or manifest["production_gate"] != "production_ready" or
                approval.get("status") != "approved" or
                approval.get("package_sha256") != digest(folder / "package.json") or
                approval.get("hashes_sha256") != digest(folder / "SHA256SUMS.json")):
            raise ValueError("Package lacks current advisor approval")
    return info



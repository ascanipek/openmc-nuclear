"""Advisor-issued student packages; hashes detect local changes, not adversarial tampering."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .experiments import PROJECT, load_manifest, preflight, launch
from .notebook_content import SCHEMA as NOTEBOOK_SCHEMA, content_digest

PACKAGES = PROJECT / "student_packages"
SCOPE = PROJECT / "docs" / "parameter_space_v1_proposed.md"
FILES = ["src/reactor_pipeline/beavrs3d.py", "src/reactor_pipeline/experiments.py",
         "src/reactor_pipeline/parameter_space.py", "src/reactor_pipeline/dataset.py",
         "src/reactor_pipeline/fuel_states.py", "src/reactor_pipeline/student_package.py",
         "src/reactor_pipeline/research_results.py", "src/reactor_pipeline/notebook_content.py",
         "scripts/experiments.py", "notebooks/01_deney_calistir.ipynb",
         "notebooks/02_sonuclari_incele.ipynb", "docs/dataset_contract_v1.md",
         "docs/student_experiment_workflow.md", "docs/scope_decision_v1.md", "pyproject.toml"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_draft(manifest_path, package_id):
    path, manifest, _ = load_manifest(manifest_path)
    if not package_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in package_id):
        raise ValueError("Invalid package ID")
    if manifest["group_id"] in ("beavrs3d_d3_b1_repeats_v1", "beavrs3d_d4_b1_positions_v1"):
        raise ValueError("D3/D4 require dedicated package notebooks; use the reviewed integrity-v2 builder")
    destination = PACKAGES / package_id
    destination.mkdir(parents=True, exist_ok=False)
    rels = FILES + [str(path.relative_to(PROJECT)), manifest["reference_config"]]
    hashes = {}
    notebooks = {}
    for rel in rels:
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT / rel, target)
        if rel == "notebooks/01_deney_calistir.ipynb":
            notebook_text = target.read_text(encoding="utf-8")
            notebook_text = notebook_text.replace("beavrs3d_d3_b1_repeats_v1", package_id)
            target.write_text(notebook_text, encoding="utf-8")
        if target.suffix == ".ipynb":
            notebooks[rel] = content_digest(target)
        else:
            hashes[rel] = digest(target)
    notebook_manifest = destination / "NOTEBOOK_CONTENT_SHA256.json"
    notebook_manifest.write_text(json.dumps({"schema": NOTEBOOK_SCHEMA, "notebooks": notebooks},
                                            ensure_ascii=False, indent=2))
    hashes[notebook_manifest.name] = digest(notebook_manifest)
    (destination / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2))
    info = {"schema_version": 2, "notebook_integrity_schema": NOTEBOOK_SCHEMA,
            "package_id": package_id, "group_id": manifest["group_id"],
            "model": manifest["model"], "manifest": str(path.relative_to(PROJECT)),
            "reference_config": manifest["reference_config"],
            "scope_proposal_sha256": digest(SCOPE), "approval_status": "draft_unapproved",
            "purpose": "student fixed manifest; protected raw files and canonical notebook inputs"}
    (destination / "package.json").write_text(json.dumps(info, indent=2))
    return destination


def verify(package_dir, *, require_approval=True):
    folder = Path(package_dir).resolve()
    if folder.parent != PACKAGES.resolve():
        raise ValueError("Package must be directly under student_packages")
    info = json.loads((folder / "package.json").read_text())
    hashes = json.loads((folder / "SHA256SUMS.json").read_text())
    expected_notebooks = {
        "beavrs3d_d3_b1_repeats_v1": ("notebooks/01_D3_calistir.ipynb", "notebooks/02_D3_sonuclari_incele.ipynb"),
        "beavrs3d_d4_b1_positions_v1": ("notebooks/01_D4_calistir.ipynb", "notebooks/02_D4_sonuclari_incele.ipynb"),
    }
    schema = info.get("notebook_integrity_schema")
    if schema is None:
        if info["package_id"] in expected_notebooks:
            required = {*expected_notebooks[info["package_id"]], "README.md", "src/reactor_pipeline/research_results.py"}
            if not required.issubset(hashes):
                raise ValueError("Required student package files are not hash pinned")
    elif schema == NOTEBOOK_SCHEMA:
        if info.get("schema_version") != 2 or "NOTEBOOK_CONTENT_SHA256.json" not in hashes:
            raise ValueError("Notebook integrity manifest is not hash pinned")
        if any(rel.endswith(".ipynb") for rel in hashes):
            raise ValueError("Version 2 notebooks must use content hashes only")
        notebook_manifest = json.loads((folder / "NOTEBOOK_CONTENT_SHA256.json").read_text(encoding="utf-8"))
        notebooks = notebook_manifest.get("notebooks")
        if notebook_manifest.get("schema") != NOTEBOOK_SCHEMA or not isinstance(notebooks, dict):
            raise ValueError("Unsupported notebook content manifest")
        actual_paths = {str(x.relative_to(folder)) for x in (folder / "notebooks").glob("*.ipynb")}
        if set(notebooks) != actual_paths:
            raise ValueError("Notebook list changed after package preparation")
        if info["group_id"] in expected_notebooks:
            required = set(expected_notebooks[info["group_id"]])
            if not required.issubset(notebooks):
                raise ValueError("Required student notebook inputs are not pinned")
            if not {"README.md", "src/reactor_pipeline/research_results.py", "src/reactor_pipeline/notebook_content.py"}.issubset(hashes):
                raise ValueError("Required student package files are not hash pinned")
        for rel, expected in notebooks.items():
            if not rel.startswith("notebooks/") or Path(rel).parent != Path("notebooks") or not rel.endswith(".ipynb"):
                raise ValueError("Invalid notebook manifest path")
            candidate = folder / rel
            if not candidate.is_file() or content_digest(candidate) != expected:
                raise ValueError(f"Notebook input hash mismatch: {candidate}")
    else:
        raise ValueError("Unsupported notebook integrity schema")
    for rel, expected in hashes.items():
        candidates = (folder / rel,) if Path(rel).parent == Path(".") or rel.startswith("notebooks/") else (folder / rel, PROJECT / rel)
        for candidate in candidates:
            if not candidate.is_file() or digest(candidate) != expected:
                raise ValueError(f"Package hash mismatch: {candidate}")
    if digest(SCOPE) != info["scope_proposal_sha256"]:
        raise ValueError("Scope proposal changed after package preparation")
    path, manifest, _ = load_manifest(PROJECT / info["manifest"])
    if manifest["group_id"] != info["group_id"]:
        raise ValueError("Manifest group mismatch")
    if require_approval:
        approval = json.loads((folder / "approval.json").read_text())
        if approval.get("status") != "approved" or approval.get("package_sha256") != digest(folder / "package.json") or approval.get("hashes_sha256") != digest(folder / "SHA256SUMS.json"):
            raise ValueError("Package lacks matching advisor approval")
        if info["group_id"] == "beavrs3d_d3_b1_repeats_v1":
            if approval.get("authorization") != "d3_research_repeats_only" or info["model"] != "beavrs_derived_3d_assembly_v1":
                raise ValueError("D3 research authorization mismatch")
        elif info["group_id"] == "beavrs3d_d4_b1_positions_v1":
            from .experiments import read_group
            _, _, d3_status = read_group("beavrs3d_d3_b1_repeats_v1")
            review_path = PROJECT / "runs/beavrs_3d/groups/beavrs3d_d3_b1_repeats_v1/review.json"
            review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
            if (approval.get("authorization") != "d4_research_after_d3_review" or
                    d3_status["state"] != "completed" or review.get("operator_acknowledged") is not True or
                    approval.get("d3_review_sha256") != digest(review_path)):
                raise ValueError("D4 requires completed D3, explicit review and matching D4 advisor approval")
        else:
            scope_approval = json.loads((PROJECT / "docs" / "scope_approval.json").read_text())
            if scope_approval.get("status") != "approved" or scope_approval.get("proposal_sha256") != digest(SCOPE):
                raise ValueError("Advisor scope/range decision not approved")
    return info


def launch_approved(package_dir):
    info = verify(package_dir, require_approval=True)
    check = preflight(PROJECT / info["manifest"])
    if check["group_id"] != info["group_id"]:
        raise ValueError("Preflight group mismatch")
    # Existing launcher supplies the atomic duplicate guard and detached WSL worker.
    return launch(PROJECT / info["manifest"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    make = sub.add_parser("draft")
    make.add_argument("manifest")
    make.add_argument("package_id")
    check = sub.add_parser("verify")
    check.add_argument("package_dir")
    args = parser.parse_args(argv)
    if args.action == "draft":
        print(create_draft(args.manifest, args.package_id))
    else:
        print(json.dumps(verify(args.package_dir), indent=2))


if __name__ == "__main__":
    main()









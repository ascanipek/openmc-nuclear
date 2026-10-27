"""Freeze the preselected 32 adaptive controls into the existing V2 package system."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reactor_pipeline import v2_students

SELECTION = ROOT / "scenarios/v2_adaptive128_v1/adaptive_01/selected_32.json"
REPORT = ROOT / "reports/adaptive_selection_v1/selection_report.json"
CATALOGUE = SELECTION.parent / "catalogue.json"
SPACE = ROOT / "configs/v2_parameter_space_pilot_scope_v1.json"
HALTON_PROFILE = ROOT / "configs/v2_calculation_profile_halton128_80k_24h_research_v1.json"
PROFILE = ROOT / "configs/v2_calculation_profile_adaptive01_80k_24h_research_v1.json"
OUTPUT = ROOT / "student_packages/v2_adaptive128_v1/adaptive_01"
PACKAGE_ID = "v2_adaptive_01_beavrs_v2_pilot_scope_v1"
AUTHORIZATION = "Advisor's ADAPTIVE-01 request, 2026-10-27; first 32 only"


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    if PROFILE.exists() or CATALOGUE.exists() or OUTPUT.exists():
        raise FileExistsError("ADAPTIVE-01 package/profile already exists; will not overwrite")
    selected = json.loads(SELECTION.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if selected["selection_report_sha256"] != v2_students.digest(REPORT):
        raise ValueError("Selection report changed")
    if len(selected["selected"]) != 32 or len({x["scenario_id"] for x in selected["selected"]}) != 32:
        raise ValueError("Selection must contain exactly 32 unique cases")
    space = v2_students.load_space(SPACE)
    original = v2_students.load_profile(HALTON_PROFILE)
    if not v2_students.production_ready(space_path=SPACE, profile_path=HALTON_PROFILE):
        raise ValueError("Reference Halton profile is not approved")
    if original["calculation"] != {"particles_per_generation": 80000, "batches": 600,
                                   "inactive": 300, "generations_per_batch": 1, "threads": 6}:
        raise ValueError("Halton calculation budget differs")
    reference_sha = v2_students.digest(ROOT / space["reference_config"])
    if selected["reference_config_sha256"] != reference_sha:
        raise ValueError("Reference config changed")
    for case in selected["selected"]:
        if v2_students.scenario_id(case["controls"], reference_sha) != case["scenario_id"]:
            raise ValueError("Selected controls/identity changed")
    profile = {"schema_version": 1,
               "profile_id": "beavrs_v2_adaptive01_80k_24h_research_v1",
               "status": "approved",
               "purpose": "ADAPTIVE-01 first 32 cases only; controlled research; no later adaptive groups",
               "calculation": original["calculation"],
               "seed_base": 73001,
               "group_runtime_budget_seconds": 86400,
               "production_approval": "adaptive01_first32_equal_halton_transport_budget_only",
               "decision_source": AUTHORIZATION}
    write_new(PROFILE, profile)
    write_new(Path(str(PROFILE) + ".approval.json"), {
        "status": "approved", "document_sha256": v2_students.digest(PROFILE),
        "reviewer": "danisman: " + AUTHORIZATION,
        "scope": "only_adaptive_01_first_32_controlled_research",
        "physical_acceptance": "not_assessed", "statistical_convergence": "review_required",
        "training_acceptance": "not_granted", "decision_source": AUTHORIZATION})
    if not v2_students.production_ready(space_path=SPACE, profile_path=PROFILE):
        raise ValueError("New adaptive calculation profile not approved")
    catalogue = {
        "schema": "beavrs_v2_scenario_list_v1", "state": "production_ready",
        "model": space["model"], "space_id": space["space_id"],
        "space_sha256": v2_students.digest(SPACE),
        "profile_id": profile["profile_id"], "profile_sha256": v2_students.digest(PROFILE),
        "reference_config_sha256": reference_sha,
        "sampling_seed": report["candidate_generation"]["seed"],
        "sampling_method": "scrambled_Sobol_4096_then_ensemble_35_35_20_10_diverse_greedy_v1",
        "selection_report_sha256": v2_students.digest(REPORT),
        "requested_count": 32, "scenario_count": 32, "generation_status": "complete",
        "scenarios": selected["selected"], "rejected": [],
        "calculation_profile_separate": True,
    }
    write_new(CATALOGUE, catalogue)
    v2_students.allocate(CATALOGUE, ["adaptive_01"], OUTPUT,
                         space_path=SPACE, profile_path=PROFILE)
    package = OUTPUT / PACKAGE_ID
    manifest = v2_students._read(package / "manifest.json")
    if (len(manifest["experiments"]) != 32 or
        [x["scenario_id"] for x in manifest["experiments"]] !=
            [x["scenario_id"] for x in selected["selected"]] or
        [x["calculation"]["seed"] for x in manifest["experiments"]] != list(range(73001, 73033))):
        raise ValueError("Allocated package identity or seeds differ")
    readme = package / "README.md"
    with readme.open("a", encoding="utf-8") as stream:
        stream.write("\nADAPTIVE-01: first 32 only; selection evidence at "
                     "reports/adaptive_selection_v1/selection_report.json (SHA256 "
                     + v2_students.digest(REPORT) + ").\n"
                     "Equal transport settings to Halton: 600/300 batches, 80,000 particles/generation, "
                     "one generation/batch, six threads; 24-hour group ceiling. "
                     "Completed is not physical or statistical acceptance.\n\n"
                     "WSL openmc-proje environment, from project root:\n"
                     "- Status: python scripts/v2_student_production.py status "
                     + str(package.relative_to(ROOT)) + "\n"
                     "- Stop: python scripts/v2_student_production.py stop "
                     + str(package.relative_to(ROOT)) + "\n"
                     "- Resume after explicit review: python scripts/v2_student_production.py resume "
                     + str(package.relative_to(ROOT)) + "\n"
                     "- Results: open 02_sonuclari_incele.ipynb, read-only.\n")
    hashes_path = package / "SHA256SUMS.json"
    hashes = v2_students._read(hashes_path)
    hashes["README.md"] = v2_students.digest(readme)
    hashes_path.write_text(json.dumps(hashes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    package_path = package / "package.json"
    info = v2_students._read(package_path)
    info["hashes_sha256"] = v2_students.digest(hashes_path)
    package_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_new(package / "approval.json", {
        "status": "approved", "authorization": "adaptive01_first32_controlled_research_only",
        "model": space["model"], "group_id": PACKAGE_ID,
        "meaning": "Technical transport preparation only; no physical, convergence or training acceptance",
        "package_sha256": v2_students.digest(package_path),
        "hashes_sha256": v2_students.digest(hashes_path),
        "decision_source": AUTHORIZATION})
    v2_students.verify_package(package, require_approval=True)
    print(json.dumps({"package": str(package), "cases": 32,
                      "profile": str(PROFILE), "profile_sha256": v2_students.digest(PROFILE),
                      "package_sha256": v2_students.digest(package_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

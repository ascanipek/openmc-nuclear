"""Deterministic nested V2 proposal: 8 preserved + 16 OAT + Halton candidates.

This module prepares draft catalogues and student packages only. No transport.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import random

from .parameter_space import CONTROLS, resolve_proposed
from . import v2_scenarios as base

PROJECT = base.PROJECT
SPACE = PROJECT / "configs/v2_parameter_space_pilot_proposed_v1.json"
PROFILE = PROJECT / "configs/v2_calculation_profile_pilot_draft_v1.json"
DISTRIBUTION = PROJECT / "configs/v2_student_distribution_draft_v1.json"
LEGACY_CATALOGUE = PROJECT / "scenarios/v2_catalogue_draft_v1.json"
SEED = 20261018
PRIMES = (2, 3, 5, 7, 11, 13, 17, 19)


def _radical_inverse(index, radix):
    result, place = 0.0, 1.0 / radix
    while index:
        index, digit = divmod(index, radix)
        result += digit * place
        place /= radix
    return result


def _catalogue(records, rejected, count, space_path, profile_path):
    space, profile = base.load_space(space_path), base.load_profile(profile_path)
    shift_rng = random.Random(SEED)
    order = list(space["nominal"])
    sampling = {
        "version": "legacy_8_OAT_shifted_Halton_v1",
        "control_order": order,
        "halton_bases": list(PRIMES),
        "halton_shifts": [shift_rng.random() for _ in order],
        "scaling": "linear lower + (upper-lower) * shifted radical inverse",
        "generator_sha256": base.digest(__file__),
    }
    return {
        "schema": "beavrs_v2_scenario_list_v1",
        "state": "production_ready" if base.production_ready(space, profile, space_path, profile_path)
                 else "draft_unapproved",
        "model": space["model"], "space_id": space["space_id"],
        "space_sha256": base.digest(space_path), "profile_id": profile["profile_id"],
        "profile_sha256": base.digest(profile_path),
        "reference_config_sha256": base.digest(PROJECT / space["reference_config"]),
        "sampling_seed": SEED, "sampling_method": "legacy_8_then_OAT_endpoints_then_shifted_Halton_v1",
        "sampling_parameters": sampling,
        "requested_count": count, "scenario_count": len(records),
        "generation_status": "complete" if len(records) == count else "incomplete_rejected",
        "scenarios": deepcopy(records), "rejected": deepcopy(rejected),
        "calculation_profile_separate": True,
    }


def nested_catalogues(space_path=SPACE, profile_path=PROFILE, legacy_path=LEGACY_CATALOGUE):
    space = base.load_space(space_path)
    base.load_profile(profile_path)
    reference_sha = base.digest(PROJECT / space["reference_config"])
    legacy = base._read(legacy_path)
    if legacy.get("scenario_count") != 8 or len(legacy["scenarios"]) != 8:
        raise ValueError("Pinned draft must contain exactly eight legacy scenarios")
    records, rejected, seen = [], [], set()

    def consider(controls, label):
        try:
            resolve_proposed(controls)
            for key in CONTROLS:
                bounds = space["ranges"][key]
                if not bounds["lower"] <= controls[key] <= bounds["upper"]:
                    raise ValueError(f"{key} outside proposed sampling bounds")
            sid = base.scenario_id(controls, reference_sha)
            if sid in seen:
                raise ValueError("duplicate physical scenario")
        except (ValueError, RuntimeError, UserWarning) as exc:
            rejected.append({"candidate": label, "controls": controls,
                             "reason": f"{type(exc).__name__}: {exc}"})
            return
        seen.add(sid)
        records.append({"scenario_id": sid, "controls": deepcopy(controls),
                        "sampling_stratum": label})

    for index, row in enumerate(legacy["scenarios"]):
        if base.scenario_id(row["controls"], reference_sha) != row["scenario_id"]:
            raise ValueError("Legacy physical scenario identity changed")
        consider(row["controls"], f"preserved_draft_{index+1}")
    if len(records) != 8:
        raise ValueError("Legacy scenario fell outside proposed bounds or duplicated")
    for key in space["nominal"]:
        for endpoint in ("lower", "upper"):
            controls = deepcopy(space["nominal"])
            proposed = space["ranges"][key][endpoint]
            if proposed == controls[key]:
                proposed = (space["ranges"][key]["lower"] + space["ranges"][key]["upper"]) / 2
            controls[key] = proposed
            consider(controls, f"one_at_a_time_{key}_{endpoint}")
    if len(records) != 24:
        raise ValueError("Expected 16 unique one-at-a-time endpoints")
    rng = random.Random(SEED)
    shifts = [rng.random() for _ in CONTROLS]
    names = list(space["nominal"])
    index = 1
    while len(records) < 256 and index <= 10000:
        controls = {}
        for dim, key in enumerate(names):
            bound = space["ranges"][key]
            unit = (_radical_inverse(index, PRIMES[dim]) + shifts[dim]) % 1.0
            controls[key] = bound["lower"] + (bound["upper"] - bound["lower"]) * unit
        consider(controls, f"multiparameter_halton_{index}")
        index += 1
    if len(records) != 256:
        raise ValueError(f"Only {len(records)} valid scenarios from 10000 candidates")
    return {n: _catalogue(records[:n], rejected, n, space_path, profile_path)
            for n in (32, 128, 256)}


def prepare(output_root, *, space_path=SPACE, profile_path=PROFILE,
            distribution_path=DISTRIBUTION, legacy_path=LEGACY_CATALOGUE):
    space_path, profile_path, distribution_path, legacy_path = map(
        Path, (space_path, profile_path, distribution_path, legacy_path))
    root = Path(output_root).resolve()
    if root.exists():
        raise FileExistsError(root)
    distribution = base._read(distribution_path)
    students = distribution["student_ids"]
    if (distribution.get("schema_version") != 1 or
            distribution.get("status") not in ("draft_unapproved", "approved") or
            distribution.get("students_are_placeholders") is not (distribution["status"] == "draft_unapproved") or
            distribution.get("stages") != [32, 128, 256] or
            not students or len(students) != len(set(students))):
        raise ValueError("Invalid central student distribution")
    ready = base.production_ready(space_path=space_path, profile_path=profile_path)
    if ready and (distribution["status"] != "approved" or
                  not base._approved(distribution, distribution_path)):
        raise ValueError("Student distribution lacks pinned approval")
    catalogues = nested_catalogues(space_path, profile_path, legacy_path)
    root.mkdir(parents=True)
    previous = 0
    result = {}
    for count, total in catalogues.items():
        stage = f"stage_{count}"
        folder = root / stage
        folder.mkdir()
        base._write_new(folder / "catalogue_total.json", total)
        delta = _catalogue(total["scenarios"][previous:count], total["rejected"],
                           count-previous, space_path, profile_path)
        delta["parent_total_count"] = count
        delta["new_scenario_offset"] = previous
        base._write_new(folder / "catalogue_new.json", delta)
        ids = [f"{stage}_{student}" for student in students]
        packages = base.allocate(folder / "catalogue_new.json", ids, folder / "packages",
                                 space_path=space_path, profile_path=profile_path)
        for package in packages.iterdir():
            info_path = package / "package.json"
            info = base._read(info_path)
            info["distribution_config"] = str(distribution_path.resolve().relative_to(PROJECT))
            info["distribution_sha256"] = base.digest(distribution_path)
            info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
        counts = {p.name: len(base._read(p / "manifest.json")["experiments"])
                  for p in packages.iterdir()}
        result[stage] = {"total": count, "new": count-previous, "package_counts": counts,
                         "catalogue": str(folder / "catalogue_total.json")}
        previous = count
    base._write_new(root / "preparation.json", {
        "state": "production_ready_subject_to_package_approval" if ready else "draft_unapproved",
        "distribution_id": distribution["distribution_id"],
        "distribution_sha256": base.digest(distribution_path),
        "space_sha256": base.digest(space_path),
        "profile_sha256": base.digest(profile_path),
        "legacy_catalogue_sha256": base.digest(legacy_path),
        "sampling_seed": SEED,
        "stages": result,
        "production_approval": None,
    })
    return result




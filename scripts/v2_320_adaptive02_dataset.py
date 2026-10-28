"""Append validated ADAPTIVE-02 handoff to the frozen adaptive-01 dataset."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reactor_pipeline import v2_dataset, v2_students
from v2_256_ml_dataset import ARRAY_KEYS, SOURCE_FILES, sha, read, rows_csv

OLD = ROOT / "datasets/v2_288_adaptive01_exploratory_v1"
OUT = ROOT / "datasets/v2_320_adaptive02_exploratory_v1"
PACKAGE = ROOT / "student_packages/v2_adaptive128_v1/adaptive_02/student_packages/v2_adaptive128_v1/adaptive_02/v2_adaptive_02_beavrs_v2_pilot_scope_v1"
GROUP = ROOT / "runs/beavrs_3d/v2_groups" / PACKAGE.name
SELECTION = ROOT / "scenarios/v2_adaptive128_v1/adaptive_02/selected_32.json"
RECEIPT = ROOT / "deliveries/imported" / PACKAGE.name / "0f07922c29faf9ab2dbe8d2e1a5ea2bbe0445bda0cf3f1d219596c83c7073a65/receipt.json"


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def build():
    if OUT.exists():
        raise FileExistsError(OUT)
    old_manifest = read(OLD / "dataset_manifest.json")
    old_splits = read(OLD / "splits.json")
    for name, digest in old_manifest["output_sha256"].items():
        if sha(OLD / name) != digest:
            raise ValueError(f"Frozen 256 changed: {name}")
    old_rows = csv_rows(OLD / "scenarios.csv")
    old_targets = csv_rows(OLD / "targets_keff.csv")
    old_quality = csv_rows(OLD / "quality_report.csv")
    old_ids = [row["scenario_id"] for row in old_rows]
    role = {sid: key for key in ("train", "calibration", "test") for sid in old_splits[key]}
    if (len(old_rows) != 288 or len(set(old_ids)) != 288 or
            [row["scenario_id"] for row in old_targets] != old_ids or
            {key: len(old_splits[key]) for key in ("train", "calibration", "test")} !=
                {"train": 240, "calibration": 25, "test": 23} or
            len(role) != 288 or set(role) != set(old_ids) or
            any(row["split"] != role[row["scenario_id"]] for row in old_rows)):
        raise ValueError("Frozen 288 identity/split mismatch")
    receipt = read(RECEIPT)
    package_info = read(PACKAGE / "package.json")
    approval = read(PACKAGE / "approval.json")
    if (receipt["package_id"] != PACKAGE.name or
            receipt["package_sha256"] != sha(PACKAGE / "package.json") or
            receipt["manifest_sha256"] != sha(PACKAGE / "manifest.json") or
            receipt["group_state"] != "completed" or
            len(receipt["completed_experiments"]) != 32 or
            approval.get("status") != "approved" or
            approval.get("package_sha256") != receipt["package_sha256"] or
            package_info.get("state") != "production_ready"):
        raise ValueError("ADAPTIVE-02 imported receipt or technical approval mismatch")
    package_manifest = read(PACKAGE / "manifest.json")
    group_manifest = read(GROUP / "manifest.json")
    status = read(GROUP / "status.json")
    selected = read(SELECTION)["selected"]
    cases = package_manifest["experiments"]
    if (status["state"] != "completed" or len(status["completed_experiments"]) != 32 or
            status.get("error") is not None or cases != group_manifest["experiments"] or
            sha(GROUP / "manifest.json") != status["manifest_sha256"] or
            len(cases) != 32 or
            [x["scenario_id"] for x in cases] != [x["scenario_id"] for x in selected] or
            [x["controls"] for x in cases] != [x["controls"] for x in selected] or
            {x["experiment_id"] for x in cases} != set(status["completed_experiments"])):
        raise ValueError("ADAPTIVE-02 package/selection/completion mismatch")
    seen = set(old_ids)
    arrays = {key: [] for key in (*ARRAY_KEYS, "target_normalized_kappa")}
    with np.load(OLD / "fields.npz", allow_pickle=False) as old_fields:
        for key in arrays:
            if old_fields[key].shape[0] != 288:
                raise ValueError(f"Old field shape differs: {key}")
            arrays[key].append(old_fields[key])
    new_rows, new_targets, new_quality = [], [], []
    source_hashes = []
    for offset, case in enumerate(cases):
        sid = case["scenario_id"]
        if sid in seen:
            raise ValueError(f"Duplicate scenario: {sid}")
        seen.add(sid)
        attempts = list((GROUP / "experiments" / case["experiment_id"]).glob("attempt_*"))
        complete = [p for p in attempts if (p / "status.json").is_file() and
                    read(p / "status.json").get("state") == "completed"]
        if len(complete) != 1:
            raise ValueError(f"Expected one completed attempt: {case['experiment_id']}")
        attempt = complete[0]
        if list(attempt.glob("statepoint.*.h5")):
            raise ValueError(f"Lightweight handoff unexpectedly contains statepoint: {attempt}")
        item = v2_dataset._attempt(attempt, preview=True)
        if item is None:
            raise ValueError(f"Attempt not exportable: {attempt}")
        fields, summary, resolved, target = (item[key] for key in ("fields", "summary", "resolved", "target"))
        if (summary["scenario_id"] != sid or summary["experiment_id"] != case["experiment_id"] or
                resolved["controls"] != case["controls"] or
                resolved["calculation"] != case["calculation"] or
                resolved["reference_config_sha256"] != old_rows[0]["reference_config_sha256"] or
                resolved["openmc_version"] != "0.16.0" or
                resolved["nuclear_data"]["coverage_result"] !=
                    "all required library temperatures bracket requested material temperatures"):
            raise ValueError(f"Physical or calculation provenance mismatch: {sid}")
        if {key: case["calculation"][key] for key in
            ("particles_per_generation", "batches", "inactive", "generations_per_batch", "threads")} != {
                "particles_per_generation": 80000, "batches": 600, "inactive": 300,
                "generations_per_batch": 1, "threads": 6}:
            raise ValueError(f"Calculation budget differs: {sid}")
        fuel = fields["fuel_volume_fraction"] > 0
        raw = fields["kappa_fission_mean"]
        fission = fields["fission_mean"]
        fission_se = fields["fission_std_dev"]
        if (target.shape != (20, 17, 17) or not np.isfinite(target).all() or
                np.any(target < 0) or np.any(target[~fuel] != 0) or
                not np.isclose(target.sum(), 1, rtol=0, atol=1e-10) or
                np.any(raw < 0) or np.any(fission < 0) or
                not np.isfinite(fields["k_generation"]).all() or
                not np.isfinite(fields["shannon_entropy"]).all()):
            raise ValueError(f"Normalized field/history differs: {sid}")
        for key in ARRAY_KEYS:
            arrays[key].append(fields[key][None])
        arrays["target_normalized_kappa"].append(target[None])
        hashes = {name.replace(".", "_") + "_sha256": sha(attempt / name) for name in SOURCE_FILES}
        k = summary["k_effective"]
        if not (np.isfinite(k["mean"]) and np.isfinite(k["mc_standard_error"]) and
                k["mean"] > 0 and k["mc_standard_error"] >= 0):
            raise ValueError(f"Invalid k: {sid}")
        row = {"row": 288 + offset, "scenario_id": sid, "owner": "adaptive_02",
               "stage": "adaptive_02", "split": "train", **case["controls"],
               "experiment_id": case["experiment_id"], "run_id": summary["run_id"],
               "seed": case["calculation"]["seed"], "openmc_version": resolved["openmc_version"],
               **{key: case["calculation"][key] for key in
                  ("particles_per_generation", "batches", "inactive", "generations_per_batch", "threads")},
               "cross_sections_xml_sha256": resolved["nuclear_data"]["cross_sections_xml_sha256"],
               "reference_config_sha256": resolved["reference_config_sha256"],
               "package_id": PACKAGE.name, "source_attempt": str(attempt.relative_to(ROOT)),
               "source_zip_sha256": receipt["zip_sha256"], **hashes}
        if set(row) != set(old_rows[0]):
            raise ValueError(f"Scenario CSV schema mismatch: {sid}")
        new_rows.append(row)
        new_targets.append({"row": 288 + offset, "scenario_id": sid, "k_mean": k["mean"],
                            "k_mc_standard_error": k["mc_standard_error"], "k_unit": k["unit"],
                            "target_kappa_sum": float(target.sum()),
                            "raw_kappa_sum_fuel": float(raw[fuel].sum())})
        low = fuel & ((fission == 0) | (fission < 5 * fission_se) |
                      (fission < 1e-6 * float(fission.max())))
        zero = int(np.count_nonzero(fuel & (raw == 0)))
        old_filter = fields["relative_error_reporting_mask"]
        rel = np.divide(fields["kappa_fission_std_dev"], raw,
                        out=np.full((20, 17, 17), np.nan), where=fuel & (raw > 0))
        valid_rel = rel[np.isfinite(rel)]
        details = {"row": 288 + offset, "scenario_id": sid,
                   "fuel_voxels": int(fuel.sum()), "zero_fuel_kappa_voxels": zero,
                   "zero_fuel_fission_voxels": int(np.count_nonzero(fuel & (fission == 0))),
                   "zero_flux_voxels": int(np.count_nonzero(fields["flux_mean"] == 0)),
                   "zero_kappa_standard_error_voxels": int(np.count_nonzero(fields["kappa_fission_std_dev"] == 0)),
                   "low_signal_fuel_voxels": int(low.sum()),
                   "low_signal_kappa_share": float(raw[low].sum() / raw[fuel].sum()),
                   "previous_reliability_filter_voxels": int(old_filter.sum()),
                   "positive_kappa_voxels_outside_previous_filter": int(np.count_nonzero(fuel & ~old_filter & (raw > 0))),
                   "kappa_relative_mc_error_median_positive_signal": float(np.median(valid_rel)) if len(valid_rel) else "",
                   "kappa_relative_mc_error_p95_positive_signal": float(np.percentile(valid_rel, 95)) if len(valid_rel) else "",
                   "raw_kappa_sum_fuel": float(raw[fuel].sum()),
                   "raw_fission_sum_fuel": float(fission[fuel].sum())}
        checks = [
            ("structure_and_identity", "PASS", "Frozen 288 + imported receipt, package, attempt, mesh and normalization checked"),
            ("fuel_zero_signal", "WARNING" if zero else "PASS", f"{zero} measured-zero fuel voxels"),
            ("low_signal", "WARNING" if low.any() else "PASS", "Original V2 low-signal diagnostic"),
            ("statepoint_local", "NOT_ASSESSED", "Lightweight handoff omits statepoint; retained on student source machine"),
            ("source_convergence", "NOT_ASSESSED", "Independent source convergence review required"),
            ("physical_validation", "NOT_ASSESSED", "No physical validation acceptance"),
            ("training_acceptance", "NOT_ASSESSED", "Exploratory inclusion only; no accepted marker"),
        ]
        new_quality.extend({**details, "check": name, "status": state, "detail": detail}
                           for name, state, detail in checks)
        source_hashes.append({"experiment_id": case["experiment_id"], "scenario_id": sid,
                              "source_attempt": str(attempt.relative_to(ROOT)), "source_sha256": hashes})
    if len(new_rows) != 32 or len(seen) != 320:
        raise ValueError("Expected 32 new and 320 unique scenarios")
    combined = {key: np.concatenate(value, axis=0) for key, value in arrays.items()}
    if (any(value.shape[0] != 320 for value in combined.values()) or
            any(set(row) != set(old_quality[0]) for row in new_quality)):
        raise ValueError("Combined field or quality schema mismatch")
    split = {**old_splits, "version": "frozen_256_plus_adaptive01_adaptive02_train_v1",
             "policy": "Original 208/25/23 unchanged; 32 ADAPTIVE-01 and 32 ADAPTIVE-02 IDs added to train",
             "test_use": "Original 23 test cases only; no fitting, tuning or calibration",
            "train": [*old_splits["train"], *(row["scenario_id"] for row in new_rows)]}
    if {key: len(split[key]) for key in ("train", "calibration", "test")} != {
            "train": 272, "calibration": 25, "test": 23}:
        raise ValueError("Invalid 320 split")
    OUT.mkdir(parents=True)
    rows_csv(OUT / "scenarios.csv", [*old_rows, *new_rows])
    rows_csv(OUT / "targets_keff.csv", [*old_targets, *new_targets])
    rows_csv(OUT / "quality_report.csv", [*old_quality, *new_quality])
    np.savez_compressed(OUT / "fields.npz", **combined)
    (OUT / "splits.json").write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema": "beavrs_v2_320_adaptive02_exploratory_v1", "branch": "adaptive_02",
                "state": "PROVISIONAL_EXPLORATORY; no physical/statistical/training acceptance",
                "scenario_count": 320, "source_256_count": 256, "new_adaptive01_count": 32,
                "new_adaptive02_count": 32,
                "split_counts": {key: len(split[key]) for key in ("train", "calibration", "test")},
                "old_dataset_sha256": {p.name: sha(p) for p in OLD.iterdir() if p.is_file()},
                "old_288_row_order_and_values": "Preserved exactly in first 288 rows/array slices",
                "source_package_sha256": sha(PACKAGE / "package.json"),
                "source_selection_sha256": sha(SELECTION),
                "source_group_manifest_sha256": sha(GROUP / "manifest.json"),
                "source_group_status_sha256": sha(GROUP / "status.json"),
                "source_receipt_sha256": sha(RECEIPT),
                "source_zip_sha256": receipt["zip_sha256"],
                "source_statepoint_policy": "omitted from lightweight handoff; retained on source machine",
                "source_attempts": source_hashes,
                "array_order": old_manifest["array_order"],
                "mesh_shape_zyx": old_manifest["mesh_shape_zyx"],
                "field_units": old_manifest["field_units"],
                "normalized_target": old_manifest["normalized_target"],
                "normalized_target_uncertainty": old_manifest["normalized_target_uncertainty"],
                "nuclear_index_hash_counts": dict(Counter(row["cross_sections_xml_sha256"] for row in [*old_rows, *new_rows])),
                "nuclear_hdf5_byte_equivalence": old_manifest["nuclear_hdf5_byte_equivalence"],
                "quality_warning": "Zero and low-signal voxels, source convergence and physical validation remain under review",
                "output_sha256": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()}}
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"dataset": str(OUT), "scenarios": 320,
                      "split_counts": manifest["split_counts"],
                      "nuclear_index_hash_counts": manifest["nuclear_index_hash_counts"]}))


if __name__ == "__main__":
    build()

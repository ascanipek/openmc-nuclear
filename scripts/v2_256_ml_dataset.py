"""Deterministic preview dataset from checksum-verified imported V2 handoffs.

No acceptance markers are created or inferred. This module never launches transport.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from reactor_pipeline import v2_dataset
from reactor_pipeline.dataset import SHAPE, split_for

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = (
    "u235_enrichment_wt_percent", "fuel_temperature_K", "moderator_temperature_K",
    "coolant_pressure_MPa", "elemental_boron_ppm", "pin_pitch_cm",
    "pellet_radius_cm", "insertion_percent",
)
SOURCE_FILES = ("status.json", "summary.json", "resolved_config.json", "fields.npz")
ARRAY_KEYS = tuple(x for x in v2_dataset.REQUIRED_FIELDS if x != "array_order")
SCHEMA = "beavrs_v2_imported_256_preview_v1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows_csv(path, rows):
    if not rows:
        raise ValueError("Empty CSV")
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def collect(catalogue_path, imports_root, audit_path):
    catalogue_path, imports_root, audit_path = map(Path, (catalogue_path, imports_root, audit_path))
    catalogue = read(catalogue_path)
    if catalogue.get("scenario_count") != 256 or len(catalogue["scenarios"]) != 256:
        raise ValueError("Expected exactly 256 catalogue scenarios")
    scenarios = catalogue["scenarios"]
    ids = [x["scenario_id"] for x in scenarios]
    if len(set(ids)) != 256 or any(set(x["controls"]) != set(CONTROLS) for x in scenarios):
        raise ValueError("Duplicate scenario or incompatible controls in catalogue")
    with audit_path.open(encoding="utf-8") as stream:
        audit = list(csv.DictReader(stream))
    if len(audit) != 256 or {x["scenario_id"] for x in audit} != set(ids):
        raise ValueError("Central audit does not match catalogue")
    if any(x["verified_state"] != "completed" or int(x["completed_attempts"]) < 1 for x in audit):
        raise ValueError("Central audit has missing completion")
    audit_by_id = {x["scenario_id"]: x for x in audit}
    receipt_paths = sorted(imports_root.glob("*/*/receipt.json"))
    if len(receipt_paths) != 12:
        raise ValueError(f"Expected 12 imported delivery receipts; found {len(receipt_paths)}")
    by_id = {}
    source_groups = []
    for receipt_path in receipt_paths:
        bundle = receipt_path.parent
        receipt = read(receipt_path)
        ledger = read(bundle / "checksums.json")
        manifest_path = bundle / "package/manifest.json"
        package_path = bundle / "package/package.json"
        for file_path, key in ((manifest_path, "manifest_sha256"), (package_path, "package_sha256")):
            if sha(file_path) != receipt[key]:
                raise ValueError(f"Receipt package hash mismatch: {file_path}")
        manifest = read(manifest_path)
        if manifest != read(bundle / "group/manifest.json"):
            raise ValueError(f"Saved manifest mismatch: {bundle}")
        if receipt["package_id"] != manifest["group_id"] or receipt["package_id"] != bundle.parent.name:
            raise ValueError(f"Group identity mismatch: {bundle}")
        if set(receipt["scenario_ids"]) != {x["scenario_id"] for x in manifest["experiments"]}:
            raise ValueError(f"Receipt scenarios mismatch: {bundle}")
        source_groups.append({"package_id": receipt["package_id"], "zip_sha256": receipt["zip_sha256"],
                              "receipt_sha256": sha(receipt_path), "manifest_sha256": receipt["manifest_sha256"],
                              "package_sha256": receipt["package_sha256"]})
        recorded = {(x["scenario_id"], x["run_id"], x["attempt_sha256"]): x["state"]
                    for x in receipt["runs"]}
        for case in manifest["experiments"]:
            sid = case["scenario_id"]
            if sid not in set(ids) or sid in by_id:
                raise ValueError(f"Unexpected or duplicate scenario in imports: {sid}")
            if case["controls"] != scenarios[ids.index(sid)]["controls"]:
                raise ValueError(f"Catalogue physical inputs differ: {sid}")
            if (receipt["owner"], receipt["stage"], receipt["package_id"]) != (
                    audit_by_id[sid]["owner"], audit_by_id[sid]["stage"], audit_by_id[sid]["package_id"]):
                raise ValueError(f"Audit assignment mismatch: {sid}")
            case_dir = bundle / "group/experiments" / case["experiment_id"]
            successful, attempts = [], []
            for attempt in sorted(case_dir.glob("attempt_*")):
                status_path = attempt / "status.json"
                status = read(status_path)
                if status.get("scenario_id") != sid or status.get("experiment_id") != case["experiment_id"]:
                    raise ValueError(f"Attempt case mismatch: {attempt}")
                if status["state"] == "completed":
                    relative = attempt.relative_to(bundle).as_posix()
                    for filename in SOURCE_FILES + ("openmc.log", "model.xml", "report.html"):
                        key = relative + "/" + filename
                        if key not in ledger or sha(attempt / filename) != ledger[key]:
                            raise ValueError(f"Source checksum mismatch: {key}")
                    item = v2_dataset._attempt(attempt, preview=True)
                    if item is None or item["resolved"]["controls"] != case["controls"]:
                        raise ValueError(f"Invalid completed attempt: {attempt}")
                    if item["resolved"]["calculation"] != case["calculation"]:
                        raise ValueError(f"Calculation differs from manifest: {attempt}")
                    hashes = {name: sha(attempt / name) for name in SOURCE_FILES}
                    attempt_sha = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
                    if recorded.get((sid, status["run_id"], attempt_sha)) != "completed":
                        raise ValueError(f"Receipt run hash mismatch: {attempt}")
                    successful.append((attempt, item, hashes))
                attempts.append({"state": status["state"], "run_id": status.get("run_id"),
                                 "path": str(attempt.relative_to(ROOT))})
            if len(successful) != 1:
                raise ValueError(f"Expected exactly one completed attempt for {sid}; got {len(successful)}")
            if len(attempts) != int(audit_by_id[sid]["completed_attempts"]) + int(audit_by_id[sid]["failed_attempts"]):
                raise ValueError(f"Attempt count differs from central audit: {sid}")
            attempt, item, hashes = successful[0]
            by_id[sid] = {"attempt": attempt, "item": item, "hashes": hashes,
                          "attempts": attempts, "receipt": receipt, "bundle": bundle}
    if set(by_id) != set(ids):
        raise ValueError(f"Imported scenario coverage mismatch: {len(by_id)} of 256")
    return catalogue, scenarios, by_id, source_groups


def build(catalogue_path, imports_root, audit_path, output_dir):
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    catalogue, scenarios, by_id, source_groups = collect(catalogue_path, imports_root, audit_path)
    arrays = {key: [] for key in ARRAY_KEYS}
    arrays["target_normalized_kappa"] = []
    scenario_rows, target_rows, quality_rows, source_rows = [], [], [], []
    for index, scenario in enumerate(scenarios):
        sid = scenario["scenario_id"]
        record = by_id[sid]
        item = record["item"]
        summary, resolved, fields = item["summary"], item["resolved"], item["fields"]
        if resolved["reference_config_sha256"] != catalogue["reference_config_sha256"]:
            raise ValueError(f"Reference configuration differs from catalogue: {sid}")
        if resolved["openmc_version"] != "0.16.0":
            raise ValueError(f"OpenMC version differs: {sid}")
        calc = resolved["calculation"]
        if tuple(calc[key] for key in ("particles_per_generation", "batches", "inactive", "generations_per_batch")) != (80000, 600, 300, 1):
            raise ValueError(f"Calculation profile differs: {sid}")
        if resolved["nuclear_data"]["coverage_result"] != "all required library temperatures bracket requested material temperatures":
            raise ValueError(f"Nuclear temperature coverage differs: {sid}")
        raw = fields["kappa_fission_mean"]
        fuel = fields["fuel_volume_fraction"] > 0
        target = item["target"]
        if target.shape != SHAPE or not np.isclose(float(target.sum()), 1, rtol=0, atol=1e-10):
            raise ValueError(f"Bad normalized target: {sid}")
        if not np.array_equal(target[~fuel], np.zeros_like(target[~fuel])):
            raise ValueError(f"Target outside fuel geometry: {sid}")
        k = summary["k_effective"]
        if not (np.isfinite(k["mean"]) and np.isfinite(k["mc_standard_error"]) and
                k["mean"] > 0 and k["mc_standard_error"] >= 0):
            raise ValueError(f"Invalid k target: {sid}")
        for key in ARRAY_KEYS:
            arrays[key].append(fields[key])
        arrays["target_normalized_kappa"].append(target)
        split = split_for(sid)
        scenario_rows.append({"row": index, "scenario_id": sid, "owner": record["receipt"]["owner"],
                              "stage": record["receipt"]["stage"], "split": split,
                              **{key: scenario["controls"][key] for key in CONTROLS},
                              "experiment_id": summary["experiment_id"], "run_id": summary["run_id"],
                              "seed": resolved["calculation"]["seed"],
                              "openmc_version": resolved["openmc_version"],
                              "particles_per_generation": resolved["calculation"]["particles_per_generation"],
                              "batches": resolved["calculation"]["batches"],
                              "inactive": resolved["calculation"]["inactive"],
                              "generations_per_batch": resolved["calculation"]["generations_per_batch"],
                              "threads": resolved["calculation"]["threads"],
                              "cross_sections_xml_sha256": resolved["nuclear_data"]["cross_sections_xml_sha256"],
                              "reference_config_sha256": resolved["reference_config_sha256"],
                              "package_id": record["receipt"]["package_id"],
                              "source_attempt": str(record["attempt"].relative_to(ROOT)),
                              "source_zip_sha256": record["receipt"]["zip_sha256"],
                              **{name.replace(".", "_") + "_sha256": digest for name, digest in record["hashes"].items()}})
        target_rows.append({"row": index, "scenario_id": sid, "k_mean": k["mean"],
                            "k_mc_standard_error": k["mc_standard_error"],
                            "k_unit": k["unit"], "target_kappa_sum": float(target.sum()),
                            "raw_kappa_sum_fuel": float(raw[fuel].sum())})
        original_attempt = (ROOT / "runs/beavrs_3d/v2_groups" / record["receipt"]["package_id"] /
                            "experiments" / summary["experiment_id"] / record["attempt"].name)
        statepoint_local = (original_attempt / "status.json").is_file() and (
            read(original_attempt / "status.json").get("run_id") == summary["run_id"]) and bool(
                list(original_attempt.glob("statepoint.*.h5")))
        old_filter = fields["relative_error_reporting_mask"]
        fission = fields["fission_mean"]
        fission_se = fields["fission_std_dev"]
        low = fuel & ((fission == 0) | (fission < 5 * fission_se) |
                      (fission < 1e-6 * float(fission.max())))
        low_kappa_share = float(raw[low].sum() / raw[fuel].sum())
        zero_fuel = int(np.count_nonzero(fuel & (raw == 0)))
        rel = np.divide(fields["kappa_fission_std_dev"], raw,
                        out=np.full(SHAPE, np.nan), where=(fuel & (raw > 0)))
        rel_valid = rel[np.isfinite(rel)]
        if not np.all(np.isfinite(fields["k_generation"])) or not np.all(np.isfinite(fields["shannon_entropy"])):
            raise ValueError(f"Invalid generation diagnostics: {sid}")
        negative_means = sum(int(np.count_nonzero(fields[key] < 0))
                             for key in ("flux_mean", "fission_mean", "kappa_fission_mean"))
        negative_std = sum(int(np.count_nonzero(fields[key] < 0))
                           for key in ("flux_std_dev", "fission_std_dev", "kappa_fission_std_dev"))
        if negative_means or negative_std:
            raise ValueError(f"Negative tally mean or standard error: {sid}")
        checks = [
            ("structure_and_identity", "PASS", "Catalogue, receipt, source hashes, [z,y,x], units, mesh and normalization validated"),
            ("fuel_zero_signal", "WARNING" if zero_fuel else "PASS", f"{zero_fuel} of {int(fuel.sum())} geometric fuel voxels have zero measured kappa-fission"),
            ("low_signal", "WARNING" if int(low.sum()) else "PASS",
             f"{int(low.sum())} geometric fuel voxels meet existing v2_runner low-signal diagnostic; kappa share {low_kappa_share:.8g}"),
            ("statepoint_local", "PASS" if statepoint_local else "WARNING", "Present" if statepoint_local else "Omitted from lightweight delivery; retained on source machine"),
            ("nuclear_index", "PASS" if resolved["nuclear_data"]["cross_sections_xml_sha256"] ==
             "ba7f6d5a371b5a8de8157356f8ef5d1c17cb0ed60accccfbc3075f46ae13f489" else "WARNING",
             "Index checksum recorded; alternate Kaggle index path/hash needs HDF5 byte-level equivalence review"
             if resolved["nuclear_data"]["cross_sections_xml_sha256"] !=
             "ba7f6d5a371b5a8de8157356f8ef5d1c17cb0ed60accccfbc3075f46ae13f489"
             else "Local ENDF/B-VIII.0 cross_sections.xml index checksum"),
            ("source_convergence", "NOT_ASSESSED", "Generation histories stored; independent source convergence review required"),
            ("physical_validation", "NOT_ASSESSED", "No physical validation acceptance granted"),
            ("training_acceptance", "NOT_ASSESSED", "No accepted_for_data_production marker"),
        ]
        quality_rows.extend({"row": index, "scenario_id": sid, "check": check, "status": status,
                             "detail": detail, "fuel_voxels": int(fuel.sum()),
                             "zero_fuel_kappa_voxels": zero_fuel,
                             "zero_fuel_fission_voxels": int(np.count_nonzero(fuel & (fission == 0))),
                             "zero_flux_voxels": int(np.count_nonzero(fields["flux_mean"] == 0)),
                             "zero_kappa_standard_error_voxels": int(np.count_nonzero(fields["kappa_fission_std_dev"] == 0)),
                             "low_signal_fuel_voxels": int(low.sum()),
                             "low_signal_kappa_share": low_kappa_share,
                             "previous_reliability_filter_voxels": int(old_filter.sum()),
                             "positive_kappa_voxels_outside_previous_filter": int(np.count_nonzero(fuel & ~old_filter & (raw > 0))),
                             "kappa_relative_mc_error_median_positive_signal": float(np.median(rel_valid)) if len(rel_valid) else "",
                             "kappa_relative_mc_error_p95_positive_signal": float(np.percentile(rel_valid, 95)) if len(rel_valid) else "",
                             "raw_kappa_sum_fuel": float(raw[fuel].sum()),
                             "raw_fission_sum_fuel": float(fields["fission_mean"][fuel].sum())}
                            for check, status, detail in checks)
        source_rows.append({"scenario_id": sid, "run_id": summary["run_id"],
                            "all_attempts": record["attempts"]})
    stacked = {key: np.stack(values) for key, values in arrays.items()}
    split_ids = {name: [row["scenario_id"] for row in scenario_rows if row["split"] == name]
                 for name in ("train", "calibration", "test")}
    if sum(len(x) for x in split_ids.values()) != 256 or set().union(*map(set, split_ids.values())) != {
            x["scenario_id"] for x in scenarios}:
        raise ValueError("Invalid split partition")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v2_ml_preview_", dir=output_dir.parent) as temp:
        work = Path(temp)
        rows_csv(work / "scenarios.csv", scenario_rows)
        rows_csv(work / "targets_keff.csv", target_rows)
        rows_csv(work / "quality_report.csv", quality_rows)
        np.savez_compressed(work / "fields.npz", **stacked)
        (work / "splits.json").write_text(json.dumps({
            "version": "scenario_sha256_80_10_10_v1", "policy": "Existing v2 dataset split_for; scenario identity stable",
            "test_use": "Hold out from model selection and adaptive sampling", **split_ids,
        }, indent=2) + "\n", encoding="utf-8")
        (work / "dataset_manifest.json").write_text(json.dumps({
            "schema": SCHEMA, "state": "preview_not_accepted_for_training",
            "scenario_count": 256, "row_order": "catalogue_total_256.json order",
            "array_order": ["sample", "z", "y", "x"], "mesh_shape_zyx": list(SHAPE),
            "field_units": v2_dataset.UNITS,
            "normalized_target": "kappa_fission_mean / sum(kappa_fission_mean over fuel_volume_fraction > 0); no second volume weighting",
            "normalized_target_uncertainty": "not estimated; covariance with common denominator unavailable",
            "low_signal_policy": "Geometric fuel mask fixed; measured zero voxels retained and flagged; no relative error for zero mean",
            "training_eligible_count": 0, "physical_acceptance": "not_assessed",
            "statistical_acceptance": "review_required",
            "catalogue_sha256": sha(catalogue_path), "central_audit_sha256": sha(audit_path),
            "exporter_sha256": sha(Path(__file__)),
            "openmc_version": "0.16.0",
            "nuclear_index_hash_counts": {
                key: sum(row["cross_sections_xml_sha256"] == key for row in scenario_rows)
                for key in sorted({row["cross_sections_xml_sha256"] for row in scenario_rows})
            },
            "nuclear_hdf5_byte_equivalence": "not_assessed_for_alternate_index",
            "statepoints_available_on_this_machine": sum(
                row["status"] == "PASS" for row in quality_rows if row["check"] == "statepoint_local"),
            "source_groups": source_groups, "source_attempts": source_rows,
            "output_sha256": {name: sha(work / name) for name in (
                "scenarios.csv", "targets_keff.csv", "quality_report.csv", "fields.npz", "splits.json")},
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        work.rename(output_dir)
    return {"scenarios": 256, "splits": {name: len(values) for name, values in split_ids.items()},
            "output": str(output_dir)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, default=ROOT / "scenarios/v2_students_portable_v1/catalogue_total_256.json")
    parser.add_argument("--imports", type=Path, default=ROOT / "deliveries/imported")
    parser.add_argument("--audit", type=Path, default=ROOT / "deliveries/imported/central_256_audit.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "datasets/v2_256_preview_v1")
    args = parser.parse_args()
    print(json.dumps(build(args.catalogue, args.imports, args.audit, args.output), indent=2))


if __name__ == "__main__":
    main()








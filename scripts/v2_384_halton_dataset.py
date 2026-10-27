"""Build provisional 384-case Halton branch from frozen 256 and validated receipts."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reactor_pipeline import v2_dataset  # noqa: E402
from v2_256_ml_dataset import ARRAY_KEYS, SOURCE_FILES, sha, read, rows_csv  # noqa: E402

OLD = ROOT / "datasets/v2_256_preview_v1"
OUT = ROOT / "datasets/v2_384_halton_v1"
IMPORTS = ROOT / "deliveries/imported_halton128"
ASSIGNMENT = ROOT / "configs/v2_halton128_assignment_v1.json"
LOCAL_INDEX = "ba7f6d5a371b5a8de8157356f8ef5d1c17cb0ed60accccfbc3075f46ae13f489"


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
            raise ValueError(f"Frozen 256 source changed: {name}")
    old_rows = csv_rows(OLD / "scenarios.csv")
    old_targets = csv_rows(OLD / "targets_keff.csv")
    old_quality = csv_rows(OLD / "quality_report.csv")
    old_ids = [row["scenario_id"] for row in old_rows]
    if len(old_ids) != 256 or len(set(old_ids)) != 256 or [x["scenario_id"] for x in old_targets] != old_ids:
        raise ValueError("Frozen 256 row order or identity differs")
    if {key: len(old_splits[key]) for key in ("train", "calibration", "test")} != {"train": 208, "calibration": 25, "test": 23}:
        raise ValueError("Frozen split counts differ")
    role = {sid: key for key in ("train", "calibration", "test") for sid in old_splits[key]}
    if len(role) != 256 or set(role) != set(old_ids) or any(row["split"] != role[row["scenario_id"]] for row in old_rows):
        raise ValueError("Frozen split identity differs")
    assignment = read(ASSIGNMENT)
    seen = set(old_ids)
    records, sources, failed_attempts = [], [], []
    for number in ("01", "02", "03", "04"):
        package_id = f"v2_halton_{number}_beavrs_v2_pilot_scope_v1"
        receipts = list((IMPORTS / package_id).glob("*/receipt.json"))
        if len(receipts) != 1:
            raise ValueError(f"Expected one imported receipt: {package_id}")
        receipt_path = receipts[0]
        bundle = receipt_path.parent
        receipt = read(receipt_path)
        catalogue_path = ROOT / assignment["source_catalogues"][f"halton_{number}"]
        catalogue = read(catalogue_path)
        cases = read(bundle / "package/manifest.json")["experiments"]
        pin = assignment["packages"][package_id]
        if (receipt["group_state"] != "completed" or len(receipt["completed_experiments"]) != 32 or
                len(cases) != 32 or len(catalogue["scenarios"]) != 32 or
                receipt["package_sha256"] != pin["package_sha256"] or
                receipt["manifest_sha256"] != pin["manifest_sha256"] or
                sha(bundle / "package/package.json") != pin["package_sha256"] or
                sha(bundle / "package/manifest.json") != pin["manifest_sha256"] or
                read(bundle / "group/manifest.json")["experiments"] != cases or
                [case["scenario_id"] for case in cases] != pin["scenario_ids"]):
            raise ValueError(f"Group/package mismatch: {package_id}")
        for name, digest in read(bundle / "checksums.json").items():
            if sha(bundle / name) != digest:
                raise ValueError(f"Imported file changed: {bundle / name}")
        sources.append({"package_id": package_id, "receipt_sha256": sha(receipt_path),
                        "zip_sha256": receipt["zip_sha256"], "catalogue_sha256": sha(catalogue_path)})
        for case, source in zip(cases, catalogue["scenarios"]):
            sid = case["scenario_id"]
            if sid in seen or sid != source["scenario_id"] or case["controls"] != source["controls"]:
                raise ValueError(f"Duplicate or mismatched Halton scenario: {sid}")
            seen.add(sid)
            attempts = list((bundle / "group/experiments" / case["experiment_id"]).glob("attempt_*"))
            completed = [a for a in attempts if read(a / "status.json")["state"] == "completed"]
            if len(completed) != 1:
                raise ValueError(f"Expected exactly one completed attempt: {case['experiment_id']}")
            for other in attempts:
                if other != completed[0]:
                    failed_attempts.append({"package_id": package_id, "experiment_id": case["experiment_id"],
                                            "attempt": str(other.relative_to(ROOT)),
                                            "state": read(other / "status.json")["state"]})
            attempt = completed[0]
            item = v2_dataset._attempt(attempt, preview=True)
            if item is None or item["resolved"]["controls"] != case["controls"] or item["resolved"]["calculation"] != case["calculation"]:
                raise ValueError(f"Invalid completed attempt: {attempt}")
            if item["summary"]["scenario_id"] != sid or item["summary"]["experiment_id"] != case["experiment_id"]:
                raise ValueError(f"Attempt identity mismatch: {attempt}")
            resolved = item["resolved"]
            if resolved["reference_config_sha256"] != old_rows[0]["reference_config_sha256"] or resolved["openmc_version"] != "0.16.0":
                raise ValueError(f"Physical reference/version mismatch: {sid}")
            if resolved["nuclear_data"]["coverage_result"] != "all required library temperatures bracket requested material temperatures":
                raise ValueError(f"Nuclear temperature coverage mismatch: {sid}")
            if {k: case["calculation"][k] for k in ("particles_per_generation", "batches", "inactive", "generations_per_batch")} != {
                    "particles_per_generation": 80000, "batches": 600, "inactive": 300, "generations_per_batch": 1}:
                raise ValueError(f"Calculation budget mismatch: {sid}")
            records.append((case, item, receipt, attempt))
    if len(records) != 128 or len(seen) != 384:
        raise ValueError("Expected 128 new and 384 total unique scenarios")

    arrays = {key: [] for key in (*ARRAY_KEYS, "target_normalized_kappa")}
    with np.load(OLD / "fields.npz", allow_pickle=False) as original:
        for key in arrays:
            if original[key].shape[0] != 256:
                raise ValueError(f"Frozen array shape mismatch: {key}")
            arrays[key].append(original[key])
    new_rows, new_targets, new_quality = [], [], []
    for offset, (case, item, receipt, attempt) in enumerate(records):
        index, sid = 256 + offset, case["scenario_id"]
        fields, summary, resolved = item["fields"], item["summary"], item["resolved"]
        fuel = fields["fuel_volume_fraction"] > 0
        raw = fields["kappa_fission_mean"]
        fission, fission_se = fields["fission_mean"], fields["fission_std_dev"]
        target = item["target"]
        if (target.shape != (20, 17, 17) or not np.isclose(target.sum(), 1, atol=1e-10, rtol=0) or
                np.any(target[~fuel] != 0) or np.any(target < 0) or
                not np.all(np.isfinite(fields["k_generation"])) or
                not np.all(np.isfinite(fields["shannon_entropy"]))):
            raise ValueError(f"Normalized field/history invalid: {sid}")
        if any(np.any(fields[k] < 0) for k in ("flux_mean", "fission_mean", "kappa_fission_mean")):
            raise ValueError(f"Negative physical tally: {sid}")
        for key in ARRAY_KEYS:
            arrays[key].append(fields[key][None])
        arrays["target_normalized_kappa"].append(target[None])
        hashes = {name.replace(".", "_") + "_sha256": sha(attempt / name) for name in SOURCE_FILES}
        k = summary["k_effective"]
        if not np.isfinite(k["mean"]) or not np.isfinite(k["mc_standard_error"]) or k["mean"] <= 0 or k["mc_standard_error"] < 0:
            raise ValueError(f"Invalid k target: {sid}")
        row = {"row": index, "scenario_id": sid, "owner": receipt["owner"], "stage": receipt["stage"],
               "split": "train", **case["controls"], "experiment_id": case["experiment_id"],
               "run_id": summary["run_id"], "seed": case["calculation"]["seed"],
               "openmc_version": resolved["openmc_version"],
               **{key: case["calculation"][key] for key in ("particles_per_generation", "batches", "inactive", "generations_per_batch", "threads")},
               "cross_sections_xml_sha256": resolved["nuclear_data"]["cross_sections_xml_sha256"],
               "reference_config_sha256": resolved["reference_config_sha256"],
               "package_id": receipt["package_id"], "source_attempt": str(attempt.relative_to(ROOT)),
               "source_zip_sha256": receipt["zip_sha256"], **hashes}
        if set(row) != set(old_rows[0]):
            raise ValueError(f"Scenario CSV schema mismatch: {sid}")
        new_rows.append(row)
        new_targets.append({"row": index, "scenario_id": sid, "k_mean": k["mean"],
                            "k_mc_standard_error": k["mc_standard_error"], "k_unit": k["unit"],
                            "target_kappa_sum": float(target.sum()), "raw_kappa_sum_fuel": float(raw[fuel].sum())})
        low = fuel & ((fission == 0) | (fission < 5 * fission_se) | (fission < 1e-6 * float(fission.max())))
        zero = int(np.count_nonzero(fuel & (raw == 0)))
        old_filter = fields["relative_error_reporting_mask"]
        rel = np.divide(fields["kappa_fission_std_dev"], raw,
                        out=np.full((20, 17, 17), np.nan), where=fuel & (raw > 0))
        valid_rel = rel[np.isfinite(rel)]
        local = ROOT / "runs/beavrs_3d/v2_groups" / receipt["package_id"] / "experiments" / case["experiment_id"] / attempt.name
        statepoint_local = ((local / "status.json").is_file() and read(local / "status.json").get("run_id") == summary["run_id"] and
                            bool(list(local.glob("statepoint.*.h5"))))
        checks = [
            ("structure_and_identity", "PASS", "Receipt, catalogue, hashes, [z,y,x], units, mesh and normalization validated"),
            ("fuel_zero_signal", "WARNING" if zero else "PASS", f"{zero} measured-zero geometric fuel voxels"),
            ("low_signal", "WARNING" if low.any() else "PASS", "Existing V2 low-signal diagnostic"),
            ("statepoint_local", "PASS" if statepoint_local else "WARNING", "Local source statepoint" if statepoint_local else "Omitted from lightweight ZIP"),
            ("nuclear_index", "PASS" if resolved["nuclear_data"]["cross_sections_xml_sha256"] == LOCAL_INDEX else "WARNING", "Alternate index needs HDF5 byte equivalence review"),
            ("source_convergence", "NOT_ASSESSED", "Independent source convergence review required"),
            ("physical_validation", "NOT_ASSESSED", "No physical validation acceptance"),
            ("training_acceptance", "NOT_ASSESSED", "Exploratory inclusion only; no accepted_for_data_production marker"),
        ]
        details = {"row": index, "scenario_id": sid, "fuel_voxels": int(fuel.sum()),
                   "zero_fuel_kappa_voxels": zero, "zero_fuel_fission_voxels": int(np.count_nonzero(fuel & (fission == 0))),
                   "zero_flux_voxels": int(np.count_nonzero(fields["flux_mean"] == 0)),
                   "zero_kappa_standard_error_voxels": int(np.count_nonzero(fields["kappa_fission_std_dev"] == 0)),
                   "low_signal_fuel_voxels": int(low.sum()),
                   "low_signal_kappa_share": float(raw[low].sum() / raw[fuel].sum()),
                   "previous_reliability_filter_voxels": int(old_filter.sum()),
                   "positive_kappa_voxels_outside_previous_filter": int(np.count_nonzero(fuel & ~old_filter & (raw > 0))),
                   "kappa_relative_mc_error_median_positive_signal": float(np.median(valid_rel)) if len(valid_rel) else "",
                   "kappa_relative_mc_error_p95_positive_signal": float(np.percentile(valid_rel, 95)) if len(valid_rel) else "",
                   "raw_kappa_sum_fuel": float(raw[fuel].sum()), "raw_fission_sum_fuel": float(fission[fuel].sum())}
        new_quality.extend({**details, "check": name, "status": state, "detail": detail} for name, state, detail in checks)

    combined = {key: np.concatenate(values, axis=0) for key, values in arrays.items()}
    if any(value.shape[0] != 384 for value in combined.values()) or any(set(row) != set(old_quality[0]) for row in new_quality):
        raise ValueError("Combined array or quality schema mismatch")
    split = {**old_splits, "version": "frozen_256_plus_halton128_train_v1",
             "policy": "Original 208/25/23 unchanged; all 128 Halton IDs added to train",
             "test_use": "Original 23 test cases only; no fitting, tuning or calibration",
             "train": [*old_splits["train"], *(row["scenario_id"] for row in new_rows)]}
    if {key: len(split[key]) for key in ("train", "calibration", "test")} != {"train": 336, "calibration": 25, "test": 23}:
        raise ValueError("Invalid 384 split counts")
    OUT.mkdir(parents=True)
    rows_csv(OUT / "scenarios.csv", [*old_rows, *new_rows])
    rows_csv(OUT / "targets_keff.csv", [*old_targets, *new_targets])
    rows_csv(OUT / "quality_report.csv", [*old_quality, *new_quality])
    np.savez_compressed(OUT / "fields.npz", **combined)
    (OUT / "splits.json").write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema": "beavrs_v2_384_halton_preview_v1", "branch": "halton",
                "state": "PROVISIONAL_EXPLORATORY; no physical/statistical/training acceptance",
                "scenario_count": 384, "source_256_count": 256, "new_halton_count": 128,
                "split_counts": {key: len(split[key]) for key in ("train", "calibration", "test")},
                "old_dataset_sha256": {p.name: sha(p) for p in OLD.iterdir() if p.is_file()},
                "old_256_row_order_and_values": "Preserved exactly in first 256 rows/array slices",
                "source_groups": sources, "failed_or_incomplete_attempts_not_used": failed_attempts,
                "source_assignment_sha256": sha(ASSIGNMENT),
                "array_order": old_manifest["array_order"], "mesh_shape_zyx": old_manifest["mesh_shape_zyx"],
                "field_units": old_manifest["field_units"], "normalized_target": old_manifest["normalized_target"],
                "normalized_target_uncertainty": old_manifest["normalized_target_uncertainty"],
                "nuclear_index_hash_counts": dict(Counter(row["cross_sections_xml_sha256"] for row in [*old_rows, *new_rows])),
                "nuclear_hdf5_byte_equivalence": old_manifest["nuclear_hdf5_byte_equivalence"],
                "quality_warning": "Zero/low-signal voxels and source convergence require separate review; completion is not validation",
                "output_sha256": {p.name: sha(p) for p in OUT.iterdir() if p.is_file()}}
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "scenarios": 384, "new": 128,
                      "splits": manifest["split_counts"], "nuclear_index_hash_counts": manifest["nuclear_index_hash_counts"]}))


if __name__ == "__main__":
    build()



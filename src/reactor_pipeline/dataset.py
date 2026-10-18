"""Read-only recorded-run to versioned training/preview dataset export."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .beavrs3d import MODEL_ID
from .experiments import GROUPS

SCHEMA = "beavrs3d_dataset_v1"
SHAPE = (20, 17, 17)
UNITS = {"fission": "reactions/source particle",
         "kappa_fission": "eV/source particle; fission energy generation approximation, not total local heat deposition",
         "flux": "particle-cm/source particle"}


def normalized_kappa(raw, fuel_fraction):
    raw = np.asarray(raw, dtype=float)
    fuel_fraction = np.asarray(fuel_fraction, dtype=float)
    if raw.shape != SHAPE or fuel_fraction.shape != SHAPE:
        raise ValueError("Expected [z,y,x] = [20,17,17]")
    if not np.all(np.isfinite(raw)) or np.any(raw < 0):
        raise ValueError("Invalid raw kappa-fission mean")
    if not np.all(np.isfinite(fuel_fraction)) or np.any((fuel_fraction < 0) | (fuel_fraction > 1)):
        raise ValueError("Invalid geometric fuel fractions")
    mask = fuel_fraction > 0
    if np.any(raw[~mask] > max(1e-12, 1e-8 * float(raw.max()))):
        raise ValueError("Kappa-fission outside geometric fuel mask")
    denominator = float(raw[mask].sum())
    if denominator <= 0:
        raise ValueError("Non-positive fuel kappa-fission integral")
    normalized = np.zeros_like(raw)
    normalized[mask] = raw[mask] / denominator
    return normalized, mask


def _read_attempt(attempt, preview):
    status = json.loads((attempt / "status.json").read_text())
    summary = json.loads((attempt / "summary.json").read_text())
    resolved = json.loads((attempt / "resolved_config.json").read_text())
    if status.get("state") != "completed" or summary.get("completion_state") != "completed":
        return None
    if not preview and not (attempt / "acceptance.json").is_file():
        return None
    if not preview:
        acceptance = json.loads((attempt / "acceptance.json").read_text())
        if (acceptance.get("run_id") != status.get("run_id") or
                acceptance.get("status") != "accepted_for_data_production" or
                acceptance.get("source_convergence_reviewed") is not True or
                acceptance.get("physical_validation_reviewed") is not True or
                not acceptance.get("reviewer")):
            return None
    if resolved.get("model") != MODEL_ID or resolved.get("scenario_id") != status.get("scenario_id"):
        raise ValueError(f"Incompatible identity/model: {attempt}")
    if summary.get("run_id") != status.get("run_id") or summary.get("scenario_id") != status.get("scenario_id"):
        raise ValueError(f"Inconsistent run identity: {attempt}")
    if summary.get("array_order") != ["z", "y", "x"] or summary.get("mesh_shape_zyx") != list(SHAPE):
        raise ValueError(f"Incompatible axes/mesh: {attempt}")
    if summary.get("field_units", {}).get("kappa_fission") != UNITS["kappa_fission"]:
        raise ValueError(f"Incompatible kappa-fission units: {attempt}")
    if summary.get("field_units", {}).get("fission") != UNITS["fission"] or summary.get("field_units", {}).get("flux") != UNITS["flux"]:
        raise ValueError(f"Incompatible field units: {attempt}")
    with np.load(attempt / "fields.npz", allow_pickle=False) as fields:
        if fields["array_order"].tolist() != ["z", "y", "x"]:
            raise ValueError("Incompatible NPZ axis order")
        keys = ("fission_mean", "fission_std_dev", "kappa_fission_mean", "kappa_fission_std_dev",
                "flux_mean", "flux_std_dev", "fuel_volume_fraction", "aic_volume_fraction",
                "b4c_volume_fraction", "x_edges_cm", "y_edges_cm", "z_edges_cm",
                "k_generation", "shannon_entropy", "relative_error_reporting_mask")
        values = {key: fields[key].copy() for key in keys}
    for key in keys[:9]:
        if values[key].shape != SHAPE or not np.all(np.isfinite(values[key])):
            raise ValueError(f"Invalid field {key}: {attempt}")
    for axis, count in (("x", 18), ("y", 18), ("z", 21)):
        edges = values[f"{axis}_edges_cm"]
        if edges.shape != (count,) or not np.all(np.diff(edges) > 0):
            raise ValueError(f"Invalid {axis} coordinates: {attempt}")
    target, mask = normalized_kappa(values["kappa_fission_mean"], values["fuel_volume_fraction"])
    calc = resolved["calculation"]
    return {"attempt": str(attempt.resolve()), "scenario_id": status["scenario_id"],
            "run_id": status["run_id"], "summary": summary, "resolved": resolved,
            "fields": values, "target": target, "fuel_mask": mask,
            "active_histories": (calc["batches"]-calc["inactive"])*calc["particles_per_generation"]}


def split_for(scenario_id, version="scenario_sha256_80_10_10_v1"):
    if version != "scenario_sha256_80_10_10_v1":
        raise ValueError("Unsupported split version")
    value = int(hashlib.sha256((version + ":" + scenario_id).encode()).hexdigest()[:8], 16) % 10
    return "train" if value < 8 else "calibration" if value == 8 else "test"


def build_dataset(group_ids, output_dir, *, preview=False):
    selected = {}
    all_runs = {}
    for group_id in group_ids:
        if not group_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in group_id):
            raise ValueError("Invalid group ID")
        group = GROUPS / group_id
        manifest = json.loads((group / "manifest.json").read_text())
        if manifest.get("model") != MODEL_ID:
            raise ValueError("Mixed model versions")
        for case in manifest["experiments"]:
            for attempt in sorted((group / "experiments" / case["experiment_id"]).glob("attempt_*")):
                record = _read_attempt(attempt, preview)
                if record is None:
                    continue
                sid = record["scenario_id"]
                all_runs.setdefault(sid, []).append(record)
                # One example per physical scenario; deterministic highest active-history selection.
                if sid not in selected or (record["active_histories"], record["run_id"]) > (
                        selected[sid]["active_histories"], selected[sid]["run_id"]):
                    selected[sid] = record
    if selected:
        first = next(iter(selected.values()))["fields"]
        for item in selected.values():
            for axis in ("x", "y", "z"):
                key = f"{axis}_edges_cm"
                if not np.array_equal(item["fields"][key], first[key]):
                    raise ValueError("Incompatible physical mesh coordinates")
    out = Path(output_dir)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    rows = []
    arrays = {}
    for index, sid in enumerate(sorted(selected)):
        item = selected[sid]
        fields = item["fields"]
        key = f"sample_{index:05d}"
        arrays[key + "_target_normalized_kappa"] = item["target"]
        arrays[key + "_fuel_mask"] = item["fuel_mask"]
        arrays[key + "_fission_zero_measured"] = (fields["fission_mean"] == 0) & item["fuel_mask"]
        arrays[key + "_kappa_fission_zero_measured"] = (fields["kappa_fission_mean"] == 0) & item["fuel_mask"]
        for name, value in fields.items():
            arrays[key + "_" + name] = value
        rows.append({"scenario_id": sid, "split": split_for(sid),
                     "selected_run_id": item["run_id"], "selected_source": item["attempt"],
                     "all_source_runs": [r["attempt"] for r in all_runs[sid]],
                     "model": MODEL_ID, "k_mean": item["summary"]["k_effective"]["mean"],
                     "k_mc_standard_error": item["summary"]["k_effective"]["mc_standard_error"],
                     "physical_controls": {
                         "insertion_percent": item["resolved"]["insertion_percent"],
                         "u235_enrichment_nominal_wt_percent": 1.6,
                         "elemental_boron_ppm": item["resolved"]["reference_config"]["elemental_boron_ppm"],
                         "water_density_g_cm3": item["resolved"]["reference_config"]["materials"]["water"]["density_g_cm3"],
                         "fuel_density_g_cm3": item["resolved"]["reference_config"]["materials"]["fuel"]["density_g_cm3"],
                         "fuel_temperature_K": item["resolved"]["reference_config"]["materials"]["fuel"]["temperature_K"],
                         "moderator_temperature_K": item["resolved"]["reference_config"]["materials"]["water"]["temperature_K"],
                         "coolant_pressure_MPa": item["resolved"]["reference_config"].get("coolant_pressure_MPa"),
                         "pin_pitch_cm": item["resolved"]["reference_config"]["geometry"]["pin_pitch_cm"],
                         "pellet_radius_cm": item["resolved"]["reference_config"]["geometry"]["pellet_radius_cm"],
                         "fuel_history_state_id": None},
                     "reference_config_sha256": item["resolved"]["reference_config_sha256"],
                     "active_histories": item["active_histories"],
                     "normalization": "raw kappa-fission mean / sum(raw mean over geometric fuel voxels)",
                     "quality": "preview_not_accepted" if preview else "accepted_for_data_production"})
    np.savez_compressed(out / "samples.npz", **arrays)
    (out / "index.json").write_text(json.dumps({"schema": SCHEMA, "preview": preview,
        "split_version": "scenario_sha256_80_10_10_v1", "shape_zyx": SHAPE,
        "sample_count": len(rows), "samples": rows}, indent=2))
    (out / "splits.json").write_text(json.dumps({"version": "scenario_sha256_80_10_10_v1",
        "train": [r["scenario_id"] for r in rows if r["split"] == "train"],
        "calibration": [r["scenario_id"] for r in rows if r["split"] == "calibration"],
        "test": [r["scenario_id"] for r in rows if r["split"] == "test"]}, indent=2))
    # Only training examples determine preprocessing statistics; no fitting if train is empty.
    train = [r for r in rows if r["split"] == "train"]
    k_values = [r["k_mean"] for r in train]
    (out / "train_preprocessing.json").write_text(json.dumps({"fit_split": "train",
        "k_mean": float(np.mean(k_values)) if k_values else None,
        "k_std": float(np.std(k_values)) if k_values else None,
        "n_train": len(train)}, indent=2))
    return {"sample_count": len(rows), "preview": preview, "output": str(out)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir")
    parser.add_argument("group_ids", nargs="+")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(build_dataset(args.group_ids, args.output_dir, preview=args.preview), indent=2))


if __name__ == "__main__":
    main()





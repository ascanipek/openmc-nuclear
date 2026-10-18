"""Read-only v2 dataset export; no acceptance marker means no production sample."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .dataset import normalized_kappa, split_for, SHAPE, UNITS
from .parameter_space import MODEL_ID
from .v2_runner import GROUPS
from .v2_scenarios import digest, identity

REQUIRED_FIELDS = ("fission_mean", "fission_std_dev", "kappa_fission_mean",
                   "kappa_fission_std_dev", "flux_mean", "flux_std_dev",
                   "fuel_volume_fraction", "aic_volume_fraction", "b4c_volume_fraction",
                   "fission_expected_zero", "kappa_fission_expected_zero",
                   "relative_error_reporting_mask", "x_edges_cm", "y_edges_cm", "z_edges_cm",
                   "k_generation", "shannon_entropy", "array_order")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _attempt(path, preview):
    status = _read(path / "status.json")
    if status.get("state") != "completed":
        return None
    summary = _read(path / "summary.json")
    resolved = _read(path / "resolved_config.json")
    if summary.get("completion_state") != "completed":
        raise ValueError(f"Completed status has incomplete summary: {path}")
    if not preview:
        marker = path / "acceptance.json"
        if not marker.is_file():
            return None
        approval = _read(marker)
        if (approval.get("status") != "accepted_for_data_production" or
                approval.get("run_id") != status.get("run_id") or
                approval.get("source_convergence_reviewed") is not True or
                approval.get("physical_validation_reviewed") is not True or
                not approval.get("reviewer")):
            raise ValueError(f"Invalid production acceptance marker: {path}")
    if any(item.get("model") != MODEL_ID for item in (summary, resolved)):
        raise ValueError(f"Mixed model: {path}")
    for key in ("run_id", "scenario_id"):
        if status.get(key) != summary.get(key) or status.get(key) != resolved.get(key):
            raise ValueError(f"Inconsistent {key}: {path}")
    if summary.get("array_order") != ["z", "y", "x"] or summary.get("mesh_shape_zyx") != list(SHAPE):
        raise ValueError(f"Incompatible array order/shape: {path}")
    if any(summary.get("field_units", {}).get(name) != value for name, value in UNITS.items()):
        raise ValueError(f"Incompatible field units: {path}")
    if summary.get("k_effective", {}).get("unit") != "dimensionless":
        raise ValueError(f"Invalid k unit: {path}")
    cfg = resolved.get("resolved_config", {})
    if (cfg.get("model") != MODEL_ID or cfg.get("array_order") != "z,y,x" or
            cfg.get("mesh_dimension_xyz") != [17, 17, 20] or
            cfg.get("temperature_method") != "interpolation"):
        raise ValueError(f"Incompatible resolved physical configuration: {path}")
    reference_sha = resolved["reference_config_sha256"]
    if identity({"model": MODEL_ID, "reference_config_sha256": reference_sha,
                 "controls": resolved["controls"]}) != status["scenario_id"]:
        raise ValueError(f"Scenario identity mismatch: {path}")
    if identity({"scenario_id": status["scenario_id"], "calculation": resolved["calculation"],
                 "model": MODEL_ID, "reference_config_sha256": reference_sha,
                 "package_ledger_sha256": resolved["package_ledger_sha256"],
                 "cross_sections_xml_sha256": resolved["nuclear_data"]["cross_sections_xml_sha256"]}) != status["run_id"]:
        raise ValueError(f"Run identity mismatch: {path}")
    with np.load(path / "fields.npz", allow_pickle=False) as data:
        if not set(REQUIRED_FIELDS).issubset(data.files):
            raise ValueError(f"Missing field: {path}")
        fields = {name: data[name].copy() for name in REQUIRED_FIELDS}
    if fields["array_order"].tolist() != ["z", "y", "x"]:
        raise ValueError(f"NPZ axis order mismatch: {path}")
    for name in REQUIRED_FIELDS[:12]:
        if fields[name].shape != SHAPE or not np.all(np.isfinite(fields[name])):
            raise ValueError(f"Invalid field {name}: {path}")
    for name in ("fission_std_dev", "kappa_fission_std_dev", "flux_std_dev"):
        if np.any(fields[name] < 0):
            raise ValueError(f"Negative MC standard error: {path}")
    for axis, n in (("x", 18), ("y", 18), ("z", 21)):
        edges = fields[f"{axis}_edges_cm"]
        if edges.shape != (n,) or not np.all(np.diff(edges) > 0):
            raise ValueError(f"Invalid coordinates: {path}")
    geometry = cfg["geometry"]
    half = geometry["assembly_pitch_cm"] / 2
    expected_edges = {
        "x": np.linspace(-half, half, 18),
        "y": np.linspace(-half, half, 18),
        "z": np.linspace(geometry["fuel_bottom_cm"], geometry["fuel_top_cm"], 21),
    }
    for axis, expected in expected_edges.items():
        if not np.allclose(fields[f"{axis}_edges_cm"], expected, rtol=0, atol=1e-9):
            raise ValueError(f"Incompatible {axis} mesh coordinates for resolved geometry: {path}")
    mask = fields["fuel_volume_fraction"] > 0
    if not np.array_equal(fields["fission_expected_zero"], ~mask) or not np.array_equal(fields["kappa_fission_expected_zero"], ~mask):
        raise ValueError(f"Invalid geometry mask: {path}")
    target, _ = normalized_kappa(fields["kappa_fission_mean"], fields["fuel_volume_fraction"])
    calc = resolved["calculation"]
    active_histories = (calc["batches"] - calc["inactive"]) * calc["particles_per_generation"] * calc["generations_per_batch"]
    return {"path": path, "summary": summary, "resolved": resolved, "fields": fields,
            "target": target, "active_histories": active_histories}


def export(group_ids, output_dir, *, preview=False):
    selected, all_runs = {}, {}
    for group_id in group_ids:
        if not group_id.startswith("v2_") or "/" in group_id or ".." in group_id:
            raise ValueError("Invalid v2 group ID")
        group = GROUPS / group_id
        manifest = _read(group / "manifest.json")
        if manifest["group_id"] != group_id or manifest["model"] != MODEL_ID:
            raise ValueError("Group model/identity mismatch")
        for case in manifest["experiments"]:
            for path in sorted((group / "experiments" / case["experiment_id"]).glob("attempt_*")):
                item = _attempt(path, preview)
                if item is None:
                    continue
                sid = item["summary"]["scenario_id"]
                if sid != case["scenario_id"]:
                    raise ValueError("Case/scenario identity mismatch")
                all_runs.setdefault(sid, []).append(item)
                if sid not in selected or (item["active_histories"], item["summary"]["run_id"]) > (
                        selected[sid]["active_histories"], selected[sid]["summary"]["run_id"]):
                    selected[sid] = item
    out = Path(output_dir)
    if out.exists():
        raise FileExistsError(out)
    arrays, rows = {}, []
    for index, sid in enumerate(sorted(selected)):
        item = selected[sid]
        fields = item["fields"]
        name = f"sample_{index:05d}"
        arrays[name + "_target_normalized_kappa"] = item["target"]
        for key, value in fields.items():
            arrays[name + "_" + key] = value
        summary, resolved = item["summary"], item["resolved"]
        cfg = resolved["resolved_config"]
        geom = cfg["geometry"]
        tip = geom["fuel_top_cm"] - resolved["controls"]["insertion_percent"] / 100 * (
            geom["fuel_top_cm"] - geom["fuel_bottom_cm"])
        derived = {
            "water_solution_density_g_cm3": cfg["materials"]["water"]["density_g_cm3"],
            "water_density_method": cfg["water_density_method"],
            "assembly_pitch_cm": geom["assembly_pitch_cm"],
            "rod_tip_cm": tip,
            "aic_top_cm": tip + geom["aic_length_cm"],
            "b4c_top_cm": tip + geom["aic_length_cm"] + geom["b4c_length_cm"],
            "material_temperature_K": {key: mat["temperature_K"]
                                       for key, mat in cfg["materials"].items()},
            "fuel_atom_density_atom_b_cm": cfg["materials"]["fuel"]["atom_density_atom_b_cm"],
            "water_atom_density_atom_b_cm": cfg["materials"]["water"]["atom_density_atom_b_cm"],
        }
        rows.append({"scenario_id": sid, "split": split_for(sid),
                     "selected_run_id": summary["run_id"],
                     "selected_source": str(item["path"].resolve()),
                     "all_source_runs": [{"run_id": r["summary"]["run_id"],
                                          "path": str(r["path"].resolve())} for r in all_runs[sid]],
                     "model": MODEL_ID, "physical_controls": resolved["controls"],
                     "derived_inputs": derived,
                     "resolved_water_density_g_cm3": cfg["materials"]["water"]["density_g_cm3"],
                     "reference_config_sha256": resolved["reference_config_sha256"],
                     "k_mean": summary["k_effective"]["mean"],
                     "k_mc_standard_error": summary["k_effective"]["mc_standard_error"],
                     "active_histories": item["active_histories"],
                     "normalization": "raw kappa-fission over sum in geometric fuel voxels",
                     "quality": "preview_not_accepted" if preview else "accepted_for_data_production"})
    out.mkdir(parents=True)
    np.savez_compressed(out / "samples.npz", **arrays)
    (out / "index.json").write_text(json.dumps({"schema": "beavrs3d_v2_dataset_v1",
        "preview": preview, "axis_order": ["z", "y", "x"], "shape_zyx": list(SHAPE),
        "sample_count": len(rows), "samples": rows}, indent=2), encoding="utf-8")
    (out / "splits.json").write_text(json.dumps({"version": "scenario_sha256_80_10_10_v1",
        **{split: [row["scenario_id"] for row in rows if row["split"] == split]
           for split in ("train", "calibration", "test")}}, indent=2), encoding="utf-8")
    train = [row["k_mean"] for row in rows if row["split"] == "train"]
    (out / "train_preprocessing.json").write_text(json.dumps({"fit_split": "train",
        "n_train": len(train), "k_mean": float(np.mean(train)) if train else None,
        "k_std": float(np.std(train)) if train else None}, indent=2), encoding="utf-8")
    return {"sample_count": len(rows), "preview": preview, "output": str(out)}

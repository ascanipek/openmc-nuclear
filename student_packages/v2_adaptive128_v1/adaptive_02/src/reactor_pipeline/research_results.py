"""Read-only comparisons for the fixed D3/D4 student notebooks."""
from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib.pyplot as plt
import numpy as np

from .experiments import PROJECT, _completed_attempt, read_group

D2_ID = "beavrs3d_d2_budget_v1"
D3_ID = "beavrs3d_d3_b1_repeats_v1"
D4_ID = "beavrs3d_d4_b1_positions_v1"
B1_ID = "D2-B1"
FIELD_NAMES = ("fission_mean", "fission_std_dev", "kappa_fission_mean",
               "kappa_fission_std_dev", "fuel_volume_fraction", "relative_error_reporting_mask",
               "k_generation", "shannon_entropy", "z_edges_cm")


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _manifest(group_id):
    return _json(PROJECT / "manifests" / f"{group_id}.json")


def _xml_physics(attempt):
    """Small XML metadata signature; ignore arbitrary OpenMC object IDs and seed."""
    settings = ET.parse(attempt / "settings.xml").getroot()
    source = settings.find("source")
    source_space = source.find("space")
    source_constraints = source.find("constraints")
    settings_mesh = settings.find("mesh")
    setting_keys = ("run_mode", "particles", "batches", "inactive", "generations_per_batch",
                    "temperature_default", "temperature_method")
    setting_signature = tuple((key, settings.findtext(key)) for key in setting_keys)
    source_signature = (tuple(sorted(source.attrib.items())), tuple(sorted(source_space.attrib.items())),
                        source_space.findtext("parameters"),
                        tuple(sorted((child.tag, child.text) for child in source_constraints)))
    def mesh_signature(mesh):
        return (mesh.get("name"), mesh.findtext("dimension"),
                mesh.findtext("lower_left"), mesh.findtext("upper_right"))
    tallies = ET.parse(attempt / "tallies.xml").getroot()
    tally = tallies.findall("tally")
    filters = tallies.findall("filter")
    meshes = tallies.findall("mesh")
    if len(tally) != 1 or len(filters) != 1 or len(meshes) != 1 or filters[0].get("type") != "mesh":
        raise ValueError("Unexpected tally/filter/mesh structure")
    tally_signature = (mesh_signature(meshes[0]), tally[0].get("name"),
                       tally[0].findtext("scores"), tally[0].findtext("estimator"))
    materials = ET.parse(attempt / "materials.xml").getroot()
    material_signature = tuple(sorted((mat.get("name"), mat.get("temperature"),
                                       tuple(sorted(mat.find("density").attrib.items())),
                                       tuple(sorted(tuple(sorted(n.attrib.items())) for n in mat.findall("nuclide"))),
                                       tuple(sorted(s.get("name") for s in mat.findall("sab"))))
                                      for mat in materials.findall("material")))
    geometry = ET.parse(attempt / "geometry.xml").getroot()
    surfaces = tuple(sorted((item.get("type"), item.get("coeffs"), item.get("boundary", ""))
                            for item in geometry.findall("surface")))
    external = tuple(item for item in surfaces if item[2] in ("reflective", "vacuum"))
    return {"settings": setting_signature, "source": source_signature,
            "settings_mesh": mesh_signature(settings_mesh), "tally": tally_signature,
            "materials": material_signature, "surfaces": surfaces, "external_boundaries": external}

def saved_group(group_id):
    """Read saved attempts independently; a partial group can still show completed cases."""
    prepared = _manifest(group_id)
    try:
        folder, saved_manifest, group_status = read_group(group_id)
    except FileNotFoundError:
        return {"group_id": group_id, "state": "not_started", "cases": {}, "folder": None}
    if saved_manifest != prepared:
        raise ValueError(f"{group_id}: saved manifest differs from prepared manifest")
    records = {}
    for case in saved_manifest["experiments"]:
        case_id = case["experiment_id"]
        attempt = _completed_attempt(folder, case_id)
        if attempt is None:
            attempts = sorted((folder / "experiments" / case_id).glob("attempt_*"))
            latest = attempts[-1] if attempts else None
            state = _json(latest / "status.json").get("state", "incomplete") if latest and (latest / "status.json").is_file() else "not_started"
            records[case_id] = {"state": state, "attempt": str(latest) if latest else None, "case": case}
            continue
        resolved = _json(attempt / "resolved_config.json")
        summary = _json(attempt / "summary.json")
        case_status = _json(attempt / "status.json")
        if resolved["experiment_id"] != case_id or case_status["run_id"] != summary["run_id"] or summary["completion_state"] != "completed":
            raise ValueError(f"{case_id}: inconsistent saved identity/status")
        with np.load(attempt / "fields.npz", allow_pickle=False) as fields:
            if fields["array_order"].tolist() != ["z", "y", "x"]:
                raise ValueError(f"{case_id}: unexpected field axis order")
            arrays = {name: fields[name].copy() for name in FIELD_NAMES}
        records[case_id] = {"state": "completed", "attempt": str(attempt), "case": case,
                            "resolved": resolved, "summary": summary, "status": case_status,
                            "fields": arrays, "xml_physics": _xml_physics(attempt)}
    return {"group_id": group_id, "state": group_status["state"], "error": group_status.get("error"),
            "cases": records, "folder": str(folder), "completed_experiments": group_status.get("completed_experiments", [])}


def reference_b1():
    group = saved_group(D2_ID)
    record = group["cases"].get(B1_ID)
    if record is None or record["state"] != "completed":
        raise FileNotFoundError("Recorded D2-B1 reference is unavailable or incomplete")
    return record


def _without_seed(calculation):
    return {key: value for key, value in calculation.items() if key != "seed"}


def validate_comparison(reference, candidate, *, allow_insertion_change=False):
    """Require equal physical inputs except requested rod position; no transport."""
    if reference["state"] != "completed" or candidate["state"] != "completed":
        raise ValueError("Only completed cases can be compared")
    a, b = reference["resolved"], candidate["resolved"]
    for key in ("model", "beavrs_source_commit", "reference_config_sha256", "temperature_method"):
        if a[key] != b[key]:
            raise ValueError(f"Incompatible {key}")
    if a["reference_config"] != b["reference_config"]:
        raise ValueError("Material, geometry, temperature or source configuration differs")
    if a["nuclear_data"]["cross_sections_xml_sha256"] != b["nuclear_data"]["cross_sections_xml_sha256"]:
        raise ValueError("Nuclear data source differs")
    if _without_seed(a["calculation"]) != _without_seed(b["calculation"]):
        raise ValueError("Calculation budgets differ")
    if not allow_insertion_change and a["insertion_percent"] != b["insertion_percent"]:
        raise ValueError("Insertion differs in a same-condition repeat")
    if (a["insertion_percent"], b["insertion_percent"]) not in ((50, 50), (50, 0), (50, 100)):
        raise ValueError("Unexpected insertion pair")
    for key in ("settings", "source", "settings_mesh", "tally", "materials", "external_boundaries"):
        if reference["xml_physics"][key] != candidate["xml_physics"][key]:
            raise ValueError(f"Saved OpenMC XML physical input differs: {key}")
    if not allow_insertion_change and reference["xml_physics"]["surfaces"] != candidate["xml_physics"]["surfaces"]:
        raise ValueError("Saved OpenMC geometry surfaces differ")
    af, bf = reference["fields"], candidate["fields"]
    if not np.array_equal(af["fuel_volume_fraction"], bf["fuel_volume_fraction"]):
        raise ValueError("Fuel geometry mask differs")
    if not np.array_equal(af["z_edges_cm"], bf["z_edges_cm"]):
        raise ValueError("Axial mesh differs")
    return True


def case_row(label, record):
    row = {"koşu": label, "durum": record["state"], "seed": record["case"]["calculation"]["seed"],
           "giriş_%": record["case"]["insertion_percent"], "süre_s": None, "k": None,
           "MC_standart_hata": None, "yakınsama": "inceleme gerekli", "fiziksel_kabul": "değerlendirilmedi",
           "yakıt_voxel": None, "sıfır_fisyon_voxel": None, "güvenilirlik_filtresi_voxel": None}
    if record["state"] == "completed":
        summary, fields = record["summary"], record["fields"]
        fuel = fields["fuel_volume_fraction"] > 0
        row.update(süre_s=summary["duration"]["value"], k=summary["k_effective"]["mean"],
                   MC_standart_hata=summary["k_effective"]["mc_standard_error"],
                   yakınsama=summary.get("statistical_convergence", "inceleme gerekli"),
                   fiziksel_kabul=summary.get("physical_acceptance", "not_assessed"),
                   yakıt_voxel=int(fuel.sum()),
                   sıfır_fisyon_voxel=int(np.count_nonzero(fuel & (fields["fission_mean"] == 0))),
                   güvenilirlik_filtresi_voxel=int(fields["relative_error_reporting_mask"].sum()))
    return row


def comparison_stats(reference, candidate):
    """Descriptive differences on a fixed geometry mask, independent of run-specific filters."""
    validate_comparison(reference, candidate, allow_insertion_change=True)
    a, b = reference["fields"], candidate["fields"]
    common = (a["fuel_volume_fraction"] > 0.2) & (b["fuel_volume_fraction"] > 0.2)
    if not np.any(common):
        raise ValueError("No common fuel geometry voxels")
    out = {"common_geometry_voxels": int(common.sum()),
           "reference_reliability_filter_voxels": int(a["relative_error_reporting_mask"].sum()),
           "candidate_reliability_filter_voxels": int(b["relative_error_reporting_mask"].sum()),
           "mask_note": "Shared >0.2 fuel volume mask is geometric; individual reliability masks are not treated as equivalent."}
    for score in ("fission", "kappa_fission"):
        difference = b[f"{score}_mean"] - a[f"{score}_mean"]
        combined_se = np.hypot(a[f"{score}_std_dev"], b[f"{score}_std_dev"])
        out[score] = {"mean_signed_raw_difference": float(np.mean(difference[common])),
                      "median_abs_raw_difference": float(np.median(np.abs(difference[common]))),
                      "median_combined_mc_standard_error": float(np.median(combined_se[common])),
                      "unit": "reactions/source particle" if score == "fission" else "eV/source particle"}
    return out


def _normalized_profile(record, score):
    values = record["fields"][f"{score}_mean"].sum(axis=(1, 2))
    total = values.sum()
    return values / total if total > 0 else np.full_like(values, np.nan)


def profile_plot(records):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    for label, record in records.items():
        if record["state"] != "completed":
            continue
        z_edges = record["fields"]["z_edges_cm"]
        z = (z_edges[:-1] + z_edges[1:]) / 2
        for ax, score in zip(axes, ("fission", "kappa_fission")):
            ax.plot(z, _normalized_profile(record, score), marker=".", label=label)
    axes[0].set(title="Normalize eksenel fisyon payı", xlabel="z (cm)", ylabel="Dilim payı")
    axes[1].set(title="Normalize eksenel kappa-fission payı", xlabel="z (cm)", ylabel="Dilim payı")
    for ax in axes:
        ax.legend()
    return fig


def history_plot(records):
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, constrained_layout=True)
    for label, record in records.items():
        if record["state"] != "completed":
            continue
        fields = record["fields"]
        x = np.arange(1, fields["k_generation"].size + 1)
        axes[0].plot(x, fields["k_generation"], lw=0.7, alpha=0.8, label=label)
        axes[1].plot(x, fields["shannon_entropy"], lw=0.7, alpha=0.8, label=label)
    axes[0].set(ylabel="Nesil k", title="Kaydedilmiş nesil geçmişleri")
    axes[1].set(xlabel="Batch / nesil", ylabel="Kaynak Shannon entropisi")
    for ax in axes:
        ax.axvline(300.5, color="gray", ls="--", lw=1)
        ax.legend()
    return fig


def field_difference_plot(reference, candidate, label):
    validate_comparison(reference, candidate, allow_insertion_change=True)
    a, b = reference["fields"], candidate["fields"]
    mask = (a["fuel_volume_fraction"] > 0.2) & (b["fuel_volume_fraction"] > 0.2)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, score, unit in zip(axes, ("fission", "kappa_fission"),
                               ("reactions/source", "eV/source")):
        delta = np.where(mask, b[f"{score}_mean"] - a[f"{score}_mean"], 0).sum(axis=0)
        bound = float(np.max(np.abs(delta))) or 1.0
        image = ax.imshow(delta, origin="lower", cmap="coolwarm", vmin=-bound, vmax=bound)
        ax.set(title=f"{label}: Δ {score} ({unit})", xlabel="x sütunu", ylabel="y satırı")
        fig.colorbar(image, ax=ax, shrink=0.75)
    return fig


def repeat_scatter(records):
    completed = [r for r in records.values() if r["state"] == "completed"]
    values = [r["summary"]["k_effective"]["mean"] for r in completed]
    return {"n": len(values), "k_mean_of_available_repeats": float(np.mean(values)) if values else None,
            "sample_standard_deviation": float(np.std(values, ddof=1)) if len(values) >= 2 else None,
            "meaning": "descriptive across independent seeds; three runs do not establish convergence or physical validity"}



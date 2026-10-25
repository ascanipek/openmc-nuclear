"""Fuel-history state catalogue gate; no fabricated depletion states are shipped."""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = {"state_id", "model", "source_chain_sha256", "source_cross_sections_sha256",
            "initial_u235_enrichment_wt_percent", "burnup_MWd_per_kgU", "history_id",
            "power_history", "temperature_history", "control_history", "fuel_volume_cm3",
            "nuclide_atom_density_atom_b_cm", "contains_I135_Xe135", "validation_status"}


def load_fuel_state(path, *, enrichment, burnup_MWd_per_kgU, history_id, model):
    state = json.loads(Path(path).read_text())
    if set(state) != REQUIRED:
        raise ValueError("Incomplete or unexpected fuel-history state schema")
    if state["validation_status"] != "accepted" or not state["source_chain_sha256"] or not state["source_cross_sections_sha256"]:
        raise ValueError("Fuel state is not accepted with pinned depletion inputs")
    if state["model"] != model or state["history_id"] != history_id or state["initial_u235_enrichment_wt_percent"] != enrichment or state["burnup_MWd_per_kgU"] != burnup_MWd_per_kgU:
        raise ValueError("Incompatible enrichment/history/model for fuel state")
    if not state["contains_I135_Xe135"] or not {"I135", "Xe135"} <= set(state["nuclide_atom_density_atom_b_cm"]):
        raise ValueError("I135/Xe135 joint inventory missing")
    if not state["power_history"] or not state["temperature_history"] or not state["control_history"]:
        raise ValueError("Timed history incomplete")
    if state["fuel_volume_cm3"] <= 0 or state["burnup_MWd_per_kgU"] < 0:
        raise ValueError("Invalid depletion volume/burnup")
    return state


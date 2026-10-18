"""Read-only comparison of saved Jupyter inputs against a hash-verified snapshot."""
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(current, snapshot, approved_sha256):
    current, snapshot = Path(current), Path(snapshot)
    if sha256(snapshot) != approved_sha256:
        raise ValueError("Approved snapshot SHA256 mismatch")
    old = json.loads(snapshot.read_text(encoding="utf-8"))
    new = json.loads(current.read_text(encoding="utf-8"))
    def inputs(book):
        return [(c["cell_type"], "".join(c.get("source", []))) for c in book["cells"]]
    before, after = inputs(old), inputs(new)
    common = min(len(before), len(after))
    return {
        "raw_sha256_equal": sha256(current) == approved_sha256,
        "inputs_equal": before == after,
        "changed_input_cells": [i for i in range(common) if before[i] != after[i]],
        "added_input_cells": after[common:],
        "removed_input_cells": before[common:],
        "outputs_or_execution_counts_changed": [i for i in range(common)
            if old["cells"][i].get("outputs") != new["cells"][i].get("outputs") or
               old["cells"][i].get("execution_count") != new["cells"][i].get("execution_count")],
        "notebook_metadata_changed": old.get("metadata") != new.get("metadata"),
    }

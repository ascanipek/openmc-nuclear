"""Versioned, deterministic digest of inputs that control notebook execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "notebook-inputs-v1"


def canonical_inputs(path):
    book = json.loads(Path(path).read_text(encoding="utf-8"))
    if book.get("nbformat") != 4 or not isinstance(book.get("cells"), list):
        raise ValueError("Unsupported notebook format")
    meta = book.get("metadata", {})
    cells = []
    for cell in book["cells"]:
        kind = cell.get("cell_type")
        if kind not in ("code", "markdown", "raw"):
            raise ValueError("Unsupported notebook cell type")
        source = cell.get("source")
        if isinstance(source, list) and all(isinstance(x, str) for x in source):
            source = "".join(source)
        if not isinstance(source, str):
            raise ValueError("Invalid notebook cell source")
        cell_id = cell.get("id")
        if cell_id is not None and not isinstance(cell_id, str):
            raise ValueError("Invalid notebook cell ID")
        tags = cell.get("metadata", {}).get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("Invalid notebook cell tags")
        cells.append({"cell_type": kind, "source": source, "cell_id": cell_id, "tags": tags})
    return {
        "schema": SCHEMA,
        "nbformat": 4,
        "kernel_name": meta.get("kernelspec", {}).get("name"),
        "language_name": meta.get("language_info", {}).get("name"),
        "launch_policy": meta.get("launch_policy"),
        "cells": cells,
    }


def content_digest(path):
    payload = json.dumps(canonical_inputs(path), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

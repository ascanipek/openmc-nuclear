#!/usr/bin/env python3
"""Run prepared BEAVRS experiment manifests from the WSL Conda environment."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reactor_pipeline.experiments import main


if __name__ == "__main__":
    main()

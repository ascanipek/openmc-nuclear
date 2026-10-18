#!/usr/bin/env python3
"""Prepared v2 nominal integration; preflight is read-only, launch is explicit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reactor_pipeline.v2_integration import preflight, status, launch, worker

if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action not in ('preflight', 'status', 'launch', 'worker'):
        raise SystemExit('Use preflight, status, launch or worker')
    import json
    print(json.dumps(globals()[action](), indent=2, default=str))

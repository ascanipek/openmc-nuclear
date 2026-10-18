"""Prepare nested V2 draft catalogues and non-overlapping student packages; no MC."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reactor_pipeline.v2_pilot import prepare, SPACE, PROFILE, DISTRIBUTION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root")
    parser.add_argument("--space", default=str(SPACE))
    parser.add_argument("--profile", default=str(PROFILE))
    parser.add_argument("--distribution", default=str(DISTRIBUTION))
    args = parser.parse_args()
    print(json.dumps(prepare(args.output_root, space_path=args.space,
                             profile_path=args.profile,
                             distribution_path=args.distribution),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

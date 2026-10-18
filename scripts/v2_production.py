"""WSL CLI for v2 draft catalogues, packages, read-only results, and explicit launch."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reactor_pipeline import v2_scenarios as scenarios, v2_runner as runner, v2_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    generate = sub.add_parser("generate")
    generate.add_argument("output")
    generate.add_argument("--count", type=int, required=True)
    generate.add_argument("--seed", type=int, required=True)
    allocate = sub.add_parser("allocate")
    allocate.add_argument("catalogue")
    allocate.add_argument("output_root")
    allocate.add_argument("--students", nargs="+", required=True)
    for action in ("verify", "preflight", "status", "launch", "resume", "stop", "results", "worker"):
        sub.add_parser(action).add_argument("package")
    export = sub.add_parser("export")
    export.add_argument("output")
    export.add_argument("groups", nargs="+")
    export.add_argument("--preview", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "generate":
        result = scenarios.generate(args.count, args.seed, args.output)
    elif args.action == "allocate":
        result = str(scenarios.allocate(args.catalogue, args.students, args.output_root))
    elif args.action == "verify":
        result = scenarios.verify_package(args.package)
    elif args.action == "preflight":
        result = runner.preflight(args.package)
    elif args.action == "status":
        result = runner.status(args.package)
    elif args.action == "launch":
        result = runner.launch(args.package)
    elif args.action == "resume":
        result = runner.resume(args.package)
    elif args.action == "stop":
        result = runner.stop(args.package)
    elif args.action == "results":
        result = runner.saved_results(args.package)
    elif args.action == "worker":
        runner.worker(args.package)
        return
    else:
        result = v2_dataset.export(args.groups, args.output, preview=args.preview)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

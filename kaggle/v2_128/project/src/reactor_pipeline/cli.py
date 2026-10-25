"""Command line entry point for the 2D pilot and isolated BEAVRS-derived 3D model."""
import argparse
import json
from pathlib import Path
from .config import load_scenarios
from .results import plot_results
from .runner import run_one


def main(argv=None):
    parser = argparse.ArgumentParser(prog="reactor-pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run one 2D pilot scenario or a sequential scenario list")
    run.add_argument("scenario_json", type=Path)
    run.add_argument("--runs-root", type=Path, default=Path("runs") / "pipeline")
    run.add_argument("--no-resume", action="store_true")
    run.add_argument("--purpose", default="pilot_not_validated_training_data")
    plot = commands.add_parser("plot", help="plot saved 2D result folders with a shared color scale")
    plot.add_argument("folders", nargs="+", type=Path)
    plot.add_argument("--output", type=Path)
    check3d = commands.add_parser("check-3d", help="check and plot 0/50/100%% 3D geometry without transport")
    check3d.add_argument("--reference", type=Path)
    check3d.add_argument("--runs-root", type=Path, default=Path("runs") / "beavrs_3d")
    run3d = commands.add_parser("run-3d-integration", help="run the single specified 50%% integration case")
    run3d.add_argument("--reference", type=Path)
    run3d.add_argument("--runs-root", type=Path, default=Path("runs") / "beavrs_3d")
    plot3d = commands.add_parser("plot-3d", help="plot an existing 3D integration result")
    plot3d.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        scenarios = load_scenarios(args.scenario_json)
        for scenario in scenarios:
            print(json.dumps(run_one(scenario, args.runs_root, resume=not args.no_resume, purpose=args.purpose)), flush=True)
    elif args.command == "plot":
        print(plot_results(args.folders, args.output))
    elif args.command == "check-3d":
        from .beavrs3d import DEFAULT_CONFIG, geometry_check_suite
        folder, record = geometry_check_suite(args.reference or DEFAULT_CONFIG, args.runs_root)
        print(json.dumps({"folder": str(folder), "state": record["state"]}), flush=True)
    elif args.command == "run-3d-integration":
        from .beavrs3d import DEFAULT_CONFIG, run_integration
        folder, result = run_integration(args.reference or DEFAULT_CONFIG, args.runs_root)
        print(json.dumps({"folder": str(folder), "k_mean": result["k_mean"],
                          "k_mc_standard_error": result["k_mc_standard_error"],
                          "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
    else:
        from .beavrs3d import plot_integration_results
        print([str(p) for p in plot_integration_results(args.folder)])


if __name__ == "__main__":
    main()



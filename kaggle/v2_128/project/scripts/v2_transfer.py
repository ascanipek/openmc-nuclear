"""Read-only/export and validated import of V2 student results; never runs OpenMC."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from reactor_pipeline import v2_transfer


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    out=sub.add_parser("export");out.add_argument("package");out.add_argument("zip_path")
    inp=sub.add_parser("import");inp.add_argument("zip_path")
    view=sub.add_parser("status");view.add_argument("--stage",choices=("stage_32","stage_128","stage_256"))
    view.add_argument("--owner",choices=("ogrenci_01","ogrenci_02","ogrenci_03","ogrenci_04"))
    args=parser.parse_args(argv)
    if args.action=="export": result=v2_transfer.export_package(args.package,args.zip_path)
    elif args.action=="import": result=v2_transfer.import_zip(args.zip_path)
    else:
        rows=[r for r in v2_transfer.status_table() if (not args.stage or r["stage"]==args.stage)
              and (not args.owner or r["owner"]==args.owner)]
        columns=("stage","owner","scenario_id","state","distinct_runs","physical_acceptance","statistical_acceptance")
        print("\t".join(columns))
        for row in rows:print("\t".join(str(row[key]) for key in columns))
        print("TOTAL",len(rows),"COMPLETED",sum(r["state"]=="completed" for r in rows),
              "MISSING",sum(r["state"]=="missing" for r in rows),
              "FAILED",sum(r["state"]=="failed" for r in rows),sep="\t")
        return
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__": main()

"""Build the self-contained ADAPTIVE-02 student snapshot using existing V2 runner."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "student_packages/v2_adaptive128_v1/adaptive_02"
ZIP = ROOT / "deliveries/v2_adaptive_02_student_v1.zip"
SELECTED = ROOT / "scenarios/v2_adaptive128_v1/adaptive_02/selected_32.json"
SELECTION_REPORT = ROOT / "reports/adaptive_selection_02_v1/selection_report.json"
SPACE_NAME = "v2_parameter_space_pilot_scope_v1.json"
PROFILE_NAME = "v2_calculation_profile_adaptive02_80k_24h_research_v1.json"
PROFILE_ID = "beavrs_v2_adaptive02_80k_24h_research_v1"
PACKAGE_ID = "v2_adaptive_02_beavrs_v2_pilot_scope_v1"
AUTH = "Advisor's 2026-10-27 ADAPTIVE-02 32-case student package request"


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write("\n")


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/source,target)


def main():
    if BUNDLE.exists() or ZIP.exists():
        raise FileExistsError("Adaptive-02 student bundle or ZIP exists; will not overwrite")
    selected=json.loads(SELECTED.read_text())
    report=json.loads(SELECTION_REPORT.read_text())
    if selected["selection_report_sha256"]!=sha(SELECTION_REPORT) or selected["selected_count"]!=32:
        raise ValueError("Selection evidence changed")
    ids=[x["scenario_id"] for x in selected["selected"]]
    if len(ids)!=32 or len(set(ids))!=32:
        raise ValueError("Selected IDs not unique 32")
    BUNDLE.mkdir(parents=True)
    for source in ("environment.yml","student_setup.md"):
        copy(source,BUNDLE/source)
    shutil.copytree(ROOT/"src/reactor_pipeline",BUNDLE/"src/reactor_pipeline",
                    ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    for source in ("scripts/v2_student_production.py","scripts/v2_transfer.py"):
        copy(source,BUNDLE/source)
    # Transport-neutral fix in this new, pinned snapshot only. Existing project sources stay unchanged.
    runner_path=BUNDLE/"src/reactor_pipeline/v2_student_runner.py"
    runner=runner_path.read_text()
    old='    return {**record, "pid": process.get("pid"), "process_alive": process_alive(process.get("pid"), process, group, SCRIPT),'
    replacement=('    registered = process.get("worker_folder") == str(group.resolve())\n'
                 '    identity = dict(process, worker_folder=str(Path(package).resolve()))\n'
                 '    alive = registered and process_alive(process.get("pid"), identity, Path(package).resolve(), SCRIPT)\n'
                 '    return {**record, "pid": process.get("pid"), "process_alive": alive,')
    if runner.count(old)!=1:
        raise ValueError("Expected existing runner status call not found")
    runner_path.write_text(runner.replace(old,replacement),encoding="utf-8")
    for source in ("configs/beavrs_derived_3d_reference.json",
                   f"configs/{SPACE_NAME}",f"configs/{SPACE_NAME}.approval.json"):
        copy(source,BUNDLE/source)
    # The previous adaptive profile is scope-limited; make a numerically identical scope-limited profile.
    old_profile=json.loads((ROOT/"configs/v2_calculation_profile_adaptive01_80k_24h_research_v1.json").read_text())
    calculation={"particles_per_generation":80000,"batches":600,"inactive":300,
                 "generations_per_batch":1,"threads":6}
    if old_profile["calculation"]!=calculation or old_profile["group_runtime_budget_seconds"]!=86400:
        raise ValueError("Reference transport settings differ")
    profile={"schema_version":1,"profile_id":PROFILE_ID,"status":"approved",
             "purpose":"ADAPTIVE-02 32-case student research only; no later adaptive groups",
             "calculation":calculation,"seed_base":74001,"group_runtime_budget_seconds":86400,
             "production_approval":"adaptive02_first32_equal_halton_transport_budget_only",
             "decision_source":AUTH}
    profile_path=BUNDLE/"configs"/PROFILE_NAME
    write_new(profile_path,profile)
    write_new(Path(str(profile_path)+".approval.json"),{
        "status":"approved","document_sha256":sha(profile_path),"reviewer":"danisman: "+AUTH,
        "scope":"only_adaptive_02_first_32_controlled_research",
        "physical_acceptance":"not_assessed","statistical_convergence":"review_required",
        "training_acceptance":"not_granted","decision_source":AUTH})
    # Include provenance as data, not as extra execution machinery.
    copy("reports/adaptive_selection_02_v1/selection_report.json",BUNDLE/"reports/adaptive_selection_02_v1/selection_report.json")
    copy("reports/adaptive_selection_02_v1/selected_scores.csv",BUNDLE/"reports/adaptive_selection_02_v1/selected_scores.csv")
    copy("scenarios/v2_adaptive128_v1/adaptive_02/selected_32.json",BUNDLE/"scenarios/v2_adaptive128_v1/adaptive_02/selected_32.json")
    sys.path.insert(0,str(BUNDLE/"src"))
    from reactor_pipeline import v2_students
    space_path=BUNDLE/"configs"/SPACE_NAME
    if not v2_students.production_ready(space_path=space_path,profile_path=profile_path):
        raise ValueError("Snapshot profile or space lacks technical approval")
    space=v2_students.load_space(space_path)
    ref_sha=sha(BUNDLE/space["reference_config"])
    for case in selected["selected"]:
        if v2_students.scenario_id(case["controls"],ref_sha)!=case["scenario_id"]:
            raise ValueError("Selected scenario identity changed")
    catalogue={"schema":"beavrs_v2_scenario_list_v1","state":"production_ready",
               "model":space["model"],"space_id":space["space_id"],
               "space_sha256":sha(space_path),"profile_id":PROFILE_ID,
               "profile_sha256":sha(profile_path),"reference_config_sha256":ref_sha,
               "sampling_seed":report["algorithm"]["candidate_seed"],
               "sampling_method":report["algorithm"]["version"],
               "selection_report_sha256":sha(SELECTION_REPORT),
               "requested_count":32,"scenario_count":32,"generation_status":"complete",
               "scenarios":selected["selected"],"rejected":[],"calculation_profile_separate":True}
    catalogue_path=BUNDLE/"scenarios/v2_adaptive128_v1/adaptive_02/catalogue.json"
    write_new(catalogue_path,catalogue)
    output=BUNDLE/"student_packages/v2_adaptive128_v1/adaptive_02"
    v2_students.allocate(catalogue_path,["adaptive_02"],output,
                         space_path=space_path,profile_path=profile_path)
    package=output/PACKAGE_ID
    manifest=v2_students._read(package/"manifest.json")
    if len(manifest["experiments"])!=32 or [case["scenario_id"] for case in manifest["experiments"]]!=ids:
        raise ValueError("Allocated scenarios differ")
    if [case["calculation"]["seed"] for case in manifest["experiments"]]!=list(range(74001,74033)):
        raise ValueError("Allocated seeds differ")
    with (package/"README.md").open("a",encoding="utf-8") as stream:
        stream.write("\nADAPTIVE-02; 32 cases only. Use student_packages/v2_adaptive128_v1/adaptive_02/README.md. "
                     "Physical/statistical/training acceptance not granted.\n")
    hashes_path=package/"SHA256SUMS.json"
    hashes=v2_students._read(hashes_path)
    hashes["README.md"]=sha(package/"README.md")
    hashes_path.write_text(json.dumps(hashes,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    package_path=package/"package.json"
    info=v2_students._read(package_path)
    info["hashes_sha256"]=sha(hashes_path)
    package_path.write_text(json.dumps(info,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    write_new(package/"approval.json",{
        "status":"approved","authorization":"adaptive02_first32_controlled_research_student_only",
        "model":space["model"],"group_id":PACKAGE_ID,
        "meaning":"Technical run preparation only; no physical, convergence or training acceptance",
        "package_sha256":sha(package_path),"hashes_sha256":sha(hashes_path),
        "decision_source":AUTH})
    v2_students.verify_package(package,require_approval=True)
    if (BUNDLE/"runs").exists():
        raise ValueError("Bundle unexpectedly contains runs")
    package_rel=package.relative_to(BUNDLE).as_posix()
    readme=("# ADAPTIVE-02 öğrenci paketi\n\n"
        "Bu ZIP'i WSL Ubuntu'daki **~/openmc-proje/student_packages/v2_adaptive128_v1/** dizinine açın. "
        "Klasör **~/openmc-proje/student_packages/v2_adaptive128_v1/adaptive_02/** oluşur. "
        "`student_setup.md` içindeki bir defalık OpenMC 0.16.0, openmc-proje kerneli ve "
        "ENDF/B-VIII.0 HDF5 kurulumunu izleyin. Nükleer veri bu ZIP'te yoktur; "
        "`OPENMC_CROSS_SECTIONS` mevcut Conda ortamınızın yerel XML dosyasını göstermelidir.\n\n"
        "```bash\nconda activate openmc-proje\ncd ~/openmc-proje/student_packages/v2_adaptive128_v1/adaptive_02\n"
        f"PAKET=\"{package_rel}\"\n"
        "python -c \"import os, openmc; from pathlib import Path; p=Path(os.environ['OPENMC_CROSS_SECTIONS']); "
        "assert p.is_file(); print(openmc.__version__, p)\"\n"
        "python scripts/v2_student_production.py verify \"$PAKET\"\n"
        "python scripts/v2_student_production.py preflight \"$PAKET\"\n"
        "```\n\n"
        "**Başlatma (bir kez):** `$PAKET/01_calistir.ipynb` dosyasını JupyterLab'da "
        "`Python (OpenMC Proje)` kerneliyle açıp Run All yapın. Aynı işlemi terminalden yapmak isterseniz "
        "yalnız `python scripts/v2_student_production.py launch \"$PAKET\"` komutunu kullanın; "
        "notebook ve terminali birlikte başlatmayın. İşçi tarayıcıdan bağımsız çalışır.\n\n"
        "```bash\npython scripts/v2_student_production.py status \"$PAKET\"\n"
        "python scripts/v2_student_production.py stop \"$PAKET\"\n"
        "python scripts/v2_student_production.py resume \"$PAKET\"\n"
        "```\n\n"
        "`stop` ve `resume` yalnız danışman yönlendirmesiyle kullanılır. "
        "Tamamlanan koşular tekrar çalıştırılmaz; `failed`/`stopped` grup kendiliğinden devam etmez. "
        "`02_sonuclari_incele.ipynb` yalnız sonuçları okur.\n\n"
        "Grup tamamlanınca teslim ZIP'i:\n\n"
        "```bash\nmkdir -p deliveries\n"
        f"python scripts/v2_transfer.py export \"$PAKET\" \"deliveries/{PACKAGE_ID}.zip\"\n"
        "```\n\n"
        "Statepoint dosyaları hafif teslim ZIP'inde yer almaz; kaynak makinede saklayın. "
        "`completed` fiziksel doğrulama veya eğitim kabulü değildir. "
        "24 saatlik grup tavanı öğrenci bilgisayarında 32 koşunun biteceğinin garantisi değildir.\n")
    (BUNDLE/"README.md").write_text(readme,encoding="utf-8")
    ZIP.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ZIP,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix!=".pyc":
                archive.write(path,(Path("adaptive_02")/path.relative_to(BUNDLE)).as_posix())
    print(json.dumps({"bundle":str(BUNDLE),"package":str(package),"zip":str(ZIP),
                      "zip_bytes":ZIP.stat().st_size,"zip_sha256":sha(ZIP),
                      "package_sha256":sha(package_path),"profile_sha256":sha(profile_path)}))


if __name__=="__main__":
    main()


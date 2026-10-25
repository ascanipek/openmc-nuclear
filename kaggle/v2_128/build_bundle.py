"""Build four new Halton Kaggle packages without running OpenMC."""
from copy import deepcopy
import hashlib, json, shutil, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SOURCE = REPO / "kaggle/ogrenci_04"
PROJECT = ROOT / "project"
STAGES = tuple(f"halton_{n:02d}" for n in range(1, 5))
OWNER = "advisor_halton"
SEED_BASE = 72001
PROFILE_NAME = "v2_calculation_profile_halton128_80k_24h_research_v1.json"

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")

def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"Expected one fragment: {before[:70]}")
    return source.replace(before, after)

def copy_reviewed_project():
    if PROJECT.exists() or (ROOT / "bundle_hashes.json").exists():
        raise FileExistsError("Frozen package exists; refusing overwrite")
    for relative, expected in read(SOURCE / "bundle_hashes.json")["files"].items():
        if sha(SOURCE / relative) != expected:
            raise ValueError(f"Existing reviewed Kaggle bundle differs: {relative}")
    shutil.copytree(SOURCE / "project/src", PROJECT / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SOURCE / "project/scripts", PROJECT / "scripts")
    for name in ("beavrs_derived_3d_reference.json",
                 "v2_parameter_space_pilot_scope_v1.json",
                 "v2_parameter_space_pilot_scope_v1.json.approval.json"):
        target = PROJECT / "configs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / "project/configs" / name, target)

def profile():
    old = read(SOURCE / "project/configs/v2_calculation_profile_256_students_80k_24h_research_v1.json")
    expected = {"particles_per_generation": 80000, "batches": 600, "inactive": 300,
                "generations_per_batch": 1, "threads": 6}
    if old["calculation"] != expected or old["group_runtime_budget_seconds"] != 86400:
        raise ValueError("Existing 32-case research profile differs")
    new = deepcopy(old)
    new.update(profile_id="beavrs_v2_halton128_80k_24h_research_v1",
               purpose="Four new 32-case Halton continuation groups only; controlled research",
               seed_base=SEED_BASE,
               production_approval="halton_indices_233_to_360_controlled_research_only",
               decision_source="Advisor user request, 2026-10-24: prepare 128 new Halton Kaggle CPU cases")
    path = PROJECT / "configs" / PROFILE_NAME
    write_new(path, new)
    write_new(Path(str(path) + ".approval.json"), {
        "status": "approved", "document_sha256": sha(path),
        "reviewer": "danisman: user request 2026-10-24 for 128 new Halton research cases",
        "scope": "only_halton_indices_233_to_360_in_four_32_case_groups",
        "physical_acceptance": "not_assessed", "statistical_convergence": "review_required",
        "training_acceptance": "not_granted"})
    return path

def catalogues(profile_path):
    sys.path.insert(0, str(PROJECT / "src"))
    from reactor_pipeline import v2_pilot, v2_students
    from reactor_pipeline.parameter_space import resolve_proposed
    old_path = REPO / "scenarios/v2_students_portable_v1/catalogue_total_256.json"
    old = read(old_path)
    space_path = PROJECT / "configs/v2_parameter_space_pilot_scope_v1.json"
    space = read(space_path)
    proposed = read(REPO / "configs/v2_parameter_space_pilot_proposed_v1.json")
    sampling = old["sampling_parameters"]
    if (len(old["scenarios"]) != 256 or old["sampling_seed"] != v2_pilot.SEED or
            old["reference_config_sha256"] != sha(PROJECT / space["reference_config"]) or
            sampling["halton_bases"] != list(v2_pilot.PRIMES) or
            sampling["control_order"] != list(space["nominal"]) or
            sampling["generator_sha256"] != sha(PROJECT / "src/reactor_pipeline/v2_pilot.py") or
            old["scenarios"][-1]["sampling_stratum"] != "multiparameter_halton_232"):
        raise ValueError("Pinned 256-case catalogue and Halton generator differ")
    for key in sampling["control_order"]:
        if any(space["ranges"][key][edge] != proposed["ranges"][key][edge]
               for edge in ("lower", "upper")):
            raise ValueError(f"Approved range differs from original Halton range: {key}")
    shifts = sampling["halton_shifts"]
    if len(shifts) != 8:
        raise ValueError("Expected eight pinned coordinate shifts")
    prior_ids = {row["scenario_id"] for row in old["scenarios"]}
    prior_values = {json.dumps(row["controls"], sort_keys=True) for row in old["scenarios"]}
    records = []
    for index in range(233, 361):
        controls = {}
        for dim, key in enumerate(sampling["control_order"]):
            bounds = space["ranges"][key]
            unit = (v2_pilot._radical_inverse(index, sampling["halton_bases"][dim]) + shifts[dim]) % 1.0
            controls[key] = bounds["lower"] + (bounds["upper"] - bounds["lower"]) * unit
            if not bounds["lower"] <= controls[key] <= bounds["upper"]:
                raise ValueError(f"Halton {index} outside approved {key} range")
        resolve_proposed(controls)
        sid = v2_students.scenario_id(controls, old["reference_config_sha256"])
        encoded = json.dumps(controls, sort_keys=True)
        if sid in prior_ids or encoded in prior_values:
            raise ValueError(f"Halton {index} repeats an earlier physical scenario")
        prior_ids.add(sid)
        prior_values.add(encoded)
        records.append({"scenario_id": sid, "controls": controls,
                        "sampling_stratum": f"multiparameter_halton_{index}",
                        "halton_index": index})
    if len(records) != 128 or len({row["scenario_id"] for row in records}) != 128:
        raise ValueError("Expected 128 distinct new scenarios")
    common = {"schema": "beavrs_v2_scenario_list_v1", "state": "production_ready",
              "model": space["model"], "space_id": space["space_id"],
              "space_sha256": sha(space_path), "profile_id": read(profile_path)["profile_id"],
              "profile_sha256": sha(profile_path),
              "reference_config_sha256": old["reference_config_sha256"],
              "sampling_seed": old["sampling_seed"],
              "sampling_method": "continuation_of_legacy_8_then_OAT_endpoints_then_shifted_Halton_v1",
              "sampling_parameters": sampling, "previous_catalogue_sha256": sha(old_path),
              "generation_status": "complete", "rejected": [],
              "calculation_profile_separate": True}
    catalog_root = PROJECT / "scenarios/v2_halton128_v1"
    write_new(catalog_root / "catalogue_new_128.json",
              dict(common, requested_count=128, scenario_count=128,
                   halton_index_start=233, halton_index_end=360, scenarios=records))
    for group, stage in enumerate(STAGES):
        write_new(catalog_root / f"catalogue_{stage}.json",
                  dict(common, requested_count=32, scenario_count=32,
                       halton_index_start=233 + group*32, halton_index_end=264 + group*32,
                       scenarios=records[group*32:(group+1)*32]))
    return space_path, records

def packages(space_path, profile_path, records):
    from reactor_pipeline import v2_students
    registry = {}
    for group, stage in enumerate(STAGES):
        catalogue = PROJECT / "scenarios/v2_halton128_v1" / f"catalogue_{stage}.json"
        output = PROJECT / "student_packages/v2_halton128_v1" / stage
        v2_students.allocate(catalogue, [stage], output,
                             space_path=space_path, profile_path=profile_path)
        package = next(output.iterdir())
        manifest_path = package / "manifest.json"
        manifest = read(manifest_path)
        for within, case in enumerate(manifest["experiments"]):
            source = records[group*32+within]
            if (case["scenario_id"], case["controls"]) != (source["scenario_id"], source["controls"]):
                raise ValueError("Package order differs from consecutive Halton indices")
            case["calculation"]["seed"] = SEED_BASE + group*32 + within
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (package / "README.md").write_text(
            f"# {stage}: Halton {233+group*32}–{264+group*32}\n\n"
            "32 fixed cases. Use only the outer 01_kaggle_calistir.ipynb on Kaggle. "
            "The package notebooks exist for the current package hash format. "
            "completed is not physical or statistical acceptance.\n", encoding="utf-8")
        hashes_path = package / "SHA256SUMS.json"
        hashes = read(hashes_path)
        hashes.update({"manifest.json": sha(manifest_path), "README.md": sha(package / "README.md")})
        hashes_path.write_text(json.dumps(hashes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        info_path = package / "package.json"
        info = read(info_path)
        info.update(owner=OWNER, stage=stage, manifest_sha256=sha(manifest_path),
                    hashes_sha256=sha(hashes_path))
        info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_new(package / "approval.json", {
            "status": "approved", "authorization": "new_128_Halton_Kaggle_CPU_research_only",
            "model": manifest["model"], "group_id": manifest["group_id"],
            "meaning": "Technical run preparation only; no physical, convergence or training acceptance",
            "package_sha256": sha(info_path), "hashes_sha256": sha(hashes_path),
            "decision_source": "Advisor user request, 2026-10-24: four new 32-case Kaggle CPU groups"})
        v2_students.verify_package(package, require_approval=True)
        registry[info["package_id"]] = {
            "owner": OWNER, "stage": stage, "package_path": str(package.relative_to(PROJECT)),
            "scenario_ids": [case["scenario_id"] for case in manifest["experiments"]],
            "package_sha256": sha(info_path), "manifest_sha256": sha(manifest_path)}
    scenario_assignment = {
        row["scenario_id"]: {
            "owner": OWNER, "stage": STAGES[index // 32],
            "source": f"continuation_halton_{row['halton_index']}",
            "quality": "not_assessed"}
        for index, row in enumerate(records)}
    write_new(PROJECT / "configs/v2_student_assignment_v1.json", {
        "schema": "v2_student_assignment_v1",
        "status": "distribution_prepared_no_physics_acceptance",
        "decision_source": "Advisor user request, 2026-10-24: only Halton indices 233–360",
        "source_catalogues": {stage: f"scenarios/v2_halton128_v1/catalogue_{stage}.json"
                              for stage in STAGES}, "packages": registry,
        "scenarios": scenario_assignment})

def adapter_and_notebook():
    adapter = (SOURCE / "kaggle_runner.py").read_text(encoding="utf-8")
    adapter = replace_once(adapter, 'STAGES = ("stage_32", "stage_128", "stage_256")',
                           'STAGES = ("halton_01", "halton_02", "halton_03", "halton_04")')
    adapter = replace_once(adapter, 'OWNER = "ogrenci_04"', f'OWNER = "{OWNER}"')
    adapter = replace_once(adapter,
        'package_id = f"v2_{stage}_{OWNER}_beavrs_v2_pilot_scope_v1"\n'
        '    return Path(project) / "student_packages/v2_students_portable_v1" / stage / OWNER / package_id',
        'package_id = f"v2_{stage}_beavrs_v2_pilot_scope_v1"\n'
        '    return Path(project) / "student_packages/v2_halton128_v1" / stage / package_id')
    adapter = replace_once(adapter, '{"stage_32": 8, "stage_128": 24, "stage_256": 32}[stage]',
                           '{name: 32 for name in STAGES}[stage]')
    adapter = replace_once(adapter, 'existing approved ogrenci_04 V2 packages',
                           'four new Halton V2 packages')
    (ROOT / "kaggle_runner.py").write_text(adapter, encoding="utf-8")
    notebook = read(SOURCE / "01_kaggle_calistir.ipynb")
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        text = "".join(cell["source"])
        text = text.replace('SELECTED_STAGE = "stage_256"  # 32 yeni koşu; önceki aşamalar otomatik başlamaz',
                            'SELECTED_STAGE = "halton_01"  # sonraki paketler otomatik başlamaz')
        text = text.replace('CODE_DATASET_ROOT = "/kaggle/input/datasets/ascanipek/openmc-code-base"',
                            'CODE_DATASET_ROOT = "/kaggle/input/V2_128_KOD_DATASET_ADI"')
        text = text.replace('expected = {"stage_32": 8, "stage_128": 24, "stage_256": 32}[stage]',
                            'expected = 32')
        text = text.replace('package = (code_root / "project/student_packages/v2_students_portable_v1"\n'
                            '           / SELECTED_STAGE / "ogrenci_04"\n'
                            '           / f"v2_{SELECTED_STAGE}_ogrenci_04_beavrs_v2_pilot_scope_v1")',
                            'package = kr._package(code_root / "project", SELECTED_STAGE)')
        cell["source"] = text.splitlines(keepends=True)
        cell["outputs"] = []
        cell["execution_count"] = None
    notebook["cells"][0]["source"] = [
        "# Yeni 128 Halton senaryosu — Kaggle CPU\n",
        "**Run All** yalnız seçili 32 koşuluk paketi başlatır. Sonraki pakete otomatik geçmez. "
        "Senaryo tablosu ve ön kontrol hesap hücresinden önce gösterilir. "
        "completed fiziksel veya istatistiksel kabul değildir.\n"]
    write_new(ROOT / "01_kaggle_calistir.ipynb", notebook)

def freeze():
    files = {path.relative_to(ROOT).as_posix(): sha(path)
             for path in sorted(PROJECT.rglob("*"))
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    files.update({name: sha(ROOT / name)
                  for name in ("kaggle_runner.py", "01_kaggle_calistir.ipynb", "README.md")})
    write_new(ROOT / "bundle_hashes.json", {
        "schema": "kaggle_code_bundle_sha256_v1", "owner": OWNER,
        "stages": {stage: 32 for stage in STAGES}, "files": dict(sorted(files.items()))})
    output = ROOT / "v2_128_kod_dataset.zip"
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(ROOT / "bundle_hashes.json", "bundle_hashes.json")
        for name in sorted(files):
            archive.write(ROOT / name, name)
    return len(files), output

def main():
    copy_reviewed_project()
    profile_path = profile()
    space_path, records = catalogues(profile_path)
    packages(space_path, profile_path, records)
    adapter_and_notebook()
    count, output = freeze()
    print(json.dumps({"new_scenarios": len(records), "halton_indices": [233, 360],
                      "stages": list(STAGES), "bundle_files": count,
                      "zip": str(output), "zip_sha256": sha(output)}, indent=2))

if __name__ == "__main__":
    main()


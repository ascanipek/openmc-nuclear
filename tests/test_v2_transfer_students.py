"""No transport: portable package and synthetic handoff validation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from reactor_pipeline import v2_students, v2_transfer, v2_student_runner

P = v2_students.PROJECT
PKG = P / "student_packages/v2_students_portable_v1/stage_32/ogrenci_02/v2_stage_32_ogrenci_02_beavrs_v2_pilot_scope_v1"


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class StudentHandoffTests(unittest.TestCase):
    def test_distribution_unique_pilot_reuse_and_mocked_launch_gate(self):
        assignment=json.loads((P/"configs/v2_student_assignment_v1.json").read_text())
        self.assertEqual(len(assignment["scenarios"]),256)
        self.assertEqual(len(assignment["pilot_reuse"]["scenario_ids"]),8)
        self.assertEqual({assignment["scenarios"][sid]["owner"] for sid in assignment["pilot_reuse"]["scenario_ids"]},{"ogrenci_01"})
        self.assertEqual({stage:data["new_to_run"] for stage,data in assignment["stages"].items()},
                         {"stage_32":24,"stage_128":96,"stage_256":128})
        self.assertEqual(len(assignment["packages"]),12)  # one historical advisor + 11 new packages
        for entry in assignment["packages"].values():
            self.assertEqual(len(entry["scenario_ids"]),8 if entry["stage"]=="stage_32" else 24 if entry["stage"]=="stage_128" else 32)
        with patch.object(v2_student_runner.subprocess,"Popen",side_effect=AssertionError("worker started")) as spawn:
            with self.assertRaises((ValueError,FileNotFoundError)):
                v2_student_runner.launch(PKG)
            spawn.assert_not_called()

    def fixture(self, root, *, missing_fields=False, controls=None, result_marker="A", run_id="run-one", seed=1, package_id="v2_stage_32_ogrenci_02_synthetic"):
        controls = controls or v2_students.load_space()["nominal"]
        refsha = v2_students.digest(P / "configs/beavrs_derived_3d_reference.json")
        sid = v2_students.scenario_id(controls, refsha)
        calc = {"batches":600,"inactive":300,"particles_per_generation":80000,"generations_per_batch":1,"threads":6,"seed":seed}
        manifest = {"group_id":package_id,"model":v2_transfer.MODEL_ID,"reference_config_sha256":refsha,
                    "experiments":[{"experiment_id":"E1","scenario_id":sid,"controls":controls,"calculation":calc}]}
        package = {"package_id":package_id,"model":v2_transfer.MODEL_ID,"project_root":".","package_path":"unused"}
        base = "group/experiments/E1/attempt_1/"
        files = {"package/manifest.json":encoded(manifest),"group/manifest.json":encoded(manifest),
                 "package/package.json":encoded(package),"package/SHA256SUMS.json":encoded({}),
                 "group/status.json":encoded({"state":"completed"}),
                 base+"status.json":encoded({"state":"completed","scenario_id":sid,"run_id":run_id}),
                 base+"summary.json":encoded({"marker":result_marker}),
                 base+"resolved_config.json":encoded({"controls":controls,"calculation":calc}),
                 base+"openmc.log":b"log",base+"report.html":b"report",base+"model.xml":b"<model/>",
                 base+"fields.npz":b"small synthetic bytes"}
        if missing_fields: del files[base+"fields.npz"]
        meta={"schema":v2_transfer.SCHEMA,"model":v2_transfer.MODEL_ID,"package_id":package_id,
              "manifest_sha256":hashlib.sha256(files["package/manifest.json"]).hexdigest(),
              "package_sha256":hashlib.sha256(files["package/package.json"]).hexdigest(),
              "hashes_sha256":hashlib.sha256(files["package/SHA256SUMS.json"]).hexdigest()}
        files["transfer.json"]=encoded(meta)
        checks={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        path=Path(root)/(result_marker+".zip")
        with zipfile.ZipFile(path,"w") as archive:
            for name,data in files.items():archive.writestr(name,data)
            archive.writestr("checksums.json",encoded(checks))
        assignment={"schema":"v2_student_assignment_v1","packages":{package_id:{"owner":"ogrenci_02","stage":"stage_32",
                   "package_sha256":meta["package_sha256"],"manifest_sha256":meta["manifest_sha256"],"scenario_ids":[sid]}}}
        ap=Path(root)/"assignment.json";ap.write_bytes(encoded(assignment))
        return path,ap,controls,calc

    def test_portable_package_verifies_after_relocation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"new_user_project"
            shutil.copytree(P/"src/reactor_pipeline",root/"src/reactor_pipeline",ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(P/"configs",root/"configs")
            (root/"scripts").mkdir()
            shutil.copy2(P/"scripts/v2_student_production.py",root/"scripts/v2_student_production.py")
            shutil.copy2(P/"scripts/v2_transfer.py",root/"scripts/v2_transfer.py")
            target=root/PKG.relative_to(P)
            shutil.copytree(PKG,target)
            code=("from reactor_pipeline.v2_students import verify_package; "
                  f"verify_package({str(target)!r}, require_approval=False)")
            env=dict(os.environ,PYTHONPATH=str(root/"src"))
            run=subprocess.run([sys.executable,"-c",code],cwd=target,env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertNotIn("/home/ascanipek",json.dumps(json.loads((target/"package.json").read_text())))

    def test_duplicate_corrupt_conflict_missing_and_zip_slip(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            z,ap,controls,calc=self.fixture(root)
            inbox=root/"imported"
            with patch.object(v2_transfer.v2_dataset,"_attempt",return_value={"resolved":{"controls":controls,"calculation":calc}}):
                first=v2_transfer.import_zip(z,inbox,ap)
                self.assertEqual(first["state"],"imported")
                self.assertEqual(v2_transfer.import_zip(z,inbox,ap)["state"],"duplicate")
                z2,_,_,_=self.fixture(root,result_marker="B")
                with self.assertRaisesRegex(ValueError,"Conflicting delivery"):
                    v2_transfer.import_zip(z2,inbox,ap)
                missing,_,_,_=self.fixture(root,missing_fields=True,result_marker="missing")
                with self.assertRaisesRegex(ValueError,"missing required outputs"):
                    v2_transfer.import_zip(missing,inbox,ap)
            bad=root/"bad.zip"
            with zipfile.ZipFile(z) as source,zipfile.ZipFile(bad,"w") as output:
                for name in source.namelist():
                    data=source.read(name)
                    if name.endswith("summary.json"):data+=b"tamper"
                    output.writestr(name,data)
            with self.assertRaisesRegex(ValueError,"Checksum mismatch"):
                v2_transfer.import_zip(bad,inbox,ap)
            slip=root/"slip.zip"
            with zipfile.ZipFile(z) as source, zipfile.ZipFile(slip,"w") as output:
                for name in source.namelist():output.writestr(name,source.read(name))
                output.writestr("../escape","bad")
            with self.assertRaisesRegex(ValueError,"Unsafe ZIP path"):
                v2_transfer.import_zip(slip,inbox,ap)

    def test_distinct_seeds_or_budgets_remain_separate_runs_of_one_scenario(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            z1,ap,controls,calc=self.fixture(root,result_marker="A",run_id="run-one")
            first_assignment=json.loads(ap.read_text())
            z2,_,_,_=self.fixture(root,result_marker="B",run_id="run-two",seed=2,
                                   package_id="v2_stage_32_ogrenci_02_repeat")
            second_assignment=json.loads(ap.read_text())
            first_assignment["packages"].update(second_assignment["packages"])
            ap.write_bytes(encoded(first_assignment))
            inbox=root/"imports"
            with patch.object(v2_transfer.v2_dataset,"_attempt",side_effect=lambda path, preview:
                              {"resolved":json.loads((path/"resolved_config.json").read_text())}):
                one=v2_transfer.import_zip(z1,inbox,ap)
                two=v2_transfer.import_zip(z2,inbox,ap)
            self.assertEqual(one["state"],"imported")
            self.assertEqual(two["state"],"imported")
            self.assertEqual(one["receipt"]["scenario_ids"],two["receipt"]["scenario_ids"])
            self.assertNotEqual(one["receipt"]["runs"][0]["run_id"],two["receipt"]["runs"][0]["run_id"])

    def test_same_package_id_with_changed_budget_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            z1,ap,controls,calc=self.fixture(root,result_marker="first",seed=1)
            inbox=root/"imports"
            with patch.object(v2_transfer.v2_dataset,"_attempt",side_effect=lambda path, preview:
                              {"resolved":json.loads((path/"resolved_config.json").read_text())}):
                v2_transfer.import_zip(z1,inbox,ap)
                z2,_,_,_=self.fixture(root,result_marker="second",run_id="new-run",seed=2)
                with self.assertRaisesRegex(ValueError,"Conflicting package identity"):
                    v2_transfer.import_zip(z2,inbox,ap)

    def test_conflicting_scenario_identity_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            z,ap,controls,calc=self.fixture(root)
            with zipfile.ZipFile(z) as source:
                files={name:source.read(name) for name in source.namelist() if name!="checksums.json"}
            manifest=json.loads(files["package/manifest.json"])
            manifest["experiments"][0]["controls"]["elemental_boron_ppm"]=11
            files["package/manifest.json"]=encoded(manifest)
            files["group/manifest.json"]=encoded(manifest)
            meta=json.loads(files["transfer.json"]);meta["manifest_sha256"]=hashlib.sha256(files["package/manifest.json"]).hexdigest();files["transfer.json"]=encoded(meta)
            assignment=json.loads(ap.read_text());assignment["packages"][meta["package_id"]]["manifest_sha256"]=meta["manifest_sha256"];ap.write_bytes(encoded(assignment))
            altered=root/"altered.zip"
            with zipfile.ZipFile(altered,"w") as output:
                for name,data in files.items():output.writestr(name,data)
                output.writestr("checksums.json",encoded({name:hashlib.sha256(data).hexdigest() for name,data in files.items()}))
            with self.assertRaisesRegex(ValueError,"Scenario identity mismatch"):
                v2_transfer.import_zip(altered,root/"imports",ap)

if __name__=="__main__":unittest.main()



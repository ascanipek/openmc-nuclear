"""Adaptive-02 selection and extracted portable ZIP checks; transport never starts."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ZIP=ROOT/"deliveries/v2_adaptive_02_student_v1.zip"
SELECTION=ROOT/"reports/adaptive_selection_02_v1"
SELECTED=ROOT/"scenarios/v2_adaptive128_v1/adaptive_02/selected_32.json"
PACKAGE_REL=Path("student_packages/v2_adaptive128_v1/adaptive_02/v2_adaptive_02_beavrs_v2_pilot_scope_v1")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Adaptive02PortableChecks(unittest.TestCase):
    def test_selection_is_train_only_and_unique(self):
        report=json.loads((SELECTION/"selection_report.json").read_text())
        chosen=json.loads(SELECTED.read_text())["selected"]
        old=json.loads((ROOT/"datasets/v2_256_preview_v1/splits.json").read_text())
        adaptive01=json.loads((ROOT/"scenarios/v2_adaptive128_v1/adaptive_01/selected_32.json").read_text())["selected"]
        halton=json.loads((ROOT/"scenarios/v2_halton128_v1/catalogue_new_128.json").read_text())["scenarios"]
        existing=set().union(*[set(old[key]) for key in ("train","calibration","test")])
        existing|={row["scenario_id"] for row in adaptive01}
        existing|={row["scenario_id"] for row in halton}
        ids=[row["scenario_id"] for row in chosen]
        self.assertEqual(len(ids),32)
        self.assertEqual(len(set(ids)),32)
        self.assertFalse(set(ids)&existing)
        self.assertEqual(report["algorithm"]["weights"],{"k_uncertainty":.35,
            "field_uncertainty":.35,"sparsity":.20,"criticality":.10})
        self.assertEqual(report["algorithm"]["candidate_seed"],20261121)
        self.assertEqual(report["data_firewall"]["calibration_excluded"],25)
        self.assertEqual(report["data_firewall"]["test_excluded"],23)
        with (SELECTION/"training_only_oof_uncertainty.csv").open(newline="",encoding="utf-8") as stream:
            oof=list(csv.DictReader(stream))
        training=json.loads((ROOT/"datasets/v2_288_adaptive01_exploratory_v1/splits.json").read_text())["train"]
        self.assertEqual({r["scenario_id"] for r in oof},set(training))
        folds=json.loads((SELECTION/"oof_folds.json").read_text())
        forbidden=set(old["calibration"])|set(old["test"])
        for fold in folds:
            fit,val=set(fold["fit_scenario_ids"]),set(fold["validation_scenario_ids"])
            self.assertFalse((fit|val)&forbidden)
            self.assertFalse(fit&val)
        space=json.loads((ROOT/"configs/v2_parameter_space_pilot_scope_v1.json").read_text())
        for row in chosen:
            for name,value in row["controls"].items():
                self.assertTrue(space["ranges"][name]["lower"]<=value<=space["ranges"][name]["upper"])
        self.assertGreaterEqual(report["selection"]["min_pairwise_distance_normalized_8d"],.35)

    def test_zip_extracts_to_student_and_existing_commands_pass(self):
        self.assertTrue(ZIP.is_file())
        with zipfile.ZipFile(ZIP) as archive:
            self.assertIsNone(archive.testzip())
            names=archive.namelist()
            self.assertEqual(len(names),len(set(names)))
            self.assertTrue(all(name.startswith("adaptive_02/") and ".." not in Path(name).parts for name in names))
            self.assertFalse(any("data/endfb" in name or "statepoint" in name or "/runs/" in name for name in names))
            with tempfile.TemporaryDirectory(prefix="adaptive02_portable_") as temp:
                student=Path(temp)/"student_packages/v2_adaptive128_v1"
                student.mkdir(parents=True)
                archive.extractall(student)
                bundle=student/"adaptive_02"
                package=bundle/PACKAGE_REL
                for path in (bundle/"README.md",bundle/"student_setup.md",bundle/"environment.yml",
                             bundle/"scripts/v2_student_production.py",bundle/"scripts/v2_transfer.py",
                             bundle/"configs/v2_parameter_space_pilot_scope_v1.json",
                             package/"01_calistir.ipynb",package/"02_sonuclari_incele.ipynb",
                             package/"manifest.json",package/"approval.json"):
                    self.assertTrue(path.is_file(),str(path))
                env=dict(__import__("os").environ)
                env.pop("PYTHONPATH",None)
                for command in ("verify","preflight","status"):
                    result=subprocess.run([sys.executable,str(bundle/"scripts/v2_student_production.py"),
                                           command,str(package)],cwd=bundle,env=env,
                                          text=True,capture_output=True,check=True)
                    value=json.loads(result.stdout)
                    if command=="preflight":
                        self.assertEqual(len(value["cases"]),32)
                        self.assertFalse(value["transport_started"])
                    if command=="status":
                        self.assertEqual(value["state"],"not_started")
                manifest=json.loads((package/"manifest.json").read_text())
                self.assertEqual(len(manifest["experiments"]),32)
                self.assertEqual([case["calculation"]["seed"] for case in manifest["experiments"]],list(range(74001,74033)))


if __name__=="__main__":
    unittest.main()





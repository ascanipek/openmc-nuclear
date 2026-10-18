"""Advisor pilot safeguards; no transport or launch."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from reactor_pipeline import v2_runner as runner, v2_scenarios as scenarios

P = scenarios.PROJECT
ROOT = P / "student_packages/v2_advisor_pilot_v1"
PKG = ROOT / "v2_advisor_pilot8_beavrs_v2_pilot_scope_v1"
SPLIT = P / "scenarios/v2_advisor_pilot_v1/split.json"


class AdvisorPilotTests(unittest.TestCase):
    def test_catalogue_split_preserves_ids_values_and_budget(self):
        source = scenarios._read(P / "student_packages/v2_staged_draft_v1/stage_32/catalogue_total.json")
        split = scenarios._read(SPLIT)
        first = scenarios._read(P / "scenarios/v2_advisor_pilot_v1/initial_8_catalogue.json")
        rest = scenarios._read(P / "scenarios/v2_advisor_pilot_v1/remaining_24_catalogue.json")
        self.assertEqual(len(first["scenarios"]), 8)
        self.assertEqual(len(rest["scenarios"]), 24)
        self.assertEqual(set(split["initial_indices_zero_based"] + split["remaining_indices_zero_based"]), set(range(32)))
        self.assertEqual(set(split["initial_indices_zero_based"]) & set(split["remaining_indices_zero_based"]), set())
        for cat, indices in ((first, split["initial_indices_zero_based"]), (rest, split["remaining_indices_zero_based"])):
            self.assertEqual(cat["scenarios"], [source["scenarios"][i] for i in indices])
        m = scenarios._read(PKG / "manifest.json")
        self.assertEqual([c["scenario_id"] for c in m["experiments"]],
                         [r["scenario_id"] for r in first["scenarios"]])
        self.assertEqual(m["group_runtime_budget_seconds"], 14400)
        self.assertEqual([c["calculation"]["seed"] for c in m["experiments"]], list(range(71001,71009)))
        for case in m["experiments"]:
            calc = case["calculation"]
            self.assertEqual((calc["batches"], calc["inactive"], calc["particles_per_generation"],
                              calc["generations_per_batch"], calc["threads"]), (600,300,80000,1,6))
        self.assertLess(8*runner._estimate_seconds(m["experiments"][0]["calculation"]), 14400)

    def test_package_is_sealed_and_unapproved_copy_blocks_launch(self):
        scenarios.verify_package(PKG, require_approval=False)
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / PKG.name
            shutil.copytree(PKG, copied, ignore=shutil.ignore_patterns("approval.json"))
            with patch.object(runner.subprocess, "Popen", side_effect=AssertionError("transport started")) as spawn:
                with self.assertRaises((ValueError, FileNotFoundError)):
                    runner.launch(copied)
                spawn.assert_not_called()
            book = copied / "01_calistir.ipynb"
            nb = json.loads(book.read_text())
            nb["cells"][-1]["outputs"] = [{"output_type":"stream","name":"stdout","text":["hello\n"]}]
            nb["cells"][-1]["execution_count"] = 3
            book.write_text(json.dumps(nb))
            scenarios.verify_package(copied, require_approval=False)
            nb["cells"][-1]["source"] = ["print('modified')\n"]
            book.write_text(json.dumps(nb))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                scenarios.verify_package(copied, require_approval=False)

    def test_descriptive_mask_counts_zeros_outside_old_filter(self):
        shape=(2,2,2)
        f=np.array([[[10.,0.],[.01,0.]],[[1.,0.],[0.,0.]]])
        se=np.array([[[1.,0.],[.02,0.]],[[.1,0.],[0.,0.]]])
        fuel=np.zeros(shape);fuel.flat[:5]=1
        old=np.zeros(shape,dtype=bool);old[0,0,0]=True
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"fields.npz"
            np.savez(path,fuel_volume_fraction=fuel,fission_mean=f,fission_std_dev=se,
                     kappa_fission_mean=2*f,kappa_fission_std_dev=2*se,
                     relative_error_reporting_mask=old,z_edges_cm=np.array([0.,1.,2.]),
                     k_generation=np.ones(4),shannon_entropy=np.ones(4))
            d=runner._pilot_diagnostics(path,12.,10.,2)
        self.assertEqual(d["fuel_intersecting_voxels"],5)
        self.assertEqual(d["zero_fission_mean_voxels"],2)
        self.assertEqual(d["previous_reliability_filter_voxels"],1)
        self.assertEqual(d["fission_relative_mc_error"]["all_geometric_fuel"]["undefined_relative_error_voxels"],2)
        self.assertEqual(d["fission_relative_mc_error"]["outside_previous_filter"]["voxels"],4)
        self.assertEqual(d["duration_minus_estimate_seconds"],2.)
        self.assertAlmostEqual(sum(d["axial_fission_share"]),1.)

    def test_new_input_export_is_single_model_xml_without_transport(self):
        from reactor_pipeline.parameter_space import build_proposed
        controls=scenarios.load_space(P/"configs/v2_parameter_space_pilot_scope_v1.json")["nominal"]
        assembly=build_proposed(controls,batches=2,inactive=1,particles=100,seed=1,check_nuclear_data=False)
        with tempfile.TemporaryDirectory() as tmp:
            assembly.model.export_to_model_xml(path=Path(tmp)/"model.xml")
            self.assertEqual({p.name for p in Path(tmp).glob("*.xml")},{"model.xml"})

if __name__ == "__main__":
    unittest.main()

"""Read-only scientific training review of the frozen 256-scenario preview.

Writes separate review reports. It never edits the preview, source runs, or acceptance records.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import tempfile

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/v2_256_preview_v1"
OUTPUT = ROOT / "datasets/v2_256_training_review_v1"
LOCAL_INDEX = "ba7f6d5a371b5a8de8157356f8ef5d1c17cb0ed60accccfbc3075f46ae13f489"
KAGGLE_INDEX = "b47cef3ac4a48d66d75fa412b68d497d59c9daac52a403fe18133ad7ba683055"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percentiles(values):
    return {key: float(np.percentile(values, p)) for key, p in
            (("min", 0), ("median", 50), ("p95", 95), ("max", 100))}


def main(output=OUTPUT):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    manifest = read_json(DATA / "dataset_manifest.json")
    if manifest["scenario_count"] != 256 or manifest["state"] != "preview_not_accepted_for_training":
        raise ValueError("Expected frozen unaccepted 256-scenario preview")
    for name, expected in manifest["output_sha256"].items():
        if digest(DATA / name) != expected:
            raise ValueError(f"Preview output hash mismatch: {name}")
    scenarios = read_csv(DATA / "scenarios.csv")
    targets = read_csv(DATA / "targets_keff.csv")
    catalogue = read_json(ROOT / "scenarios/v2_students_portable_v1/catalogue_total_256.json")
    if digest(ROOT / "scenarios/v2_students_portable_v1/catalogue_total_256.json") != manifest["catalogue_sha256"]:
        raise ValueError("Catalogue hash mismatch")
    expected_ids = [x["scenario_id"] for x in catalogue["scenarios"]]
    if [x["scenario_id"] for x in scenarios] != expected_ids or [x["scenario_id"] for x in targets] != expected_ids:
        raise ValueError("Scenario or target alignment changed")
    splits = read_json(DATA / "splits.json")
    if any(set(splits[a]) & set(splits[b]) for a, b in
           (("train", "calibration"), ("train", "test"), ("calibration", "test"))):
        raise ValueError("Split overlap")
    if set().union(*(set(splits[x]) for x in ("train", "calibration", "test"))) != set(expected_ids):
        raise ValueError("Split coverage changed")
    provenance = {}
    for name in ("stage128_ogrenci04_provenance.csv", "stage256_ogrenci04_provenance.csv"):
        for row in read_csv(ROOT / "runs/beavrs_3d/audits" / name):
            provenance[row["scenario_id"]] = row
    decisions, axial, xy = [], [], []
    index_paths, required_metadata, grid_metadata, commits, log_threads = Counter(), set(), set(), Counter(), Counter()
    warning_signatures, statepoints_verified = Counter(), 0
    with np.load(DATA / "fields.npz", allow_pickle=False) as fields:
        if fields["kappa_fission_mean"].shape != (256, 20, 17, 17):
            raise ValueError("Wrong field shape")
        raw = fields["kappa_fission_mean"]
        raw_se = fields["kappa_fission_std_dev"]
        fission = fields["fission_mean"]
        fission_se = fields["fission_std_dev"]
        fuel = fields["fuel_volume_fraction"] > 0
        normalized = fields["target_normalized_kappa"]
        if not np.allclose(normalized.sum(axis=(1, 2, 3)), 1.0, rtol=0, atol=1e-10):
            raise ValueError("Normalized field sums changed")
        if not np.all(normalized[~fuel] == 0):
            raise ValueError("Normalized field outside geometric fuel")
        low = fuel & ((fission == 0) | (fission < 5 * fission_se) |
                      (fission < 1e-6 * fission.max(axis=(1, 2, 3))[:, None, None, None]))
        zero = fuel & (raw == 0)
        for index, (row, target) in enumerate(zip(scenarios, targets)):
            sid = row["scenario_id"]
            attempt = ROOT / row["source_attempt"]
            summary = read_json(attempt / "summary.json")
            resolved = read_json(attempt / "resolved_config.json")
            if summary["run_id"] != row["run_id"] or summary["scenario_id"] != sid:
                raise ValueError(f"Source summary identity changed: {sid}")
            if summary["k_effective"]["mean"] != float(target["k_mean"]) or (
                    summary["k_effective"]["mc_standard_error"] != float(target["k_mc_standard_error"])):
                raise ValueError(f"Source k changed: {sid}")
            nd = resolved["nuclear_data"]
            index_paths[(nd["cross_sections_xml_sha256"], nd["cross_sections_xml"])] += 1
            required_metadata.add(tuple(nd["required_libraries"]))
            grid_metadata.add(json.dumps(nd["temperature_grid_K"], sort_keys=True))
            if nd["cross_sections_xml_sha256"] != row["cross_sections_xml_sha256"]:
                raise ValueError(f"Nuclear index mismatch: {sid}")
            log = (attempt / "openmc.log").read_text(encoding="utf-8", errors="replace")
            commit = re.search(r"Commit Hash\s*\|\s*([0-9a-f]+)", log)
            threads = re.search(r"OpenMP Threads\s*\|\s*(\d+)", log)
            if commit is None or threads is None:
                raise ValueError(f"OpenMC log identity missing: {sid}")
            commits[commit.group(1)] += 1
            actual_threads = int(threads.group(1))
            log_threads[actual_threads] += 1
            for line in log.splitlines():
                if "WARNING:" in line:
                    warning_signatures[line.strip()] += 1
            if sid in provenance:
                entry = provenance[sid]
                if (entry["run_id"] != row["run_id"] or int(entry["actual_threads"]) != actual_threads or
                        entry["nuclear_index_sha256"] != row["cross_sections_xml_sha256"]):
                    raise ValueError(f"Platform provenance mismatch: {sid}")
            local_attempt = (ROOT / "runs/beavrs_3d/v2_groups" / row["package_id"] /
                             "experiments" / row["experiment_id"] / attempt.name)
            statepoints = sorted(local_attempt.glob("statepoint.*.h5"))
            if len(statepoints) > 1:
                raise ValueError(f"Multiple local statepoints: {sid}")
            sp_verified = False
            if statepoints:
                transfer = read_json(attempt.parents[3] / "transfer.json")
                relative_statepoint = ("group/experiments/" + row["experiment_id"] + "/" +
                                       attempt.name + "/" + statepoints[0].name)
                matching = [x for x in transfer.get("omitted_statepoints", [])
                            if x["relative_path"] == relative_statepoint]
                if (len(matching) != 1 or statepoints[0].stat().st_size != matching[0]["bytes"] or
                        digest(statepoints[0]) != matching[0]["sha256"]):
                    raise ValueError(f"Statepoint transfer SHA-256 differs: {sid}")
                with h5py.File(statepoints[0], "r") as statepoint:
                    actual_k = statepoint["k_combined"][()]
                    if not np.array_equal(actual_k, np.array([
                            float(target["k_mean"]), float(target["k_mc_standard_error"])])):
                        raise ValueError(f"Statepoint k differs: {sid}")
                    if not np.array_equal(statepoint["k_generation"][()], fields["k_generation"][index]):
                        raise ValueError(f"Statepoint k history differs: {sid}")
                    if not np.array_equal(statepoint["entropy"][()], fields["shannon_entropy"][index]):
                        raise ValueError(f"Statepoint entropy history differs: {sid}")
                    if (int(statepoint["n_batches"][()]) != 600 or
                            int(statepoint["n_inactive"][()]) != 300 or
                            int(statepoint["n_particles"][()]) != 80000 or
                            int(statepoint["seed"][()]) != int(row["seed"])):
                        raise ValueError(f"Statepoint budget differs: {sid}")
                statepoints_verified += 1
                sp_verified = True
            fuel_count = int(fuel[index].sum())
            zero_count = int(zero[index].sum())
            low_count = int(low[index].sum())
            measured_total = float(raw[index][fuel[index]].sum())
            if not np.isfinite(measured_total) or measured_total <= 0:
                raise ValueError(f"Nonpositive field normalization: {sid}")
            if not np.allclose(normalized[index], np.where(fuel[index], raw[index] / measured_total, 0),
                               rtol=0, atol=1e-12):
                raise ValueError(f"Normalized target differs: {sid}")
            positive = fuel[index] & (raw[index] > 0)
            relative = raw_se[index][positive] / raw[index][positive]
            k_history = fields["k_generation"][index]
            entropy = fields["shannon_entropy"][index]
            if len(k_history) != 600 or len(entropy) != 600:
                raise ValueError(f"History length differs: {sid}")
            early_k, late_k = float(k_history[300:350].mean()), float(k_history[550:600].mean())
            early_entropy, late_entropy = float(entropy[300:350].mean()), float(entropy[550:600].mean())
            decisions.append({
                "row": index, "scenario_id": sid, "split": row["split"], "owner": row["owner"],
                "stage": row["stage"], "run_id": row["run_id"],
                "insertion_percent": row["insertion_percent"],
                "keff_training_status": "REVIEW_REQUIRED",
                "field3d_training_status": "REVIEW_REQUIRED",
                "decision_reason": "completed and structurally valid; source convergence and model validation unaccepted",
                "nuclear_index_review": "alternate_Kaggle_index_HDF5_bytes_unverified"
                if row["cross_sections_xml_sha256"] == KAGGLE_INDEX else "same_XML_index_HDF5_bytes_unverified",
                "openmc_commit": commit.group(1), "requested_threads": row["threads"],
                "actual_threads": actual_threads, "statepoint_available_and_verified": sp_verified,
                "k_mean": target["k_mean"], "k_mc_standard_error": target["k_mc_standard_error"],
                "k_first_active_50_mean": early_k, "k_last_active_50_mean": late_k,
                "k_last_minus_first_active_50": late_k - early_k,
                "entropy_first_active_50_mean": early_entropy,
                "entropy_last_active_50_mean": late_entropy,
                "entropy_last_minus_first_active_50": late_entropy - early_entropy,
                "fuel_voxels": fuel_count, "zero_kappa_fuel_voxels": zero_count,
                "zero_kappa_fuel_fraction": zero_count / fuel_count,
                "low_signal_fuel_voxels": low_count, "low_signal_fuel_fraction": low_count / fuel_count,
                "low_signal_measured_kappa_share": float(raw[index][low[index]].sum() / measured_total),
                "positive_kappa_voxels": int(positive.sum()),
                "positive_kappa_relative_mc_error_median": float(np.median(relative)),
                "positive_kappa_relative_mc_error_p95": float(np.percentile(relative, 95)),
                "sum_voxel_std_dev_over_measured_sum_upper_bound": float(raw_se[index][fuel[index]].sum() / measured_total),
                "top_four_slices_zero_fuel_voxels": int(zero[index, -4:].sum()),
                "top_four_slices_measured_kappa_share": float(raw[index, -4:].sum() / measured_total),
            })
        for z in range(20):
            total_fuel = int(fuel[:, z].sum())
            axial.append({"z_index": z, "z_lower_cm_min": float(fields["z_edges_cm"][:, z].min()),
                          "z_upper_cm_max": float(fields["z_edges_cm"][:, z + 1].max()),
                          "fuel_voxels": total_fuel, "zero_kappa_fuel_voxels": int(zero[:, z].sum()),
                          "zero_fraction": float(zero[:, z].sum() / total_fuel),
                          "low_signal_fuel_voxels": int(low[:, z].sum()),
                          "low_signal_fraction": float(low[:, z].sum() / total_fuel),
                          "measured_kappa_share_across_all": float(raw[:, z].sum() / raw.sum())})
        for y in range(17):
            for x in range(17):
                n = int(fuel[:, :, y, x].sum())
                xy.append({"y_index": y, "x_index": x, "fuel_voxels": n,
                           "zero_kappa_fuel_voxels": int(zero[:, :, y, x].sum()),
                           "zero_fraction": float(zero[:, :, y, x].sum() / n) if n else "",
                           "low_signal_fuel_voxels": int(low[:, :, y, x].sum()),
                           "low_signal_fraction": float(low[:, :, y, x].sum() / n) if n else ""})
    if len(required_metadata) != 1 or len(grid_metadata) != 1 or commits != {
            "617d35a5063c57796b43428bc401e627d2011046": 256}:
        raise ValueError("Unexpected OpenMC or nuclear data metadata variation")
    if statepoints_verified != 120 or log_threads != {6: 245, 4: 11}:
        raise ValueError("Statepoint or actual thread count differs from central audit")
    splits_counts = {name: {"total": len(splits[name]),
                            "keff_ACCEPT": 0, "keff_REVIEW_REQUIRED": len(splits[name]),
                            "field3d_ACCEPT": 0, "field3d_REVIEW_REQUIRED": len(splits[name]),
                            "statepoint_verified": sum(r["statepoint_available_and_verified"] for r in decisions
                                                       if r["split"] == name),
                            "same_index": sum(r["nuclear_index_review"].startswith("same_XML") for r in decisions
                                              if r["split"] == name),
                            "no_low_signal_diagnostic": sum(r["low_signal_fuel_voxels"] == 0 for r in decisions
                                                            if r["split"] == name)}
                     for name in ("train", "calibration", "test")}
    candidate_counts = {
        "same_index_and_statepoint": {
            name: sum(r["split"] == name and r["statepoint_available_and_verified"] and
                      r["nuclear_index_review"].startswith("same_XML") for r in decisions)
            for name in ("train", "calibration", "test")
        },
        "same_index_statepoint_no_low_signal": {
            name: sum(r["split"] == name and r["statepoint_available_and_verified"] and
                      r["nuclear_index_review"].startswith("same_XML") and
                      r["low_signal_fuel_voxels"] == 0 for r in decisions)
            for name in ("train", "calibration", "test")
        },
    }
    insertion = np.array([float(r["insertion_percent"]) for r in decisions])
    zero_fraction = np.array([r["zero_kappa_fuel_fraction"] for r in decisions])
    low_fraction = np.array([r["low_signal_fuel_fraction"] for r in decisions])
    insertion_rows = []
    for lower, upper in ((0, 25), (25, 50), (50, 75), (75, 101)):
        selected = [r for r in decisions if lower <= float(r["insertion_percent"]) < upper]
        insertion_rows.append({
            "insertion_range_percent": f"[{lower},{upper})", "scenario_count": len(selected),
            "zero_fuel_fraction_median": float(np.median([r["zero_kappa_fuel_fraction"] for r in selected])),
            "low_signal_fraction_median": float(np.median([r["low_signal_fuel_fraction"] for r in selected])),
            "top_four_zero_fraction": sum(r["top_four_slices_zero_fuel_voxels"] for r in selected) /
                                     (len(selected) * 4 * 264),
        })
    summary = {
        "schema": "v2_256_training_review_v1", "source_preview_manifest_sha256": digest(DATA / "dataset_manifest.json"),
        "source_split_sha256": digest(DATA / "splits.json"),
        "decision_policy": "ACCEPT requires documented source convergence and physical/model validation; no new numeric threshold applied. Existing valid but unreviewed records are REVIEW_REQUIRED, not REJECT.",
        "decision_counts": {"keff": {"ACCEPT": 0, "REVIEW_REQUIRED": 256, "REJECT": 0, "NOT_ASSESSED": 0},
                            "field3d": {"ACCEPT": 0, "REVIEW_REQUIRED": 256, "REJECT": 0, "NOT_ASSESSED": 0}},
        "split_counts": splits_counts, "conditional_review_priority_counts": candidate_counts,
        "statepoints_verified_here": statepoints_verified,
        "statepoints_missing_here": 256 - statepoints_verified,
        "actual_threads": dict(log_threads), "openmc_commits": dict(commits),
        "nuclear_index_paths": [{"sha256": key[0], "path": key[1], "count": value}
                                for key, value in sorted(index_paths.items())],
        "required_library_list_variants": len(required_metadata),
        "temperature_grid_variants": len(grid_metadata),
        "nuclear_HDF5_byte_equivalence": "not_verified_across_source_machines",
        "warning_signatures": dict(warning_signatures),
        "k_mc_standard_error": percentiles([float(r["k_mc_standard_error"]) for r in decisions]),
        "fuel_voxels_per_scenario": percentiles([r["fuel_voxels"] for r in decisions]),
        "zero_fuel_voxels_total": sum(r["zero_kappa_fuel_voxels"] for r in decisions),
        "low_signal_voxels_total": sum(r["low_signal_fuel_voxels"] for r in decisions),
        "scenarios_with_any_zero_fuel_voxel": sum(r["zero_kappa_fuel_voxels"] > 0 for r in decisions),
        "scenarios_with_any_low_signal_voxel": sum(r["low_signal_fuel_voxels"] > 0 for r in decisions),
        "zero_fuel_fraction_per_scenario": percentiles(zero_fraction),
        "low_signal_fraction_per_scenario": percentiles(low_fraction),
        "low_signal_measured_kappa_share": percentiles([r["low_signal_measured_kappa_share"] for r in decisions]),
        "positive_kappa_relative_error_p95_per_scenario": percentiles(
            [r["positive_kappa_relative_mc_error_p95"] for r in decisions]),
        "early_late_active_k_absolute_difference": percentiles(
            [abs(r["k_last_minus_first_active_50"]) for r in decisions]),
        "early_late_active_entropy_absolute_difference": percentiles(
            [abs(r["entropy_last_minus_first_active_50"]) for r in decisions]),
        "insertion_zero_fraction_pearson_descriptive": float(np.corrcoef(insertion, zero_fraction)[0, 1]),
        "insertion_low_fraction_pearson_descriptive": float(np.corrcoef(insertion, low_fraction)[0, 1]),
        "top_four_slices_zero_fuel_fraction": float(
            sum(r["top_four_slices_zero_fuel_voxels"] for r in decisions) /
            (256 * 4 * 264)),
        "no_low_signal_scenarios": sum(r["low_signal_fuel_voxels"] == 0 for r in decisions),
        "recommendation": "No production ML training acceptance. Review convergence, nuclear data provenance, model validity, and 3D target quality before approval.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v2_256_training_review_", dir=output.parent) as temp:
        work = Path(temp)
        write_csv(work / "training_decisions.csv", decisions)
        write_csv(work / "axial_quality.csv", axial)
        write_csv(work / "xy_quality.csv", xy)
        write_csv(work / "insertion_quality.csv", insertion_rows)
        (work / "review_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
        text = (
            "# 256 V2 senaryosu: ML eğitimine kabul incelemesi\n\n"
            "Bu kayıt, kaynak veri setinden ayrıdır; kabul işareti veya yeni MC sonucu değildir.\n\n"
            "## Karar\n\n"
            "k ve 3B bağıl kappa-fission için ACCEPT 0, REVIEW_REQUIRED 256, REJECT 0. "
            "Tüm kayıtlar yapısal olarak geçerlidir; kaynak yakınsaması ve idealize demetin fiziksel/model doğrulaması "
            "senaryo bazında kabul edilmemiştir. Başarılı transport, bu kabulün yerine geçmez.\n\n"
            "## Kanıt ve sınırlama\n\n"
            f"Yerel statepoint ile k, geçmiş, entropi, seed ve bütçesi eşleşen: {statepoints_verified}/256. "
            "Diğer 136 büyük statepoint hafif teslimlere alınmamıştır; onların tally/k geçmişi kaynak statepoint'ten "
            "bu makinede bağımsız yeniden denetlenemez. Kaydedilmiş alan ve logları vardır.\n\n"
            "OpenMC commit'i tüm koşularda aynıdır. Nükleer veri için gerekli nüklid listesi ve sıcaklık gridleri "
            "metadata düzeyinde aynı; 11 Kaggle koşusunda yol yeniden yazıldığı için XML indeks hash'i farklıdır. "
            "Hiçbir kaynak makinedeki tüm HDF5 dosyalarının koşu anı byte hash'leri mevcut değildir. "
            "Bu nedenle kütüphanelerin fiziksel eşdeğerliği dosya adı veya indeks hash'iyle ilan edilemez. "
            "OpenMC loglarında Zr96 ve Cd106 olasılık tablosu negatif değer uyarıları kayıtlıdır.\n\n"
            f"Yakıt voxel'i: 5280/senaryo. Sıfır ölçümlü yakıt voxel'i toplamı: {summary['zero_fuel_voxels_total']}; "
            f"düşük sinyal toplamı: {summary['low_signal_voxels_total']}. "
            f"Üst dört dilimde sıfır payı: {summary['top_four_slices_zero_fuel_fraction']:.1%}. "
            "Düşük sinyal tanımı mevcut v2_runner tanısıdır; bir eğitim kabul eşiği değildir. "
            "Sıfır ölçüm fiziksel sıfır demek değildir. Eksenel ve XY ayrıntısı ayrı CSV dosyalarındadır.\n\n"
            "## Bölme ve ilk eğitim koşulu\n\n"
            "Mevcut 208/25/23 eğitim/kalibrasyon/test bölmesi değişmedi. Şu anda kabul edilmiş eğitim alt kümesi "
            "boştur. Yalnız yöntemi denemek için preview verisi kullanılırsa bu bilimsel eğitim kabulü diye "
            "sunulmamalı; test bölmesi model seçimi ve adaptif örnekleme dışında tutulmalı; 11 farklı indeksli "
            "senaryo ayrı işaretlenmelidir. Resmî ilk eğitim için kaynak yakınsama incelemesi, hedefe özgü "
            "uzaysal hata ölçütü, HDF5 kaynak kanıtı ve idealize modelin kullanım sınırı belgelenmelidir.\n\n"
            "Yeniden MC için otomatik liste üretilmedi: önce eksik statepoint ve HDF5 provenance istenmeli, "
            "ardından kaynak tanısı veya hedef çözünürlüğü yetersiz kalan belirli senaryolar seçilmelidir. "
            "Çubuklu üst dilimlerde ek tarihçe gerekebilir; mevcut sıfırları otomatik ret saymak doğru değildir.\n"
        )
        text += (
            "\n## Sayısal tanılar\n\n"
            f"Her koşu 600/300 batch ve 80.000 parçacık/nesil kullanır: 24 milyon aktif tarihçe. "
            f"k MC standart hatası medyanı {summary['k_mc_standard_error']['median']:.8f}, "
            f"aralığı {summary['k_mc_standard_error']['min']:.8f}–"
            f"{summary['k_mc_standard_error']['max']:.8f}. Önceden belgelenmiş 0,0002 önerisinin "
            f"üzerinde {sum(float(r['k_mc_standard_error']) > 0.0002 for r in decisions)} koşu vardır; "
            "bu öneri kabul kapısı olarak uygulanmadı. Aktif pencerenin ilk ve son 50 batch k ortalamaları "
            f"arasındaki mutlak fark medyanı {summary['early_late_active_k_absolute_difference']['median']:.6f}, "
            f"%95 yüzdeliği {summary['early_late_active_k_absolute_difference']['p95']:.6f}; "
            "pencere ortalamalarının korelasyonu/hatası modellenmediği için bu fark kaynak yakınsaması testi değildir.\n\n"
            f"Sıfır yakıt voxel oranının senaryo medyanı {summary['zero_fuel_fraction_per_scenario']['median']:.1%}, "
            f"%95 yüzdeliği {summary['zero_fuel_fraction_per_scenario']['p95']:.1%}; düşük sinyal için "
            f"aynı değerler {summary['low_signal_fraction_per_scenario']['median']:.1%} ve "
            f"{summary['low_signal_fraction_per_scenario']['p95']:.1%}. Düşük sinyalli voxel'lerin "
            f"ölçülen toplam kappa-fission payının medyanı "
            f"{summary['low_signal_measured_kappa_share']['median']:.4%}, en yükseği "
            f"{summary['low_signal_measured_kappa_share']['max']:.4%}; örneklenmemiş gerçek katkıya "
            "üst sınır değildir. Pozitif ölçümlü yakıt voxel'lerinde koşu başına göreli MC hatanın "
            f"%95 yüzdelik medyanı {summary['positive_kappa_relative_error_p95_per_scenario']['median']:.1%}. "
            "Çubuk giriş oranı ile sıfır/düşük sinyal oranlarının betimleyici Pearson korelasyonları "
            f"{summary['insertion_zero_fraction_pearson_descriptive']:.3f}/"
            f"{summary['insertion_low_fraction_pearson_descriptive']:.3f}; sekiz kontrol birlikte değiştiği "
            "için nedensel etki diye yorumlanmaz.\n\n"
            "## Koşullu ilk alt küme\n\n"
            "Aynı XML indeks hash'i ve bu makinede SHA-256/statepoint doğrulaması birlikte bulunan "
            "öncelikli inceleme kümesi eğitim/kalibrasyon/testte 91/9/9'dur. Bunun hiçbir üyesi "
            "henüz ACCEPT değildir; HDF5 byte eşdeğerliği ve yakınsama incelemesi gerekir. Bu kümede "
            "mevcut düşük sinyal tanısına hiç girmeyenler yalnız 11/2/1'dir ve kapsamlı 3B öğrenme "
            "için temsil gücü çok sınırlıdır. Bu alt kümeler mevcut split kimliklerini değiştirmez.\n"
        )
        (work / "review.md").write_text(text, encoding="utf-8")
        work.rename(output)
    return summary


if __name__ == "__main__":
    result = main()
    print(json.dumps({"decisions": result["decision_counts"], "splits": result["split_counts"],
                      "statepoints_verified": result["statepoints_verified_here"],
                      "output": str(OUTPUT)}, indent=2))





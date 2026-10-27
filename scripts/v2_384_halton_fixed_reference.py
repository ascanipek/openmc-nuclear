"""Copy prior fixed-23 comparison as a read-only reference beside repeated CV."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/comparison_256_vs_384_halton_v1/comparison.json"
OUT = ROOT / "reports/repeated_cv_256_vs_384_v1"


def main():
    target = OUT / "fixed23_reference.json"
    markdown = OUT / "fixed23_reference.md"
    if target.exists() or markdown.exists():
        raise FileExistsError("Fixed test reference already saved")
    source = json.loads(SOURCE.read_text())
    if not source["test_identity"]["same_ids"] or source["split_counts"]["test"] != 23:
        raise ValueError("Prior fixed test identity differs")
    record = {
        "schema": "beavrs_v2_fixed23_reference_v1",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "role": "previously recorded fixed-23 test comparison; no retraining",
        "not_combined_with_cv_ranking": True,
        "test_examined_previously": True,
        "keff_published_256": source["keff"]["published_256_xgboost_3_4_1"],
        "keff_same_env_256": source["keff"]["same_env_256_xgboost_3_2_0"],
        "keff_384": source["keff"]["halton_384_xgboost_3_2_0"],
        "field3d_256_relative_l2": source["field3d"]["baseline_256_mean_relative_l2"],
        "field3d_384_relative_l2": source["field3d"]["halton_384_mean_relative_l2"],
    }
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    markdown.write_text(
        "# Önceki sabit 23 test sonucu — ayrı referans\n\n"
        "Bu değerler mevcut karşılaştırma kaydından okunmuştur; yeni eğitim yapılmadı. "
        "23 test olgusu önceki analizlerde incelendiği için tamamen dokunulmamış nihai test değildir.\n\n"
        "| Metrik | 256 | 384 |\n| --- | ---: | ---: |\n"
        f"| k MAE (aynı yerel sürüm) | {record['keff_same_env_256']['mae']:.6f} | {record['keff_384']['mae']:.6f} |\n"
        f"| k RMSE (aynı yerel sürüm) | {record['keff_same_env_256']['rmse']:.6f} | {record['keff_384']['rmse']:.6f} |\n"
        f"| 3B göreli L2 | {record['field3d_256_relative_l2']:.6f} | {record['field3d_384_relative_l2']:.6f} |\n\n"
        "Bu sabit test ile tekrarlı CV'nin doğrulama popülasyonları ve eğitim havuzları farklıdır; "
        "ölçütlerini tek bir performans sıralamasında karıştırmayın.\n",
        encoding="utf-8")
    print(json.dumps({"source": str(SOURCE), "reference": str(target)}))


if __name__ == "__main__":
    main()


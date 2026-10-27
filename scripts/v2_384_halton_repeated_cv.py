"""Repeated paired 5x5 CV for frozen 233 vs 361 pools; no OpenMC transport."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn

sys.path.insert(0, "/tmp/openmc_xgboost_320")
import xgboost
from sklearn.metrics import r2_score
from sklearn.model_selection import KFold
from xgboost import XGBRegressor
from field3d_surrogate_v1 import FEATURES, field_metrics, make_model, rel_l2

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "datasets/v2_256_preview_v1"
DATA = ROOT / "datasets/v2_384_halton_v1"
OUT = ROOT / "reports/repeated_cv_256_vs_384_v1"
SEEDS = [20261027, 20261028, 20261029, 20261030, 20261031]
K_PARAMS = {"objective": "reg:squarederror", "tree_method": "hist",
            "random_state": 20261025, "n_jobs": min(4, os.cpu_count() or 1),
            "subsample": 1.0, "colsample_bytree": 1.0,
            "n_estimators": 400, "max_depth": 2, "learning_rate": 0.05}
FIELD_PARAMS = {"max_depth": 4, "n_estimators": 120, "learning_rate": 0.05}
RANK = 12
SHAPE = (20, 17, 17)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sources():
    if OUT.exists():
        raise FileExistsError(OUT)
    manifest = json.loads((DATA / "dataset_manifest.json").read_text())
    if manifest["scenario_count"] != 384 or manifest["branch"] != "halton":
        raise ValueError("384 dataset branch/size mismatch")
    for name, digest in manifest["old_dataset_sha256"].items():
        if sha(OLD / name) != digest:
            raise ValueError(f"Frozen 256 changed: {name}")
    for name, digest in manifest["output_sha256"].items():
        if sha(DATA / name) != digest:
            raise ValueError(f"384 data changed: {name}")
    old_rows = pd.read_csv(OLD / "scenarios.csv")
    rows = pd.read_csv(DATA / "scenarios.csv")
    old_targets = pd.read_csv(OLD / "targets_keff.csv")
    targets = pd.read_csv(DATA / "targets_keff.csv")
    old_split = json.loads((OLD / "splits.json").read_text())
    new_split = json.loads((DATA / "splits.json").read_text())
    if not old_rows.equals(rows.iloc[:256].reset_index(drop=True)):
        raise ValueError("First 256 scenario inputs/IDs changed")
    if not old_targets.equals(targets.iloc[:256].reset_index(drop=True)):
        raise ValueError("First 256 k/MC errors changed")
    if rows.scenario_id.nunique() != 384 or not rows.scenario_id.equals(targets.scenario_id):
        raise ValueError("Duplicate or reordered targets")
    if (new_split["train"][:208] != old_split["train"] or
            new_split["calibration"] != old_split["calibration"] or
            new_split["test"] != old_split["test"] or
            len(new_split["train"]) != 336 or len(new_split["test"]) != 23 or
            len(new_split["calibration"]) != 25):
        raise ValueError("Frozen split changed")
    role = {sid: label for label in ("train", "calibration", "test") for sid in new_split[label]}
    if len(role) != 384 or any(role[sid] != label for sid, label in zip(rows.scenario_id, rows.split)):
        raise ValueError("Row/split mismatch")
    if not np.isfinite(rows[FEATURES].to_numpy(float)).all():
        raise ValueError("Non-finite physical input")
    k_report = json.loads((ROOT / "reports/keff_384_halton_v1/training_report.json").read_text())
    field_report = json.loads((ROOT / "reports/field3d_384_halton_v1/training_report.json").read_text())
    old_field = json.loads((ROOT / "reports/field3d_surrogate_v1/training_report.json").read_text())
    if ({key: k_report["hyperparameters"][key] for key in ("n_estimators", "max_depth", "learning_rate")} !=
            {key: K_PARAMS[key] for key in ("n_estimators", "max_depth", "learning_rate")} or
            field_report["rank"] != RANK or field_report["hyperparameters"] != FIELD_PARAMS or
            old_field["selected"]["rank"] != RANK or old_field["selected"]["parameters"] != FIELD_PARAMS):
        raise ValueError("Recorded model settings differ")
    with np.load(OLD / "fields.npz", allow_pickle=False) as previous, np.load(DATA / "fields.npz", allow_pickle=False) as current:
        if set(previous.files) != set(current.files):
            raise ValueError("3D array keys differ")
        for key in previous.files:
            if not np.array_equal(previous[key], current[key][:256]):
                raise ValueError(f"Frozen 3D array changed: {key}")
        target = current["target_normalized_kappa"].copy()
        fuel = current["fuel_volume_fraction"] > 0
        fission = current["fission_mean"].copy()
        fission_se = current["fission_std_dev"].copy()
        raw_se = current["kappa_fission_std_dev"].copy()
    if (target.shape != (384, *SHAPE) or not np.isfinite(target).all() or
            np.any(target < 0) or np.any(target[~fuel] != 0) or
            not np.allclose(target.sum(axis=(1, 2, 3)), 1, atol=1e-10, rtol=0) or
            not np.all(fuel.sum(axis=(1, 2, 3)) == 5280)):
        raise ValueError("3D axis, mask, or normalization mismatch")
    base_ids = set(old_split["train"]) | set(old_split["calibration"])
    test_ids = set(old_split["test"])
    halton_ids = set(rows.iloc[256:].scenario_id)
    if len(base_ids) != 233 or len(halton_ids) != 128 or base_ids & test_ids or halton_ids & (base_ids | test_ids):
        raise ValueError("Pool identity mismatch")
    base = np.array([i for i, sid in enumerate(rows.scenario_id) if sid in base_ids], dtype=int)
    added = np.arange(256, 384, dtype=int)
    extended = np.r_[base, added]
    if len(base) != 233 or len(extended) != 361:
        raise ValueError("Pool size mismatch")
    low = fuel & ((fission == 0) | (fission < 5*fission_se) |
                  (fission < 1e-6*fission.max(axis=(1, 2, 3))[:, None, None, None]))
    return rows, targets, target, fuel, low, raw_se, base, extended, added, manifest


def fold_plan(rows, base, extended, added):
    memberships, plans = [], {}
    for repeat, seed in enumerate(SEEDS, 1):
        base_fold = np.empty(len(base), dtype=int)
        splitter = KFold(n_splits=5, shuffle=True, random_state=seed)
        for fold, (_, val_local) in enumerate(splitter.split(base)):
            base_fold[val_local] = fold
        halton_fold = np.empty(len(added), dtype=int)
        permutation = np.random.default_rng(seed + 100000).permutation(len(added))
        halton_fold[permutation] = np.arange(len(added)) % 5
        extended_fold = np.r_[base_fold, halton_fold]
        for arm, indices, assigned in (("A_233", base, base_fold), ("B_361", extended, extended_fold)):
            if len(indices) != len(set(indices)) or any(int((assigned == f).sum()) == 0 for f in range(5)):
                raise ValueError("Bad fold plan")
            plans[(repeat, arm)] = (indices, assigned)
            for local, index in enumerate(indices):
                memberships.append({"repeat": repeat, "seed": seed, "arm": arm,
                                    "scenario_id": rows.scenario_id.iloc[index],
                                    "source": "halton_128" if index >= 256 else "initial_233",
                                    "validation_fold": int(assigned[local])})
        if not np.array_equal(extended_fold[:len(base)], base_fold):
            raise ValueError("Common scenario fold pairing failed")
        if max(np.bincount(halton_fold)) - min(np.bincount(halton_fold)) > 1:
            raise ValueError("Halton fold distribution not balanced")
    return plans, pd.DataFrame(memberships)


def summarize(frame):
    actual, pred = frame.k_true.to_numpy(float), frame.k_pred.to_numpy(float)
    return {
        "count": len(frame),
        "k_mae": float(np.mean(np.abs(pred-actual))),
        "k_rmse": float(np.sqrt(np.mean((pred-actual)**2))),
        "k_r2": float(r2_score(actual, pred)),
        "k_max_absolute_error": float(np.max(np.abs(pred-actual))),
        "k_side_mismatch": int(((pred >= 1) != (actual >= 1)).sum()),
        "field_relative_l2_mean": float(frame.field_relative_l2.mean()),
        "field_half_l1_mean": float(frame.field_half_l1.mean()),
        "field_axial_half_l1_mean": float(frame.field_axial_half_l1.mean()),
        "pca_relative_l2_mean": float(frame.pca_relative_l2.mean()),
        "negative_fuel_voxel_fraction": float(frame.negative_fuel_voxels.sum() / frame.fuel_voxels.sum()),
        "post_relative_l2_mean": float(frame.post_relative_l2.mean()),
    }


def main():
    start = time.monotonic()
    rows, targets, target, fuel, low, raw_se, base, extended, added, source_manifest = verify_sources()
    plans, membership = fold_plan(rows, base, extended, added)
    X = rows[FEATURES].to_numpy(float)
    k_true = targets.k_mean.to_numpy(float)
    k_se = targets.k_mc_standard_error.to_numpy(float)
    y = target.reshape(384, 5780, order="C")
    pools = {"A_233": base, "B_361": extended}
    predictions = {
        name: np.full((len(SEEDS), len(indices), *SHAPE), np.nan, dtype=np.float64)
        for name, indices in pools.items()
    }
    oof_rows, fold_sizes = [], []
    for repeat, seed in enumerate(SEEDS, 1):
        for fold in range(5):
            for arm in ("A_233", "B_361"):
                indices, assignment = plans[(repeat, arm)]
                fit_local = np.flatnonzero(assignment != fold)
                val_local = np.flatnonzero(assignment == fold)
                fit, val = indices[fit_local], indices[val_local]
                if set(rows.scenario_id.iloc[fit]) & set(rows.scenario_id.iloc[val]) or np.any(rows.iloc[np.r_[fit, val]].split == "test"):
                    raise ValueError("Fold leakage or test inclusion")
                fold_sizes.append({
                    "repeat": repeat, "seed": seed, "fold": fold, "arm": arm,
                    "training_count": len(fit), "validation_count": len(val),
                    "validation_old_count": int((val < 256).sum()),
                    "validation_halton_count": int((val >= 256).sum()),
                })
                k_model = XGBRegressor(**K_PARAMS)
                k_model.fit(X[fit], k_true[fit])
                k_pred = k_model.predict(X[val]).astype(float)
                mean = y[fit].mean(axis=0)
                _, _, basis = np.linalg.svd(y[fit]-mean, full_matrices=False)
                axes = basis[:RANK]
                coef_fit = (y[fit]-mean) @ axes.T
                field_model = make_model("XGBoost", FIELD_PARAMS)
                field_model.fit(X[fit], coef_fit)
                field_pred = (mean + field_model.predict(X[val]) @ axes).reshape(-1, *SHAPE)
                predictions[arm][repeat-1, val_local] = field_pred
                pca_val = (mean + (y[val]-mean) @ axes.T @ axes).reshape(-1, *SHAPE)
                mask = fuel[val]
                post = np.where(mask, np.maximum(field_pred, 0), 0)
                denominator = post.sum(axis=(1, 2, 3))
                if np.any(denominator <= 0):
                    raise ValueError("Postprocessed field has no fuel signal")
                post = post / denominator[:, None, None, None]
                metrics = field_metrics(target[val], field_pred, mask, low[val], raw_se[val])
                post_metrics = field_metrics(target[val], post, mask, low[val], raw_se[val])
                pca_err = rel_l2(target[val], pca_val, mask)
                for position, index in enumerate(val):
                    row = metrics.iloc[position]
                    oof_rows.append({
                        "repeat": repeat, "seed": seed, "fold": fold, "arm": arm,
                        "scenario_id": rows.scenario_id.iloc[index],
                        "source": "halton_128" if index >= 256 else "initial_233",
                        "insertion_percent": float(rows.insertion_percent.iloc[index]),
                        "k_true": float(k_true[index]), "k_mc_standard_error": float(k_se[index]),
                        "k_pred": float(k_pred[position]),
                        "k_absolute_error": float(abs(k_pred[position]-k_true[index])),
                        "k_side_mismatch": int((k_pred[position] >= 1) != (k_true[index] >= 1)),
                        "field_relative_l2": float(row.relative_l2_fuel),
                        "field_half_l1": float(row.half_l1_share_error_raw),
                        "field_axial_half_l1": float(row.axial_half_l1_share_error_raw),
                        "pca_relative_l2": float(pca_err[position]),
                        "negative_fuel_voxels": int(row.negative_fuel_voxels),
                        "fuel_voxels": int(mask[position].sum()),
                        "post_relative_l2": float(post_metrics.relative_l2_fuel.iloc[position]),
                        "measured_zero_fuel_voxels": int(np.count_nonzero(mask[position] & (target[val[position]] == 0))),
                        "low_signal_fuel_voxels": int(low[val[position]].sum()),
                    })
                print(f"repeat={repeat} fold={fold} arm={arm} fit={len(fit)} val={len(val)} "
                      f"k_mae={np.mean(np.abs(k_pred-k_true[val])):.5g} "
                      f"field_l2={metrics.relative_l2_fuel.mean():.5g}", flush=True)
    for arm, array in predictions.items():
        if not np.isfinite(array).all():
            raise ValueError(f"Incomplete OOF field predictions: {arm}")
    oof = pd.DataFrame(oof_rows)
    if len(oof) != 5*(233+361) or oof.duplicated(["arm", "repeat", "scenario_id"]).any():
        raise ValueError("OOF coverage mismatch")
    for arm, n in (("A_233", 233), ("B_361", 361)):
        for repeat in range(1, 6):
            if len(oof[(oof.arm == arm) & (oof.repeat == repeat)]) != n:
                raise ValueError("OOF scenario missing")
    a = oof[oof.arm == "A_233"].set_index(["repeat", "scenario_id"]).sort_index()
    common_b = oof[(oof.arm == "B_361") & (oof.source == "initial_233")].set_index(["repeat", "scenario_id"]).sort_index()
    if not a.index.equals(common_b.index) or not (a.fold == common_b.fold).all():
        raise ValueError("Paired common OOF keys/folds differ")
    summaries = []
    for repeat in range(1, 6):
        for label, subset in (("A_common233", oof[(oof.arm == "A_233") & (oof.repeat == repeat)]),
                              ("B_common233", oof[(oof.arm == "B_361") & (oof.repeat == repeat) & (oof.source == "initial_233")]),
                              ("B_all361", oof[(oof.arm == "B_361") & (oof.repeat == repeat)])):
            summaries.append({"repeat": repeat, "seed": SEEDS[repeat-1], "evaluation": label, **summarize(subset)})
    repeats = pd.DataFrame(summaries)
    metrics = ["k_mae", "k_rmse", "k_r2", "k_max_absolute_error", "k_side_mismatch",
               "field_relative_l2_mean", "field_half_l1_mean",
               "field_axial_half_l1_mean", "pca_relative_l2_mean",
               "negative_fuel_voxel_fraction", "post_relative_l2_mean"]
    comparison = repeats.pivot(index="repeat", columns="evaluation", values=metrics)
    paired = pd.DataFrame({"repeat": np.arange(1, 6), "seed": SEEDS})
    for metric in metrics:
        paired[f"A_{metric}"] = comparison[(metric, "A_common233")].to_numpy()
        paired[f"B_common_{metric}"] = comparison[(metric, "B_common233")].to_numpy()
        paired[f"new_minus_old_{metric}"] = paired[f"B_common_{metric}"]-paired[f"A_{metric}"]
        paired[f"B_all361_{metric}"] = comparison[(metric, "B_all361")].to_numpy()
    
    per_scenario = (
        a[["k_pred", "k_absolute_error", "field_relative_l2", "field_half_l1", "field_axial_half_l1"]]
        .groupby(level="scenario_id").mean().add_prefix("A_")
        .join(common_b[["k_pred", "k_absolute_error", "field_relative_l2", "field_half_l1", "field_axial_half_l1"]]
              .groupby(level="scenario_id").mean().add_prefix("B_"))
        .reset_index()
    )
    per_scenario["k_error_new_minus_old"] = per_scenario.B_k_absolute_error - per_scenario.A_k_absolute_error
    per_scenario["field_l2_new_minus_old"] = per_scenario.B_field_relative_l2 - per_scenario.A_field_relative_l2
    overview = []
    for metric in metrics:
        for label, col in (("A_common233", f"A_{metric}"),
                           ("B_common233", f"B_common_{metric}"),
                           ("B_all361", f"B_all361_{metric}")):
            overview.append({"metric": metric, "evaluation": label,
                             "mean_over_5_repeats": float(paired[col].mean()),
                             "sd_over_5_repeats": float(paired[col].std(ddof=1))})
        delta = paired[f"new_minus_old_{metric}"]
        overview.append({"metric": metric, "evaluation": "B_common_minus_A_paired",
                         "mean_over_5_repeats": float(delta.mean()),
                         "sd_over_5_repeats": float(delta.std(ddof=1))})
    summary_table = pd.DataFrame(overview)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".repeated_cv_work_", dir=OUT.parent) as temporary:
        work = Path(temporary)
        membership.to_csv(work / "fold_membership.csv", index=False)
        pd.DataFrame(fold_sizes).to_csv(work / "fold_sizes.csv", index=False)
        oof.to_csv(work / "oof_predictions_and_metrics.csv", index=False)
        repeats.to_csv(work / "repeat_metrics.csv", index=False)
        paired.to_csv(work / "paired_repeat_differences.csv", index=False)
        per_scenario.to_csv(work / "paired_common233_by_scenario.csv", index=False)
        summary_table.to_csv(work / "metric_summary.csv", index=False)
        for arm, indices in pools.items():
            np.savez_compressed(
                work / f"field_oof_{arm}.npz",
                scenario_id=np.asarray(rows.scenario_id.iloc[indices].tolist(), dtype="U64"),
                repeat_seed=np.asarray(SEEDS, dtype=np.int64),
                truth=target[indices],
                predicted_raw=predictions[arm],
                fuel_mask=fuel[indices],
                axis_order=np.array(["repeat", "sample", "z", "y", "x"]),
            )
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        for ax, metric, title in zip(axes, ("k_mae", "field_relative_l2_mean"),
                                     ("k MAE", "3D relative L2")):
            for label, style in (("A_common233", "o-"), ("B_common233", "s-"), ("B_all361", "^--")):
                data = repeats[repeats.evaluation == label]
                ax.plot(data.repeat, data[metric], style, label=label)
            ax.set(xlabel="Repeat", ylabel=title, xticks=np.arange(1, 6))
            ax.grid(True, alpha=.25); ax.legend(fontsize=7)
        fig.tight_layout(); fig.savefig(work / "repeat_metrics.png", dpi=150); plt.close(fig)
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].scatter(per_scenario.A_k_absolute_error, per_scenario.B_k_absolute_error, alpha=.5)
        axes[1].scatter(per_scenario.A_field_relative_l2, per_scenario.B_field_relative_l2, alpha=.5)
        for ax, title in zip(axes, ("k absolute error", "3D relative L2")):
            limit = max(ax.get_xlim()[1], ax.get_ylim()[1])
            ax.plot([0, limit], [0, limit], "k--", linewidth=1)
            ax.set(xlabel="A: 233 pool", ylabel="B: 361 pool", title=title)
            ax.grid(True, alpha=.25)
        fig.tight_layout(); fig.savefig(work / "paired_common233.png", dpi=150); plt.close(fig)
        report = {
            "schema": "beavrs_v2_repeated_cv_256_vs_384_v1",
            "scientific_status": "PROVISIONAL_EXPLORATORY; no physical/statistical acceptance",
            "design": {"repeats": 5, "folds_each": 5, "seeds": SEEDS,
                       "common_fold_policy": "KFold over frozen 233; same old scenario validation fold in A and B",
                       "halton_fold_policy": "seeded permutation then round-robin balanced across B validation folds",
                       "pool_A": "208 old train + 25 old calibration = 233",
                       "pool_B": "same 233 + 128 Halton = 361",
                       "excluded": "same frozen 23 old test cases",
                       "validation_exposure": "each scenario exactly once per repeat per relevant arm",
                       "fold_fit_policy": "all models and PCA refit from scratch on fold training only",
                       "calibration": "none; no outer validation target used for tuning"},
            "model_settings": {"features": FEATURES, "k": K_PARAMS,
                               "field": {"pca_rank": RANK, "xgboost": FIELD_PARAMS}},
            "paired_comparison": "A and B OOF for identical 233 scenario IDs and validation fold per repeat",
            "full_B_comparison": "B_all361 describes a different validation population; do not interpret as paired 233",
            "aggregate_metric_summary": summary_table.to_dict("records"),
            "paired_common233_scenario_count": 233,
            "source_dataset_manifest_sha256": sha(DATA / "dataset_manifest.json"),
            "source_old_splits_sha256": sha(OLD / "splits.json"),
            "source_new_splits_sha256": sha(DATA / "splits.json"),
            "source_quality": {
                "original_training_acceptance": "not_granted",
                "halton_training_acceptance": "not_granted",
                "alternate_nuclear_index_cases": 11,
                "zero_and_low_signal": "retained; see quality_summary.json in prior comparison report",
                "source_convergence": "not_assessed",
            },
            "software": {"python": platform.python_version(), "numpy": np.__version__,
                         "pandas": pd.__version__, "sklearn": sklearn.__version__,
                         "xgboost": xgboost.__version__},
            "runtime_seconds": time.monotonic()-start,
            "warnings": [
                "Five repeated OOF predictions of the same physical scenario are correlated; repeat-level summaries are the unit of variability.",
                "A and B training sizes and B validation population differ. Paired old-scenario comparison is primary.",
                "Old 23 test cases remain excluded from all CV, but were examined in prior work and are not a pristine final test.",
                "Halton outcomes must not enter future adaptive selection or its tuning.",
                "No new independent physical validation or nuclear HDF5 byte-equivalence review is performed.",
            ],
        }
        (work / "reproducibility_manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# Tekrarlı 5×5 CV: 233 başlangıç ve 361 Halton havuzu", "",
                 "**PROVISIONAL / EXPLORATORY.** OpenMC simülasyonu yapılmadı.",
                 "Eski 23 test olgusu CV'ye alınmadı. Ortak 233 olgunun fold üyeliği A ve B'de her tekrarda aynıdır.",
                 "128 Halton olgusu B doğrulama fold'larına 25–26 adet olacak biçimde dengeli dağıtıldı.",
                 "PCA her fold'da yalnız eğitim bölümünde öğrenildi. Sabit XGBoost ayarları kullanıldı.",
                 "", "| Ölçüt | A ortak 233 (ortalama±SS) | B ortak 233 (ortalama±SS) | B tüm 361 (ortalama±SS) |",
                 "| --- | ---: | ---: | ---: |"]
        for metric in ("k_mae", "k_rmse", "field_relative_l2_mean", "field_half_l1_mean",
                       "field_axial_half_l1_mean", "pca_relative_l2_mean"):
            values = {row["evaluation"]: row for row in overview if row["metric"] == metric}
            def render(name):
                row = values[name]
                return f"{row['mean_over_5_repeats']:.6g} ± {row['sd_over_5_repeats']:.3g}"
            lines.append(f"| {metric} | {render('A_common233')} | {render('B_common233')} | {render('B_all361')} |")
        lines += ["", "Ana veri miktarı karşılaştırması B ortak 233 ile A ortak 233 arasındaki eşleştirilmiş OOF farkıdır.",
                  "B tüm 361 sonucu daha farklı bir doğrulama popülasyonunu içerdiği için ayrı yorumlanır.",
                  "Beş tekrardaki aynı senaryonun tahminleri bağımsız örnek sayılmaz.",
                  "Farklı fold eğitim/validation sayıları veri miktarı etkisiyle birlikte yorumlanmalıdır.",
                  "Önceki sabit 23 test sonucunu değiştirmedik; doğrudan CV metrikleriyle tek bir sıralamada birleştirmiyoruz.",
                  "Sıfır/düşük sinyalli voxel, alternatif nükleer indeks ve kaynak yakınsaması uyarıları sürmektedir.",
                  "Gelecekteki adaptif seçim, yeni 128 Halton fiziksel sonucunu kullanmamalıdır.",
                  ""]
        (work / "README.md").write_text("\n".join(lines), encoding="utf-8")
        report["output_sha256"] = {p.name: sha(p) for p in work.iterdir() if p.is_file() and p.name != "reproducibility_manifest.json"}
        (work / "reproducibility_manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        work.rename(OUT)
    print(json.dumps({
        "output": str(OUT),
        "A_k_mae": float(repeats[repeats.evaluation == "A_common233"].k_mae.mean()),
        "B_common_k_mae": float(repeats[repeats.evaluation == "B_common233"].k_mae.mean()),
        "B_all_k_mae": float(repeats[repeats.evaluation == "B_all361"].k_mae.mean()),
        "A_field_l2": float(repeats[repeats.evaluation == "A_common233"].field_relative_l2_mean.mean()),
        "B_common_field_l2": float(repeats[repeats.evaluation == "B_common233"].field_relative_l2_mean.mean()),
        "B_all_field_l2": float(repeats[repeats.evaluation == "B_all361"].field_relative_l2_mean.mean()),
        "seconds": time.monotonic()-start,
    }))


if __name__ == "__main__":
    main()



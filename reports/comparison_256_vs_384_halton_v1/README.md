# 256 → 384 Halton comparison

PROVISIONAL / EXPLORATORY. No physical or training acceptance.
Same original 23 test IDs. Original 208/25/23 split is frozen; 128 Halton cases join train only.
The original 23 test cases were examined previously, so this is not a final untouched test.

| Metric | 256 | 384 | New − old | Change |
| --- | ---: | ---: | ---: | ---: |
| k_mae | 0.0123072 | 0.00739859 | -0.00490861 | -39.88% |
| k_rmse | 0.0156623 | 0.00854302 | -0.00711931 | -45.45% |
| k_max_absolute_error | 0.0374425 | 0.0152996 | -0.0221429 | -59.14% |
| field3d_relative_l2 | 0.048522 | 0.0419263 | -0.00659574 | -13.59% |
| field3d_half_l1_share | 0.0240892 | 0.0205037 | -0.00358551 | -14.88% |
| field3d_axial_half_l1_share | 0.0233507 | 0.0197556 | -0.00359506 | -15.40% |

Primary k comparison retrains the 256 XGBoost model in the same local 3.2.0 runtime as the 384 model.
Published 256 k MAE/RMSE (XGBoost 3.4.1): 0.0123072 / 0.0156623.
Criticality-side mistakes around k=1: 3 → 0 (descriptive; not a safety classification).

## Control insertion bands

| Band | n | k MAE 256 → 384 | field L2 256 → 384 |
| --- | ---: | ---: | ---: |
| low | 7 | 0.011265 → 0.0095927 | 0.044002 → 0.039398 |
| middle | 10 | 0.0086803 → 0.0060655 | 0.044858 → 0.037942 |
| high | 6 | 0.019568 → 0.0070606 | 0.059901 → 0.051516 |

## Limits

Sparse region means the upper quartile of the 23 test cases by eight-dimensional normalized nearest-neighbor distance to the original 208 training cases. It is descriptive, not a validated domain threshold.
Pitch changes physical x/y coordinates even when array indices match. The 3D target is relative kappa-fission, an approximation to fission energy generation.
Raw negative 3D predictions and a separate clipped/renormalized comparison are recorded in the 3D report.
The 11 alternate nuclear-index cases in the original 256 still need HDF5 byte-equivalence review.
The two failed Halton-03 attempts were excluded, recorded, and replaced by its one completed attempt.
No adaptive scenario selection should use the 128 Halton physical results.

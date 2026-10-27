# 3B relative kappa-fission, Halton 384 branch

PROVISIONAL / EXPLORATORY. Frozen 256 split; 128 new Halton cases enter train only. 12-component PCA is fit inside each of five training folds and once on the full 336 training cases. XGBoost depth=4, 120 trees, learning_rate=0.05. Raw predictions and separate clipped/renormalized comparison are retained. Same 23 previously examined test cases. Target is a fission energy generation approximation, not absolute reactor power. See training_report.json, test_case_metrics.csv and the XY/XZ/axial figures.

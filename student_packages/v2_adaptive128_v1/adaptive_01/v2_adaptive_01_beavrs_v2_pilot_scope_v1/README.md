# v2_adaptive_01_beavrs_v2_pilot_scope_v1

Atanmis senaryo: 32. 01_calistir.ipynb Run All onaydan sonra bagimsiz WSL iscisini baslatir. 02_sonuclari_incele.ipynb salt okur. Taslak paket uretim icin kapalidir.

ADAPTIVE-01: first 32 only; selection evidence at reports/adaptive_selection_v1/selection_report.json (SHA256 527fb6150677a580a0b17499fe674915ec5249f1457cbbf508c2d7fecd934197).
Equal transport settings to Halton: 600/300 batches, 80,000 particles/generation, one generation/batch, six threads; 24-hour group ceiling. Completed is not physical or statistical acceptance.

WSL openmc-proje environment, from project root:
- Status: python scripts/v2_student_production.py status student_packages/v2_adaptive128_v1/adaptive_01/v2_adaptive_01_beavrs_v2_pilot_scope_v1
- Stop: python scripts/v2_student_production.py stop student_packages/v2_adaptive128_v1/adaptive_01/v2_adaptive_01_beavrs_v2_pilot_scope_v1
- Resume after explicit review: python scripts/v2_student_production.py resume student_packages/v2_adaptive128_v1/adaptive_01/v2_adaptive_01_beavrs_v2_pilot_scope_v1
- Results: open 02_sonuclari_incele.ipynb, read-only.

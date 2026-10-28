# Adaptive 02 sonrası model karşılaştırması

**PROVISIONAL_EXPLORATORY.** Fiziksel, istatistiksel ve eğitim kabulü verilmedi.

Aynı 23 eski test senaryosu; 208 → 240 → 272 eğitim. Kalibrasyon 25 değişmedi.
PCA ve modeller yalnız eğitim fold'unda fit edildi; hiperparametre araması yapılmadı.

| Aşama | Eğitim | k MAE | k RMSE | k max abs | k=1 uyuşmazlık | 3B L2 ort. | 3B L2 P95 | Negatif voxel oranı | Kırpılmış 3B L2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| initial_256 | 208 | 0.012307 | 0.015662 | 0.037443 | 3 | 0.048522 | 0.066185 | 0.201507 | 0.048835 |
| adaptive01_288 | 240 | 0.009032 | 0.011290 | 0.024404 | 0 | 0.046238 | 0.064531 | 0.178162 | 0.046586 |
| adaptive02_320 | 272 | 0.011058 | 0.012766 | 0.025112 | 0 | 0.046716 | 0.069098 | 0.165769 | 0.046930 |

Negatif enerji payı, toplam normalizasyon, giriş bantları ve test bazlı metrikler JSON/CSV'dedir.
Kırpma ve yeniden normalizasyon yalnız ayrı değerlendirmedir; ham tahminler korunmuştur.
Adaptive 02 statepoint'leri öğrenci kaynak makinesindedir. Kaynak yakınsaması ve veri eşdeğerliği açık konulardır.
Bu 23 test senaryosu önceki çalışmalarda incelendi; yeni dış doğrulama değildir.

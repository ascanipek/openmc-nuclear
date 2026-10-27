# ADAPTIVE-01 sonrası ilk vekil model karşılaştırması

**PROVISIONAL / EXPLORATORY.** Fiziksel, kaynak yakınsaması ve eğitim veri kabulü tamamlanmadı.

- İlk 256 kayıt aynen korundu; eğitim 208 → 240, kalibrasyon 25, test 23.
- Sabit hiperparametreler; 5-fold yalnız eğitim içi CV; PCA her fold eğitiminde ayrı fit. Kalibrasyon ve test model seçimi için kullanılmadı.
- Aynı 23 test daha önceki çalışmalarda incelendi; tamamen yeni bağımsız doğrulama değildir.

| Test metriği | 256 aynı ortam | 256 + Adaptive 01 | Fark | Değişim |
|---|---:|---:|---:|---:|
| k_mae | 0.012307 | 0.009032 | -0.003275 | -26.6% |
| k_rmse | 0.015662 | 0.011290 | -0.004372 | -27.9% |
| field_relative_l2 | 0.048522 | 0.046238 | -0.002284 | -4.7% |

Ham 3B tahminler ayrıca negatif voxel ve toplam normalize pay açısından raporlandı; kırpma/yeniden normalizasyon ayrı gösterilir.

Kaynak kütüphane eşdeğerliği, düşük sinyalli voxel'ler ve kaynak yakınsaması inceleme gerektirir.

| Aynı testte fiziksel tutarlılık | 256 | 288 |
|---|---:|---:|
| raw_half_l1_share_error_mean | 0.024089 | 0.023282 |
| raw_axial_half_l1_share_error_mean | 0.023351 | 0.022459 |
| raw_upper4_low_signal_absolute_share_error_mean | 0.000975 | 0.001164 |
| raw_negative_fuel_voxel_fraction | 0.201507 | 0.178162 |
| raw_negative_fuel_share_magnitude_total | 0.059314 | 0.066393 |
| raw_fuel_sum_min | 1.000000 | 1.000000 |
| raw_fuel_sum_max | 1.000000 | 1.000000 |
| post_relative_l2_mean | 0.048835 | 0.046586 |

Düşük sinyalli üst bölge hatası ve negatif pay büyüklüğü artmıştır; toplam L2 iyileşmesi tek başına fiziksel kabul değildir.

# Tekrarlı 5×5 CV: 233 başlangıç ve 361 Halton havuzu

**PROVISIONAL / EXPLORATORY.** OpenMC simülasyonu yapılmadı.
Eski 23 test olgusu CV'ye alınmadı. Ortak 233 olgunun fold üyeliği A ve B'de her tekrarda aynıdır.
128 Halton olgusu B doğrulama fold'larına 25–26 adet olacak biçimde dengeli dağıtıldı.
PCA her fold'da yalnız eğitim bölümünde öğrenildi. Sabit XGBoost ayarları kullanıldı.

| Ölçüt | A ortak 233 (ortalama±SS) | B ortak 233 (ortalama±SS) | B tüm 361 (ortalama±SS) |
| --- | ---: | ---: | ---: |
| k_mae | 0.0141928 ± 0.000941 | 0.0102588 ± 0.000735 | 0.0107623 ± 0.000785 |
| k_rmse | 0.020626 ± 0.00156 | 0.0153882 ± 0.00118 | 0.0156417 ± 0.0011 |
| field_relative_l2_mean | 0.0602298 ± 0.00181 | 0.0469307 ± 0.00093 | 0.04815 ± 0.000603 |
| field_half_l1_mean | 0.0305949 ± 0.000795 | 0.0237743 ± 0.000589 | 0.0246333 ± 0.000354 |
| field_axial_half_l1_mean | 0.02986 ± 0.000834 | 0.0230254 ± 0.000629 | 0.023901 ± 0.00038 |
| pca_relative_l2_mean | 0.0143418 ± 0.000123 | 0.014195 ± 8.37e-05 | 0.013903 ± 6.16e-05 |

Ana veri miktarı karşılaştırması B ortak 233 ile A ortak 233 arasındaki eşleştirilmiş OOF farkıdır.
B tüm 361 sonucu daha farklı bir doğrulama popülasyonunu içerdiği için ayrı yorumlanır.
Beş tekrardaki aynı senaryonun tahminleri bağımsız örnek sayılmaz.
Farklı fold eğitim/validation sayıları veri miktarı etkisiyle birlikte yorumlanmalıdır.
Önceki sabit 23 test sonucunu değiştirmedik; doğrudan CV metrikleriyle tek bir sıralamada birleştirmiyoruz.
Sıfır/düşük sinyalli voxel, alternatif nükleer indeks ve kaynak yakınsaması uyarıları sürmektedir.
Gelecekteki adaptif seçim, yeni 128 Halton fiziksel sonucunu kullanmamalıdır.

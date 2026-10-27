# Tekrarlı CV ve 384 senaryoluk full-data adayları

**Bilimsel durum: PROVISIONAL / EXPLORATORY.** Yeni OpenMC simülasyonu yapılmadı. Kaynak 256 ve 384 veri setleri, eski bölmeler, modeller ve raporlar değiştirilmedi.

## Veri ve deney düzeni

- 384 veri setinin ilk 256 senaryosu, sekiz fiziksel girdi, k/MC standart hatası, 3B alan, maske ve koordinat dizileri eski veri setiyle birebir eşleşti. 128 Halton senaryosu benzersizdir.
- Deney A: eski 208 eğitim + 25 kalibrasyon = **233** ortak senaryo.
- Deney B: aynı 233 + 128 Halton = **361** senaryo.
- Eski **23 test senaryosu** her iki tekrarlı CV deneyinden çıkarıldı.
- Beş sabit seed ile **5×5 fold** uygulandı. Her tekrarda ortak 233 senaryonun doğrulama fold'u A/B arasında aynı tutuldu. Halton senaryoları B'nin fold'larına 25–26 adet olarak dengeli dağıtıldı.
- k modeli: önceki sabit XGBoost ayarları (400 ağaç, derinlik 2, öğrenme oranı 0,05). 3B model: fold eğitiminde öğrenilen 12 bileşenli PCA ve sabit XGBoost (120 ağaç, derinlik 4, öğrenme oranı 0,05). Yeni hiperparametre araması veya belirsizlik kalibrasyonu yapılmadı.

## Eşleştirilmiş ortak 233 senaryoda OOF sonuçları

Değerler **beş tekrarın ortalaması ± tekrarlar arası standart sapma**. Aynı senaryonun beş tahmini bağımsız gözlem sayılmadı.

| Metrik | A: 233 | B: ortak 233 | B − A | Göreli değişim |
| --- | ---: | ---: | ---: | ---: |
| k MAE | 0,014193 ± 0,000941 | 0,010259 ± 0,000735 | −0,003934 | −%27,7 |
| k RMSE | 0,020626 ± 0,001561 | 0,015388 ± 0,001183 | −0,005238 | −%25,4 |
| 3B göreli L2 | 0,060230 ± 0,001808 | 0,046931 ± 0,000930 | −0,013299 | −%22,1 |

Üç metrik **5 tekrarın tamamında** iyileşti. Aynı ortak senaryolara dayanan 25 eşleştirilmiş doğrulama fold'unda k MAE ve 3B L2 **25/25**, k RMSE **24/25** fold'da azaldı. Fold'lar ve tekrarlar ilişkili olduğundan bu sayılar bağımsız deney sayısı değildir.

## Genişletilmiş 361 senaryonun ayrı CV sonucu

| Metrik | B: tüm 361 (ortalama ± SS) |
| --- | ---: |
| k MAE | 0,010762 ± 0,000785 |
| k RMSE | 0,015642 ± 0,001098 |
| 3B göreli L2 | 0,048150 ± 0,000603 |

Bu satırlar Halton senaryolarını da doğrulama popülasyonuna katar; eşleştirilmiş 233 karşılaştırmasıyla karıştırılmamalıdır. Yalnız yeni 128 Halton senaryosunun OOF ortalaması k MAE **0,011679**, 3B göreli L2 **0,050369** oldu.

Ortak 233'te ortalama k=1 eşik uyuşmazlığı tekrar başına **6,0 → 3,6**, 3B L1 pay hatası **0,030595 → 0,023774**, aksiyel pay hatası **0,029860 → 0,023025**. Negatif yakıt voxel oranı **%18,54 → %19,63**: genel alan hatası azalsa da bu fiziksel olmayan çıktı sorunu devam ediyor. Ham ve kırpılıp yeniden normalize edilen tahmin hataları ayrı kaydedildi.

[Fold üyelikleri](fold_membership.csv), [tüm OOF tahminleri ve gerçek k değerleri](oof_predictions_and_metrics.csv), [OOF 3B alanları](field_oof_B_361.npz), [tekrar metrikleri](repeat_metrics.csv), [eşleştirilmiş farklar](paired_repeat_differences.csv), [25 fold eşleştirmesi](paired_fold_common233.csv), [çubuk girişi bantları](insertion_band_metrics.csv), [grafik](repeat_metrics.png) ve [tekrar üretim manifesti](reproducibility_manifest.json) kayıtlıdır.

## Önceki sabit test ve full-data adayları

[Önceki aynı 23 test senaryosunun 256/384 sonucu](fixed23_reference.md) kayıtlı kaynaktan **yeniden eğitilmeden** aktarılmıştır. CV doğrulama havuzu ile bu sabit testin ölçütleri tek bir performans sıralamasına sokulmaz. Bu 23 senaryo önceki analizlerde incelendiği için nihai, tamamen dokunulmamış test değildir.

CV sonrasında k ve 3B PCA+XGBoost modelleri **384 senaryonun tamamıyla** yeniden eğitildi: [full384_models_v1](../full384_models_v1/). Dosyalar ve ayarlar [manifestte](../full384_models_v1/reproducibility_manifest.json) kayıtlıdır. Eski 23 test senaryosu da artık bu adayların eğitimindedir; **bu modeller için bağımsız test sayısı sıfırdır**. Eğitim üzerindeki hatalar yalnız *apparent/in-sample* tanıdır, genelleme başarısı değildir. Modeller araştırma amaçlı uygulama prototipi adaylarıdır.

## Sınırlar

CV iyileşmesi tutarlı görünse de A/B eğitim sayıları ve B'nin tam doğrulama popülasyonu farklıdır. İlk 256 ve yeni 128 koşunun bilimsel kabulü verilmedi. Ölçülen sıfır/düşük sinyalli voxel'ler, ilk 256'daki 11 alternatif nükleer indeks için doğrulanmamış HDF5 eşdeğerliği ve bağımsız kaynak yakınsaması incelemesinin eksikliği sürüyor. 3B alan normalize fisyon enerjisi üretimi yaklaşımıdır; mutlak güç haritası değildir. Gelecekteki adaptif 128 seçimi yeni Halton 128'in fiziksel çıktılarını, belirsizliklerini veya ayarlarını kullanmamalıdır. Full-data adaylarının gerçek genellemesi yeni bağımsız OpenMC senaryolarıyla değerlendirilmelidir.


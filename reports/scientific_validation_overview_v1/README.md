# 512 senaryo bilimsel doğrulama — genel özet v1

**PROVISIONAL_EXPLORATORY.** Yeni OpenMC transport, senaryo seçimi veya öğrenci paketi yapılmadı. Eski V2 pipeline, veri setleri, modeller ve sonuçlar değiştirilmedi.

## Temel bulgular

| Soru | Kanıta dayalı sonuç |
|---|---|
| Model nerede zorlanıyor? | Birleşik modelin eğitim OOF 3B L2si yüksek çubuk girişinde 0.058903; düşük/orta bantta yaklaşık 0.039. Üst eksenel düşük üretim bölgesinde negatif ham tahmin ve düşük sinyal yoğunlaşır. |
| Halton–adaptif farkı? | Eski 23 testte Halton k MAE 0.007399, adaptif 0.010407; ancak ortak başlangıç 208 OOF kayıtlarında birleşik kol Haltondan daha iyi. Örnekleme yöntemi için genellenebilir üstünlük kanıtlanmadı. |
| Kontrollü gerçek PINN? | Analitik 1B difüzyonda 5 seedli gerçek PDE rezidüelli PINN bağıl L2 0.000050, rezidüelsiz aynı MLP 0.035005; 5/5 optimizer durması başarılı. Bu toy probleme özgüdür. |
| 3B PINN eksiği? | Enerji/açı çözümlü akı veya doğrulanmış alan bazlı çok gruplu D, saçılma, soğurma ve fisyon katsayıları yok. Mevcut mask/pozitiflik/toplam pay kısıtı gerçek PINN değildir. |
| Yeni 512 MC gerekli mi? | Şimdi toplu 512 yeni koşu kararı verilmez. Önce bağımsız test protokolü, kaynak/MC kalite kabulü, statepoint ve nükleer veri eşdeğerliği çözülmeli. |

## Kanıt ve öncelikler

Bağımsız test senaryoları bu görevde seçilmedi. Eski 23 test çok kez incelendiğinden model ayarında kullanılmadı. Yeni testten önce model/hash, ölçütler ve karar kapıları dondurulmalıdır.

512 koşunun tamamında 600 nesil k/entropi geçmişi vardır; kaynak yakınsaması 512/512 NOT_ASSESSED. Yalnız 64 kaynak deneme yolunda statepoint vardır; aynı deney adına ait yerel dosya 248 senaryoda bulunur, deneme/byte eşlemesi ayrıca gerekir. 11 alternatif nükleer indeksin 690 mantıksal giriş eşleşir; Kaggle HDF5 bayt eşdeğerliği kanıtlanmadı. Fiziksel ve eğitim kabulü 512/512 NOT_ASSESSED.

Öncelik: özgün Kaggle HDF5 hash envanteri ve eksik statepoint arşivi, senaryo bazlı kaynak yakınsama/yerel MC kalite eşiği, ardından dondurulmuş modelle bağımsız test. Bu kanıtlar gelmeden yeni toplu üretim veya nükleer güvenlik sonucu önerilmez.

## Ayrıntılı raporlar

1. [Bağımsız test protokolü](../independent_test_protocol_v1/README.md)
2. [Fiziksel hata analizi](../physical_error_analysis_v1/README.md)
3. [Gerçek PINN deneyi ve fizibilite](../pinn_feasibility_and_experiment_v2/README.md)
4. [Fiziksel/istatistiksel kabul auditi](../physical_validation_audit_v1/README.md)

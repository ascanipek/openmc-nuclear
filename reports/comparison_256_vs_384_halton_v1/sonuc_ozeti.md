# 256 → 384 Halton senaryosu: sonuç özeti

**Durum:** PROVISIONAL / EXPLORATORY. Bu çalışma fiziksel doğrulama, istatistiksel yakınsama veya eğitim verisi kabulü vermez. Yeni OpenMC simülasyonu çalıştırılmadı.

## Veri bütünlüğü ve bölme

Dört Halton grubundan **128 farklı tamamlanmış senaryo** doğrulandı ve ilk 256 senaryoya eklendi. İlk 256'nın senaryo kimlikleri, girdi ve hedef satırları, sayısal alan dizileri ve kaynak dosya hash'leri birebir korundu. Yeni veri seti ayrı bir klasördedir: [datasets/v2_384_halton_v1](../../datasets/v2_384_halton_v1/).

| Bölme | İlk 256 | Yeni 384 |
| --- | ---: | ---: |
| Eğitim | 208 | 336 |
| Kalibrasyon | 25 | 25 |
| Test | 23 | 23 |

Yeni 128 Halton senaryosunun tamamı yalnız eğitim havuzuna eklendi. Eski 25 kalibrasyon ve 23 test kimliği değişmedi. PCA her çapraz doğrulama katında yalnız o katın eğitim örneklerine uyduruldu; test grubu model veya hiperparametre seçimine katılmadı.

## Aynı 23 test senaryosundaki sonuçlar

| Hata ölçütü | 256 | 384 | Mutlak fark (yeni − eski) | Yüzdesel değişim |
| --- | ---: | ---: | ---: | ---: |
| k-effective MAE | 0,012307 | 0,007399 | −0,004909 | −%39,9 |
| k-effective RMSE | 0,015662 | 0,008543 | −0,007119 | −%45,5 |
| 3B alan göreli L2 | 0,048522 | 0,041926 | −0,006596 | −%13,6 |

k modeli kayıtlı XGBoost ayarlarını kullandı: derinlik 2, 400 ağaç, öğrenme oranı 0,05 ve beş katlı eğitim içi çapraz doğrulama. Eski yayımlanmış k modeli farklı XGBoost sürümünde oluşturulduğu için, 256 örnekli model ayrıca yeni modelle aynı yerel sürümde yeniden eğitilip bu tablonun k karşılaştırmasına esas alındı. Eski rapor ve model dosyaları değiştirilmedi.

3B model, eğitim üzerinde öğrenilen **12 bileşenli PCA** ile derinlik 4, 120 ağaç ve öğrenme oranı 0,05 kullanan XGBoost'u birleştirir. PCA yeniden oluşturma hatası ile toplam ML tahmin hatası ayrı tutuldu. PCA test göreli L2 hatası 0,014747'den 0,014863'e hafifçe yükseldi; toplam 3B tahmin hatası ise azaldı.

Testte k=1'in hangi tarafında kalındığına ilişkin betimleyici uyuşmazlık sayısı 3'ten 0'a indi. Eski eğitim verisine sekiz parametrede en uzak olan altı test senaryosunda k MAE 0,013263'ten 0,005124'e, 3B göreli L2 0,055435'ten 0,039553'e indi. Bu altı senaryo için kullanılan uzaklık tanımı rapor kodunda kayıtlıdır; doğrulanmış bir geçerlilik sınırı değildir.

Ayrıntılı sonuçlar: [k eğitim raporu](../keff_384_halton_v1/training_report.json), [3B eğitim raporu](../field3d_384_halton_v1/training_report.json), [karşılaştırma sayıları](metrics.csv), [test olguları](same_test_predictions.csv), [çubuk giriş aralıkları](insertion_bands.csv) ve [grafik](test_error_by_insertion.png).

## Bilimsel ve teknik sınırlar

- Yeni 128 koşunun tamamının kalite durumu `review_required`. `completed`, fiziksel doğrulama veya eğitim verisi kabulü değildir.
- Yeni 128'de geometrik yakıt voxel'lerinin **%13,6'sında** ölçülen kappa-fission sıfır; **%28,1'i** mevcut düşük sinyal tanımına giriyor. Ölçülen sıfır, kendiliğinden fiziksel sıfır veya sıfır belirsizlik değildir. [Kalite özeti](quality_summary.md)
- Ham 3B ML tahmininde yakıt voxel'lerinin **%18,8'i negatif**. Negatifleri kırpıp alanı yeniden normalleştiren ayrı karşılaştırmada göreli L2 **0,041926'dan 0,042100'e** çıktı. Ham sonuç gizlenmedi.
- Eski 256 koşunun 11'inde alternatif nükleer veri indeksi hash'i vardır. HDF5 dosyalarının bayt düzeyinde eşdeğerliği henüz doğrulanmadı.
- Halton-03'ün 11. koşusunda iki başarısız tekrar ve bir tamamlanmış deneme vardı. Veri setine yalnız tamamlanmış deneme alındı; başarısız tekrarlar [veri seti manifestinde](../../datasets/v2_384_halton_v1/dataset_manifest.json) kayıtlı.
- Hafif teslim ZIP'leri statepoint dosyalarını içermez. Halton-01/02'nin kaynak statepoint'leri yerel koşu dizininde korunuyor; Halton-03/04 için öğrencilerin kaynak kopyaları derin kaynak yakınsaması incelemesinde gerekebilir.
- Yakıt pimi aralığı değiştikçe fiziksel X/Y koordinatları değişir; ortak [z,y,x] indeksleri her senaryoda aynı fiziksel koordinat anlamına gelmez. Hedef, mutlak reaktör güç haritası değil, normalize kappa-fission enerji üretimi yaklaşımıdır.
- Aynı 23 test senaryosu önceki araştırmalarda incelendi. Sonuçlar yararlı bir karşılaştırmadır, fakat tamamen dokunulmamış nihai doğrulama sonucu değildir. Gelecekteki adaptif senaryo seçiminde bu 128 Halton sonucunun fiziksel çıktıları kullanılmamalıdır.

## Çıktılar ve doğrulama

- Veri seti, alanlar, maskeler, koordinatlar, MC standart hataları, split ve manifest: [datasets/v2_384_halton_v1](../../datasets/v2_384_halton_v1/)
- k modeli, beş katlı CV ve test raporu: [reports/keff_384_halton_v1](../keff_384_halton_v1/)
- PCA, 3B model, alan kesitleri ve eksenel profiller: [reports/field3d_384_halton_v1](../field3d_384_halton_v1/)
- Karşılaştırma, kalite ve aynı sürümde yeniden eğitilen 256 k modeli: [bu klasör](./)

Kaydedilen modeller yeniden yüklenerek test tahminleri doğrulandı. PCA eğitim kimlikleri 336 eğitim senaryosuyla birebir eşleşiyor; test kimlikleri PCA öğrenimine girmedi. Mevcut otomatik testler **91/91 başarılı**. Sonuç notebook'unun normal çalıştırma çıktısını kaynak değişikliği sayan test, projenin sürümlü notebook içerik hash'iyle karşılaştıracak şekilde düzeltildi. Eski 256 veri seti, notebook'lar, modeller ve raporlar değiştirilmedi.



# 3B bağıl kappa-fission vekil modelleri — keşif analizi

Bu çalışma gerçek OpenMC `target_normalized_kappa` alanını kullanır. Hedef [z,y,x] = [20,17,17] düzeninde, yakıt voxel'leri üzerinde toplamı 1 olan **fisyon enerjisi üretimi yaklaşımıdır**; mutlak güç veya toplam yerel ısı birikimi değildir. 256 alanın tamamı bilimsel olarak `REVIEW_REQUIRED` durumundadır.

## Yöntem

- Sabit 208 eğitim / 25 kalibrasyon / 23 test ayrımı değişmedi. Kalibrasyon model seçiminde kullanılmadı.
- 5 katlı eğitim içi CV'nin her katında PCA, yalnız kat eğitimi üzerine yeniden uyduruldu. Ridge/GPR girdi ölçeklemesi de kat eğitiminden öğrenildi.
- 8, 12, 16, 24 bileşen; Ridge alpha 0.1/1/10; GPR sabit RBF/Matérn-3/2 kernel; XGBoost 120 ağaç, derinlik 2/4 karşılaştırıldı. GPR optimizasyonu maliyeti sınırlamak için kapatıldı; bu kapsamlı bir GPR ayarı değildir.
- Seçim metriği geometrik yakıt voxel'lerinde toplam 3B göreli L2 hatasının CV ortalamasıdır. PCA tek başına yeniden oluşturma hatası ayrıdır.
- Test yalnız seçim sonrası değerlendirildi. Tahminler ham hâlde kaydedildi. Fiziksel karşılaştırma için sıfıra kırpma ve yakıt toplamına göre yeniden normalizasyon ayrı çıktı olarak hesaplandı; seçim buna göre yapılmadı.

## İlk sonuç

| Ölçüt | Sonuç |
|---|---:|
| Seçilen yapı | 12 PCA bileşeni + XGBoost (derinlik 4, 120 ağaç) |
| Eğitim CV, PCA tek başına göreli L2 | %1,44 |
| Eğitim CV, toplam tahmin göreli L2 | %6,67 |
| Bağımsız test, PCA tek başına göreli L2 | %1,47 |
| Bağımsız test, ham toplam tahmin göreli L2 | %4,85 |
| Bağımsız test, son işlemli göreli L2 | %4,88 |

CV'de 12/16/24 bileşenli XGBoost sonuçları neredeyse eşittir; sayısal bağda daha az bileşen seçildi. Ham testte 24.471 yakıt voxel'inde negatif tahmin oluştu (23×5.280 voxel'in %20,15'i). Toplam negatif pay büyüklüğü 23 koşuda 0,0593'tür. Ham tahminin yakıt toplamı 1 olsa da negatif voxel'ler fiziksel değildir. Son işlem negatifleri kaldırdı fakat göreli L2'yi hafif artırdı.

Üst dört dilimde düşük sinyalli bölgelerin gerçek ortalama payı yaklaşık 0,0000266/senaryo; ham tahminin bu bölgelerdeki ortalama mutlak pay hatası yaklaşık 0,000975'tir. Çok küçük ortalamaya göre bağıl hata yüzdesi verilmedi.

PCA ortak mesh **indeksleri** üzerinde çalışır. Pitch değişince X/Y fiziksel koordinatları değişir; bu model sabit santimetre koordinatlarında enterpolasyon değildir. 11 senaryodaki alternatif nükleer veri indeksinin HDF5 bayt eşdeğerliği doğrulanmamıştır. Normalize hedefin tam belirsizliği için gereken kovaryans da yoktur.

## Dosyalar

- `cv_model_comparison.csv`: 28 adayın eğitim CV sonucu
- `test_case_metrics.csv`: 23 test senaryosunun PCA/ham ML/son işlemli metrikleri
- `test_fields.npz`: gerçek, PCA, ham ML, son işlemli alanlar; maskeler ve fiziksel koordinatlar
- `selected_pca.npz`, `selected_model.joblib`: seçilen PCA ve model
- `training_report.json`: veri hash'leri, yöntem, ortam, genel metrikler
- `*.png`: CV, XY/XZ ve eksenel profil grafikleri

Yeniden üretim betiği: `scripts/field3d_surrogate_v1.py`. WSL'de `teknofest26` Python 3.11, scikit-learn 1.9.0, XGBoost 3.2.0 kullanıldı. XGBoost mevcut Conda ortamı değiştirilmeden `/tmp/openmc_xgboost_320` içine kuruldu; geçici dizin temizlenirse bu sürüm yeniden sağlanmalıdır. Joblib modeli yalnız güvenilir dosyadan yükleyin. OpenMC taşıma hesabı yapılmadı.

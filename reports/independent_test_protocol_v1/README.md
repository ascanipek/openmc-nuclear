# Bağımsız test protokolü v1

**Statü: PROVISIONAL_EXPLORATORY.** Bu belge yeni test senaryosu seçmez, üretmez ve çalıştırmaz. Mevcut 23 test örneği geçmiş model geliştirme raporlarında tekrar kullanıldığı için nihai bağımsız doğrulama değildir.

## Amaç ve iki ayrı kohort

Genel genelleme kohortu, onaylı sekiz parametreli pilot uzayın tamamındaki tahmin hatasını ölçer. Fiziksel stres kohortu, yüksek kontrol çubuğu girişi ve düşük sinyalli üst bölge gibi önceden belirlenmiş zor bölgeleri ayrıca ölçer. Stres kohortunun sonucu genel hata tahminine ağırlıksız karıştırılmaz.

Kohort boyutları, hesap maliyeti ve beklenen eşleştirilmiş hata değişkenliğiyle yapılacak güç/maliyet hesabından sonra, OpenMC sonucu görülmeden sabitlenir. Bu sürüm örnek sayısı veya parametre değeri seçmez.

## Seçim ve çakışma engeli

Önce pilot kapsamın sürümlü sekiz parametre sınırı ve sıcaklık–basınç–su fazı ile geometri birleşim kısıtları dondurulur. Genel kohort uzay dolduran, önceden kaydedilmiş seedli bir tasarımdan; stres kohortu önceden tanımlanan yüksek giriş bölgesinden seçilir. Düşük/orta/yüksek çubuk girişi bantları, bor ve sıcaklık aralıkları, pitch ve pelet yarıçapı birlikte kapsanır; bant başına sonuçlar ayrı raporlanır.

Her adayın kanonik sekizli fiziksel vektörü ve senaryo kimliği mevcut 512 katalogla ve kendi kohortlarıyla karşılaştırılır. Tam eşleşmeler reddedilir; normalize sekiz boyutlu uzaklıkla çok yakın örnekler ayrı listelenir. Yakınlık eşiği sonuç görülmeden belirlenir. Bu kontrol fiziksel geçerlilik denetiminin yerine geçmez.

## İzolasyon ve tek değerlendirme kapısı

Test planı, seçim kodu, seed, model sürümleri, PCA, ölçekleyiciler, hiperparametreler, hedef/mask tanımları, kalite kuralları ve birincil metrikler yeni MC başlamadan hashli ve değiştirilemez kayda alınır. Test kimlikleri ve çıktıları eğitim, CV, kalibrasyon, adaptif seçim veya erken durdurma koduna verilmez. Sonuçlar ayrı salt okunur depoda tutulur.

Kaydedilmiş XGBoost/PCA ve varsa YSA adayları yalnız dondurulmuş hâlleriyle ilk kez değerlendirilir. Birincil rapor bir kere üretilir; sonradan yapılan analizler ikincil/keşifsel olarak sürümlenir. Teste bakılarak model seçimi veya yeniden ayar yapılırsa aynı test artık bağımsız kabul edilmez.

## Önceden kaydedilecek değerlendirme ve kabul mantığı

Birincil metrikler: k için MAE ve RMSE; 3B normalize kappa-fission için geometrik yakıt maskesinde senaryo bazlı bağıl L2. İkincil metrikler: k maksimum mutlak hata, k=1 eşik uyuşmazlığı, P95 alan L2, pay L1, eksenel üretim payı, negatif yakıt voxel/pay, kırpma etkisi, çubuk bantları, düşük sinyal ve sıfır tally kapsamı.

Model farkları aynı test senaryosunda eşleştirilmiş hata farklarıyla ve senaryo düzeyinde yeniden örneklenen belirsizlik aralıklarıyla verilir; voxel veya tekrarlı seed bağımsız örnek sayılmaz. Genel ve stres kohortlarının sonuçları ayrı tutulur. Çoklu model/metric karşılaştırmaları önceden belirtilir.

Yazılımsal tamamlanma, MC istatistiksel yeterlilik ve fiziksel geçerlilik ayrı kapılardır. Fiziksel kabul eşikleri henüz doğrulanmış değil; bunlar kaynak yakınsaması, nükleer veri eşdeğerliği, düşük sinyal ve kullanım amacına bağlı hata toleransı üzerinden **ilk yeni test sonucu görülmeden** yetkili bilimsel incelemeyle sayısallaştırılır. Eşik yokken başarılı koşu ya da küçük ML hatası otomatik kabul sayılmaz.

## Dondurma kaydı

Gelecekteki yürütme kaydı en az şu hashleri içerir: 512 kaynak manifesti, seçici kod/seed, yeni test manifesti, OpenMC config/profil, nükleer veri indeksi ve HDF5 envanteri, model/PCA dosyaları, değerlendirme kodu. Ön kontrol sonucu ve sonradan yapılan her sapma ayrıca tarihli kaydedilir.

Örnekleme yöntemi üstünlüğünün ön kayıtlı karşılaştırması Halton eksi adaptif senaryo bazlı mutlak k hatası ve 3B bağıl L2 farkıdır. Her hedef için eşleştirilmiş ortalama hata farkı, senaryo bootstrap %95 güven aralığı ve tek yönlü işaret-değiştirme permütasyon p değeri hesaplanır. İki birincil p değeri Holm yöntemiyle düzeltilir; yön doğru ve düzeltilmiş p<0.05 olmadıkça üstünlük iddiası yoktur. Güven aralığı etki büyüklüğünü gösterir. Bu istatistiksel karar fiziksel doğrulama yerine geçmez.

Uygulama yeterliliği için k ve 3B alanın mutlak hata toleransları, kaynak yakınsaması/MC kalite kuralları ve stres bölgesi koşulları sonuçlar görülmeden yetkili kullanım amacıyla sayısallaştırılmalıdır; şu anda bu eşikler onaylı olmadığı için otomatik ACCEPT üretilemez.

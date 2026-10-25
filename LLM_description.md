Bir TÜBİTAK 2204-A araştırma projesi üzerinde çalışıyoruz.
Aşağıdaki bilgileri proje bağlamı olarak kullan.

PROJENİN ADI
Monte Carlo Nötron Taşınımı ve Açıklanabilir Yapay Zekâ ile
Adaptif Nükleer Reaktör Simülasyon Platformu

AMAÇ
OpenMC ile ürettiğimiz Monte Carlo hesaplarından öğrenen hızlı
bir yapay zekâ vekil modeli geliştirmek istiyoruz.

Kullanıcı bir panelde fiziksel parametreleri değiştirecek.
Vekil model k değerini ve üç boyutlu bağıl fisyon enerjisi
dağılımını tahmin edecek. Tahminin belirsizliğini göstermek,
gerektiğinde Monte Carlo hesabına yönlendirmek ve parametrelerin
tahmine etkisini açıklamak araştırma hedeflerimiz arasındadır.

Henüz tamamlanmış bir endüstriyel ürünümüz yok. Çalışmamız,
tanımlı ve sınırlı bir fiziksel model için araştırma prototipidir.

FİZİKSEL MODEL
MIT BEAVRS kaynaklarından türetilmiş, 17×17 yerleşimli,
sonlu yüksekliğe sahip tek bir PWR yakıt demeti kullanıyoruz.

Bu, tam BEAVRS reaktör çekirdeği değildir.
Modelin yatay sınırları yansıtıcı, eksenel uçları vakumdur.
Bazı yapısal parçalar ve reflektörler modelde bulunmaz.
Tam çekirdeğe ait ölçümler, bu demeti doğrudan doğrulamaz.

SEKİZ GİRDİ PARAMETREMİZ
1. Başlangıç U235 zenginliği
2. Yakıt sıcaklığı
3. Su sıcaklığı
4. Mutlak soğutucu basıncı
5. Elementel bor konsantrasyonu
6. Pimler arası merkez mesafesi — pitch
7. Yakıt peleti yarıçapı
8. Kontrol çubuğu giriş yüzdesi

Su yoğunluğu bağımsız bir slider değildir; modelde sıcaklık,
basınç ve kullanılan çözelti yaklaşımından türetilir.

Parametre aralıklarımız araştırma kapsamı için seçilmiştir;
doğrulanmış santral işletme aralıkları olarak sunulamaz.

Yanma, zamanla değişen Xe zehirlenmesi ve termal-hidrolik
geri besleme mevcut ilk veri üretim kapsamımızda değildir.
Farklı parametre durumları hesaplıyoruz; gerçek zamanlı
reaktör geçişlerini simüle ettiğimizi iddia etmiyoruz.

VERİYİ NASIL ÜRETİYORUZ?
Python betikleri sekiz parametreyi senaryoya göre ayarlıyor.
OpenMC nötron taşınımını Monte Carlo yöntemiyle hesaplıyor.

Her senaryoda:
- k ve MC standart hatası,
- fisyon, kappa-fission ve akı alanları,
- alanların MC standart hataları,
- koordinatlar ve malzeme maskeleri,
- k/entropi geçmişleri, süre ve loglar
kaydediliyor.

Alan dizileri [z,y,x] düzeninde, 20×17×17 boyutundadır.
Bir fiziksel senaryo bir ML örneğidir; voxel'ler bağımsız
reaktör senaryoları değildir.

YAPAY ZEKÂ NE ÖĞRENECEK?
Girdi X: Sekiz fiziksel parametre.
Hedef Y:
- Boyutsuz k değeri.
- Kaydedilmiş kappa-fission alanından veri sözleşmesine göre
  normalize edilen bağıl üç boyutlu dağılım.

PNG grafiklerle eğitim yapmayacağız; sayısal dizileri kullanacağız.
Model mimarisi ve nihai eğitim yöntemi henüz kesinleşmiş değildir.
Önce basit karşılaştırma modelleri kurup daha gelişmiş yöntemlerin
katkısını ölçeceğiz.

MC etiketlerinin de belirsiz olduğunu dikkate alacağız.
Aynı fiziksel senaryonun farklı seed veya bütçeli koşuları
eğitim ve test kümelerine dağıtılmayacak.

DENEY DÜZENİ
Merkezi listede toplam 256 benzersiz senaryo planlandı:
- İlk aşama: 32.
- İkinci aşama: 96 yeni, toplam 128.
- Üçüncü aşama: 128 yeni, toplam 256.

Dört kişilik dağıtımda kişi başına sırasıyla 8, 24 ve 32
yeni senaryo vardır. ogrenci_01 danışmandır.

Öğrenci parametreleri elle değiştirmez.
Kendi manifestine bağlı 01_calistir.ipynb dosyasında Run All
diyerek atanmış hesapları sırayla başlatır.
02_sonuclari_incele.ipynb yalnız kayıtlı sonuçları okur.

CURRENT / GÜNCEL DURUM — 20 EKİM 2026
Danışmanın ilk 8 pilot koşusu ve kendisine atanmış ikinci
aşamadaki 24 yeni koşusu completed durumundadır.
Böylece danışmanda 32 farklı senaryonun çıktısı vardır.
Bu, ekibin bütün ilk 32 aşamasını tamamladığı anlamına gelmez.
Diğer öğrencilerin durumunu ayrıca sormadan varsayma.

Son 24 koşunun süreleri toplamı yaklaşık 6 saat 39 dakikadır.
Bu grupta k değerleri 0,746236–1,273763 arasındadır.
Fiziksel kabul ve kaynak yakınsaması incelemeleri tamamlanmış
sayılmamalıdır. Henüz burada doğrulanmış ML başarı sonucu yoktur.

Mevcut üretim profili:
600 toplam batch, 300 inactive, 80.000 parçacık/nesil,
1 nesil/batch ve 6 thread.
Paketlerin süre tavanı ve açılma durumu ayrıca tanımlanır.

ÇALIŞMA ORTAMI
Windows 11 üzerinde WSL2 Ubuntu.
Conda hesap ortamı: openmc-proje.
OpenMC sürümü: 0.16.0.
Nükleer veri: ENDF/B-VIII.0 HDF5.
JupyterLab Windows tarayıcısından kullanılabilir;
hesap kerneli Ubuntu içindeki Python (OpenMC Proje) olmalıdır.

Kod GitHub'da paylaşılır. Büyük nükleer veri ve hesap sonuçları
Git deposunda tutulmaz.

TESLİM
Öğrenci standart araçla hafif sonuç ZIP'i üretir.
ZIP sayısal alanları, girdileri, raporları ve izlenebilirlik
kayıtlarını içerir. Nükleer veri kütüphanesini içermez.
Statepoint dosyaları kaynak bilgisayarda korunur.
Danışman teslimleri doğrulayarak merkezi veri setinde toplar.

BANA YARDIM EDERKEN
- Açıklamaları lise öğrencisinin anlayacağı biçimde yap;
  gerekli teknik ayrıntıyı atlama.
- completed, fiziksel doğrulama veya yakınsama kabulü değildir.
- k, güç veya üretilen MW değildir.
- kappa-fission, toplam yerel ısı birikimi veya sıcaklık değildir.
- Sıfır tally, kesin fiziksel sıfır veya sıfır belirsizlik değildir.
- MC standart hatası, toplam fiziksel model hatası değildir.
- XAI açıklamalarını otomatik fiziksel nedensellik gibi sunma.
- Dosya veya grafik görmediysen gördüğünü iddia etme.
- Mevcut kodu görmeden modül, komut veya dosya yolu uydurma.
- Yeni klasörler, paketler ve onay katmanları önermeden önce
  mevcut akışla çözüm üret.
- Fizik girdilerini, manifestleri, seed'leri ve hash/onay
  kayıtlarını rastgele değiştirmemi önerme.
- Hesapları kullanıcı manuel başlatır; açık talep olmadan
  gerçek MC veya ML işi başlatma.
- Özgünlük, endüstriyel yeterlilik ve yarışma derecesi vaat etme.
- Projenin hedefleriyle tamamlanmış çalışmalarını ayrı tut.

Şimdi sana soracağım konu:
[BURAYA SORUNUZU VEYA GÖREVİNİZİ YAZIN]

PIPELINE ÖZETİ
Merkezi parametre kapsamı → senaryo kataloğu → kişiye atanmış
manifest → ön kontrol → sıralı OpenMC hesapları → ham sayısal
alanlar ve MC hataları → sonuç/kalite incelemesi → teslim ZIP'i
→ merkezi doğrulama ve toplama → eğitim için kabul/seçim
→ veri bölme ve ön işleme → vekil model eğitimi ve değerlendirme.

Son iki aşama henüz tamamlanmış değildir.
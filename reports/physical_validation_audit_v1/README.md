# Fiziksel ve istatistiksel doğrulama audit v1

**PROVISIONAL_EXPLORATORY.** 512 kaydın yazılımsal tamamlanması fiziksel veya eğitim kabulü değildir. Kaynak veri manifestindeki beş çıktı hash değeri ve 512 senaryo kimliği doğrulandı. HDF5 statepoint yükleri topluca okunmadı.

## Kaynak yakınsaması ve k geçmişi

512 senaryonun 600 nesillik k ve Shannon entropisi geçmişi sonlu ve kayıtlıdır; ilk 300 nesil inactive. Aktif ilk 100 ve son 100 ortalama k farkının medyanı 0.0000613, mutlak fark P95i 0.001512dir. Entropinin son 100 nesil eğim medyanı 3.53e-6 / nesildir. Bunlar betimleyicidir; nesiller bağımsız gözlem değildir ve önceden onaylı yakınsama eşiği yoktur. Fisyon kaynağı yakınsaması hâlâ NOT_ASSESSED. Senaryo bazlı değerler history_descriptors.csv içindedir.

## MC standart hataları ve yerel sinyal

k için raporlanan MC standart hatası medyan 0.0001838, P95 0.0001981, maksimum 0.0002087dir. Ham 3B kappa/fission/flux ortalama ve SE alanları tüm 512 kayıt için vardır. Quality tablosunda fuel_zero_signal için 350, low_signal için 449 senaryo WARNING alır. Sıfır tally ve sıfır raporlanan SE, fiziksel sıfır veya kesinlik kanıtı değildir. Normalize alan için voxel kovaryansı bulunmadığından ham SE doğrudan normalize pay belirsizliği değildir.

## Statepoint kanıtı

Kaynak deneme klasöründe 64 senaryonun statepoint.600.h5 dosyası vardır. Projedeki diğer klasörler de deney adıyla eşleştirildiğinde 248/512 senaryo için en az bir yerel statepoint bulunur; bu eşleşme aynı deneme ve aynı byte içeriği olduğunu kanıtlamaz. 264 senaryoda aynı deney adına ait yerel statepoint bulunamadı. Hafif teslim politikası birçok kaynağın statepointini taşımamış olabilir. Önce öğrenci/kaynak arşivleri geri alınmalıdır; yeniden MC hesabı ilk seçenek değildir. Dosya varlığı içerik doğrulaması değildir.

## Alternatif nükleer veri indeksi

501 senaryonun XML indeksi yerel hash ba7f6d5a...; 11 senaryonun Kaggle indeksi b47cef3a... kullanır. İki özgün Kaggle XML kopyası aynı hashte. Yerel ve Kaggle XMLlerin 690 library girdisi, malzeme adı, tür ve veri kökü çıkarılmış göreli HDF5 yolu bakımından sırasıyla aynıdır. Kaggle XML yolu /kaggle/input içindedir ve bu makinede o HDF5 dosyaları yoktur. Dolayısıyla HDF5 baytları, sıcaklık tabloları ve gerçek nükleer veri eşdeğerliği doğrulanmadı. Yalnız dosya adı veya XML yapısından eşdeğerlik varsayılmadı.

## Çözüm sırası

Mevcut dosyalarla yapılabilir: her senaryonun k/entropi geçmişini, ham tally SE ve sinyal kapsamasını betimlemek; ulaşılabilir statepointlerin kimlik ve tally karşılaştırmasını ayrı hedefli denetlemek; eşikler belirlenince mevcut kayıtları yeniden puanlamak. Ek dosya gerekir: eksik özgün statepointler ve Kaggle nükleer veri Datasetinin doğrulanabilir HDF5 hash envanteri. Yeni transport ancak gerekli özgün veri bulunamazsa veya önceden tanımlanan istatistiksel/ kaynak yakınsama kabulü başarısız olursa değerlendirilebilir.

Mevcut kalite kayıtlarında physical_validation ve training_acceptance 512/512 NOT_ASSESSED, source_convergence 512/512 NOT_ASSESSED. Kabul sayısal eşiği bu görevde uydurulmadı. Audit tablosu quality_check_counts.csv, kaynak geçmişi history_descriptors.csv, statepoint durumu statepoint_availability.csv ve nükleer indeks ayrıntısı nuclear_index_comparison.json içindedir.

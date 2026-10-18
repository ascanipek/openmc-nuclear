# OpenMC demet araştırma pipeline'ı

Bu proje BEAVRS kaynaklarından türetilmiş 17×17 sonlu yükseklikli yalıtılmış bir demet modelini ve kontrollü V2 pilot veri toplama akışını içerir. Tam çekirdek ölçümleriyle doğrulanmış bir işletme modeli veya kabul edilmiş eğitim veri kümesi değildir. Yanma ve Xe kapsam dışındadır.

Öğrenciler için tek başlangıç noktası [student_setup.md](student_setup.md). Proje hesabı Windows Python'unda değil WSL2 Ubuntu içindeki `openmc-proje` Conda ortamında yapılır. [environment.yml](environment.yml) hesap ortamının tanımıdır; nükleer HDF5 kütüphanesi ayrı, yerel indirilir. Temiz kurulum henüz sınanmadı.

Merkezi [öğrenci sahiplik kaydı](configs/v2_student_assignment_v1.json) ilk 32 fiziksel senaryoyu sekizer atar: `ogrenci_01` danışmanın tamamlanmış sekiz pilot sonucunu **yeniden hesaplamadan** kullanır; `ogrenci_02`–`04` yer tutucu adlarıyla yeni sekizer koşu alır. Sonraki aşamalarda dört öğrenciye 24'er ve 32'şer **yeni** senaryo düşer. Bunlar ayrı inceleme/onay olmadan başlamaz. Paylaşılacak temiz notebook'lar [sürümlü öğrenci paketlerinde](student_packages/v2_students_portable_v1); geçmiş çalıştırılmış notebook'lar ve sonuçlar yerel tutulur.

Bir öğrencinin paketi içinde `manifest.json` sabit deney listesidir. `01_calistir.ipynb` yalnız onaylı paketi Run All ile bağımsız WSL işçisine verir; `02_sonuclari_incele.ipynb` kayıtları okur. Paket hash'leri kod, konfigürasyon, manifest ve notebook girdilerini kapsar. Notebook çıktısı kaydedilince onay bozulmaz. `completed` yalnız çıktı bütünlüğüdür; fiziksel/istatistiksel kabul ayrı kalır.

Sonuç teslimi ve danışman toplaması [v2_transfer.py](scripts/v2_transfer.py) ile yapılır. Hafif ZIP statepoint dosyasını içermez; kaynak makinede tutulur. Teslim, checksum ve model/senaryo/atama kontrollerinden geçer; bozuk veya çelişen teslim reddedilir, eski sonuçların üzerine yazılmaz. Eğitim veri aktarımı ancak ayrı kabul kayıtlarından sonra [v2_dataset.py](src/reactor_pipeline/v2_dataset.py) ile yapılır.

Tarihsel v1 kaynak ve doğrulama notları `docs/` altında korunur; önceki D2/D3/D4 sonuçları ve onaylı pilot koşuları değiştirilmedi. Testler gerçek taşıma başlatmadan `python -m unittest discover -s tests` ile çalıştırılır.

## Güncel ilk 32 notebook dizini

notebooks/01_deney_calistir.ipynb salt okunur dizindir. Danışmanın tamamlanmış sekiz pilotu ile diğer üç öğrenciye atanmış 24 yeni koşuyu ve mevcut notebook yollarını gösterir. İlk aşamada yalnız bu dizinin işaret ettiği notebook çiftlerini kullanın. v2_staged_draft_v1 eski, onaysız taslaktır; eski runner hashine ve farklı dağıtıma bağlıdır. Eski sonuçlar yeniden etiketlenmez veya yeniden çalıştırılmaz. İlk 32 aşamasında ogrenci_02–04 paketlerinin teknik approval.json kayıtları oluşturuldu; bu fiziksel veya eğitim verisi kabulü değildir. Sonraki aşamaların ayrı onayı gerekir.

# V2 öğrenci stage_128 / stage_256 teknik hazırlık incelemesi

## Sonraki danışman kararı ve uygulama (2026-10-20)

Bu belgenin aşağıdaki 12/16 saatlik önerileri tarihsel ön incelemedir; güncel karar onları geçersiz kılar. Danışman üç stage_128 paketi için 64.800 saniye (18 saat), üç stage_256 paketi için 86.400 saniye (24 saat) tavanını ve altı paketin teknik çalıştırma onayını açıkça verdi. İki sürümlü, onaylı hesap profili aynı aşamadaki üç paket arasında paylaşılır; ortak taslak profil ve danışmanın özel profilleri değiştirilmedi. Altı manifestin deney listeleri önceki sürümleriyle birebir aynıdır. Paket, profil, notebook, kaynak kod ve merkezi pin doğrulamaları ile başlatmasız ön kontroller geçti; tüm grup durumları not_started. Geçici dizinde altı ZIP export/import denemesi geçti. 83 otomatik test geçti. Bu teknik onay fiziksel doğrulama, kaynak yakınsaması veya eğitim verisi kabulü değildir. Öğrenci bilgisayarlarındaki süreler ölçülmediğinden 18/24 saat tamamlanma garantisi değildir.


Tarih: 2026-10-20. Bu kayıt **onay veya başlatma değildir**. Altı paket ve ortak taslak profil değiştirilmedi. Teknik çalıştırma onayı; fiziksel doğrulama, kaynak yakınsaması veya ML eğitim verisi kabulü değildir.

## Git anlık durumu

Depo `/home/ascanipek/openmc-proje`, dal `master`, HEAD `a75bbf4`. Yerel `origin/master` referansına göre 0 commit önde, 0 commit geride. Canlı GitHub sorgusu HTTPS kimlik doğrulaması istediği için uzak başlığın güncelliği doğrulanamadı. Commit veya push yapılmadı.

Üç stage_32 paketinin merkezi `package_sha256` pin düzeltmesi `configs/v2_student_assignment_v1.json` içinde HEAD'e göre **commit edilmemiş fark** olarak bulunuyor. Aynı dosyada önceki turdan kalma danışman stage_256/ogrenci_01 pin değişikliği de var. Önceki turdan kalan `student_setup.md`, `LLM_description.md` ve danışman stage_256/ogrenci_01 paket/profil/onay çalışma ağacı değişikliklerine bu incelemede dokunulmadı. GitHub'a gönderilebilir yeni commit henüz yok; bu yerel dosyalar uygun kapsamda incelenip commit edildikten sonra, canlı uzak başlık tekrar doğrulanarak push kararı verilmeli.

## Altı paket: mevcut doğrulama

| Aşama | Öğrenciler | Koşu/paket | Merkezi katalog ve kontrol değerleri | Hash / notebook / profil bağlantısı | Başlatmasız ön kontrol | Onay kapısı | Grup |
|---|---|---:|---|---|---|---|---|
| stage_128 | ogrenci_02, 03, 04 | 24 | Her paket birebir, benzersiz | Geçti | 24/24 geçti | Kapalı | not_started |
| stage_256 | ogrenci_02, 03, 04 | 32 | Her paket birebir, benzersiz | Geçti | 32/32 geçti | Kapalı | not_started |

Toplam 168 senaryo benzersizdir; aynı öğrencinin iki aşaması ve farklı öğrenciler arasında çakışma yoktur. Her manifestin fiziksel kontrol sözlükleri ilgili merkezi katalog kayıtlarıyla birebir eşleşti. Atamalar, hesap ayarları ve `seed_base=71001` ile başlayan grup içi seed dizileri uyumludur. `verify_package(require_approval=False)` altı pakette geçti; korunan kod, manifest, iki notebook'un içerik hash'i ve paket hash listesi bu kontroldedir. `preflight` her koşuda parametre çözümlemesi, model kurma, 10 seçilmiş geometri noktası ve nükleer veri sıcaklık kapsamı kontrolünü geçti; `transport_started=false`. Bu testler tam geometri/taşınım veya yakınsama kabulü değildir.

Altı pakette bağlı `configs/v2_calculation_profile_pilot_draft_v1.json` dosyası `draft_not_production`; grup süre tavanı `null`. Paketler `draft_unapproved`, teknik paket onayı yok. `verify_package(require_approval=True)` bu nedenle `Parameter space or calculation profile lacks production approval` ile durur. Paylaşılan taslak profil veya danışmanın özel profili bu paketler için değiştirilmemelidir.

## Bütçe değerlendirmesi ve karar önerisi

Bütün koşul manifestlerinde 80.000 parçacık/nesil, 600 toplam batch, 300 inactive, 1 nesil/batch ve 6 thread korunur. Danışman makinesindeki tamamlanmış 24 stage_128 koşusunun grup süresi 23.979 s; koşu ortalaması 998,5 s ve en uzun tamamlanan koşu 1091,1 s. İlk sekiz pilotta koşu ortalaması 1173,7 s, maksimum 1277,1 s. Bunlar farklı fiziksel durumlar ve tek makineye ait gözlemlerdir.

Runner, bu hesap ayarlarında D2-B2 ölçümü 1041,678 s üzerine 1,5 planlama çarpanı uygulayarak **1562,517 s/koşu** tahmin eder. Tahmin garanti değildir. Bir sonraki koşu için kalan süre bu tahminden azsa onu başlatmaz; toplam grup tavanı dolarsa çalışan koşuyu kesebilir. Tamamlanmış kayıtlar korunur; kesilen koşu inceleme ve açık devam kararı gerektirir.

| Aşama | Ön bütçe önerisi | Runner toplam tahmini | Tahmine kalan pay | Danışman 24 koşu ortalamasıyla doğrusal kıyas |
|---|---:|---:|---:|---:|
| stage_128, 24 koşu | 43.200 s (12 saat) | 37.500 s (10,42 saat) | 5.700 s (1,58 saat) | yaklaşık 23.963 s |
| stage_256, 32 koşu | 57.600 s (16 saat) | 50.001 s (13,89 saat) | 7.599 s (2,11 saat) | yaklaşık 31.951 s |

İki öneri de runner tahminine göre yaklaşık %15 pay bırakır. Sabit ortalama hızda her iki tavan yaklaşık 1800 s/koşu sınırına karşılık gelir. Öğrenci bilgisayarındaki daha yavaş CPU, kaynak paylaşımı, termal kısıtlama veya farklı senaryo süresi bu payı tüketebilir. Stage_32 sonuçları ve öğrencinin yerel süreleri görülmeden 12/16 saat **tamamlanma garantisi** veya evrensel bütçe olarak kabul edilmemelidir.

Danışman kararı gereklidir: Üç stage_128 paketi için 43.200 s ve üç stage_256 paketi için 57.600 s, öğrencilerin farklı makine performansı riski kabul edilerek teknik araştırma tavanı olarak onaylanacak mı? Gerekirse öğrenci başına ayrı tavan belirlenmelidir. Bu incelemede bütçe uygulanmadı.

## Onaydan sonra yalnız mevcut mekanizmayla yapılacaklar

Danışmanın stage_128/ogrenci_01 ve stage_256/ogrenci_01 örneklerine uygun olarak hedef paketler için sürümlü, paket kapsamlı hesap profilleri oluşturulmalı; ortak taslak profil değiştirilmemelidir. Her profilin hesap ayarları ve seed başlangıcı aynı kalmalı, yalnız onaylanmış grup tavanı ve teknik kapsamı belirtilmelidir. Her profil için belge hash'ine bağlı mevcut `.approval.json` kaydı gereklidir.

Her hedef paketin manifestinde yalnız profil kimliği/hash'i, `production_gate` ve grup tavanı metadata'sı güncellenmeli; `experiments` listesi, sekiz fiziksel kontrol, hesap ayarları ve seed'ler birebir korunmalıdır. Ardından yalnız ilgili paketin `package.json`, `SHA256SUMS.json`, README, mevcut mekanizmadaki `approval.json` ve merkezi atama kaydındaki ilgili paket pin/açıklaması tutarlı biçimde güncellenmelidir. Önce eski ve yeni manifest deney listesi karşılaştırılmalı; sonra `verify_package(require_approval=True)`, `preflight` ve başlatmasız testler çalıştırılmalıdır. Başka paketlerin onayları veya geçmiş sonuçları değiştirilmemelidir.

Mevcut stage_32 öğrenci grupları yerel depoda `not_started` görünüyor. Üst aşamaların açılması, teknik onayın yanı sıra danışmanın aşama sırası ve öğrenci makinesi süre değerlendirmesine bağlıdır.

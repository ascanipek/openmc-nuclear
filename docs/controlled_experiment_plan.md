# Kontrollü 3B demet deneyleri — taslak manifest

Durum: **taslak; hiçbir deney başlatılmadı.** Fiziksel temel [BEAVRS kaynak incelemesinde](reference_3d_model.md) sabitlenen MIT-CRPG commit'i `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22` ve H8 benzeri Cycle 1 HZP demetidir. Koşulun çekirdek kaynağı [HZP deney tablosu](https://github.com/mit-crpg/BEAVRS/blob/1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22/docs/specifications/expdata/expdata.tex), geometrinin kaynağı [resmî BEAVRS şartnamesidir](https://github.com/mit-crpg/BEAVRS/tree/1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22/docs/specifications/specifications).

## Önce sabitlenecek model sözleşmesi

- Fiziksel senaryo: H8 benzeri %1,6 yakıt; 975 ppm elementel bor; toplam borlu su 0,740582068 g/cm³; 566,483 K tekdüze malzeme sıcaklığı **model varsayımı**; 17×17 ve 24 RCCA; D=213 çekme adımı, yani aktif yakıta 23,72895 cm giriş. Girdilerin tam izotop atom yoğunlukları, yoğunluk ve yüzeyleri kaynak tablolarıyla karşılaştırılacak.
- **Karar bekliyor:** Yalıtılmış demetin yan sınırı ve su çevresi, z kapsamı, nozul/destek/ızgara ayrıntı düzeyi, üst/alt sınırlar ve kaynak dağılımı. BEAVRS bunları tek demet için ölçümsel bir referans olarak tanımlamaz. Karar kayda girmeden D2–D4 çalıştırılmamalı. İlk aday olarak yanlarda yansıtıcı sonsuz kafes, kaynak aktif yakıt içinde, eksende kaynakta gösterilen tam 0–460 cm aralığı değerlendirilebilir; bu seçim **henüz onaylanmış fiziksel tanım değildir**.
- Her konfigürasyonda kaynak commit'i, yerel kod revizyonu/dosya özeti, OpenMC sürümü, kesit kütüphanesi kimliği, fiziksel senaryo kimliği, **ayrı** koşu kimliği, seed, tüm hesap ayarları, sıcaklık, malzeme yoğunlukları ve nüklidleri, geometri ve sınırlar saklanacak. Fiziksel senaryo özeti veya hesap ayarı değişirse yeni koşu kimliği gerekir; eski sonuç otomatik tamamlandı sayılmamalı.
- Çıktılar yeni, benzersiz koşu dizinine yazılacak; eski `runs/` sonuçları ve referans dosyaları üzerine yazılmayacak. “completed”, yalnızca süreç ve beklenen dosyaların tamamlandığı anlamına gelir; geometri, istatistik veya BEAVRS deneysel doğruluğu anlamına gelmez.
- Ölçüm sözleşmesi: ham `k_eff ±` OpenMC MC standart hatası; 3B fisyon tally ortalaması/hatası, z kenarları, [z,y,x] yönü ve aktif yakıt maskesi; isteğe bağlı enerji/akı tally'si ancak amacı önceden yazılırsa. Piksel/pim değeri için hacim ve tarihçe başına normalizasyon açık olmalı. Eksenel dilimler, tüm aktif yakıt ve çubuklu/çubuksuz alt bölgeler ayrı tanımlanmalı; 2B 264 konum normalizasyonu her z'de körlemesine uygulanmamalı. Ortak toplamla göreli güç hesaplanırsa kovaryans veya bootstrap ile hata taşınmalı; yalnızca ham tally standart hatası “göreli güç hatası” diye sunulmamalı.
- Maliyet kaydı: geometri kurma ve dışa aktarma süresi, taşıma duvar/CPU süresi, tepe bellek, çıktı disk boyutu, aktif tarihçe sayısı ve tarihçe/s. Donanım, WSL/iş parçacığı ayarı ve eşzamanlı yük kaydedilmeli. Çalışma öncesinde eldeki RAM, disk ve zaman kotası ölçülüp güvenli durdurma sınırı belirlenmeli; bu taslak gerekçesiz sayısal eşik koymaz.
- Önceden tekil kabul kıstasları yazılacak. İstatistiksel kıstaslar D2'de gözlenen varyans/maliyet, hedeflenen kullanım (ör. sadece nitel profil mi, pin düzeyinde nicel kıyas mı) ve kabul edilebilir belirsizlik üzerinden belirlenecek. Aynı seed'li veya iç içe tarihçeli sonuçlar bağımsız örnek gibi birleştirilmeyecek.

## D1 — Geometri ve malzeme kontrolü

**Amaç:** Nötron taşımadan önce 3B tanımın kaynaktaki fiziksel girdileri gerçekleştirdiğini göstermek.

**Sabitler:** Yukarıdaki H8 HZP durumu ve sabitlenen kaynak commit'i; malzeme/nüklid tabloları. **Değişkenler:** Denetlenen z kesiti ve örnek nokta; amaçlı olarak 0, 213 ve 228 adım geometrileri (bunlar çalışma koşusu değildir). Yanal/eksenel sınır seçeneği yalnızca ayrı model varyantı olarak değerlendirilir.

**Kaydedilecekler:** Malzeme ve izotop dökümü, sıcaklık/yoğunluk karşılaştırması, yüzey/radyüs ve z düzlemleri, 24 kılavuz konumu, merkez tüp, çubuk işgali, 3B aktif-yakıt maskesi, çakışma/boşluk kontrolü, geometri ve kaynak özetleri; her farkın kaynak satırı ve açıklaması.

**Kabulün belirlenmesi:** Tablodaki fiziksel sayılar ve topoloji kaynak hassasiyeti içinde birebir uyuşmalı; koordinat sondaları yakıt/plenum/dashpot/soğurucu sınırlarının iki yanında doğru malzemeyi bulmalı. Sayısal tolerans, kayan nokta gösterimi ve kaynak basamak sayısına göre uygulamadan önce yazılır. XML metni veya nesne ID eşitliği kabul ölçütü değildir. Çakışma, kayıp hücre, yanlış 24+1 konum veya belgesiz yaklaşık yapı D1'i durdurur.

## D2 — Tek fiziksel koşulda artan hesap bütçesi

**Amaç:** D1'i geçmiş D=213 H8 koşulunun süre, bellek ve MC belirsizliği ölçeğini bulmak.

**Sabitler:** Geometri, malzemeler, sınırlar, kaynak dağılımı, tally/şema, iş parçacığı/donanım ve fiziksel durum. **Değişkenler:** Önceden sıralanmış az sayıda artan `particles × active batches` bütçesi; inactive batch sayısı kaynak yakınsama teşhisine göre seçilir. Bütçeler ve üst kaynak sınırı D1 sonunda yazılır. Tekrarlanan/nested seed sonuçları bağımsız sayılmaz.

**Kaydedilecekler:** Her bütçede ham `k_eff` ve hata, 3B tally/hata, kaynak yakınsama tanıları, zaman/bellek/disk/tarihçe/s, başarısız veya eksik çıktı nedeni.

**Kabulün belirlenmesi:** Önce hedef çıktı için gereken MC belirsizliği ve mevcut kaynak kotası tarif edilir; D2 verisiyle belirsizlik–maliyet eğrisi çıkarılır. İlerleme yalnızca kaynak yakınsaması makulse, belirsizlik hedefe yaklaşırsa, sonuçlar raporlanan hatalarıyla tutarlıysa ve maliyet sınırına uyarsa yapılır. Yakınsama, tek bir k değeri veya keyfî yüzde farkıyla ilan edilmez.

## D3 — Bağımsız tohumlarla tekrar

**Amaç:** D2'de seçilen tek bütçede hata raporlamasının ve koşu tekrarlanabilirliğinin ampirik denetimi.

**Sabitler:** D=213 fiziksel durumu, D2'den seçilmiş hesap bütçesi, yazılım/veri/donanım ayarları. **Değişken:** Birbirinden bağımsız önceden kaydedilmiş tohumlar ve benzersiz koşu kimlikleri; tekrar sayısı D2'de gözlenen varyans ve maliyetle belirlenir.

**Kaydedilecekler:** Tohum başına ham `k_eff`, standart hata, seçilmiş 3B tally/hatalar, kaynak tanıları ve maliyet; tohumlar arası ortalama/varyans ve raporlanan hatalarla uyum.

**Kabulün belirlenmesi:** Tekrar sayısı ve uyum testi/sayısal sınırı sonuçları görmeden belirlenir. Standartlaştırılmış farklar, hatalar ve olası korelasyon birlikte raporlanır; başarısız koşular dışlanır ama saklanır. “Benzer gözüküyor” veya seed eşitliği kabul ölçütü değildir.

## D4 — Önceden seçilmiş az sayıda temsilî koşul

**Amaç:** Çubuk konumunun fiziksel etkisini ve maliyetini sınırlı kapsamda görmek; tam çekirdek bank değerini ölçtüğünü iddia etmemek.

**Sabitler:** H8 yakıtı, su/bor/sıcaklık, geometri kapsamı, sınırlar, tally, D2–D3'te seçilmiş bütçe ve donanım. **Değişken:** [Eksenel şartnamedeki](https://github.com/mit-crpg/BEAVRS/blob/1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22/docs/specifications/specifications/axial/axialspec.tex) 0 (tam sokulu), 213 (HZP D), 228 (tam çekili) adım. Tohumlar koşullar arasında bağımsız seçilir; ortak rastgele sayı tasarımı istenirse kovaryans yöntemi önceden yazılır.

**Kaydedilecekler:** Her durumun ham `k_eff ± σ`, çubuk yakınındaki ve eksenel 3B fisyon/akı profilleri ile hataları, giriş derinliği ve malzeme işgal kontrolleri, maliyet; koşullar arası fark ve birleşik MC belirsizliği (bağımsız seed halinde).

**Kabulün belirlenmesi:** Geometri doğru yer değiştirmeli; gözlenen eğilim ve farklar fiziksel beklenti ile standart hatalar ışığında yorumlanmalı. Büyüklük için doğrudan ölçülmüş demet referansı yoktur, bu yüzden deneysel BEAVRS doğrulama eşiği konamaz. Önceden yazılmış belirsizlik ve maliyet hedefleri karşılanmazsa sonuç yalnızca keşifsel sayılır.

## Aşama kapıları ve raporlama

D1 kaynak/girdi uyumu ve sınır kararı olmadan D2 yok; D2'nin yakınsama ve maliyet değerlendirmesi olmadan D3/D4 bütçesi sabitlenmez. Her deneyin başarısı, çıktı dosyalarının varlığı, OpenMC sürecinin başarısı ve fiziksel yorum üç ayrı durum olarak tutulur. Son raporda girdi farkları, bütün denemeler ve başarısızlıklar, belirsizlikler, maliyetler ve **“yalıtılmış demet ölçümsel referansı bulunamadı”** sınırlaması birlikte gösterilir. Bu taslak herhangi bir deneyin çalıştırılması için izin yerine geçmez.

## v1 uygulama notu (2026-10-17)

Bu taslaktaki D=213 adım dönüşümü ve tam 0–460 cm eksenel kapsam, `beavrs_derived_3d_assembly_v1` uygulamasına **alınmadı**. Kullanıcının sonraki kararıyla v1 yalnızca aktif yakıt z=36,748–402,508 cm aralığını, uçlarda vakumu, yanlarda yansıtıcı sınırı ve aktif yüksekliğin yüzdesiyle çubuk ötelemesini kullanır. [İlk entegrasyon raporu](beavrs_3d_v1_integration_report.md) tek %50 koşusunu kaydeder. Bu koşu D2–D4 taramalarının veya deneysel doğrulamanın yerine geçmez; gelecekteki kontrollü deneyler v1 sözleşmesine göre ayrıca yeniden tanımlanmalıdır.

## Kullanıcı tarafından yürütülen v1 manifestleri (2026-10-17)

D2/D3/D4 için aktif yükseklik yüzdesiyle %0/%50/%100 giriş kullanan, kimliği ve bütçesi sabit [hazır manifestler ve işletim akışı](user_operated_experiments.md) oluşturuldu. Bu manifestler yukarıdaki D=213 taslak önerisini uygulamaz. Uzun koşular bu hazırlık sırasında başlatılmadı; aşama incelemesi ve çalıştırma kullanıcıya aittir.


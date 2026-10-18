# Kontrollü V2 pilot kapsam kararı v1

Tarih: 2026-10-18. Karar kaynağı: danışmanın bu görevde verdiği kullanıcı mesajı. Bu kayıt yalnız kontrollü pilot araştırmayı yetkilendirir; BEAVRS işletme/tasarım aralıklarının doğrulanması, kaynak yakınsaması, fiziksel kabul veya eğitim verisi kabulü değildir. D2/D3/D4 kayıtları ve nominal V2 entegrasyonu değişmedi. Kaynak BEAVRS commit'i `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22`; fiziksel dayanak ve belirsizlikler [referans incelemesinde](reference_3d_model.md), [parametre incelemesinde](parameter_space_v1_proposed.md) ve [önceki pilot önerisinde](v2_pilot_decision_proposal.md). Sayısal sınırlar kaynak BEAVRS doğrulanmış toleransı değil, danışmanın kabul ettiği araştırmacı önerisidir.

Sürümlü kapsam [v2_parameter_space_pilot_scope_v1.json](../configs/v2_parameter_space_pilot_scope_v1.json); sabit hesap profili [v2_calculation_profile_pilot_80k_4h_v1.json](../configs/v2_calculation_profile_pilot_80k_4h_v1.json). Mevcut `*.approval.json` şeması yalnız bu iki belgeyi danışmanın açık kapsam/profil kararıyla mühürler. Sekiz kontrol: U235 başlangıç zenginliği 1.6–3.1 wt%, yakıt T 556–576 K, su T 556–576 K, mutlak P 15–16 MPa, elementel B 0–975 ppm, pin pitch 1.25–1.27 cm, pelet yarıçapı 0.390–0.395 cm, çubuk girişi aktif yükseklik üzerinden %0–100. Nominal sıra 1.6 wt%, 566.483 K, 566.483 K, 15.51320325 MPa, 975 ppm, 1.25984 cm, 0.39218 cm, %50. Su fazı, T–P–yoğunluk, veri sıcaklığı ve geometri kontrolleri her koşuda ayrıca yapılır. Giriş yüzdesi BEAVRS adım ölçeğiyle eşdeğer değildir.

Hesap profili: 600 toplam, 300 inactive ve 300 aktif batch, 80.000 parçacık/nesil, 1 nesil/batch, 6 thread. Toplam 48 milyon, aktif 24 milyon parçacık geçmişi/koşu. Seed'ler 71001–71008. İlk grubun gerçek süre tavanı 14.400 s (4 saat). Sekiz koşu için D2-B2'nin tamamlanmış 1041.678 s ölçümü × 8 = 8333 s (2 saat 19 dakika); mevcut işçi başlangıç ön tahmininde ×1.5 rezerv uygulanınca 12.500 s (3 saat 28 dakika). Bu aktarım V1/D2 ölçümünden V2 koşullarına yapıldığı için garanti değildir. Tahmin kalan süreye sığmıyorsa yeni koşu başlamaz; 4 saat dolarken çalışan koşu işçi grup sinyaliyle durur. Başarılı önceki koşular ve kesilmiş koşunun kısmi dosyaları korunur; durum `budget_exhausted` olur, aynı grup kendiliğinden devam etmez.

## Sabit 32 → 8 + 24 bölümü

Kaynak [32 senaryolu katalog](../student_packages/v2_staged_draft_v1/stage_32/catalogue_total.json) salt okunur bırakıldı. [Bölme kaydı](../scenarios/v2_advisor_pilot_v1/split.json), [ilk sekiz kataloğu](../scenarios/v2_advisor_pilot_v1/initial_8_catalogue.json) ve [bekletilen 24 kataloğu](../scenarios/v2_advisor_pilot_v1/remaining_24_catalogue.json) fiziksel senaryo kimliklerini/kontrol değerlerini aynen korur. Kaynak 0-tabanlı indeksler aşağıdadır; kalan 24 otomatik başlamaz.

| Sıra | Kaynak indeks | Fiziksel seçim gerekçesi |
|---:|---:|---|
| 1 | 0 | Nominal %50, değişimler için ortak başlangıç |
| 2 | 22 | Aynı nominalde %0 giriş; eksenel çubuk ucu |
| 3 | 23 | Aynı nominalde %100 giriş; karşı uç |
| 4 | 9 | Tek değişken 3.1 wt% U235 üst örneği |
| 5 | 13 | Tek değişken 576 K su; T–P–yoğunluk bağı |
| 6 | 16 | Tek değişken 0 ppm bor; çözelti uç noktası |
| 7 | 18 | Tek değişken 1.25 cm pitch; geometri değişimi |
| 8 | 24 | Çok parametreli ilk Halton adayı; yakıt T, P, pelet ve diğer birleşik değişimleri de sınar |

İlk sekiz danışman paketi: [README](../student_packages/v2_advisor_pilot_v1/v2_advisor_pilot8_beavrs_v2_pilot_scope_v1/README.md), [manifest](../student_packages/v2_advisor_pilot_v1/v2_advisor_pilot8_beavrs_v2_pilot_scope_v1/manifest.json). Çalıştırma notebook'undaki Run All, ancak teknik paket onayı mevcutsa bağımsız işçiyi başlatır; `status` denetimi ve atomik grup dizini çift başlatmayı önler. Başarısız/durmuş grup yalnız açık `resume`; tamamlanan grup tekrarlanmaz. Sonuç notebook'u salt okumadır. Paket onayı kapsam/profil kararından ayrı bir teknik bütünlük adımıdır; fiziksel kabul değildir.

## Sonuç inceleme sözleşmesi

Koşu `report.html` ve `summary.json` içinde k±MC standart hatası, gerçekleşen/tahmini süre farkı, k/entropi geçmiş grafiği (ilk 300 batch inactive gölgesi), 20 eksenel fission ve kappa-fission payı, sabit geometrik `fuel_volume_fraction>0` maskesindeki sıfır ölçüm ve düşük sinyal sayıları, eski güvenilirlik filtresi kapsaması ve bu filtre dışı yerel MC bağıl hata dağılımı bulunur. Aynı dağılımlar düşük sinyal ve ölçülen toplam fisyonun ilk %95'ine katkı veren voxel'ler için ayrı verilir. Düşük sinyal tanımı: yakıt içeren voxel'de ortalama sıfır **veya** ortalama <5×MC standart hata **veya** maksimum ortalamanın 10^-6'sından düşük. Eşikler yalnız betimleyicidir. Sıfır tally'nin bağıl hatası tanımsızdır; sıfır fiziksel üretim veya sıfır belirsizlik sayılmaz. Kappa-fission fisyon enerji üretimi yaklaşımıdır, toplam ısı birikimi değildir. Her durumda `fields.npz` ham ortalama, MC standart hata, sabit geometri maskesi ve fiziksel koordinatları `[z,y,x]` düzeninde saklar. Yakınsama ve fiziksel kabul elle incelenir.

## Sonraki aşamalar için inceleme önerisi — otomatik kabul değil

Aşağıdaki sayılar **karar görüşmesi için aday inceleme çizgileri**dir; hiçbir yazılım bunları fiziksel/istatistiksel kabul olarak uygulamaz. D2-B2'de k MC SE=1.758×10^-4 ve önceki filtre 3641/5280 voxel idi; 20k koşulda 855/5280 sıfır tally görülmüştü. Çizgilerin anlamı ilk sekiz sonuçla yeniden ölçülmelidir.

| Aşama | Aday sayısal inceleme çizgisi | Gerekçe ve sınır |
|---|---|---|
| Kalan 24 | Her koşuda k MC SE ≤2×10^-4; sabit yakıt maskesinde pozitif-ortalama voxel'lerin ve sıfırların sayımı; ölçülen üretimin ilk %95'ini veren voxel'lerde bağıl MC hata p95 ≤10%; düşük sinyal bölgesinin ölçülen toplam fisyon payı ≤0.1% | D2-B2 bütçesiyle k hedefi olası, ama diğer çubuk konumlarında doğrulanmadı. Sıfır tally için bağıl hata uygulanmaz; sıfır sayısı ve dilim dağılımı ayrıca incelenir. |
| 128 toplam | Önceki çizgiler ve her çubuk-konum alt grubunda üst/alt dört eksenel dilimin normalize payının bağımsız yüksek bütçe tekrarına göre mutlak farkı ≤0.02/dilim; önemli voxel'lerin ≥%95 ölçülen katkısı için p95 ≤10% | Uzaysal uçlar k ile birlikte sınanır; yüksek bütçe referansı kesin gerçek değildir. Aday tekrarlar olmadan çizgi karara bağlanmaz. |
| 256 toplam | Önceki çizgiler ve sabit yakıt maskesinde sıfır tally oranı ≤%5; düşük sinyal payı ≤0.1%; k MC SE ≤2×10^-4; aktif pencere k ve entropi drift denetimi | Çok düşük sinyal bölgelerinde sıfır oranı fiziksel sonuç demek değildir. Bu çizgi 8 koşu verisiyle revize edilebilir; tek başına fiziksel kabul üretmez. |

İlk 8'den sonra: k/entropi geçmişinde belirgin geç drift, bağımsız tohum uyuşmazlığı veya üst/alt dilim profil kararsızlığı varsa **bütçe veya inactive sayısı artırımı** için ayrı yeni profil gerekir. Önemli toplam üretim taşıyan voxel'lerde yüksek bağıl hata veya sıfır tally varsa **parçacık bütçesi/mesh çözünürlüğü** yeniden tasarlanır. Sistematik geometri nokta kontrolü, malzeme/su bağıntısı, kaynak tanımı veya nükleer veri sorunu varsa **model/veri düzeltmesi** yapılır; ek parçacık bunun yerini tutmaz. Bu bulgular yoksa kalan 24 için ayrı teknik paket, süre bütçesi ve danışman incelemesi hazırlanır; bu kayıt kalan 24'ü başlatmaz.

## Nükleer veri ve gerçek XML

Kaydedilmiş nominal V2 [openmc.log](../runs/beavrs_3d/v2_integration/beavrs3d_v2_nominal_integration_v1/openmc.log) satır 33 gerçek girişin `model.xml` olduğunu, satır 78–81 Zr96'nın ENDF/B-VIII.0 HDF5 dosyasındaki 294 K ve 600 K probability table'larında negatif değer uyarısı verdiğini gösterir. Satır 159–163 Cd106 için benzer uyarı gösterir. Nominal koşu tamamlanmış statepoint ürettiğinden bu uyarı gözlenen koşuda **çalıştırma engeli değildir**. Nükleer veri etkisinin nicel incelenmesi ve alternatif işlenmiş veri karşılaştırması yapılmadı; fiziksel doğruluk belirsizliği sürer. Uyarı bastırılmadı. Yeni V2 koşucusu `export_to_model_xml` kullanır; OpenMC'nin `Model.run` varsayılanı aynı `model.xml` biçimidir. Eski koşu XML'leri değiştirilmedi/silinmedi.

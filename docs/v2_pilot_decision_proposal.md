# V2 sayısal kapsam, aşamalı pilot ve veri sözleşmesi — karar taslağı

Tarih: 2026-10-18. Bu belge danışman/araştırmacı kararı yerine geçmez. Model `beavrs_derived_3d_assembly_v2_proposed`; BEAVRS kaynak sürümü `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22`. Nominal kaynaklar ve sınırlamalar [reference_3d_model.md](reference_3d_model.md), [v2_nominal_precheck.md](v2_nominal_precheck.md) ve [parameter_space_v1_proposed.md](parameter_space_v1_proposed.md). Tam çekirdek ölçümüyle doğrudan doğrulanmış işletme aralığı yoktur. Yanma ve Xe bu kapsamda yoktur.

## Sekiz kontrolün sayısal önerisi

Bu öneri [ayrı sürümlü parametre dosyasında](../configs/v2_parameter_space_pilot_proposed_v1.json) `draft_unapproved` durumundadır. Birimler parametre adındadır. **Nominal** kaynak HZP girdilerinden ve genel işletme basıncından gelir; **alt/üst** sınırların tamamı araştırmacı örnekleme seçimidir. BEAVRS tasarım toleransı veya işletme izni değildir.

| Kontrol | Nominal | Alt | Üst | Nominal dayanağı; aralık dayanağı | Zorunlu doğrulama açığı |
|---|---:|---:|---:|---|---|
| U235 başlangıç zenginliği, wt% | 1.6 | 1.6 | 3.1 | H8 1.6% yakıt tablosu; 3.1 başka kaynak yakıt sınıfının etiketidir, aralık araştırmacı seçimi | Ara değerlerde sabit U234/U235 kütle oranı ve UO2 varsayımı kaynak 2.4/3.1 bileşimleriyle denetlenmeli |
| Yakıt T, K | 566.483 | 556 | 576 | Resmî model tekdüze nominal; ±10.483 K araştırmacı seçimi | Eksenel/işletme yakıt T alanı yok; tüm nüklid tabloları kontrolü |
| Su T, K | 566.483 | 556 | 576 | HZP 560°F dönüşümü; aralık araştırmacı seçimi | IF97 sıvı fazı ve termal saçılma kapsamı; yapısal malzemeler su T'ye eşitleniyor |
| Mutlak soğutucu P, MPa | 15.51320325 | 15.0 | 16.0 | Genel `Operating Pressure=2250 psia`, `1 psi=0.006894757 MPa`; aralık araştırmacı seçimi | HZP noktasına özgü P yok; borlu çözelti EOS doğrulanmadı |
| Elementel B, toplam çözelti ppm kütle | 975 | 0 | 975 | HZP 975 ppm; sıfır alt uç araştırmacı seçimi | Borlu çözelti yoğunluğu saf su IF97 + kütle ekleme yaklaşımı |
| Pim pitch, cm | 1.25984 | 1.25 | 1.27 | Kaynak demet geometrisi; dar aralık araştırmacı seçimi | Çakışma/kenar açıklığı ve üretilebilirlik/tolerans onayı yok |
| Pelet yarıçapı, cm | 0.39218 | 0.390 | 0.395 | Kaynak pelet kesiti; dar aralık araştırmacı seçimi | Kaplama içi 0.40005 cm sabit; gap modelinin fiziksel kabulü eksik |
| Çubuk girişi, aktif yükseklik % | 50 | 0 | 100 | %50 araştırma referansı; uçlar aktif yükseklik model kararı | Kaynak 0/228/D=213 adım ölçeğiyle eşitlenmez; %100 uç 5.08 cm ofsetli |

`resolve_proposed()` her sekiz girdiyi açıkça ister. Sıcaklık-basınç kombinasyonu IF97 sıkıştırılmış sıvı bölgesinde olmalı; basınç mutlaktır. 556/576 K × 15/16 MPa dört su köşesi ve yakıt T'nin 556/576 K köşeleri, kurulu kütüphane nüklidleri ile `c_H_in_H2O` için `interpolation` sıcaklık kapsamı ön kontrolünden geçti. Bu metadata denetimidir, taşıma/fiziksel kabul değildir. Önerilen geometri uçlarında `0.395 < 0.40005` cm ve `1.25 > 2×0.60198 = 1.20396` cm; dış kenar su boşluğu referans kadar pozitiftir. Bu birleşimler ileride her gerçek koşunun ön kontrolünde yeniden doğrulanır.

## Aşamalı merkezi liste ve paketler

[Dağıtım dosyası](../configs/v2_student_distribution_draft_v1.json) dört **yer tutucu** `ogrenci_01..04` kimliği tanımlar. [Pilot başlangıç profili](../configs/v2_calculation_profile_pilot_draft_v1.json) 80.000 parçacık/nesil, 600 batch, 300 inactive, 1 nesil/batch, 6 thread'dir; seed 71001'den başlar. Kaynak yakınsaması ve nihai hassasiyet onayı değildir; grup süre tavanı kasıtlı olarak `null`, dolayısıyla başlatma kapısı kapalıdır.

[Üretici](../src/reactor_pipeline/v2_pilot.py) mevcut [sekiz taslak senaryonun](../scenarios/v2_catalogue_draft_v1.json) **kontrollerini ve senaryo kimliklerini aynen** ilk sekize alır. Sonra her kontrol için nominalin iki tarafında 16 tek-parametre kontrolü üretir; nominal bir sınıra eşitse o yönde orta nokta seçilerek tekrar önlenir. Geri kalanı sabit tohum 20261018, sekiz asal tabanlı kaydırılmış Halton dizisi, sınırlar arasında doğrusal ölçekleme ile çok-parametreli örneklenir. Geçersiz/tekrar adaylar gerekçeleriyle katalog `rejected` alanına yazılır. Çıktı 32⊂128⊂256 tam ön ekidir. Fiziksel `scenario_id` model+referans config hash'i+sekiz kontrol; hesap profili/seed ayrı `run_id` alanına girer. Mevcut 8 nokta içinde de çok-parametreli nominal dışı koşullar vardır.

| Aşama | Toplam benzersiz fiziksel senaryo | Önceki aşamaya göre yeni | Kompozisyon | Dört yer tutucu paket |
|---|---:|---:|---|---|
| Pilot 32 | 32 | 32 | 8 korunmuş + 16 tek-parametre + 8 çok-parametre | 8'er yeni senaryo |
| Toplam 128 | 128 | 96 | Önceki 32 + 96 çok-parametre | 24'er yalnız yeni senaryo |
| Toplam 256 | 256 | 128 | Önceki 128 + 128 çok-parametre | 32'şer yalnız yeni senaryo |

Kataloglar, aşama artış dosyaları, 12 manifest ve her pakette **tek** `01_calistir.ipynb` ile **tek** `02_sonuclari_incele.ipynb`: [v2_staged_draft_v1](../student_packages/v2_staged_draft_v1). Aynı fiziksel senaryo paketler arasında tekrarlanmaz; aşama önekli grup kimliği eski aşamayı tekrar çalıştırmaz. Başlatma notebook'u kaynak/hücre içerik hash'leri, korunmuş kod, manifest, space/profil hash'leri ve `approval.json` kapısını kontrol eder; ardından mevcut bağımsız işçiye bağlanır. Çıktı/execution_count değişikliği notebook içerik hash'ini bozmaz; kaynak/hücre sıra değişikliği bozar. Çift başlatma grup dizininin atomik oluşturulmasıyla engellenir; completed/failed/stopped durumlarında kendiliğinden yeniden başlamaz. Sonuç notebook'u yalnız kayıtlı verileri okur ve girdi/hesap, k±MC hata, süre, `fields.npz` ve `summary.json` yollarını, kappa-fission ve k/entropi grafiklerini gösterir. `completed`, kabul değildir.

Taslak üretimini **hesap başlatmadan** taze çıktı dizininde tek komutla yeniden yapma:

```bash
cd /home/ascanipek/openmc-proje
PYTHONPATH=$PWD/src /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python scripts/v2_pilot.py student_packages/v2_staged_draft_yeni
```

Karardan sonra onaylanmış **yeni sürümlü** space/profil/dağıtım dosyaları ve SHA256'ya bağlı ayrı `*.approval.json` kayıtları hazırlanmalı; yer tutucu isimler gerçek atamayla değiştirilmelidir. Üreticinin `--space`, `--profile`, `--distribution` bayraklarıyla aynı tek komut yeni dizinde katalog ve hash-pimli paketleri üretir. Üretim için her paket `approval.json` teknik/danışman onayını ayrıca ister; hiçbir eski taslak sessizce açılmaz. Danışman sınırları mevcut sekiz noktayı dışlıyorsa, “ilk sekizi aynen koru” ilkesiyle çelişir ve yeni kapsam kararı gerekir. Tek profil bütün aşamalara uygulanacağı için grup süre tavanı 8/24/32 koşulluk paketlerde ayrı incelenmeli; önerilen değer henüz `null`dır.

Bölme [dataset.py](../src/reactor_pipeline/dataset.py) `scenario_sha256_80_10_10_v1` deterministik hash kuralıyla senaryo temelinde yapılır: 32'de train/kalibrasyon(doğrulama)/test 28/2/2; 128'de 106/13/9; 256'da 208/25/23. Aynı fiziksel senaryonun farklı seed veya bütçesi aynı bölmededir. Pilot küçük doğrulama/test sayısı kararsız metrik üretir; öğrenme eğrisiyle 32→128→256 kazanımı ve tekrarlar değerlendirilmeli, 256 yeterli sayılmamalı. Bu aşamada ML eğitimi yoktur.

## Hesap bütçesi ve ölçüt önerisi

Ölçülen v1 süreler (6 thread, aynı 600/300 batch): D2-B1 20k: 268.10 s; D2-B2 80k: 1041.68 s; D2-B3 320k: 4456.95 s; D4 %0/%100 20k: 268.16/253.75 s. D3 20k tekrarları 279.84/283.39 s. Başlangıç 80k profili, D2-B2'de k MC hatasının 0.0001758 olmasına ve aktif-sinyal kapsamasının B1'e göre artmasına dayanır. D4 %100 k MC hatası 20k'da 0.0002855 olsa da uzaysal üst kuyruk zayıftır; %50'de 20k'nın 5.280 yakıt voxelinden 855'i sıfır ölçülmüştür. **Hiçbir tek bütçe bütün çubuk konumlarında uzaysal alanı otomatik kabul ettirmez.**

Aşağıdaki merkez maliyet D2-B2'nin 1041.68 s/koşu süresini yeni v2 koşularına aynen taşıyan kabaca ölçeklemedir; fiziksel durum, donanım yükü, disk, Jupyter dışı işçi ve sıcaklık/çubuk konumu süreyi değiştirebilir. CPU-saat burada 6 thread × duvar-saat **tahsis edilmiş çekirdek-saat** tahminidir, ölçülmüş CPU kullanımı değildir. Dört öğrenci aynı anda, toplam en az 24 uygun çekirdekte ve ek yük yoksa ideal duvar süresi toplamın dördüdür; gerçek paralel kapasite bilinmiyor. %50 süre payı yalnız planlama rezervidir, garanti değildir.

| Toplam senaryo | Yeni aşama koşusu | Seri duvar, saat | 6-thread çekirdek-saat | 4 eşzamanlı işçi ideal duvar, saat | %50 rezervli seri duvar, saat |
|---:|---:|---:|---:|---:|---:|
| 32 | 32 | 9.26 | 55.56 | 2.31 | 13.89 |
| 128 | 96 | 37.04 | 222.22 | 9.26 | 55.56 |
| 256 | 128 | 74.07 | 444.45 | 18.52 | 111.11 |

128/256 satırları **ilk günden toplam** maliyettir; artımlı yeni aşama seri süreleri yaklaşık 27.78 ve 37.04 saattir. Seçilmiş %0/%50/%100 ve bir çok-parametreli vakada 320k/600/300 referans tekrarları ayrıca önerilir. D2-B3 hızında dört yüksek bütçe koşusu yaklaşık 4.95 seri duvar saati / 29.7 çekirdek-saat eder; 80k koşularının *yerine* geçerse artış yaklaşık 3.79 saat / 22.8 çekirdek-saattir. Bu yalnız bütçe taslağıdır, hiçbir referans manifesti başlatılmadı.

Aşağıdaki eşikler **araştırmacı kararı için adaydır**, otomatik kalite/gerçeklik onayı değildir:

- k için raporlanan MC standart hata hedefi örneğin `≤2×10^-4`; ayrıca aktif pencere ve bağımsız tohum k karşılaştırması, kaynak entropisi ve gecikmiş drift açıkça incelenir. D2-B2 bu tek sayısal hedefi %50 için karşılar; diğer konumlar ve kaynak yakınsaması hakkında hüküm vermez.
- Uzaysal hedefte sabit geometri maskesi `fuel_volume_fraction>0` tüm koşullarda korunur. Sıfır ölçümlü voxel, toplam sinyalin z boyunca payı, örnek tanı olarak `σ/μ≤20%` olan voxel sayısı ve taşıdığı `Σμ` payı; ayrıca `Σσ_i/Σμ_i` katkı-ağırlıklı üst-belirsizlik göstergesi raporlanır. Aday inceleme çizgileri sinyal kapsaması `≥99.9%` ve `Σσ/Σμ≤1%` olabilir; D2-B2'nin ikinci göstergesi %0.738'dir. Bunlar düşük sinyalli bölgeyi “doğru” ilan etmez. Üst/alt dilimlerde mutlak MC hata ve normalize profil farkı ayrı incelenmelidir.
- Fisyon enerji alanı `kappa-fission` toplam yerel ısı değil, fisyon enerjisi üretimi yaklaşımıdır. Normalize hedef `K_i / Σ_{j∈fuel} K_j`; ham tally kısmi voxel katkısını zaten içerdiği için ikinci kez hacimle çarpılmaz. Ortak paydanın kovaryansı alan hata haritasında çözülmemiştir; ham MC standart hataları saklanır. Fiziksel doğruluk ayrıca doğrulanmadıkça `acceptance.json` yazılmaz.

## Veri aktarımı ve V2 entegrasyon durumu

[v2_dataset.py](../src/reactor_pipeline/v2_dataset.py) yalnız kayıtlı v2 grup sonuçlarını okur. Çıktı `index.json` sekiz `physical_controls`, ayrı `derived_inputs` (su yoğunluğu/yöntemi, demet pitch'i, rod z uçları, uygulanan malzeme T ve yakıt/su atom yoğunlukları), seçilen ve bütün kaynak `run_id` değerlerini kaydeder. `samples.npz` normalize [z,y,x] kappa hedefini, ham fisyon/kappa/flux ortalama ve MC standart hatalarını, yakıt/AIC/B4C hacim kesirlerini, sıfır maskelerini, x/y/z kenarlarını ve k/entropi geçmişini korur. `splits.json` senaryo-temelli bölmeyi, `train_preprocessing.json` yalnız train özetini taşır. `--preview` tamamlanan ama kabul edilmeyen koşuları açıkça `preview_not_accepted` sayar; normal aktarım sadece aynı `run_id` için kaynak yakınsaması ve fiziksel inceleme işaretli kabul kaydını alır. Tek senaryonun tekrarı gelişigüzel ortalanmaz; en yüksek aktif tarihçeli koşu belirli kuralla seçilir, tüm kaynaklar listelenir. Pitch değişince x/y fiziksel kenarları senaryodan senaryoya değişir; aktarım artık her örneğin 17×17×20 koordinatını kendi çözülmüş demet geometrisine karşı doğrular ve örnek bazında saklar. Boyut, eksen sırası, birim veya çözülmüş geometriyle uyuşmayan ağ reddedilir. Sayısal pilot manifestinden iki farklı pitch için sentetik `fields.npz` üretip birlikte aktarımı ve bozuk-koordinat reddini test ettik; gerçek MC başlatılmadı.

[03_v2_nominal_entegrasyon.ipynb](../notebooks/03_v2_nominal_entegrasyon.ipynb) değişmedi: sabit tek 100/50 batch × 10k parçacık, seed 61001. Kullanıcı koşusu `completed`: k=0.98120655 ±0.00130724, süre 32.485 s, kabul `not_assessed`, yakınsama `review_required`. V1'in aynı küçük %50 entegrasyonu k=0.98216630 ±0.00115906 idi; tohumlar farklı, ayrıca v2 su çözeltisi yoğunluğu 0.740580860261 yerine kaynak tablo v1 değeri 0.740582068 g/cm³'tür (fark −1.20774×10^-6 g/cm³). Bu sonuçlar fiziksel girdileri birebir aynı olan iki koşu değildir; eşit k bekleme veya bu farktan fiziksel doğruluk hükmü çıkarma doğru olmaz.


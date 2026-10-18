# V2 nominal girdi ön kontrolü ve küçük entegrasyon

Sabit kaynak: MIT-CRPG BEAVRS şartname 3.0.2, commit `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22`; `docs/specifications/specifications/specifications.tex` satır 84, Overview / Summary of key model parameters / Performance: `Operating Pressure & 2250 psia`. Yerel kaynak kopyası `docs/sources/beavrs_1ccae04/specifications.tex`, SHA256 `1ac0506caf7459ab3cf04803b9326c72a5ac650083cfe341d50617bcb1b4ba74`. NIST dönüşümü `1 psi = 0.006894757 MPa`; `2250 psia = 15.51320325 MPa` **mutlak**. Bu genel işletme basıncıdır; HZP ölçümüne özgü basınç verilmemiştir. Araştırmacının önerdiği 15–16 MPa aralığı ayrı bir çalışma seçimi olup kaynak aralığı değildir.

`v2_integration.nominal_comparison()` ve `preflight()` taşımayı başlatmadan v1 kaynak tablosu ile v2 türetilmiş girdileri karşılaştırır. Nominal kontroller: 1.6 wt% U235, yakıt/su 566.483 K, 975 ppm elementel B, pin pitch 1.25984 cm, pelet yarıçapı 0.39218 cm ve %50 giriş. Kaynak nominal yakıt tablosu v2'de birebir korunur; diğer yakıt zenginlikleri araştırmacı varsayımıdır.

| Fiziksel girdi | v1 | v2 nominal | Fark |
|---|---:|---:|---:|
| Su/borlu çözelti kütle yoğunluğu (g/cm³) | 0.740582068 | 0.7405808602612968 | −0.0000012077387033 (−0.00016308%) |
| Su toplam atom yoğunluğu (atom/b·cm) | 0.07423630905767632 | 0.07423618061506503 | −1.284426113×10⁻⁷ |
| Su H1 atom yoğunluğu (atom/b·cm) | 0.04945635958751276 | 0.04945627100118367 | −8.858632909×10⁻⁸ |
| Su O16 atom yoğunluğu (atom/b·cm) | 0.024673179393859237 | 0.024673139538884822 | −3.985497441×10⁻⁸ |
| Su B10/B11 atom yoğunluğu (atom/b·cm) | 7.9714579589×10⁻⁶ / 3.2247234463×10⁻⁵ | 7.9714792754×10⁻⁶ / 3.2247320696×10⁻⁵ | +2.13×10⁻¹¹ / +8.62×10⁻¹¹ |
| Yakıt, He, zircaloy, SS304, AIC, B4C yoğunluk ve izotop atom yoğunlukları | kaynak | kaynak | sıfır |
| Tüm yedi malzeme sıcaklığı | 566.483 K | 566.483 K | sıfır |

Bu atom yoğunluğu farkları OpenMC malzeme nesnesinin `get_nuclide_atom_densities()` değerleridir. Kaynak tabloda verilen sayılar `ao` oranı olarak OpenMC’ye aktarılıp kütle yoğunluğuna normalize edilir; ham tablo girdileri ile üretilmiş atom yoğunlukları ayrı tutulur.

V2 su yoğunluğu saf su için OpenMC 0.16 IF97 Region 1 bağıntısından ve `rho_solution = rho_pure/(1-975×10^-6)` yaklaşımından gelir. Kaynak su tablosu ise sabit ve yuvarlatılmış izotop yoğunluklarıdır. Bu nedenle aynı kontrol etiketleri aynı fiziksel girdiler anlamına gelmez; v2 sonucu v1 referansının tam tekrarı olarak sunulamaz. v2 borlu çözelti EOS doğrulanmamıştır.

Geometri konfigürasyonu, 24 kılavuz/17×17 yerleşim, aktif yükseklik 365.76 cm, çubuk koordinatları, X/Y reflective ve z uçları vacuum sınırları birebirdir. Başlangıç kaynağının uzaysal kutusu ve fissionable kısıtı, 17×17×20 mesh, `fission`, `kappa-fission`, `flux`, tracklength tally ve sıcaklık interpolasyon yöntemi eşittir. Nükleer veri metadata ön kontrolü nominal sıcaklıklar için tüm gerekli nüklid ve `c_H_in_H2O` tablolarının kapsandığını doğrular; bu taşıma sonucu veya fiziksel doğrulama değildir.

Kullanıcının başlatabileceği tek küçük koşu: `manifests/beavrs3d_v2_nominal_integration_v1.json` ve `notebooks/03_v2_nominal_entegrasyon.ipynb`. 100 toplam/50 inactive batch, 10.000 parçacık/nesil, 1 nesil/batch, 6 thread, seed 61001. Sabit manifest ve v1 config SHA denetlenir. Run All son hücrede mevcut bağımsız WSL işçisini başlatır; bu teslimde çalıştırılmadı. Çıktı bütünlüğü tamamlanması, kaynak yakınsaması veya fiziksel kabul anlamına gelmez. D3/D4 araştırma v1 paketinden ve ana eğitim üretiminden ayrıdır.

Önerilen araştırmacı aday sınırları: zenginlik 1.6–3.1 wt%, yakıt T 556–576 K, moderatör T 556–576 K, basınç 15–16 MPa, bor 0–975 ppm, pitch 1.25–1.27 cm, pelet yarıçapı 0.39–0.395 cm, giriş 0–100%. Bu sınırlar BEAVRS tarafından doğrulanmış tarama aralığı değildir. T/P birlikte IF97 sıkıştırılmış sıvı bölgesinde kalmalı; malzeme sıcaklıkları nükleer veriyle köşelerde denetlenmelidir. Pitch > iki kat en büyük dış kılavuz/kaplama yarıçapı, pelet < kaplama iç yarıçapı, dış demet kenar su payı > 0 ve 0≤giriş≤100 gereklidir. Bu birleşimler ayrıca taşıma ve fiziksel tasarım incelemesi ister. Otomatik tarama hazırlanmadı ve onaylanmadı.



# V2 ana veri üretimi — yazılım hazırlığı, üretim kapalı

Model `beavrs_derived_3d_assembly_v2_proposed`, MIT-CRPG BEAVRS commit `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22` ve yerel kaynak tablosu üzerine kurulu idealize yalıtılmış 17×17×20 demettir. Tam çekirdek ölçümleriyle doğrudan doğrulanmış bir işletme modeli değildir. D3 çalışırken onun hash’lenmiş v1 kodu, config’i, manifesti ve paketi değiştirilmez. Bu sürüm yalnız yeni `v2_*.py`, yeni config ve taslak paketler kullanır. Yanma/Xe kapsam dışıdır.

Sekiz fiziksel kontrol `parameter_space.resolve_proposed()` aracılığıyla U izotop kütle oranı, malzeme sıcaklıkları, basınçtan türetilmiş saf su yoğunluğu ve yaklaşık borlu çözelti yoğunluğu, B izotopları, kafes/dış sınır, pelet/gap ve rod tipine bağlanır. `build_proposed()` bunları OpenMC modeline verir; `nuclear_data_precheck()` nüklid/termal saçılma ve istenen sıcaklıkların HDF5 aralığını denetler. `temperature_method=interpolation` kaydedilir. Basınç genel BEAVRS işletme değeri 2250 psia = 15,51320325 MPa mutlak; HZP noktasına özgü basınç **eksik**. Borlu çözelti yoğunluğu IF97 saf su + bor kütle payı yaklaşımıdır; ölçülmüş borlu çözelti EOS değildir. Yeni zenginlikte U234/U235 kütle oranı 1,6% kaynağından sabittir; 2,4/3,1 tablolarıyla tam karşılaştırma **eksik**. Yakıt dışı yapılar tekdüze su sıcaklığına atanır; özgül eksenel termal alan **eksik**. Pitch/pelet için kaynakla doğrulanmış tarama aralığı **eksik**.

`configs/v2_parameter_space_v1.json` fiziksel nominal değerleri, açıkça onaysız öneri aralıklarını ve birleşim kısıtlarını; `configs/v2_calculation_profile_v1.json` hesap bütçesini ayrı tutar. Şimdiki profil yalnız mevcut küçük entegrasyon manifestinin 100/50 batch ve 10.000 parçacık ayarlarını **taslak örnek** olarak taşır; nihai üretim bütçesi değildir. Sıcaklık, basınç, pitch ve pelet aralıkları `null` olduğu için yalnız nominal değerleri kullanılır. D3/D4 açık incelemesi, aralık kararı, bütçe ve kabul politikası olmadan üretim açılamaz. IF97 yöntem sınırları ve geometri çakışma sınırları deney aralığı sayılmaz.

WSL Ubuntu terminalinde, `openmc-proje` hesap ortamıyla taslak katalog ve çakışmasız öğrenci paketleri oluşturma:

```bash
cd /home/ascanipek/openmc-proje
export PYTHONPATH=$PWD/src
/home/ascanipek/miniconda3/bin/conda run -n openmc-proje python scripts/v2_production.py generate scenarios/v2_catalogue_draft_v1.json --count 8 --seed 20261018
/home/ascanipek/miniconda3/bin/conda run -n openmc-proje python scripts/v2_production.py allocate scenarios/v2_catalogue_draft_v1.json student_packages/v2_draft_v1 --students ogrenci_01 ogrenci_02
```

Katalog `scenario_id` kimliğini model + referans config hash’i + sekiz fiziksel kontrolden hesaplar. Hesap profili ve seed ayrı `run_id` oluşturur. `rejected` listesi geçersiz veya yinelenen adayları nedenleriyle kaydeder. `generation_status=incomplete_rejected` ise paylaştırma reddedilir. Paketlerde bir sabit manifest, iki notebook, hash listesi, model/config kimlikleri ve README bulunur. Paketlerin `state=draft_unapproved` olması amaçlıdır; `launch` bunları başlatmaz. Mevcut D3/D4 paketleri yayımlandığı gibi kalır.

Gelecekte üretim için **ayrı danışman kararı** gerekir: sekiz sayısal aralık, fiziksel varsayım ve birleşimlerin doğrulanması, D3/D4 sonrası son hesap profili ve grup süre bütçesi, veri kabul yöntemi. Bu karar verildikten sonra her iki config `status=approved` olarak sürümlenir; her config yanında `<dosya>.approval.json` içinde `status=approved`, config dosyasının SHA256 değeri `document_sha256` ve boş olmayan `reviewer` bulunur. Yeni katalog ve yeni paketler üretilir. Her paket için ayrıca `approval.json` içinde `status=approved`, `package.json` SHA256 değeri `package_sha256` ve `SHA256SUMS.json` SHA256 değeri `hashes_sha256` gerekir. Mevcut taslak paketlerin onayla sonradan sessizce üretime dönüşmesine izin verilmez; yeni sürüm hazırlanır. Kullanıcı onayı verilmeden bu kayıtlar oluşturulmaz.

Onaylı paketin `01_calistir.ipynb` notebook’u WSL `openmc-proje` kernelini, nükleer veri yolunu, hash’leri ve ön kontrolü gösterir. Run All yalnız onaylı paketi ayrık WSL process group işçisiyle başlatır. Kayıtlı grup varsa yeniden başlatmaz. Durum/log/PID yollarını basar. `02_sonuclari_incele.ipynb` yalnız kayıtlı tamamlanmış ara sonuçları okur; completed fiziksel/statistiksel kabul değildir. CLI salt okuma: `python scripts/v2_production.py status <paket_dizini>` veya `results`. Açık operatör eylemi olarak `stop` ve `resume` komutları vardır; notebook kendiliğinden resume yapmaz. Sabit grup bütçesi içinde kalan süre ve yeni koşu için pilot süre × 1,5 tahmini denetlenir; bu tahmin garanti değildir. Bütçe bitince yeni koşu başlamaz; etkin koşu process group düzeyinde kesilir, çıktı kısmi/başarısız sayılır.

Her tamamlanmış koşu `resolved_config.json`, `status.json`, `summary.json`, `fields.npz`, `openmc.log`, `statepoint.*.h5`, `report.html` ve profil/entropi görsellerini taşır. Grup `manifest.json`, `comparison.csv/html`, `status.json`, `group.log` taşır. Alan sırası `[z,y,x]`; `kappa-fission` fisyon enerjisi üretimi yaklaşımıdır. MC standart hata fiziksel doğruluk yüzdesi değildir. Fiziksel kabul, `acceptance.json` kayıtları ve ayrı inceleme gerektirir.

Salt kayıtlı veriden eğitim önizlemesi/aktarım:

```bash
/home/ascanipek/miniconda3/bin/conda run -n openmc-proje python scripts/v2_production.py export exports/v2_preview v2_ogrenci_01_beavrs_v2_eight_controls_proposed_v1 --preview
```

`--preview` yalnız completed koşuları `preview_not_accepted` diye işaretler; varsayılan üretim aktarımı yalnız aynı `run_id` için açık fiziksel ve kaynak yakınsama incelemesi olan `acceptance.json` kayıtlarını alır. Çıktı `samples.npz`, `index.json`, `splits.json`, `train_preprocessing.json` içerir. Aynı senaryonun tekrarları tek fiziksel örnek ve tek bölme olur; en çok aktif tarihçeli koşu seçilir, tüm kaynak koşular indekslenir. Ham ortalama/standart hata, maskeler ve fiziksel koordinatlar korunur. D2, v1 veri sözleşmesinde tek fiziksel senaryodur; v2 modeline karıştırılmaz.

V2 nominal küçük entegrasyon notebook’u `notebooks/03_v2_nominal_entegrasyon.ipynb` bağımsızdır. Run All yalnız kullanıcı tarafından başlatılmalıdır; entegrasyon fiziksel kabul değildir. Temiz ortam kurulumu ve gerçek v2 üretim koşusu henüz sınanmadı.

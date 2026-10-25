# V2 ek 128 Halton senaryosu — Kaggle CPU

Bu klasör, mevcut `ogrenci_04` Kaggle CPU akışını dört yeni 32 koşuluk gruba uyarlar. Fizik modeli, ENDF/B-VIII.0 HDF5 verisi, 3B ölçüm/çıktı şeması, OpenMC 0.16.0 kurulum hücresi, süre sınırı, kaldığı yerden devam ve hafif teslim ZIP'i aynı kod yolunu kullanır. Önceki 256 senaryo ve öğrenci paketleri değiştirilmez. `completed`, fiziksel doğrulama, kaynak yakınsaması veya eğitim verisi kabulü değildir.

| Seçim | Halton indisi | Koşu | MC seed aralığı | Sabit manifest |
| --- | ---: | ---: | ---: | --- |
| `halton_01` | 233–264 | 32 | 72001–72032 | `project/student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1/manifest.json` |
| `halton_02` | 265–296 | 32 | 72033–72064 | `project/student_packages/v2_halton128_v1/halton_02/v2_halton_02_beavrs_v2_pilot_scope_v1/manifest.json` |
| `halton_03` | 297–328 | 32 | 72065–72096 | `project/student_packages/v2_halton128_v1/halton_03/v2_halton_03_beavrs_v2_pilot_scope_v1/manifest.json` |
| `halton_04` | 329–360 | 32 | 72097–72128 | `project/student_packages/v2_halton128_v1/halton_04/v2_halton_04_beavrs_v2_pilot_scope_v1/manifest.json` |

Örnekleme tohumu **20261018**, halihazırdaki kaydırılmış Halton dizisinin sekiz kaydırma ve asal tabanı aynıdır. MC seed'leri ayrıdır ve önceki manifestlerdeki 71001–71032 değerleriyle çakışmaz. Kaynak `project/scenarios/v2_halton128_v1/catalogue_new_128.json`, aralıklar `project/configs/v2_parameter_space_pilot_scope_v1.json` içindedir. Dört paket yeni bir onay katmanı kullanmaz; mevcut profil, paket hash ve teknik onay kayıt biçimiyle sınırlı araştırma amaçlı sabitlenmiştir. Sayısal hesap ayarı **80.000 parçacık/nesil, 600 toplam batch, 300 inactive, 1 nesil/batch, 6 onaylı thread**; Kaggle'da gerçek CPU kotasına göre thread en çok 6 seçilir ve kullanılan değer kaydedilir. Her 32'lik grubun toplam süre tavanı **86.400 saniye (24 saat)**, varsayılan tek oturum bütçesi **10 saat**tir. Süre tahmini ve platformun oturumu sürdürmesi garanti değildir.

## Kaggle'da kullanım

1. [v2_128_kod_dataset.zip](v2_128_kod_dataset.zip) dosyasını kod Dataset'i olarak yükleyin. Kaggle ZIP'i açtıktan sonra Dataset kökünde `bundle_hashes.json`, `kaggle_runner.py` ve `project/` bulunmalıdır. [01_kaggle_calistir.ipynb](01_kaggle_calistir.ipynb) dosyasını ayrıca Notebook olarak import edin.
2. Aynı ENDF/B-VIII.0 nükleer veri Dataset'ini Input olarak bağlayın; açık dosyalar arasında bir `cross_sections.xml` ve işaret ettiği HDF5 dosyaları bulunmalıdır. Büyük kütüphane `/kaggle/working` içine kopyalanmaz.
3. **Accelerator None (CPU)** seçin. OpenMC kurulumu gereken ilk oturumda Internet'i açın. İlk hücrede yalnız `NUCLEAR_DATASET_ROOT`, `CODE_DATASET_ROOT`, `SELECTED_STAGE` ve `SESSION_BUDGET_SECONDS` değerlerini Kaggle'daki gerçek yollara ve bütçeye göre ayarlayın. Varsayılan `SELECTED_STAGE="halton_01"` değeridir.
4. **Run All**, seçili 32 koşunun tablosunu ve başlatmasız ön kontrolü gösterir, sonra yalnız bu gruptaki eksik koşuları sırayla hesaplar. Sonraki gruba otomatik geçmez. `halton_02`–`halton_04` için aynı notebook'ta yalnız seçimi değiştirin.

Her koşunun `resolved_config.json`, `status.json`, `summary.json`, `fields.npz`, `openmc.log`, `model.xml`, statepoint ve raporları `/kaggle/working/v2_groups/<grup>/` altında kalır. Alanlar ve standart hatalar mevcut **[z,y,x] = 20×17×17** sözleşmesini kullanır. `/kaggle/working/deliveries/` içindeki hafif ZIP, mevcut transfer biçimindedir; büyük statepoint'i içermez. Statepoint için tam `v2_groups/` Output'unu da saklayın.

Kaggle `/kaggle/working` içeriğini yeni oturuma kendiliğinden taşımaz. Kısmi koşudan sonra Output'u Dataset olarak yeni oturumun Input'una bağlayıp **aynı grubu** seçin. Kaydedilmiş tamamlanan koşuların manifesti, girdileri ve statepoint'i doğrulanır; yalnız eksikler çalışır. `Save & Run All` temiz bir oturum başlatır; önceki Output bağlanmazsa koşular yeniden başlayabilir. `failed` ve `budget_exhausted` gruplar otomatik sürdürülmez. Kullanıcı oturum bütçesi nedeniyle `stopped` olan grup, Output geri bağlanınca devam edebilir.

## Merkezi sonuç toplama

Hafif teslim ZIP'i mevcut `v2_transfer.import_zip` işleviyle, bu yeni kolun sabit atama kaydı verilerek içe alınır. Proje kökünden WSL Ubuntu `openmc-proje` ortamında, ZIP yolunu değiştirerek:

```bash
/home/ascanipek/miniconda3/bin/conda run -n openmc-proje python -c "import sys; sys.path.insert(0, 'src'); from reactor_pipeline import v2_transfer; print(v2_transfer.import_zip('YUKLENEN_TESLIM.zip', assignment_path='kaggle/v2_128/project/configs/v2_student_assignment_v1.json'))"
```

Windows terminalinden aynı komut `wsl.exe -d Ubuntu --` önekiyle çağrılır. Var olan merkezi atama dosyası bu yeni kol için değiştirilmediğinden, varsayılan `scripts/v2_transfer.py import` çağrısı yerine yukarıdaki mevcut işlevin `assignment_path` parametresi gerekir. İçe aktarma yalnız doğrulanmış teslim kaydı oluşturur; otomatik eğitim verisi kabulü vermez.

`build_bundle.py`, kaynak 256 kataloğunun son Halton indisini ve üretici hash'ini doğrulayan hazırlama kaydıdır. Normal Kaggle kullanımında çalıştırılmaz. Bu pakette gerçek Kaggle/MC koşusu yapılmadı; yalnız yerel başlatmasız doğrulama uygulanır.

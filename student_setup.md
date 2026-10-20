# Öğrenci kurulum ve deney rehberi

Bu rehber, projeyi **bir kez kurmak** ve danışmanınızın size atadığı deneyleri çalıştırıp teslim etmek içindir. Hesaplar Windows Python'unda değil, **WSL2 Ubuntu** içindeki `openmc-proje` Conda ortamında yapılır. Komut bloğunda “PowerShell” yazmıyorsa komutu **Ubuntu terminaline** yazın.

| Yol haritası | Ne yapacaksınız? |
|---|---|
| 1. Bir kez kurulum yap | Ubuntu, Conda, proje, OpenMC verisi ve notebook kernelini hazırla. |
| 2. Kendi deney notebook'unu çalıştır | Yalnız atanmış, teknik onaylı pakette `01_calistir.ipynb` dosyasını aç. |
| 3. Sonuçları incele | Durumu sorgula ve `02_sonuclari_incele.ipynb` dosyasını aç. |
| 4. ZIP teslimini oluştur | Mevcut teslim betiğiyle ZIP üret ve danışmanına gönder. |

**Sizin değiştireceğiniz bilgiler:** Danışmanın verdiği GitHub adresi, varsa arşivin tam yolu, öğrenci kimliğiniz (`ogrenci_02` gibi), açmanıza izin verilen aşama (`stage_32` gibi) ve kendi paketinizin yolu. Manifestteki parametreleri, seed'leri, hesap profilini, hash ve onay dosyalarını değiştirmeyin.

## Bir kez yapılacak kurulum

### 1. WSL2 Ubuntu ve projeyi hazırla

Ubuntu zaten kuruluysa kurulumu tekrarlamayın. Gerekirse **Windows PowerShell'i yönetici olarak** açın:

```powershell
wsl --install -d Ubuntu
wsl --list --verbose
```

Listede Ubuntu için `VERSION` değeri `2` olmalıdır. Kurulum yeniden başlatma isterse tamamlayın, sonra Ubuntu kullanıcı adınızı ve parolanızı oluşturun. [WSL kurulum yardımı](https://learn.microsoft.com/en-us/windows/wsl/install).

Bundan sonraki komutları **Ubuntu terminalinde** çalıştırın:

```bash
conda --version
git --version
```

Conda yoksa Ubuntu için [Miniconda](https://docs.anaconda.com/miniconda/install/) kurun; Windows Conda yeterli değildir. Git yoksa:

```bash
sudo apt update
sudo apt install git
```

Aşağıdaki `GITHUB_DEPO_ADRESI` alanını danışmanın verdiği gerçek adresle değiştirin:

```bash
cd ~
git clone GITHUB_DEPO_ADRESI openmc-proje
cd ~/openmc-proje
git rev-parse HEAD
```

Son komuttaki sürümü danışmanınızın bildirdiği sürümle karşılaştırın. Çalışan deney sırasında projeyi güncellemeyin. Bu rehber proje yolunu `~/openmc-proje` kabul eder; farklı yere kurduysanız sonraki `cd` komutlarını uyarlayın.

### 2. Hesap ortamını ve notebook kernelini hazırla

Proje kökünde önce mevcut Conda ortamlarını kontrol edin:

```bash
cd ~/openmc-proje
conda env list
```

Listede `openmc-proje` **yoksa** ortamı bir kez oluşturun:

```bash
conda env create -f environment.yml
```

`conda env list` içinde `openmc-proje` zaten varsa oluşturma komutunu **atlayın**; ortamı silmeyin. Sürüm uyuşmazlığını danışmanınıza bildirin. `environment.yml` OpenMC 0.16 ve Python 3.12 tanımlar. Temiz bir bilgisayarda baştan kurulum henüz sınanmadı.

Ortamı açıp kontrol edin:

```bash
conda activate openmc-proje
python -c "import sys, openmc, numpy, pandas, h5py, matplotlib; print('Python:', sys.executable); print('OpenMC:', openmc.__version__)"
openmc --version
python -m ipykernel install --user --name openmc-proje --display-name "Python (OpenMC Proje)"
```

Python yolu `openmc-proje` ortamını göstermelidir. Eksik paket hatasında rastgele paket kurmayın; hata metnini danışmanınıza gönderin.

### 3. ENDF/B-VIII.0 nükleer verisini bağla

Büyük HDF5 nükleer veri kütüphanesi Git deposunda bulunmaz. Danışmanın belirttiği **ENDF/B-VIII.0 HDF5** arşivini [OpenMC veri sayfasından](https://openmc.org/data/) edinin; başka sürüme sessizce geçmeyin.

`/ARSIVIN/TAM/YOLU.tar.xz` alanını indirdiğiniz gerçek dosyanın tam yoluyla değiştirin:

```bash
cd ~/openmc-proje
mkdir -p data/endfb-viii.0
tar -xf /ARSIVIN/TAM/YOLU.tar.xz -C data/endfb-viii.0
find "$HOME/openmc-proje/data/endfb-viii.0" -name cross_sections.xml -print
```

`find` çıktısındaki **tam XML dosya yolunu** aşağıdaki tırnaklar arasına yazın:

```bash
conda env config vars set -n openmc-proje OPENMC_CROSS_SECTIONS="/XML/DOSYASININ/TAM/YOLU/cross_sections.xml"
conda deactivate
conda activate openmc-proje
python -c "import os; from pathlib import Path; p=Path(os.environ['OPENMC_CROSS_SECTIONS']); assert p.is_file(), p; print('Veri XML:', p)"
```

XML bulunmazsa veya birden çok XML çıkarsa danışmanınıza sorun. Notebook ön kontrolü ayrıca gerekli izotopları ve sıcaklık kapsamını denetler.

### 4. JupyterLab arayüzünü hazırla

JupyterLab Ubuntu'da zaten çalışıyorsa **mevcut sunucuyu kullanın**; danışmanın `teknofest26` ortamını kopyalamanız gerekmez. JupyterLab yoksa, hesap ortamından ayrı arayüz ortamını **bir kez** kurun:

```bash
conda create -n openmc-jupyter -c conda-forge jupyterlab
```

Hesap kerneli yine **Python (OpenMC Proje)** kalır. Arayüz ve hesap ortamlarını birleştirmeyin.

### 5. Bilgisayarını kontrol et

Aşağıdaki çıktıları danışmanınıza gönderin:

```bash
nproc
free -h
df -h ~/openmc-proje
du -sh ~/openmc-proje/data
```

Mevcut deney profili koşu başına **6 thread** kullanır; uygunluğu danışmanınız değerlendirsin. Uzun hesap sırasında bilgisayarı elektriğe bağlayın, otomatik uykuyu kapatın, WSL'yi kapatmayın ve aynı anda başka deney paketi başlatmayın. Laboratuvarda Deep Freeze varsa proje ile `runs/` sonuçlarının yeniden başlatmada silinmeyeceğini doğrulayın.

## Her deneyde yapılacaklar

### 1. Kendi paketini bul ve JupyterLab'i aç

Danışmanınız **öğrenci kimliğinizi ve açılacak aşamayı** bildirir. İlk aşamada yeni koşular `stage_32/ogrenci_02`, `ogrenci_03` ve `ogrenci_04` paketlerindedir. `ogrenci_01` danışmandır; ilk sekiz pilot koşusu tamamlanmıştır, yeniden çalıştırılmaz. Sonraki aşamalarda kişi başına 24, ardından 32 yeni koşu planlanmıştır; bu aşamalar yalnız ayrı izinle açılır. Danışmanın 19 Ekim 2026 istisnası yalnız mevcut `stage_128/ogrenci_01` paketine aittir.

Aşağıdaki **örnek** `ogrenci_02` ve `stage_32` içindir. Danışmanınız başka paket verdiyse `PAKET` satırını kendi paketinizin **gerçek klasör yoluyla** değiştirin; klasör adını tahmin etmeyin. Bu değişken yalnız açık olduğu terminalde kalır.

```bash
conda activate openmc-proje
cd ~/openmc-proje
PAKET="student_packages/v2_students_portable_v1/stage_32/ogrenci_02/v2_stage_32_ogrenci_02_beavrs_v2_pilot_scope_v1"
test -f "$PAKET/manifest.json" && test -f "$PAKET/01_calistir.ipynb" && echo "Paket bulundu"
```

`Paket bulundu` yazmıyorsa devam etmeyin; yolu danışmanınızla kontrol edin. Her pakette yalnız bir çalıştırma (`01_calistir.ipynb`) ve bir sonuç (`02_sonuclari_incele.ipynb`) notebook'u vardır.

`openmc-jupyter` ortamını 4. adımda kurduysanız Ubuntu terminalinde:

```bash
conda run --no-capture-output -n openmc-jupyter jupyter lab --no-browser
```

Başka bir JupyterLab kurulumunuz varsa onu mevcut yöntemiyle açın; `openmc-jupyter` komutunu kullanmayın. Zaten açık sunucu varsa yenisini açmayın. Terminaldeki token içeren `http://localhost:...` adresini Windows tarayıcısında açın; tokenı başkalarıyla paylaşmayın. Notebook kernelini **Python (OpenMC Proje)** seçin.

### 2. Atanmış deneyleri başlat

JupyterLab dosya tarayıcısında kendi `$PAKET` klasörünü açıp `01_calistir.ipynb` dosyasında **Run All** seçin. Bu eylem uzun hesabı başlatabilir. Notebook önce paket bütünlüğünü, atanmış koşulları ve ön kontrolü gösterir; onaylı pakette son hücre bağımsız WSL işçisini başlatır.

Çıktıdaki **grup kimliği, PID, log, durum ve sonuç yollarını** kaydedin. Notebook hücresinin bitmesi, bütün koşuların bittiği anlamına gelmez. Tarayıcı kapanabilir; **bilgisayar ve WSL açık kalmalıdır**. Aynı grubu ikinci kez başlatmayın. Tamamlanan grup tekrar çalıştırılmaz; başarısız veya durmuş grup kendiliğinden devam etmez.

Hash ya da teknik onay hatası görürseniz dosyaları düzeltmeye çalışmayın; hata metnini danışmanınıza gönderin. Eski taslak paketleri veya başka öğrencinin notebook'unu çalıştırmayın.

### 3. Durumu ve sonuçları incele

Aynı Ubuntu terminalinde `PAKET` değişkeni hâlâ tanımlıysa:

```bash
python scripts/v2_student_production.py status "$PAKET"
```

Yeni terminal açtıysanız önce `conda activate openmc-proje`, `cd ~/openmc-proje` ve kendi `PAKET="..."` satırınızı tekrar yazın. `02_sonuclari_incele.ipynb` dosyasında **Run All** yalnız kaydedilmiş sonuçları okur; devam eden grubun tamamlanmış ara sonuçlarını da gösterebilir, yeni simülasyon başlatmaz.

`completed`, hesap çıktı dosyalarının tamamlandığını belirtir; **fiziksel doğrulama, kaynak yakınsaması, istatistiksel kalite veya eğitim verisi kabulü değildir**. MC standart hatası fiziksel doğruluk yüzdesi değildir. Sıfır tally gerçek üretimin kesin sıfır olduğu anlamına gelmez; `kappa-fission` fisyon enerjisi üretimi yaklaşımıdır, toplam ısı birikimi değildir.

Durum ile süreç bilgisi çelişirse (örneğin `running` yanında `process_alive=false`), yalnız bu bayrağa bakarak yeniden başlatmayın. Log ve sonuçları kontrol edip danışmanınıza bildirin. `failed`, `stopped` veya `budget_exhausted` durumunda kısmi çıktıları silmeyin.

Durdurma veya devam **yalnız danışman yönlendirmesiyle** yapılır. Yalnız gereken **tek komutu** seçin:

Durdurmak için:

```bash
python scripts/v2_student_production.py stop "$PAKET"
```

Danışmanınız açıkça devam etmenizi söylediyse:

```bash
python scripts/v2_student_production.py resume "$PAKET"
```

`stop` komutu sinyal gönderilmediğini bildirirse işletim sistemi sürecini kendiniz öldürmeyin; danışmanınıza sorun. Süre tavanı pakete özeldir; başka paketin 4 veya 12 saatlik tavanını kendi paketinize aktarmayın.

### 4. ZIP teslimini oluştur

Grup tamamlandığında sonuç notebook'unu inceleyin ve kaydedin. Ubuntu terminalinde `openmc-proje` ortamı açık, proje kökünde ve kendi `PAKET` değişkeniniz tanımlı olmalıdır:

```bash
python scripts/v2_transfer.py export "$PAKET" "deliveries/$(basename "$PAKET").zip"
```

Betik ZIP'i `deliveries/` içine oluşturur; mevcut ZIP'in üzerine yazmaz. Hata verirse dosyaları gizleyerek elle ZIP hazırlamayın. ZIP'i danışmanın belirttiği ortak konuma gönderin ve dosya adını değiştirmeyin.

Hafif teslim ZIP'i nükleer veri kütüphanesini ve büyük statepoint HDF5 dosyalarını içermez. Kaynak `runs/` sonuçlarını, logları ve statepoint dosyalarını danışmanınız arşivlendiğini söyleyene kadar **silmeyin**.

## Bir sorun olduğunda

Danışmanınıza öğrenci kimliğinizi, paket/deney kimliğini, kullandığınız komutu veya hücreyi, **hata metninin tamamını** ve durum sorgusu çıktısını gönderin. Jupyter tokenını paylaşmayın. Kodu, manifesti, hesap profilini, seed'i, hash veya onay dosyasını kendi başınıza değiştirmeyin.

## Danışman için: teslimleri toplama

İndirilen ZIP'i Ubuntu içinden erişilebilir bir konuma alın. Proje kökünde:

```bash
conda activate openmc-proje
cd ~/openmc-proje
python scripts/v2_transfer.py import /TESLIMIN/TAM/YOLU.zip
python scripts/v2_transfer.py status --stage stage_32
```

İçe aktarma dosya bütünlüğünü ve senaryo atamasını doğrular; fiziksel/istatistiksel kabul veya eğitim verisi kabulü vermez. `--stage` değerini incelenen aşamaya göre seçin. Diğer aşamaların kapıları ayrı inceleme ve onay gerektirir.

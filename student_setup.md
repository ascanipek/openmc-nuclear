# Öğrenci kurulum ve deney çalıştırma rehberi

Bu rehber, projeyi kendi bilgisayarınızda kurmanız, size atanmış
deneyleri çalıştırmanız ve sonuçları danışmanınıza teslim etmeniz içindir.

> Kurulum bir kez yapılır. Her deney için yeniden kurulum yapılmaz.
> Komutlarda aksi belirtilmedikçe Ubuntu terminalini kullanın.

## 1. Ne yapacağız?

OpenMC, verilen yakıt, su ve geometri özellikleri için nötronların
davranışını Monte Carlo yöntemiyle hesaplar.

Her senaryo için şunları kaydedeceğiz:

- Nötron çoğalma faktörü: **k**
- Üç boyutlu fisyon ve fisyon enerjisi dağılımları
- Hesapların Monte Carlo standart hataları
- Hesap geçmişi ve çalışma süresi

Bu sayısal veriler daha sonra hızlı bir yapay zekâ vekil modeli
geliştirmekte kullanılacak.

Modelimiz, BEAVRS kaynaklarından türetilmiş bir yakıt demeti araştırma
modelidir. Gerçek bir santralin tamamını veya işletme güvenliğini
doğrulayan bir sistem değildir.

## 2. Bana kaç deney atanacak?

Her öğrencinin kendi deney listesi ve çalıştırma notebook'u vardır.

| Aşama | Kişi başına yeni deney | Ekipte biriken toplam |
|---|---:|---:|
| İlk aşama | 8 | 32 |
| İkinci aşama | 24 | 128 |
| Üçüncü aşama | 32 | 256 |

Bu dağılım dört kişi içindir. `ogrenci_01` danışmandır; diğer kimlikleri
danışmanınız size bildirecektir.

Danışmanın ilk sekiz deneyi zaten tamamlanmıştır. Yeniden yapılmayacaktır.

**Bir notebook birden fazla deneyi sırayla çalıştırır.**
Örneğin ilk aşamada kendi notebook'unuzda bir kez Run All dediğinizde
size atanmış sekiz deney sırayla hesaplanır.

- Başka öğrencinin paketini çalıştırmayın.
- Manifest, parametre, seed, hesap profili veya kodu değiştirmeyin.
- Sonraki aşamaya danışmanınız haber vermeden geçmeyin.

## 3. Windows'a WSL2 Ubuntu kurulumu

Ubuntu zaten kuruluysa bu bölümü tekrar uygulamayın.

Windows PowerShell'i yönetici olarak açın:

```powershell
wsl --install -d Ubuntu
```

İstenirse bilgisayarı yeniden başlatın. Ubuntu'yu açıp Linux kullanıcı
adınızı ve parolanızı oluşturun.

PowerShell'de kontrol edin:

```powershell
wsl --list --verbose
```

Ubuntu satırındaki VERSION değeri `2` olmalıdır.

Resmî yardım:
https://learn.microsoft.com/en-us/windows/wsl/install

**Bundan sonraki komutlar Ubuntu terminalinde çalıştırılacaktır.**

## 4. Conda ve projeyi hazırlama

Önce kontrol edin:

```bash
conda --version
git --version
```

Conda bulunamazsa Ubuntu içine Linux sürümü Miniconda kurulmalıdır.
Windows'a kurulmuş Conda bu proje için yeterli değildir.

Kurulum:
https://docs.anaconda.com/miniconda/install/

Git bulunamazsa:

```bash
sudo apt update
sudo apt install git
```

Danışmanınızın verdiği GitHub adresini aşağıdaki yer tutucunun yerine
yazarak projeyi indirin:

```bash
cd ~
git clone GITHUB_DEPO_ADRESI openmc-proje
cd ~/openmc-proje
```

> Projeyi Ubuntu kullanıcı klasöründe tutun.
> Bu rehberde proje yolu `~/openmc-proje` olarak kabul edilmiştir.

Deneylere başlamadan önce danışmanınızla aynı kod sürümünde olduğunuzu
doğrulayın:

```bash
git rev-parse HEAD
```

Çalışan bir deney sırasında kod güncellemesi yapmayın.

## 5. OpenMC ortamını oluşturma

Mevcut ortamları kontrol edin:

```bash
conda env list
```

`openmc-proje` yoksa proje kökünde oluşturun:

```bash
cd ~/openmc-proje
conda env create -f environment.yml
```

Ortam zaten varsa silmeyin veya yeniden oluşturmayın.
Sürüm uyuşmazlığını danışmanınıza bildirin.

Ortamı etkinleştirin ve kontrol edin:

```bash
conda activate openmc-proje

python -c "import sys, openmc, numpy, pandas, h5py, matplotlib; print('Python:', sys.executable); print('OpenMC:', openmc.__version__)"
openmc --version
```

Python yolu `openmc-proje` ortamını göstermelidir.

Notebook kernelini kaydedin:

```bash
python -m ipykernel install --user --name openmc-proje --display-name "Python (OpenMC Proje)"
```

Bir paket eksikliği hatası alırsanız rastgele paket kurmayın.
Hata metnini danışmanınıza gönderin.

## 6. OpenMC nükleer verisini indirme

Bu büyük veri kütüphanesi GitHub deposunda bulunmaz.
Her bilgisayara ayrıca indirilir.

Resmî kaynak:
https://openmc.org/data/

Danışmanınızın belirttiği **ENDF/B-VIII.0 HDF5** arşivini indirin.
Farklı bir kütüphane seçmeyin.

Ubuntu terminalinde:

```bash
cd ~/openmc-proje
mkdir -p data/endfb-viii.0
```

Arşivi gerçek dosya yolunu yazarak açın:

```bash
tar -xf /ARSIVIN/TAM/YOLU.tar.xz -C data/endfb-viii.0
```

XML dosyasını bulun:

```bash
find "$HOME/openmc-proje/data/endfb-viii.0" -name cross_sections.xml -print
```

Çıktıdaki tam yolu aşağıdaki yer tutucuya yazın:

```bash
conda env config vars set -n openmc-proje OPENMC_CROSS_SECTIONS="/XML/DOSYASININ/TAM/YOLU/cross_sections.xml"
conda deactivate
conda activate openmc-proje
```

Bu ayar `openmc-proje` ortamında kalıcıdır. Kontrol edin:

```bash
python -c "import os; from pathlib import Path; p=Path(os.environ['OPENMC_CROSS_SECTIONS']); assert p.is_file(), p; print('Veri XML:', p)"
```

Birden fazla XML bulunduysa veya dosya bulunamadıysa danışmanınıza sorun.

XML'in bulunması ilk kontroldür. Deney notebook'u ayrıca gerekli
izotopları ve sıcaklık kapsamını denetleyecektir.

## 7. Bilgisayar kontrolü

Aşağıdaki çıktıları danışmanınıza gönderin:

```bash
nproc
free -h
df -h ~/openmc-proje
du -sh ~/openmc-proje/data
```

Mevcut deney profili koşu başına **6 thread** kullanır.
Bilgisayarınıza uygunluğu danışmanınız değerlendirecektir.
Hesap profilini kendiniz değiştirmeyin.

- Bilgisayarın otomatik uykuya geçmesini engelleyin.
- Dizüstü bilgisayarı elektriğe bağlayın.
- Aynı anda birden fazla deney paketi başlatmayın.
- Ubuntu'yu kapatmayın ve bilgisayarı yeniden başlatmayın.
- Laboratuvarda Deep Freeze varsa proje ve sonuçların yeniden
  başlatmada silinmeyecek konumda olduğunu doğrulayın.

## 8. JupyterLab'i açma

JupyterLab zaten bir Ubuntu ortamında çalışıyorsa mevcut sunucuyu
kullanabilirsiniz. Danışmanınızın `teknofest26` ortamını kurmanız gerekmez.

JupyterLab yoksa, hesap ortamından ayrı bir arayüz ortamını bir kez kurun:

```bash
conda create -n openmc-jupyter -c conda-forge jupyterlab
```

Her kullanımda Ubuntu terminalinde:

```bash
conda activate openmc-proje
cd ~/openmc-proje
conda run --no-capture-output -n openmc-jupyter jupyter lab --no-browser
```

Terminalde gösterilen token içeren `http://localhost:...` adresini
Windows tarayıcısında açın. Bu adresi başkalarıyla paylaşmayın.

Notebook açıldığında kernel olarak mutlaka:

**Python (OpenMC Proje)**

seçin. JupyterLab arayüzüyle hesap kerneli farklı ortamlarda olabilir.

## 9. Kendi deney paketini açma

İlk aşama için JupyterLab dosya tarayıcısında şu dizine gidin:

```text
student_packages/
  v2_students_portable_v1/
    stage_32/
      ogrenci_02/
        paket_klasoru/
```

`ogrenci_02` yerine size atanmış kimliği kullanın.
İçeride iki notebook vardır:

| Dosya | Görevi |
|---|---|
| `01_calistir.ipynb` | Atanmış deneyleri başlatır |
| `02_sonuclari_incele.ipynb` | Kaydedilmiş sonuçları gösterir |

**İlk 32 aşamasında `ogrenci_01` yeni hesap başlatmaz;
tamamlanmış danışman pilotu kullanılır.**

Diğer taslak, eski veya danışman paketlerini çalıştırmayın.

## 10. Deneyleri başlatma

1. Kendi `01_calistir.ipynb` dosyanızı açın.
2. Kernelin **Python (OpenMC Proje)** olduğunu kontrol edin.
3. **Run All** seçin.
4. Parametre tablosunu ve ön kontrol sonucunu okuyun.
5. Başlatma çıktısındaki grup kimliği, PID, log ve durum yollarını kaydedin.

Paketin teknik onayı eksikse hesap başlamaz.
Onay veya hash dosyalarını değiştirmeyin; danışmanınıza bildirin.

Hesap bağımsız işçide devam eder. Başlatma hücresinin bitmesi,
bütün deneylerin bittiği anlamına gelmez.

Tarayıcı kapanabilir; **bilgisayar ve WSL açık kalmalıdır.**

## 11. İlerlemeyi izleme ve tamamlanma

Yeni Ubuntu terminalinde:

```bash
conda activate openmc-proje
cd ~/openmc-proje
```

Kendi paket yolunuzu bir değişkene atayın.
`PAKET_KLASORU` yerine gerçek klasör adını yazın:

```bash
PAKET="student_packages/v2_students_portable_v1/stage_32/ogrenci_02/PAKET_KLASORU"
```

Durumu görüntüleyin:

```bash
python scripts/v2_student_production.py status "$PAKET"
```

Ayrıca `02_sonuclari_incele.ipynb` dosyasında Run All yaparak
kaydedilmiş sonuçları görebilirsiniz. Bu notebook hesap başlatmaz.

**Grup `completed` olduğunda atanmış hesaplar tamamlanmıştır.**
Bu, fiziksel doğruluğun veya eğitim verisi kalitesinin kabul edildiği
anlamına gelmez.

`failed`, `stopped` veya `budget_exhausted` görürseniz:
- Hata metnini ve grup kimliğini danışmanınıza gönderin.
- Kısmi çıktıları silmeyin.
- Tekrar tekrar Run All yapmayın.

Durdurmanız gerekirse:

```bash
python scripts/v2_student_production.py stop "$PAKET"
```

Devam işlemini yalnız danışmanınız yönlendirdiğinde uygulayın:

```bash
python scripts/v2_student_production.py resume "$PAKET"
```

Süre tavanı paket bazındadır. Danışman pilotundaki 4 saat sınırını
bütün öğrenci paketleri için geçerli kabul etmeyin.

## 12. Sonuçları okuma

| Gösterge | Anlamı |
|---|---|
| `k` | Nötron çoğalma faktörünün tahmini |
| MC standart hatası | Monte Carlo örnekleme belirsizliği |
| `flux` | Nötron akısıyla ilgili sayısal ölçüm |
| `kappa-fission` | Fisyon enerjisi üretimini temsil eden ölçüm |
| Sıfır tally | O hücrede bu hesapta katkı ölçülmemesi |

MC standart hatası fiziksel doğruluk yüzdesi değildir.
Sıfır tally, gerçek üretimin kesin sıfır olduğunu göstermez.
Grafikler doğrudan MW veya sıcaklık çıktısı değildir.

Danışmanınıza şu kısa gözlemleri iletin:
- En uzun ve en kısa hesap hangisiydi?
- k ve MC hataları ne oldu?
- Dağılımda nerede yoğunlaşma görüldü?
- Sıfır veya düşük sinyalli bölgeler var mıydı?
- Uyarı veya başarısız koşu oluştu mu?

## 13. Sonuçları ZIP olarak teslim etme

Grup tamamlandığında sonuç notebook'unu inceleyip kaydedin.

Ubuntu terminalinde proje kökünden:

```bash
conda activate openmc-proje
cd ~/openmc-proje

PAKET="student_packages/v2_students_portable_v1/stage_32/ogrenci_02/PAKET_KLASORU"
mkdir -p deliveries

python scripts/v2_transfer.py export "$PAKET" "deliveries/$(basename "$PAKET").zip"
```

Kendi öğrenci kimliğinizi ve gerçek paket klasörünü kullanın.
Komut hata verirse eksik dosyaları gizleyerek elle ZIP oluşturmayın.

Oluşan ZIP'i danışmanınızın belirttiği ortak klasöre yükleyin.
Dosya adını değiştirmeyin.

**Teslim ZIP'i nükleer veri kütüphanesini içermez.**
Varsayılan hafif teslim statepoint dosyalarını da içermez.

`runs/` altındaki kaynak sonuçları ve statepoint dosyalarını
danışmanınız arşivlendiğini bildirene kadar silmeyin.

## 14. Sorun bildirirken

Şunları birlikte gönderin:

- Öğrenci kimliğiniz
- Paket ve deney kimliği
- Uyguladığınız komut veya notebook hücresi
- Hata metninin tamamı
- Durum sorgusu çıktısı

Token içeren Jupyter adresini paylaşmayın.
Sorunu çözmek için manifesti, onayı veya hash dosyalarını değiştirmeyin.

---

## Danışman için: sonuçları toplama

İndirilen ZIP'i Ubuntu içinden erişilebilir bir konuma alın.
Proje kökünde:

```bash
conda activate openmc-proje
cd ~/openmc-proje

python scripts/v2_transfer.py import /TESLIMIN/TAM/YOLU.zip
python scripts/v2_transfer.py status --stage stage_32
```

İçe aktarma; dosya bütünlüğü ve senaryo tutarlılığını denetler.
Fiziksel/istatistiksel kabul veya eğitim verisi kabulü vermez.

Sonraki aşama ancak inceleme ve gerekli paket onayları tamamlanınca açılır.
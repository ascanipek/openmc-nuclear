# Öğrenci başlangıç rehberi — kontrollü V2 araştırma dağıtımı

Bu proje OpenMC ile BEAVRS kaynaklarından türetilmiş, yalıtılmış 17×17 sonlu yükseklikli demetin araştırma koşularını üretir. Tam BEAVRS çekirdeği veya ölçülmüş işletme doğrulaması değildir. Öğrencinin görevi **kendisine atanmış sabit manifestteki** koşuları aynı model, seed ve hesap profiliyle çalıştırmak; kayıtları inceleyip ZIP teslim etmek ve sorunları bildirmektir. Manifest deney listesidir; `01_calistir.ipynb` yalnızca bu listeyi ön kontrol edip bağımsız WSL işçisini başlatan araçtır. `02_sonuclari_incele.ipynb` salt okunur incelemedir. Kod, fiziksel parametre, manifest, seed, profil, hash veya onay dosyasını değiştirmeyin. Sonuç `completed` olsa bile fiziksel doğruluk, kaynak yakınsaması ve eğitim verisi kabul edilmiş sayılmaz.

## Atama ve aşamalar

[Merkezi sahiplik kaydı](configs/v2_student_assignment_v1.json) 256 benzersiz fiziksel senaryoyu içerir. `ogrenci_01` danışmandır; `ogrenci_02`–`04` adları şimdilik yer tutucudur. İlk 32 senaryoda kişi başına sekiz: `ogrenci_01`in sekizi danışman pilotunda zaten hesaplandı, **yeniden başlatılmayacak**; diğer üç öğrencinin sekizer yeni koşusu vardır. Sonraki 128 toplam senaryo aşamasında önceki 32 üzerine 96 **yeni** koşu (kişi başına 24), 256 toplam aşamasında 128 **yeni** koşu (kişi başına 32) eklenir. Böylece hiçbir senaryo iki öğrenciye atanmaz. Yeni aşamalar yalnız açık veri/kalite ve süre incelemesinden sonra teknik onayla açılır; Run All bir sonraki aşamayı başlatmaz. Sonraki aşama paketleri şu an taslak/kapalıdır.

Kendi notebook'unuzu bulmak için proje kökünden `student_packages/v2_students_portable_v1/stage_32/<ogrenci_kimliginiz>/` dizinindeki tek paket klasörüne girin. O klasördeki `01_calistir.ipynb` çalıştırma, `02_sonuclari_incele.ipynb` sonuç dosyasıdır. `ogrenci_01` ilk aşamada tamamlanmış danışman pilotunu yalnız inceler; yeni Run All yapmaz. Başka öğrencinin klasörünü çalıştırmayın. Her paketin ayrı teknik `approval.json` kaydı olmadan başlatma kapısı açılmaz.

## Windows, WSL2 Ubuntu ve ayrı hesap ortamı

Windows PowerShell'de (gerekli sistem yetkisiyle) WSL2 Ubuntu'yu kurun ve `wsl --list --verbose` ile Ubuntu'nun sürüm 2 olduğunu görün. Gerekliyse `wsl --install -d Ubuntu` komutunu kullanın; Windows sürümüne göre yeniden başlatma gerekebilir. Resmî adımlar: [Microsoft WSL belgeleri](https://learn.microsoft.com/en-us/windows/wsl/basic-commands). Projeyi Ubuntu dosya sisteminde, kendi kullanıcı dizininizde örneğin `~/openmc-proje` altında açın. Hesap Python/OpenMC komutlarını **Ubuntu terminalinde** çalıştırın; Windows Python'una yönlendirmeyin.

Var olan Conda ortamlarını kaldırmayın veya güncellemeyin. Miniconda/Conda hazırsa `conda env list` ile `openmc-proje` varlığını kontrol edin. Yoksa proje kökünde `conda env create -f environment.yml` komutu yalnız yeni `openmc-proje` ortamını kurar. Dosya zaten mevcuttu; bu çalışmada yeniden oluşturulmadı. [Conda ortam dosyası belgeleri](https://docs.conda.io/projects/conda/en/stable/commands/env/create.html). **Temiz WSL kurulumundan bu kurulum dizisi henüz sınanmadı.** Ortamı kontrol edin:

```bash
cd ~/openmc-proje
conda run -n openmc-proje python -c 'import sys, openmc, numpy, pandas, h5py, matplotlib; print(sys.executable, openmc.__version__)'
```

Bu makinede gözlenen sürümler: Python 3.12.15, OpenMC 0.16.0, NumPy 2.5.4, pandas 3.0.6, h5py 3.16.0, Matplotlib 3.11.2. `environment.yml` Python 3.12/OpenMC 0.16 ve gerekli paketleri tanımlar; bu gözlem tüm öğrencilerde birebir sürüm eşitliği garantisi değildir. JupyterLab sunucusu ayrı bir ortamdan (danışmanda `teknofest26`) çalışabilir. Hesap notebook'u mutlaka `openmc-proje` kernelini seçmelidir; kernel mevcut değilse **yalnız hesap ortamında** `conda run -n openmc-proje python -m ipykernel install --user --name openmc-proje --display-name 'Python (OpenMC Proje)'` ile kaydedin. [IPython kernel belgeleri](https://ipython.readthedocs.io/en/stable/install/kernel_install.html). JupyterLab kurulumunu bu görev yapmadı; danışman makinesindeki mevcut JupyterLab korunur.

## Nükleer veri

OpenMC ekibinin resmî [ENDF/B-VIII.0 HDF5 kütüphanesini](https://openmc.org/data/) (sayfadaki **Official Data Libraries → ENDF/B-VIII.0 → .tar.xz**) öğrencinin kendisi indirir. Proje içindeki `data/` Git'e veya teslim ZIP'ine girmez. İndirilen arşivi Ubuntu'da örneğin `mkdir -p data/endfb-viii.0` ve `tar -xf /indirilen/arsiv.tar.xz -C data/endfb-viii.0` ile açın; gerçek `cross_sections.xml` konumunu `find data/endfb-viii.0 -name cross_sections.xml -print` ile bulun. Arşiv düzenini varsaymayın. Sonra kendi dosyanıza göre `export OPENMC_CROSS_SECTIONS="$(realpath data/.../cross_sections.xml)"` ayarlayın; hem Jupyter kernelinin hem bağımsız işçinin bu değişkeni gördüğünü doğrulayın. OpenMC [veri yapılandırması](https://docs.openmc.org/en/stable/usersguide/data.html) bu XML yolunu kullanır. Ön kontrol:

```bash
test -f "$OPENMC_CROSS_SECTIONS"
conda run -n openmc-proje python -c 'import os, pathlib, openmc; p=pathlib.Path(os.environ["OPENMC_CROSS_SECTIONS"]); assert p.is_file(); print(openmc.__version__, p)'
```

Sadece XML'in varlığı yeterli değildir: paketin ön kontrolü gereken nüklidleri, termal saçılmayı ve sıcaklık kapsamını ayrıca sınar. Eksik veri varsa hesap başlatmayın. Veri kütüphanesinin sürümü/kimliği koşunun `resolved_config.json` ve logunda kaydolur.

## Donanım ve disk kontrolü

Laboratuvar bilgisayarının yeterli olduğunu varsaymayın. Ubuntu'da `free -h`, `nproc`, `df -h .`, `du -sh data` ve `du -sh runs` sonuçlarını kaydedin; aynı anda çalışan başka işler için boş RAM/thread payını değerlendirin. İlk paketler koşu başına 6 thread ister; 6 mantıksal CPU görünmesi tek başına 6 boş çekirdek olduğu anlamına gelmez. Bu makinede veri kütüphanesi yaklaşık 16 GiB, mevcut sonuçlar yaklaşık 154 MiB; sekiz statepoint dosyasının her biri 7.038.048 bayt (toplam 56.304.384 bayt). Kalıcı diskte indirilen kütüphane **artı** koşu klasörleri, statepointler, teslim ZIP'leri ve yedekleri için alan ayırın; sayı makine ve aşamaya göre yeniden ölçülmelidir. Dolu disk başarısız/eksik çıktı riskidir. Kütüphaneyi ZIP'e eklemeyin.

## Çalıştırma ve izleme

1. Kendi paket klasöründe JupyterLab ile `01_calistir.ipynb` dosyasını açın, kernelin `openmc-proje` olduğunu görün. Hücreler atanan koşu kimlikleri, fiziksel parametreler, hesap bütçesi ve ön kontrolü gösterir. **Run All**, yalnız teknik onaylı ve bütünlüğü sağlam pakette bağımsız işçiyi başlatır; notebook'u açık tutmanız gerekmez. Mevcut grup ikinci kez başlatılmaz; tamamlanmışlar otomatik tekrar edilmez, başarısız/durmuş grup kendiliğinden sürdürülmez.
2. WSL terminalinde proje kökünden `python scripts/v2_student_production.py status <paket_klasoru>` ile PID, durum ve log yolunu görün. Paket README'si gerçek yolu verir. `tail -f runs/beavrs_3d/v2_groups/<grup_kimligi>/group.log` ilerlemeyi izler. `status.json` içindeki `completed` yalnız çıktının tamamlandığı anlamındadır; kalite alanını ayrıca okuyun.
3. Gerekiyorsa `python scripts/v2_student_production.py stop <paket_klasoru>` kimliği doğrulanmış işçiye durdurma sinyali gönderir. Yalnız failed/stopped ve kalan süre için, **açık kullanıcı kararıyla**, `python scripts/v2_student_production.py resume <paket_klasoru>` kullanılır. 4 saatlik `budget_exhausted` durumunda aynı grubu otomatik devam ettirmeyin; danışmana raporlayın. Kısmi dosyaları silmeyin.
4. `02_sonuclari_incele.ipynb` yalnız kayıtlı tamamlanmış ara ve nihai sonuçları okur; simülasyon başlatmaz. Sonuç tablosunda `k` nötron çoğalma özdeğerinin MC tahmini, yanındaki MC standart hatası örnekleme belirsizliğidir; fiziksel doğruluk yüzdesi değildir. `flux` nötron akısı tally'sidir. `kappa-fission` fisyon enerjisi üretiminin yaklaşımıdır, toplam yerel ısı birikimi değildir. `[z,y,x]` alanlarında sıfır tally sıfır fiziksel üretim veya sıfır belirsizlik kanıtı değildir.

## Teslim ve danışman toplaması

Çalıştırma notebook'unun sonundaki **Teslim** bölümü hesap başlatmayan komutu gösterir. Proje kökünden kendi paketiniz için:

```bash
python scripts/v2_transfer.py export student_packages/v2_students_portable_v1/stage_32/ogrenci_02/<paket_kimligi> deliveries/<paket_kimligi>.zip
```

Kendi kimliğiniz/yolunuzla değiştirin; başka öğrencinin paketini teslim etmeyin. ZIP manifesti, durumları, çözülmüş fiziksel girdileri, model/kod ve nükleer veri hash'lerini, `fields.npz` ham tally/MC hatalarını, koordinat/maskeleri, k/entropi geçmişlerini, logları, raporları, süre/seed/profili ve checksum listesini içerir. Varsayılan hafif ZIP statepoint içermez; **kaynak bilgisayarda statepointleri saklayın**; ZIP içindeki atlanan dosya listesi her statepointin boyutunu ve SHA256 değerini kaydeder. Doğrulama istenirse aynı dosyayı bu kimlikle ayrı aktarın. Eksik tamamlanmış çıktıyı export gizlemez, hata verir. ZIP'i öğrenci elle paylaşır; otomatik Drive/OneDrive bağlantısı yoktur.

Danışman indirdiği dosyayı proje kökünde `python scripts/v2_transfer.py import /indirilen/teslim.zip` ile güvenli şekilde doğrular ve `python scripts/v2_transfer.py status` ile beklenen/tamamlanan/eksik/başarısız senaryoları görür. Aynı ZIP tekrar import edilmez; farklı seed/bütçe ayrı **koşu**, aynı fiziksel senaryo ise tek kimlik olarak kalır. İçe alma hiçbir sonuca fiziksel veya istatistiksel kabul vermez; eğitim aktarımı için ayrı inceleme/kabul gerekir.


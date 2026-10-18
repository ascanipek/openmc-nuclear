# Kullanıcı tarafından yürütülen 3B deneyler

> Bu belge D2 dönemi iş akışını kaydeder. Yeni danışman onayı, D3/D4 B1 bütçeli manifestleri ve öğrenci paketleri için [güncel iş akışına](student_experiment_workflow.md) bakın; aşağıdaki eski D3/D4 dosyaları korunmuş tarihsel taslaklardır.

Bu akış `beavrs_derived_3d_assembly_v1` için hazırlanmıştır. Model, MIT-CRPG BEAVRS kaynak commit'i `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22` üzerinden türetilmiş, yalıtılmış bir 17×17 demettir. Yan sınırlar yansıtıcı, aktif yakıtın alt/üst sınırları vakumdur. Tam çekirdek BEAVRS ölçümüyle doğrudan doğrulama sayılmaz. Fiziksel girdiler ve varsayımlar [3B model belgesinde](reference_3d_model.md), tek küçük entegrasyonun sonuçları [entegrasyon raporunda](beavrs_3d_v1_integration_report.md) kayıtlıdır.

Uzun koşular bu teslimde **başlatılmadı**. Bu dosyadaki komutlar kullanıcı tarafından çalıştırılacak işlemlerdir. Python/OpenMC yalnızca WSL Ubuntu içindeki Conda ortamında çalıştırılmalıdır. Aşağıdaki örnekler Windows PowerShell içindir; proje yolunu UNC üzerinden açan editörde bile komutlar `wsl.exe -d Ubuntu` ile gider. Notebook'larda WSL `openmc-proje` kernelini seçin. Ortamda `ipykernel` vardır; bu ortamda JupyterLab/Notebook sunucusu kurulu değildir. Mevcut WSL uyumlu notebook arayüzünüzü kullanın. `ipywidgets` gerekmez ve kurulmayacaktır. **01 notebookunda Run All uzun deney grubunu başlatır**; yalnızca ön kontrol için son başlatma hücresini çalıştırmayın.

## Hazır manifestler

| Grup | Amaç | Önceden seçilmiş koşular | Bağımlılık |
| --- | --- | --- | --- |
| `beavrs3d_d2_budget_v1` | %50 girişte bütçe artışı | 600/300/20.000; 600/300/80.000; 600/300/320.000 batch/inactive/particles | Yok; D1 ve küçük entegrasyon önceden tamamlandı |
| `beavrs3d_d3_seeds_v1` | %50 girişte bağımsız tohumlar | 3 × 150/60/40.000, tohumlar 42001/43001/44001 | D2 tamamlanmış ve operatör tarafından incelenmiş olmalı |
| `beavrs3d_d4_positions_v1` | Önceden seçilmiş çubuk konumları | %0/%50/%100, her biri 150/60/40.000 | D3 tamamlanmış ve incelenmiş olmalı |

Sayılar hesap **planıdır**; yakınsama veya fiziksel doğruluk kabul eşiği değildir. D2 tohumları sırasıyla 31001, 41001 ve 51001 olarak sabitlenmiştir. D2 fiziksel durumu her koşuda %50 giriştir; 600 toplam batchin 300'ü inactive, 300'ü aktiftir; nesil/batch=1 ve thread=6. D2 parçacık bütçeleri 20.000, 80.000 ve 320.000 parçacık/nesildir. D2 bir bağımsız tekrar tasarımı değildir; tekrarlar D3'te ayrıca yapılır. Manifestler `manifests/` altında tam hesap ayarlarını, deney kimliklerini, fiziksel durumu ve referans konfigürasyon SHA-256 özetini tutar. Serbest parametre giriş alanı yoktur. Başka fiziksel/hesaplama düzeni için mevcut manifesti değiştirmek yerine yeni kimlikli, önceden gözden geçirilmiş manifest hazırlamak gerekir. D2 sonuçları bütçe seçimini desteklemiyorsa D3/D4'e ilerlemeyin; hazır değerler otomatik onay anlamına gelmez.

## Notebook akışı

1. `notebooks/01_deney_calistir.ipynb` dosyasını WSL bağlamında açın; kernel olarak `/home/ascanipek/miniconda3/envs/openmc-proje/bin/python` seçin. İlk hücrede `SELECTED_MANIFEST` sabit D2 dosyasına bağlıdır. İlk tablo seçili grubun deney kimliklerini, % çubuk girişini, bor/su/yakıt/sıcaklık değerlerini, toplam/aktif/inactive batch sayılarını ve toplam/aktif tarihçeleri gösterir.
2. Ayrı **ön kontrol** hücresi kaynak özetini, geometri nokta kontrollerini ve nükleer veri/sıcaklık kapsamını denetler; taşıma hesabı yapmaz. Salt ön kontrol için notebooku bu hücreye kadar çalıştırın.
3. **Son hücre** ön kontrolü tekrarlar ve mevcut `launch()` işleviyle seçili grubu başlatır. Dolayısıyla **Run All uzun koşuyu başlatır**. Notebook WSL kernelinde çalıştığından `wsl.exe` çağrılmaz. İşçi bağımsız süreçtir; hücre onu beklemeden PID, log ve durum yollarını gösterir. Aynı grup kayıtlıysa ikinci kez başlatmaz; tamamlanmış, başarısız, durmuş veya bütçesi tükenmiş grubu otomatik sürdürmez.
4. `notebooks/02_sonuclari_incele.ipynb` diskteki grupları okuyup tabloları ve kaydedilmiş grafiklerini sunar; OpenMC çağırmaz.

## Terminal komutları

Önce liste ve ön kontrol:

```powershell
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py list
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py preflight /home/ascanipek/openmc-proje/manifests/beavrs3d_d2_budget_v1.json
```

Aşağıdaki komut **uzun D2 grubunu gerçekten başlatır**; yalnızca hazır olduğunuzda çalıştırın. D3/D4 için manifest dosya adını değiştirin; bağımlılık kapıları kodla denetlenir.

```powershell
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py launch /home/ascanipek/openmc-proje/manifests/beavrs3d_d2_budget_v1.json
```

Notebookun son hücresi de aynı `launch()` işlevini kullanır; yukarıdaki terminal komutu alternatif açık başlatma yoludur. `launch` PID, grup logu ve durum dosyasını döndürür. Python işçisi WSL'de ayrı oturum/süreç grubu olarak çalışır; notebook veya tarayıcı kapansa da sürer. Aynı grup kimliğiyle ikinci `launch` atomik dizin oluşturma kontrolünde reddedilir. Çalışma kopyası `runs/beavrs_3d/groups/<group_id>/manifest.json` içinde saklanır ve SHA-256 ile denetlenir.

İlerleme ve log:

```powershell
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py status beavrs3d_d2_budget_v1
wsl.exe -d Ubuntu -- tail -n 50 /home/ascanipek/openmc-proje/runs/beavrs_3d/groups/beavrs3d_d2_budget_v1/group.log
```

Grup `status.json` içindeki `state`, `current_experiment` ve `completed_experiments` alanları ilerlemeyi gösterir. Her denemenin `status.json` dosyası hata/çalışma durumunu tutar. `process_alive` işçinin gerçekten canlı olup olmadığını ayırır. Çalışma sırasında yalnızca kaydedilmiş verileri okumak için ikinci notebook kullanılabilir.

Durdurma ve kalan koşulara devam:

```powershell
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py stop beavrs3d_d2_budget_v1
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py status beavrs3d_d2_budget_v1
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py resume beavrs3d_d2_budget_v1
```

`stop` işçinin PID kimliğini denetler, durdurma işareti bırakır ve süreç grubuna SIGTERM gönderir. Durum `stopped` olana ve `process_alive=false` görünene kadar bekleyin. `resume` önceki tamamlanmış ve bütünlüğü doğrulanmış koşuları atlar; kesilmiş/eksik koşu için **yeni deneme dizini** açar. `resume` canlı işçiyi ve tamamlanmış grubu reddeder. Eski deneme dosyalarını silmez/üzerine yazmaz. Beklenmedik güç kesintisinde durum dosyası eski bir `running` değeri taşıyabilir; canlı süreç kontrolüyle birlikte yorumlayın.

D2 sonuçlarını inceleyip D3'e ilerleme kararı verdiğinizde, yalnızca operatör aşağıdaki kayıt komutunu çalıştırır. Bu komut fiziksel kabul veya otomatik yakınsama beyanı değildir. Aynı işlem D3 sonrasında D4 için geçerlidir.

```powershell
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py inspect beavrs3d_d2_budget_v1
wsl.exe -d Ubuntu -- /home/ascanipek/miniconda3/bin/conda run -n openmc-proje python /home/ascanipek/openmc-proje/scripts/experiments.py review beavrs3d_d2_budget_v1
```

## Çıktı sözleşmesi

Her koşunun `experiments/<experiment_id>/attempt_<UTC>_<id>/` klasöründe `resolved_config.json` (kullanılan referans girdileri, hesap ayarları, veri/kod/sürüm özetleri, ayrı senaryo ve koşu kimlikleri), `status.json` (durum/hata), `summary.json` (birimli temel sonuçlar, MC standart hataları, kalite ve fiziksel kabul), `fields.npz` ([z,y,x] ham alan ortalamaları/hataları, geometrik sıfır maskeleri, raporlama maskesi, x/y/z kenarları ve eksen sırası), `openmc.log`, `statepoint.*.h5`, `report.html` ve grafikler bulunur. Eski `result.json` ile `beavrs_3d_arrays.npz` adları da tutulur. Başarısız denemede mevcut olan dosyalar saklanır ve `summary.json` hata bilgisini verir; olmayan statepoint uydurulmaz.

Grup klasöründe değiştirilemez `manifest.json` çalışma kopyası, `status.json`, `process.json`, `group.log`, `comparison.csv` ve `comparison.html` vardır. Raporlar yerel Python ile üretilir; LLM veya dış API çağrısı yapmaz. `completed` yalnızca çıktı bütünlüğüdür. `physical_acceptance=not_assessed` kalır ve yakınsama **“inceleme gerekli”** diye gösterilir; MC standart hata fiziksel doğruluk yüzdesine çevrilmez. Fiziksel kabul için ayrıca kaynak/girdi ve istatistik incelemesi gerekir.


## D2 revizyonu ve dört saatlik grup bütçesi

D2 grubu henüz hiç başlatılmadığından mevcut `beavrs3d_d2_budget_v1` manifesti bu istekle güncellendi ve her üç manifestte `group_runtime_budget_seconds=14400` sabitlendi. Güncellenmiş D2 dosyasının SHA-256 özeti `92203054e69f396465f3b4ef6cc40bd55166e77e4b60bdb52e12346b6fb199d8` değeridir. Manifestler başlatıldığında bayt düzeyinde çalışma kopyası alınır; sonradan değişiklik kabul edilmez. D2 tabloda her koşu için toplam/aktif/inactive batch ve toplam/aktif parçacık geçmişleri ayrı sütunlardır: B1 12 milyon toplam / 6 milyon aktif, B2 48 milyon / 24 milyon, B3 192 milyon / 96 milyon. Grup toplamı 252 milyon tarihçedir.

Bu 4 saat, grubun **etkin WSL işçi süresi** bütçesidir; kullanıcı tarafından durdurulmuş süre sayılmaz. WSL işçisinin kendi ön kontrolü ve sonuç işleme bu süreye dahildir; notebook/CLI ön kontrolü işçi başlamadan önce yapılır ve bütçeye sayılmaz. Önceden tamamlanmış küçük entegrasyonun 1 milyon tarihçede 34,43 saniyelik süresi kullanılarak tarihçe başına süre hesaplanır; öngörü için 1,5 katsayısı uygulanır. İlk D2 toplam tahmini yaklaşık 13.015 saniye (3,62 saat) çıkar. Bu yalnızca başlatma kararı için kaba bir üst paylı **tahmindir, garanti değildir**. Her tamamlanan koşunun gerçek süre/tarihçe değeri de sonraki koşu tahminine katılır; yavaş olan oran kullanılır. Yeni koşunun tahmini kalan etkin bütçeyi aşıyorsa koşu başlamaz, grup `budget_exhausted` durumuna geçer ve neden/status dosyasına yazılır.

Çalışan koşu sırasında 14.400 saniyelik etkin süre dolarsa işçi kendi süreç grubuna SIGTERM gönderir; OpenMC çalışması kesilir, bu denemenin mevcut dosyaları ve hata/durum kaydı korunur, grup `budget_exhausted` olur. Bu durumda `resume` reddedilir; kullanıcı koşulları ve maliyeti yeniden değerlendirip yeni kimlikli manifest hazırlamalıdır. Sinyalin işlenmesi ve çıktı temizliği nedeniyle süreç tam 14.400,000 saniyede sonlanmayı **garanti etmez**. Harici sistem yükü ve disk gecikmesi süre tahminini değiştirebilir. Bütçe sınırı kaynak yakınsaması veya fiziksel kabul değildir.





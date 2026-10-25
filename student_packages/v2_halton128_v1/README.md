# Yerel V2 Halton devam paketleri

Bu dört paket, Kaggle için sabitlenen Halton 233–360 senaryolarını aynı fiziksel girdiler, kimlikler ve MC seed'leriyle yerel WSL2 OpenMC üretim akışında çalıştırır. Kaynak kataloglar scenarios/v2_halton128_v1/ altındadır. Eski 256 senaryo ve paketleri ayrı tutulur.

| Paket | Halton indisleri | Koşu | MC seed'leri |
| --- | ---: | ---: | ---: |
| halton_01 | 233–264 | 32 | 72001–72032 |
| halton_02 | 265–296 | 32 | 72033–72064 |
| halton_03 | 297–328 | 32 | 72065–72096 |
| halton_04 | 329–360 | 32 | 72097–72128 |

Her pakette bir 01_calistir.ipynb ve bir 02_sonuclari_incele.ipynb vardır. JupyterLab'da paket klasörünü açıp WSL openmc-proje kernelini seçin. Run All yalnız seçili, onaylı ve henüz başlamamış grubu mevcut v2_student_runner bağımsız işçisiyle başlatır. Sonuç notebook'u yalnız kayıtları okur. Gruplar ayrı ayrı başlatılır; sonraki grup otomatik başlamaz.

Hesap profili configs/v2_calculation_profile_halton128_80k_24h_research_v1.json: 80.000 parçacık/nesil, 600 toplam batch, 300 inactive, 1 nesil/batch, 6 thread ve grup başına 86.400 saniye. OpenMC 0.16.0 ile aynı ENDF/B-VIII.0 HDF5 veri indeksini kullanın. Tally düzeni [z,y,x] = 20×17×17'dir. Bu sayılar kontrollü araştırma koşusuna aittir; yakınsama veya fiziksel doğruluk kabulü değildir.

Proje kökünden WSL terminalinde, openmc-proje ortamı etkin iken paket yolunu seçerek durum, durdurma, açık devam ve teslim komutlarını çalıştırın:

    python scripts/v2_student_production.py status student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1
    python scripts/v2_student_production.py stop student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1
    python scripts/v2_student_production.py resume student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1
    python scripts/v2_transfer.py export student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1 deliveries/v2_halton_01_beavrs_v2_pilot_scope_v1.zip

Diğer gruplarda halton_01 yerine halton_02, halton_03 veya halton_04 değerini kullanın. Resume yalnız açık kullanıcı kararıyla stopped veya failed durumunda ve kalan grup bütçesi varsa çalışır. Çalışma kayıtları runs/beavrs_3d/v2_groups/<grup>/ altındadır; her koşunun statepoint'i kaynak makinede kalır. Hafif teslim ZIP'i statepoint içermez.

Merkezi içe aktarma mevcut v2_transfer.import_zip işleviyle yapılır; yeni 128 senaryo için ayrı configs/v2_halton128_assignment_v1.json atama kaydı verilmelidir. Örnek, proje kökünden WSL ortamında:

    python -c "import sys; sys.path.insert(0, 'src'); from reactor_pipeline import v2_transfer; print(v2_transfer.import_zip('deliveries/v2_halton_01_beavrs_v2_pilot_scope_v1.zip', assignment_path='configs/v2_halton128_assignment_v1.json'))"

Bu içe aktarma yalnız teslim bütünlüğünü doğrular; fiziksel, istatistiksel veya eğitim verisi kabulü vermez. Mevcut işçi kimliği denetiminde process_alive gerçek işçi çalışırken yanlış false gösterebiliyor; stop sonucundaki signal_sent değerini kontrol edin. Çalışan işçinin kullandığı ortak kodu bu hazırlık kapsamında değiştirmedik.

Tüm 128 senaryo kimliği, Halton indisi, deney kimliği ve MC seed'i scenario_index.csv dosyasında listelenir.

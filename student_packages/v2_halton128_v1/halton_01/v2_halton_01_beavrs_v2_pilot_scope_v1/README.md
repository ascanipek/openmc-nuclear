# halton_01: Halton 233–264

Bu yerel paket sabitlenmiş Kaggle kataloğundaki aynı 32 fiziksel senaryoyu ve 72001–72032 MC seed aralığını kullanır. Hesap profili: configs/v2_calculation_profile_halton128_80k_24h_research_v1.json. Ayarlar: 80.000 parçacık/nesil, 600 toplam batch, 300 inactive, 1 nesil/batch ve 6 thread. Grup süre tavanı 86.400 saniyedir. Teknik onay yalnız kontrollü araştırma koşusuna yöneliktir; completed fiziksel doğrulama, kaynak yakınsaması veya eğitim verisi kabulü değildir.

JupyterLab'da WSL openmc-proje kernelini seçin. Bu klasördeki 01_calistir.ipynb dosyasının Run All işlemi yalnız onaylı ve henüz başlamamış grubu bağımsız işçiyle başlatır. 02_sonuclari_incele.ipynb yalnız kaydedilmiş sonuçları okur. Manifest, seed, profil ve fizik kodunu değiştirmeyin. Diğer Halton grupları kendiliğinden başlamaz.

Proje kökünden WSL terminalinde, openmc-proje ortamı etkin iken:

    python scripts/v2_student_production.py status student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1
    python scripts/v2_student_production.py stop student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1
    python scripts/v2_student_production.py resume student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1
    python scripts/v2_transfer.py export student_packages/v2_halton128_v1/halton_01/v2_halton_01_beavrs_v2_pilot_scope_v1 deliveries/v2_halton_01_beavrs_v2_pilot_scope_v1.zip

Durum: runs/beavrs_3d/v2_groups/v2_halton_01_beavrs_v2_pilot_scope_v1/status.json
Log: runs/beavrs_3d/v2_groups/v2_halton_01_beavrs_v2_pilot_scope_v1/group.log

Resume yalnız açık kullanıcı kararıyla stopped veya failed durumunda, kalan bütçe varsa kullanılır. Teslim ZIP'i statepoint içermez; tam grup çıktılarını kaynak bilgisayarda koruyun. Merkezi import için configs/v2_halton128_assignment_v1.json kullanılır. Mevcut işçi kimliği denetimindeki process_alive sorunu nedeniyle stop komutunun sinyal gönderdiğini varsaymayın; sonuçtaki signal_sent alanını kontrol edin.

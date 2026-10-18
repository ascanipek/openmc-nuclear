# Pipeline v1 dondurma kaydı

BEAVRS kaynak commit'i `1ccae04dc3830a5977f08ed7f5f7e1e51ded0d22`, şartname 3.0.2. Model `beavrs_derived_3d_assembly_v1` [referans belgede](reference_3d_model.md) kayıtlıdır. Çalışma öncesi kaynak/kod/konfigürasyon/manifester/notebookların 26 dosyalık kopyası `freezes/pipeline_v1_before_scope/` altındadır; `SHA256SUMS.txt` her dosyanın SHA256 özetini tutar. `data/`, `runs/` ve Conda ortamı kopyalanmadı. Bu liste yerel değişikliği saptar; güvenlik imzası değildir.

V1 D2 manifesti ve sonuçları olduğu gibi kalır. D2-B1/B2/B3 aynı fiziksel senaryo, üç ayrı koşu bütçesidir. Yeni parametre kontrol kodu `beavrs_derived_3d_assembly_v2_proposed` kimliğiyle ayrıdır; mevcut v1 koşucusuna bağlanmadı, v1 kaydını yeniden etiketlemez. V2 parametreleri için danışman kapsam/aralık onayı, kaynaklı basınç ve ayrıca küçük entegrasyon gerekir. Eski D3/D4 dosyaları korunur; B1-bütçeli yeni manifestler farklı grup kimlikleri taşır.

Durum eksenleri bağımsız kaydedilir: `code_tested`, `integration_run`, `reference_comparison`, `source_convergence_reviewed`, `accepted_for_data_production`. Bir eksenin olumlu olması diğerlerini ima etmez. `status.json:completed` dosya bütünlüğüdür; `summary.json:physical_acceptance=not_assessed` fiziksel doğrulama iddiası değildir. Doğrudan yalıtılmış demet deneysel referansı bulunmadı.

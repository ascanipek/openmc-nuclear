# ogrenci_01 — stage_128 (24 yeni fiziksel senaryo)

Bu paket taşınabilirdir; proje kendi WSL kullanıcı dizininizde kalabilir. `manifest.json` deneylerin tek sabit listesidir. `01_calistir.ipynb` yalnız doğru `openmc-proje` kernelinde, geçerli paket teknik onayından sonra Run All ile bağımsız WSL işçisini başlatır. `02_sonuclari_incele.ipynb` salt okur. `completed` fiziksel veya istatistiksel kabul değildir.

Durum: danışmanın 2026-10-19 tarihli yalnız bu paket için kontrollü araştırma istisnası ve teknik onayı vardır. Run All 24 koşuluk grubu 12 saatlik tavanla başlatır. Başka öğrencinin paketini veya aşamayı başlatmayın. Parametre, seed, manifest, profil ve kod değiştirmeyin.

Proje kökünden WSL terminalinde:

```bash
python scripts/v2_student_production.py status student_packages/v2_students_portable_v1/stage_128/ogrenci_01/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_student_production.py stop student_packages/v2_students_portable_v1/stage_128/ogrenci_01/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_student_production.py resume student_packages/v2_students_portable_v1/stage_128/ogrenci_01/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_transfer.py export student_packages/v2_students_portable_v1/stage_128/ogrenci_01/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1 deliveries/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1.zip
```

Grup durumu: `runs/beavrs_3d/v2_groups/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1/status.json`; canlı log: `runs/beavrs_3d/v2_groups/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1/group.log`; koşu sonuçları: `runs/beavrs_3d/v2_groups/v2_stage_128_ogrenci_01_beavrs_v2_pilot_scope_v1/experiments/`. `stop` yalnız doğrulanmış işçiye sinyal gönderir. `resume` yalnız açık kullanıcı kararıyla failed/stopped durumda ve kalan bütçeyle kullanılır. 12 saatlik budget_exhausted halinde danışmana haber verin. Teslim ZIP'i statepoint içermez; dosyaları kaynak bilgisayarda koruyun.

## 2026-10-19 danışman istisnası ve teknik sürüm incelemesi

Yalnız bu mevcut 24 koşuluk stage_128/ogrenci_01 paketi, diğer öğrencilerin stage_32 çalışmaları bitmeden kontrollü araştırma devamı olarak açılmıştır. İlk sekiz danışman pilotu tamamlandı; bu 24 senaryo onlarla ve kalan ilk 32 ile çakışmıyor. Model düzeltmesi sonrası yeniden hesaplama olasılığı kabul edildi. Fiziksel doğrulama, kaynak yakınsaması ve eğitim verisi kabulü verilmedi. Diğer stage_128/stage_256 paketleri taslak kalır.

Hesap: 600 toplam, 300 inactive batch; 80.000 parçacık/nesil; 1 nesil/batch; 6 thread. Grup tavanı 43.200 s (12 saat). Yeni profil configs/v2_calculation_profile_stage128_ogrenci01_80k_12h_research_v1.json yalnız bu pakete bağlıdır. 24 koşunun planlama tahmini yaklaşık 37.500 s; bu garanti değildir. Süre aşılırsa çalışan koşu kesilebilir, kısmi çıktılar korunur ve durum inceleme gerektirir.

Değişiklik öncesi SHA-256 kayıtları:
- old_profile_sha256: b8ff005646d43064c200ef05e1382ab4c99fbfaa36d0430f815f938ca8c0e09d
- old_manifest_sha256: c7572c1df0ee6456da0a2c880a46520cc7d14c58774fa8dbe85110b251ea77ac
- old_package_sha256: 1b185208b7527d0d8ef28fb0917ead542d58f031c8badfed0e41b67bba129e23
- old_ledger_sha256: 3808730b104bec5570ffc436c2256bfa7007ceece9cbd7d7828f84790b4a57e1
- old_notebook_content_sha256: a48a9b6010762336a17fd67161cec6df1616466332b2d5347a62b9f9a2b5606d
- old_assignment_sha256: 26b530e44b16f59cfef2fe6b047518d16ad9bf225d95d8eeeb954dfe58e56dd7

Eski profil configs/v2_calculation_profile_pilot_draft_v1.json değiştirilmedi. Manifestteki 24 senaryo kimliği, kontrol değerleri, hesap ayarları ve seedler aynen korundu. Bu paket için yeni profil/manifest/README/notebook içerik hashleri SHA256SUMS.json ve approval.json kayıtlarına bağlandı; merkezi atama kaydında yalnız bu paketin referans hashleri ve istisna açıklaması güncellendi. Karar kaynağı: danışmanın 2026-10-19 tarihli açık kullanıcı mesajı.

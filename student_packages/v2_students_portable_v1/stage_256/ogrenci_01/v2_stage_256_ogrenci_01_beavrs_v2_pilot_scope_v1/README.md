# ogrenci_01 — stage_256 (32 yeni fiziksel senaryo)

Bu paket taşınabilirdir; proje kendi WSL kullanıcı dizininizde kalabilir. `manifest.json` deneylerin tek sabit listesidir. `01_calistir.ipynb` yalnız doğru `openmc-proje` kernelinde, geçerli paket teknik onayından sonra Run All ile bağımsız WSL işçisini başlatır. `02_sonuclari_incele.ipynb` salt okur. `completed` fiziksel veya istatistiksel kabul değildir.

Durum: danışmanın 2026-10-20 tarihli kararıyla yalnız bu 32 koşuluk paket kontrollü araştırma için teknik olarak onaylıdır. Run All bağımsız işçiyi 57.600 saniyelik (16 saat) grup tavanıyla başlatır. Başka öğrencinin paketini veya aşamayı başlatmayın. Parametre, seed, manifest, profil ve kod değiştirmeyin.

Proje kökünden WSL terminalinde:

```bash
python scripts/v2_student_production.py status student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_student_production.py stop student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_student_production.py resume student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_transfer.py export student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1 deliveries/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1.zip
```

Grup durumu: `runs/beavrs_3d/v2_groups/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1/status.json`; canlı log: `runs/beavrs_3d/v2_groups/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1/group.log`; koşu sonuçları: `runs/beavrs_3d/v2_groups/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1/experiments/`. `stop` yalnız doğrulanmış işçiye sinyal gönderir. `resume` yalnız açık kullanıcı kararıyla failed/stopped durumda ve kalan bütçeyle kullanılır. 16 saatlik budget_exhausted halinde danışmana haber verin. Teslim ZIP'i statepoint içermez; dosyaları kaynak bilgisayarda koruyun.

## 2026-10-20 teknik kapsam kaydı

Yalnız bu mevcut stage_256/ogrenci_01 paketi için 32 benzersiz senaryo araştırma koşusu açılmıştır. Önceki danışman pilot sekizi ve stage_128/ogrenci_01 grubunun 24 koşusu tamamlanmış; bu 32 senaryo onlarla çakışmaz. Bu karar fiziksel doğrulama, kaynak yakınsaması veya eğitim verisi kabulü değildir.

Hesap: 80.000 parçacık/nesil, 600 toplam batch, 300 inactive, 1 nesil/batch, 6 thread; seedler manifestte korunur. Yalnız bu pakete bağlı profil: `configs/v2_calculation_profile_stage256_ogrenci01_80k_16h_research_v1.json`. Grup tavanı 57.600 saniyedir (16 saat). Önceki 24 koşu 23.979 saniyede tamamlandı; 32 koşu için ortalama temelli yaklaşık 31.972 saniye tahmin ve runnerın daha ihtiyatlı yaklaşık 50.000 saniye tahmini garanti değildir. Tavan dolarsa çalışan koşu kesilebilir; tamamlanmış ve kısmi kayıtlar korunur, durum inceleme gerektirir.

Değişiklik öncesi SHA-256: paylaşılan taslak profil `b8ff005646d43064c200ef05e1382ab4c99fbfaa36d0430f815f938ca8c0e09d`; manifest `994d3046e0d8688afcf193594680fa5fcc4adfda808c9e7d4f49604521645e91`; package.json `86f045496bbfa9d6392f6e5e0a7e9bc3b894fe1476897cd8fbb3ee9718677341`; SHA256SUMS.json `49d3a56514b21412dfa1917b718dfe1a442cdaa84a51ae0190ce0f5bd964a1c8`. Ortak taslak profil ve diğer öğrenci paketleri değiştirilmedi. Karar kaynağı: danışmanın 2026-10-20 tarihli açık kullanıcı mesajı.

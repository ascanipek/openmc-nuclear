# ogrenci_01 — stage_256 (32 yeni fiziksel senaryo)

Bu paket taşınabilirdir; proje kendi WSL kullanıcı dizininizde kalabilir. `manifest.json` deneylerin tek sabit listesidir. `01_calistir.ipynb` yalnız doğru `openmc-proje` kernelinde, geçerli paket teknik onayından sonra Run All ile bağımsız WSL işçisini başlatır. `02_sonuclari_incele.ipynb` salt okur. `completed` fiziksel veya istatistiksel kabul değildir.

Durum: sonraki aşama taslağı; profil bütçesi ve teknik onay henüz yok, çalıştırılmaz. Başka öğrencinin paketini veya aşamayı başlatmayın. Parametre, seed, manifest, profil ve kod değiştirmeyin.

Proje kökünden WSL terminalinde:

```bash
python scripts/v2_student_production.py status student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_student_production.py stop student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_student_production.py resume student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1
python scripts/v2_transfer.py export student_packages/v2_students_portable_v1/stage_256/ogrenci_01/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1 deliveries/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1.zip
```

Grup durumu: `runs/beavrs_3d/v2_groups/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1/status.json`; canlı log: `runs/beavrs_3d/v2_groups/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1/group.log`; koşu sonuçları: `runs/beavrs_3d/v2_groups/v2_stage_256_ogrenci_01_beavrs_v2_pilot_scope_v1/experiments/`. `stop` yalnız doğrulanmış işçiye sinyal gönderir. `resume` yalnız açık kullanıcı kararıyla failed/stopped durumda ve kalan bütçeyle kullanılır. 4 saatlik budget_exhausted halinde danışmana haber verin. Teslim ZIP'i statepoint içermez; dosyaları kaynak bilgisayarda koruyun.

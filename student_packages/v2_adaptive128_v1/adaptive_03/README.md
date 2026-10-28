# ADAPTIVE-03 öğrenci paketi

Bu ZIP'i WSL Ubuntu'daki **~/openmc-proje/student/** dizinine açın. Klasör **~/openmc-proje/student/adaptive_03/** oluşur. `student_setup.md` içindeki bir defalık OpenMC 0.16.0, openmc-proje kerneli ve ENDF/B-VIII.0 HDF5 kurulumunu izleyin. Nükleer veri bu ZIP'te yoktur; `OPENMC_CROSS_SECTIONS` mevcut Conda ortamınızın yerel XML dosyasını göstermelidir.

```bash
conda activate openmc-proje
cd ~/openmc-proje/student/adaptive_03
PAKET="student_packages/v2_adaptive128_v1/adaptive_03/v2_adaptive_03_beavrs_v2_pilot_scope_v1"
python -c "import os, openmc; from pathlib import Path; p=Path(os.environ['OPENMC_CROSS_SECTIONS']); assert p.is_file(); print(openmc.__version__, p)"
python scripts/v2_student_production.py verify "$PAKET"
python scripts/v2_student_production.py preflight "$PAKET"
```

**Başlatma (bir kez):** `$PAKET/01_calistir.ipynb` dosyasını JupyterLab'da `Python (OpenMC Proje)` kerneliyle açıp Run All yapın. Aynı işlemi terminalden yapmak isterseniz yalnız `python scripts/v2_student_production.py launch "$PAKET"` komutunu kullanın; notebook ve terminali birlikte başlatmayın. İşçi tarayıcıdan bağımsız çalışır.

```bash
python scripts/v2_student_production.py status "$PAKET"
python scripts/v2_student_production.py stop "$PAKET"
python scripts/v2_student_production.py resume "$PAKET"
```

`stop` ve `resume` yalnız danışman yönlendirmesiyle kullanılır. Tamamlanan koşular tekrar çalıştırılmaz; `failed`/`stopped` grup kendiliğinden devam etmez. `02_sonuclari_incele.ipynb` yalnız sonuçları okur.

Grup tamamlanınca teslim ZIP'i:

```bash
mkdir -p deliveries
python scripts/v2_transfer.py export "$PAKET" "deliveries/v2_adaptive_03_beavrs_v2_pilot_scope_v1.zip"
```

Statepoint dosyaları hafif teslim ZIP'inde yer almaz; kaynak makinede saklayın. `completed` fiziksel doğrulama veya eğitim kabulü değildir. 24 saatlik grup tavanı öğrenci bilgisayarında 32 koşunun biteceğinin garantisi değildir.

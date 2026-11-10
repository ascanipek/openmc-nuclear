# 512 koşunun sayısal kalite taraması — v1

**PROVISIONAL_EXPLORATORY; fiziksel ACCEPT/REJECT yok.** [Tek senaryo tablosu](numerical_quality_512.csv), önceki kanıt ve entropi raporları ile kayıtlı 600 nesillik k/entropi dizilerinden oluşturuldu. `completed` fiziksel doğrulama değildir. Bu tarama, [öneri raporundaki](../numerical_quality_criteria_v1/README.md) 25 pcm hedefini **geriye dönük ve araştırma amaçlı** uygular; hedef evrensel fiziksel kabul toleransı değildir.

| İnceleme | Sonuç | Sınır |
|---|---:|---|
| k için 1σ MC standart hatası ≤ 0,00025 | 512/512 hedef içinde | Hassasiyet hedefi; k yanlılığı veya fiziksel doğruluğu ölçmez. |
| k/entropi geçmişi inceleme önceliği | 27/512 | 25 aktif k sürüklenmesi, 1 sınırda k–entropi birlikte değişimi, 1 her ikisi; **yakınsama kararı değil**. |
| Geometrik yakıtta sıfır kappa ölçümü | 350/512 koşuda var | Ölçülen sıfır, fiziksel sıfır veya sıfır belirsizlik değildir. |
| Geometrik yakıtta düşük sinyal | 449/512 koşuda var | Yakıt voxel oranı medyan %30,63, P95 %56,02; aynı bölgenin **ham toplam kappa üretim payı** medyan %0,00813, P95 %0,02051. Yerel ayrıntı ile toplam pay ayrı değerlendirilir. |
| Eşleşen statepoint bu makinede yok | 264/512 | Kayıtlı geçmişler incelenebilir; özgün statepoint doğrulaması eksik. |
| Alternatif nükleer veri indeksi | 11/512 | Özgün HDF5 dosyalarının bayt eşdeğerliği doğrulanmadı. |

**Geçmiş taramasının kuralı:** Mutlak aktif ilk/son 100 nesil k farkı mevcut dağılımın P95'i olan **0,001512** düzeyine ulaşıyorsa inceleme önceliği verildi. Ayrıca 250–299 ile 300–349 nesilleri arasında hem |Δk| ≥ **0,001936** hem |Δentropi| ≥ **0,011533** ise sınır geçişi birlikte işaretlendi. Bunlar *bu 512 kayıttan hesaplanan üst %5 tanı eşikleri* olup önceden belirlenmiş istatistiksel test veya kabul sınırı değildir. Yalnız entropi farkı hiçbir koşuyu işaretlemedi. İşaretlenmeyen 485 koşunun kaynağı yakınsamış ilan edilmedi; CSV'de 512/512 için `source_convergence_decision=NOT_ASSESSED`. Ardışık nesiller bağımlıdır, bu pencere farklarına bağımsız örneklem anlamlılığı yüklenmez.

Bu temkinli yorum [OpenMC'nin resmî özdeğer/kaynak yakınsaması açıklamasıyla](https://docs.openmc.org/en/stable/methods/eigenvalue.html) ve [OECD/NEA NEA/NSC/R(2021)3 kaynak yakınsaması incelemesiyle](https://www.oecd-nea.org/upload/docs/application/pdf/2023-05/nea_nsc_r_2021_3.pdf) uyumludur: k ile kaynak dağılımı birlikte incelenir; tek Shannon entropisi eğrisi veya tek istatistiksel test yeterli güvence sayılmaz. Burada uzaysal kaynak/fission-matrix sınamaları yapılmadı.

**Bağımsız tekrar için en fazla dört aday** (karar değil, risk sırası):

1. `V2-ADAPTIVE_01-0009`: aktif k farkı −0,002496; sınırda Δk +0,001976 ve Δentropi −0,02684; yüksek çubuk girişi (%93,96).
2. `V2-HALTON_04-0010`: sınırda Δk +0,002301 ve Δentropi −0,01813; eşleşen statepoint burada yok. Önce özgün statepoint aransın.
3. `V2-ADAPTIVE_03-0007`: k≈0,985; yüksek giriş (%83,67), yakıt voxellerinin %58,03'ü düşük sinyalli ve aktif k farkı +0,001681; statepoint eksik.
4. **Koşullu:** `V2-STAGE_256_OGRENCI_04-0003`: k≈0,984 ve alternatif nükleer indeksli 11 koşudan biri. Önce özgün Kaggle HDF5 hash envanteri aransın; referans kütüphaneyle yeni tekrar, eski HDF5 içeriğini geriye dönük kanıtlamaz.

Tekrarlarda aynı fiziksel koşul ve bütçe, farklı seed ve açık başlangıç kaynağı kaydedilmeli. Önce eksik dosyalar aranmalı; tekrar sonuçları MC hatalarıyla birlikte yorumlanmalı. 25 pcm hedefi, tanısal işaretler ve veri kökeni eksikleri **eğitim kabulü veya fiziksel doğrulama kararı üretmez**.

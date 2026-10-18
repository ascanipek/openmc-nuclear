# Eğitim veri sözleşmesi v1

Bir **fiziksel senaryo** bir örnektir. `scenario_id`, model/konfigürasyon/girişe; `run_id` ayrıca seed, parçacık ve diğer hesap ayarlarına bağlıdır. D2-B1/B2/B3 tek senaryo olarak gruplanır. `dataset.py` tamamlanmış ve kabul işareti (`acceptance.json` içinde aynı `run_id`, `accepted_for_data_production`, `source_convergence_reviewed=true`, `physical_validation_reviewed=true` ve boş olmayan `reviewer`) olan koşuları varsayılan olarak alır. `--preview` tamamlanmış ama fiziksel kabulü olmayanları açıkça `preview_not_accepted` etiketiyle ayırır. Koşu klasörünü değiştirmez. Mevcut D2 için kabul işareti yoktur.

Kaynak dosyalar: `resolved_config.json` fiziksel/hazırlık ayarları ve kimlikler, `summary.json` boyutsuz `k_mean ± MC standard error` ve birimler, `status.json` bütünlük, `fields.npz` ham alanlar/hatalar/maskeler/koordinatlar/tanılar (yakıt içinde sıfır ölçüm bayrakları ile güvenilirlik maskesi dahil). `statepoint.*.h5` ve `openmc.log` provenance; PNG hedef değildir. Çıktı `samples.npz`, `index.json`, `splits.json`, `train_preprocessing.json` içerir. Çıktı dizini yeni olmalıdır.

Alan sırası **[z,y,x]=[20,17,17]**. Ham `kappa_fission_mean` birimi eV/kaynak parçacığıdır: fisyon enerjisi üretimi yaklaşımıdır, toplam yerel ısı birikimi veya MW değildir. Yakıtla kesişen voxel kümesi `fuel_volume_fraction > 0` üzerinden `q_i = K_i / Σ_{j∈fuel} K_j`; yakıt dışı sıfır. Bu grid-tally toplamı normalize edilir; kısmi voxel enerji katkısı ham tally içinde zaten vardır, tekrar hacim çarpılmaz. Payda sıfırsa reddedilir. Ham `*_std_dev` alanları korunur; oranların tam belirsizliği veya fiziksel doğruluk yüzdesi diye sunulmaz. Sıfır ölçüm ile `fuel_volume_fraction=0` fiziksel sıfır ayrı kalır.

Ortak karşılaştırma maskesi önceden sabit seçilmelidir; tüm yakıt maskesi üzerinden ölçü ayrıca verilir. Koşudan koşuya değişen `relative_error_reporting_mask` yalnızca betimleyicidir. Kaynak yakınsaması için `k_generation`/`shannon_entropy` saklanır; otomatik kesin kabul yoktur. Bölme `scenario_sha256_80_10_10_v1` SHA256 kuralıyla tüm koşuları aynı senaryo bölmesine atar. Eğitim ön işleme özeti yalnızca train bölmesinin k hedeflerine uydurulur. `index.json` bütün kaynak klasörlerini ve seçilen en çok aktif tarihçeli koşuyu izler. Model/ağ/eksen/birim uyumsuzluğu hata verir.

Örnek komut (yalnızca **ön inceleme aktarımı**, taşıma başlatmaz): `python -m reactor_pipeline.dataset exports/d2_preview beavrs3d_d2_budget_v1 --preview`. Varsayılan kabul edilmiş aktarım için `--preview` kaldırılır; boş kabul kümesi 0 örnek üretir.



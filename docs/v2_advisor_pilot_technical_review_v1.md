# İlk 8 danışman paketi — teknik inceleme kaydı v1

Paket: `student_packages/v2_advisor_pilot_v1/v2_advisor_pilot8_beavrs_v2_pilot_scope_v1`. İnceleme tarihi 2026-10-18. Bu dosya **teknik onay değildir**; `approval.json` oluşturulmadı. Mevcut `verify_package(..., require_approval=True)` başlatma kapısı bu kayıt gelene kadar kapalıdır. Danışmanın kullanıcı mesajı sekiz aralığı ve 600/300 × 80k/1/6 profilini kontrollü pilot için onaylar; paket içeriğinin ayrı teknik onayını ve fiziksel/istatistiksel kabulü kapsamaz.

## Somut içerik farkı

- Eski 32 taslak senaryonun ilk sekiz ve bekletilen 24 olarak çakışmasız bölümü; orijinal ID/değerler aynı.
- Ayrı danışman paketi: tek Run All çalıştırma notebook'u, tek salt okuma sonuç notebook'u, 8 koşuluk sabit manifest, 14.400 s grup tavanı, seed 71001–71008.
- Çalışma raporu sabit geometri maskesi, sıfır/düşük sinyal ve önceki filtre dışı belirsizlikleri, eksenel payları, k/entropi başlangıç geçişini, gerçekleşen süre ve tahmin sapmasını içerir.
- Yeni koşucu `model.xml` üretir; alternatif giriş XML'lerini üretmez. Uyarılar açık logda kalır.
- Eski D2/D3/D4 kayıtları, manifestleri ve nominal V2 sonucu değişmedi. Kalan 24 başlamaz.

## Başlatma kapısına bağlanacak içerik

| Dosya | SHA256 |
|---|---|
| `package.json` | `a8a16e45dafb3c42781d38d53010129ee931948095e0bcb8300fae96fe23df34` |
| `SHA256SUMS.json` | `25e60713643c5b3dad1bef76c1c10b871dfcbac3cf3646f3b97cc68b985fa532` |
| `manifest.json` | `77891f42ab6924f020ba2b26fa3a0a44fb00222d47b149a1a85a11ff74be00a8` |

Mevcut proje mekanizmasındaki **tek kalan adım**, danışmanın bu paket ve yukarıdaki iki kapı hash'i için açık teknik onayıdır. Bunun ardından yalnız mevcut biçimde paket dizinine `approval.json` yazılabilir: `status=approved`, `package_sha256` ve `hashes_sha256` yukarıdaki değerler. Kaynak veya notebook girdisi değişirse yeni inceleme gerekir. Bu onay fiziksel doğrulama, kaynak yakınsaması veya eğitim verisi kabulü değildir. Onay verilmeden Run All başlatma hücresi durur; önceki hücreler paket ve ön kontrolü gösterebilir.

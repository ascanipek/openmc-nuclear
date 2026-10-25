# 256 V2 senaryosu: ML eğitimine kabul incelemesi

Bu kayıt, kaynak veri setinden ayrıdır; kabul işareti veya yeni MC sonucu değildir.

## Karar

k ve 3B bağıl kappa-fission için ACCEPT 0, REVIEW_REQUIRED 256, REJECT 0. Tüm kayıtlar yapısal olarak geçerlidir; kaynak yakınsaması ve idealize demetin fiziksel/model doğrulaması senaryo bazında kabul edilmemiştir. Başarılı transport, bu kabulün yerine geçmez.

## Kanıt ve sınırlama

Yerel statepoint ile k, geçmiş, entropi, seed ve bütçesi eşleşen: 120/256. Diğer 136 büyük statepoint hafif teslimlere alınmamıştır; onların tally/k geçmişi kaynak statepoint'ten bu makinede bağımsız yeniden denetlenemez. Kaydedilmiş alan ve logları vardır.

OpenMC commit'i tüm koşularda aynıdır. Nükleer veri için gerekli nüklid listesi ve sıcaklık gridleri metadata düzeyinde aynı; 11 Kaggle koşusunda yol yeniden yazıldığı için XML indeks hash'i farklıdır. Hiçbir kaynak makinedeki tüm HDF5 dosyalarının koşu anı byte hash'leri mevcut değildir. Bu nedenle kütüphanelerin fiziksel eşdeğerliği dosya adı veya indeks hash'iyle ilan edilemez. OpenMC loglarında Zr96 ve Cd106 olasılık tablosu negatif değer uyarıları kayıtlıdır.

Yakıt voxel'i: 5280/senaryo. Sıfır ölçümlü yakıt voxel'i toplamı: 180434; düşük sinyal toplamı: 380837. Üst dört dilimde sıfır payı: 48.4%. Düşük sinyal tanımı mevcut v2_runner tanısıdır; bir eğitim kabul eşiği değildir. Sıfır ölçüm fiziksel sıfır demek değildir. Eksenel ve XY ayrıntısı ayrı CSV dosyalarındadır.

## Bölme ve ilk eğitim koşulu

Mevcut 208/25/23 eğitim/kalibrasyon/test bölmesi değişmedi. Şu anda kabul edilmiş eğitim alt kümesi boştur. Yalnız yöntemi denemek için preview verisi kullanılırsa bu bilimsel eğitim kabulü diye sunulmamalı; test bölmesi model seçimi ve adaptif örnekleme dışında tutulmalı; 11 farklı indeksli senaryo ayrı işaretlenmelidir. Resmî ilk eğitim için kaynak yakınsama incelemesi, hedefe özgü uzaysal hata ölçütü, HDF5 kaynak kanıtı ve idealize modelin kullanım sınırı belgelenmelidir.

Yeniden MC için otomatik liste üretilmedi: önce eksik statepoint ve HDF5 provenance istenmeli, ardından kaynak tanısı veya hedef çözünürlüğü yetersiz kalan belirli senaryolar seçilmelidir. Çubuklu üst dilimlerde ek tarihçe gerekebilir; mevcut sıfırları otomatik ret saymak doğru değildir.

## Sayısal tanılar

Her koşu 600/300 batch ve 80.000 parçacık/nesil kullanır: 24 milyon aktif tarihçe. k MC standart hatası medyanı 0.00018452, aralığı 0.00014037–0.00020869. Önceden belgelenmiş 0,0002 önerisinin üzerinde 14 koşu vardır; bu öneri kabul kapısı olarak uygulanmadı. Aktif pencerenin ilk ve son 50 batch k ortalamaları arasındaki mutlak fark medyanı 0.000602, %95 yüzdeliği 0.001783; pencere ortalamalarının korelasyonu/hatası modellenmediği için bu fark kaynak yakınsaması testi değildir.

Sıfır yakıt voxel oranının senaryo medyanı 9.7%, %95 yüzdeliği 36.2%; düşük sinyal için aynı değerler 29.8% ve 56.5%. Düşük sinyalli voxel'lerin ölçülen toplam kappa-fission payının medyanı 0.0081%, en yükseği 0.0261%; örneklenmemiş gerçek katkıya üst sınır değildir. Pozitif ölçümlü yakıt voxel'lerinde koşu başına göreli MC hatanın %95 yüzdelik medyanı 83.4%. Çubuk giriş oranı ile sıfır/düşük sinyal oranlarının betimleyici Pearson korelasyonları 0.751/0.835; sekiz kontrol birlikte değiştiği için nedensel etki diye yorumlanmaz.

## Koşullu ilk alt küme

Aynı XML indeks hash'i ve bu makinede SHA-256/statepoint doğrulaması birlikte bulunan öncelikli inceleme kümesi eğitim/kalibrasyon/testte 91/9/9'dur. Bunun hiçbir üyesi henüz ACCEPT değildir; HDF5 byte eşdeğerliği ve yakınsama incelemesi gerekir. Bu kümede mevcut düşük sinyal tanısına hiç girmeyenler yalnız 11/2/1'dir ve kapsamlı 3B öğrenme için temsil gücü çok sınırlıdır. Bu alt kümeler mevcut split kimliklerini değiştirmez.

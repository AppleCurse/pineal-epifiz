# Kullanılabilirlik (UX) İyileştirme Raporu

Ön yüz (frontend) dosyalarındaki metin ve mesajları incelediğimde, "normal" bir kullanıcının anlamakta zorlanacağı bazı teknik ifadeler tespit ettim.

1. **"TRACKER HATASI" ve "ERROR" Etiketleri**
   Ajan panelinde bir şeyler ters gittiğinde ekranda "TRACKER HATASI" yazıyor. "Tracker" terimi yazılımcılar içindir. Normal kullanıcı bunun ne anlama geldiğini bilemez.
   *Tavsiye:* Bunun yerine basitçe "BAĞLANTI KOPTU" veya "SİSTEM YANIT VERMİYOR" yazmalıdır.

2. **Hata Mesajları: "Mission launch failed"**
   Konsolda veya görev butonuna basıldığında hala İngilizce ve teknik olan hata mesajları mevcut.
   *Tavsiye:* "Görev başlatılamadı, internet bağlantınızı kontrol edip tekrar deneyin" gibi yönlendirici Türkçe mesajlar konmalıdır.

3. **Vault (Kasa) Uyarıları**
   Bir hedef analizi yapılmak istendiğinde kasa kilitliyse arka planda teknik bir uyarı dönüyor ancak ekrana tam yansımıyor olabilir.
   *Tavsiye:* Ekrana büyük harflerle "KASA KİLİTLİ. Analiz için kasayı açmalısınız." şeklinde direkt bir uyarı çıkmalıdır.

4. **"Düşük Kanıt" veya "Error_message" Kullanımları**
   Bir analiz durduğunda "error_message" isimli teknik metin ekrana basılabiliyor.
   *Tavsiye:* Kullanıcıya "Sistem bu hedef için yeterli veri bulamadığı için araştırmayı güvenli şekilde durdurdu" gibi insani bir cümle gösterilmelidir.

Bu maddeler, uygulamanın teknik soğukluğunu kırıp, kullanıcının sisteme güven duymasını sağlayacak kritik dil değişiklikleridir.

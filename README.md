# PINEAL-HERETIC (İçgörü Asistanı)

Merhaba! Pineal-Heretic, sosyal medya (örneğin Instagram) üzerindeki herkese açık profilleri inceleyen, gördüklerini sizin yerinize okuyup analiz eden akıllı bir asistandır.

Bu program hackerlık yapmaz, şifre kırmaz veya gizli hesaplara sızmaz. Bir insanın günlerce ekrana bakarak yapacağı araştırmayı (fotoğraflar, yazılar, paylaşım saatleri), saniyeler içinde yapar ve size anlaşılır bir "profil özeti" sunar.

## Ne İşe Yarar?
1. **Veri Toplar:** Sizin verdiğiniz herkese açık bir profildeki resimleri, yazıları ve saatleri okur.
2. **Karakter ve Davranış Çıkarımı Yapar:** Paylaşımlara bakarak kişinin hangi saatlerde daha aktif olduğunu, ne tarz şeyler paylaşmayı sevdiğini ve ilgi alanlarını anlamaya çalışır.
3. **Kasa (Vault) Güvenliği:** Topladığı tüm notları yerel ve şifreli bir "Kasa" içinde saklar. Dışarıya hiçbir bilgi sızdırmaz. Kasa kilitliyken sistem kesinlikle internete çıkmaz, işlem yapmaz. Sizin izniniz (kasa açık durumu) olmadan çalışmaz.
4. **Çocuk Koruması:** Sistem 18 yaş altındaki çocukların hesaplarını analiz etmeyi reddeder. Bu kesin bir kırmızı çizgidir ve sistemin en temel kurallarından biridir.

## Nasıl Kullanılır?
Uygulama son derece basittir. Ekrana girdiğinizde karşınıza bir asistan ("Aspasia") ve komuta merkezi çıkar.

- **Hedef Belirleme:** İncelemek istediğiniz profili sisteme girersiniz.
- **Kasa Kilidi:** Ekranda gördüğünüz "VAULT (KASA)" butonuna basarak kasanın kilidini açmalısınız. Kilidi açmazsanız asistan dış dünyaya bağlanmaz.
- **Araştırmayı Başlat:** Görevi başlattığınızda sistem yavaş yavaş verileri toplamaya, analizleri birleştirmeye başlar ve sonuçları ekrana Türkçe, sade bir dille döker.

## Yazılımcılar veya Meraklılar İçin
Bu depo, tamamen Python ve Svelte ile yazılmış, "otonom yapay zeka ajanları" mantığıyla çalışır. Her bir ajan (örn: *İnsan Davranışı Analisti*, *Zamanlama Uzmanı*) kendi işini yapar ve merkezdeki karar mekanizmasına gönderir.

Uygulamanın çalışması için gerekli adımlar:
1. Terminalden `baslat.bat` veya Docker komutları ile sistemi ayağa kaldırmak.
2. Tarayıcıdan `http://localhost:8000` adresine gitmek.
3. API anahtarlarınız ve diğer güvenlik duvarlarınız devredeyken asistanınızla konuşmaya başlamak.

*(Not: Eski deneme dalları temizlenmiş, raporlar `docs/reports/` altında toparlanmış ve sadece gerçekten çalışan özellikler açıkta bırakılmıştır.)*

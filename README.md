# PINEAL-HERETIC (İçgörü Asistanı)

Merhaba! Pineal-Heretic, sosyal medya (özellikle Instagram ve X) üzerindeki herkese açık profilleri inceleyen, gördüklerini sizin yerinize "insani bir gözle" okuyup analiz eden akıllı bir asistandır.

Bu program **kesinlikle bir hacker aracı değildir**, şifre kırmaz veya gizli hesaplara sızmaz. Sadece internetteki herkese açık resimleri, yazıları ve paylaşım saatlerini alır, tıpkı sizin günlerce ekrana bakarak yapacağınız gibi okur, ancak bunu saniyeler içinde yaparak size anlaşılır, dürüst bir "profil özeti" sunar.

---

## Ne İşe Yarar ve Nasıl Çalışır?

Diyelim ki bir hesabı incelemek istiyorsunuz. Programın içinde birbirinden farklı uzmanlıkları olan **12 Akıllı Ajan (Uzman)** bulunur. Görevi başlattığınızda şunlar olur:
1. **Veri Toplar:** Sizin verdiğiniz linkteki herkese açık resimleri ve yazıları çeker.
2. **Davranış ve Karakter Analizi Yazar:**
   - *Zamanlama Uzmanı*, kişinin hangi saatlerde daha aktif olduğunu söyler.
   - *İnsan Davranışı Analisti*, o kişinin paylaşımlarından ne tarz şeyleri sevdiğini, hobilerini ve karakter yapısını anlamaya çalışır.
   - Bütün uzmanlar kendi aralarında toplanıp hedefin profilini tartışarak tek, net bir rapor çıkarır.
3. **Kasa (Vault) Güvenliği:** Asistan, topladığı notları ve gördüğü fotoğrafları hiçbir zaman internette bırakmaz. Bilgisayarınızın derinlerinde yer alan, adına "Kasa (Vault)" dediğimiz şifreli bir odada tutar. **Ekranda kasayı kilitle derseniz**, sistem dış dünyayla (internetle) bağını tamamen koparır ve asla araştırma yapmaz.
4. **Çocuk Koruması (Kırmızı Çizgi):** Hedef hesaptaki kişi 18 yaşının altındaysa asistan bunu tespit eder etmez araştırmayı durdurur. Bu, sistemin üzerine kurulu olduğu değişmez, aşılamaz, en temel kuraldır.

---

## 💻 Mühendisler ve Geliştiriciler İçin Kurulum Rehberi

Proje hem **Python** tabanlı, dağıtık otonom ajanlarla çalışan bir Backend'den hem de **Svelte** ile yazılmış hızlı bir arayüzden oluşur.

### 1. Kurulum ve Başlatma
Sistemi sıfırdan kurmak ve çalıştırmak için:
- Gerekli kütüphaneleri yüklemek için (Backend):
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.lock
  ```
- Sistemi doğrudan başlatmak için Windows'ta `baslat.bat` dosyasını, Unix sistemlerde ise Docker komutunu (`docker compose up --build -d`) kullanabilirsiniz.
- Frontend'i (Ön Yüz) elle derlemek isterseniz:
  ```bash
  cd frontend
  npm ci
  npm run build
  ```

### 2. Arayüze Erişim
Kurulum bittikten sonra internet tarayıcınızı (Chrome, Safari vb.) açıp **`http://localhost:8000`** adresine gidin. Karşınıza görev kontrol ekranı ve asistanınız "Aspasia" gelecektir.

### 3. Yapılandırma ve Çalışma Prensibi (Kısa Mimari)
- Tüm sistem dışarıya çıkışlarını `agent_core/capabilities/` isimli omurgadan (backbone) geçirir. Asla dış kütüphaneler (örneğin OpenAI vb.) doğrudan kullanılamaz; daima bu geçit kapısından onay alır.
- Veri yetersizse sistem kendi kendine veri "uydurmaz". Analiz başarısız olur ve kırmızı bir uyarı basar (`Fail-Closed` kuralı).

---

*(Not: Eski yapay zeka denemeleri, bozuk kod parçaları ve kafa karıştırıcı dallar temizlenmiştir. Burası, uygulamanın çalışır ve insani en net halidir.)*

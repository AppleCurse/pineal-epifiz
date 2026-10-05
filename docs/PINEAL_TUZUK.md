# ATLAS PINEAL — TÜZÜK (v2)

**Yürürlük:** 2026-10-05
**Yerine geçtiği metin:** `README.md` §1 "Sistemin 4 Dokunulmaz İlkesi" (o ilkeler bu tüzüğün 1–4. maddeleridir; ilkeler değişmedi, **bağlamı büyüdü**).
**Bağlı olduğu karar belgesi:** [`docs/reports/YILDIZ_DEPO_KARAR_AGACI_2026-10-05.md`](reports/YILDIZ_DEPO_KARAR_AGACI_2026-10-05.md) — 325 depo, 8 kapı, 10 faz.
**Kod karşılığı:** `agent_core/capabilities/` — bu tüzüğün maddeleri, yetenek omurgasında **kapı (gate)** olarak çalışır. Tüzük metni ile kod arasında fark varsa, denetim raporu yazılır; sessizce fark bırakılmaz.

---

## Madde 0 · Neden değişti

Pineal kurulurken ilk ve tek işi şuydu:

> *"Git, bir insanı analiz et; karşısındakiyle tartıya koy; uyuyorlar mı, uymuyorlar mı söyle."*

Sistem o günden bu yana büyüdü. Kanıt mührü, 7 dalga motoru, 3'lü jüri, kasa
mandalı, adli rapor, çok kanallı OSINT ve şimdi yetenek omurgası (Capability
Spine) eklendi. **Alet, verilen ilk işten daha büyük hâle geldi.**

Bu yüzden tüzük yeniden yazıldı:

- **Uyum / ilk temas / rezonans, bu sistemin TANIMI değildir artık; SAHALARINDAN BİRİDİR.**
- Sistemin tanımı: **Atlas Pineal, kamuya açık kaynaklar üzerinde çalışan bir adli gözlem ve doğrulama istasyonudur.**
- Bir yeteneğin ürüne girip giremeyeceği, "uyum analizine yardım ediyor mu?" sorusuyla değil, **bu tüzüğün maddeleriyle** ölçülür.

---

## Madde 1 · Gözlem, hüküm değildir

1. Karakter analizi, bastırılmış narsisizm, travma, niyet okuma — **hiçbiri LLM'e tahmin ettirilmez.**
2. Yedi dalga motoru (`frequency`, `seismos`, `void`, `strata`, `gravity`, `pulse`, `key`) deterministik ve **LLM'siz** çalışır.
3. Bu ölçümler **betimleyici/heuristik kaynak ölçümleridir; psikometrik test, teşhis veya mahkeme hükmü değildir.**
4. LLM yalnızca üç yerde kullanılır: **dil sentezi, çapraz denetim (jüri), diyalog tasarımı.**
5. Bir çıktı "kişi böyledir" diyorsa ve arkasında `EvidenceItem` yoksa, o çıktı **silinir** — yumuşatılmaz.

## Madde 2 · Kanıt mührü (fail-closed)

1. Kanıtı olmayan iddia üretilemez. Veri yoksa kanal dürüstçe kapanır veya işlem durur (`InsufficientEvidenceError`).
2. Her yetenek çıktısını `EvidenceItem` olarak verir: kaynak, alınma zamanı, provenance, çıkarıcı, epistemik tür (`observation` / `absence` / `inference` / `strategy`).
3. **"Hiç iz yok" iddiası yalnızca tarama sıfır hata ile tamamlandıysa yapılır.** Hatalı/karışık koşulda yokluk iddia edilmez.
4. Alıntı korpusu (`quote_guard`) yalnızca kesin statülü, kaynakta birebir geçen metinlerden oluşur; uydurma alıntı imha edilir.
5. Boşluk **sallanarak doldurulmaz** — bu bir tercih değil, sistemin çalışma biçimidir.

## Madde 3 · Şeffaflık: simülasyon yok

1. Arayüzde rastgele yanan sahte LED, yapay zamanlayıcı, `demoMode` **bulunmaz.**
2. Ekranda görülen her durum, güven puanı ve log; FastAPI WebSocket / Redis Pub/Sub üzerinden akan **gerçek** telemetridir.
3. Bir yetenek kullanılamıyorsa ekranda `available: false` + **makine-okunur sebep** görünür; "çalıştı" görüntüsü verilmez.
4. Skorlar, hangi modelin/kaç denemenin/maliyetin ürettiği bilgisiyle birlikte kanıt zincirine yazılır.

## Madde 4 · Kasa ve rıza: kilit ve izin

> **2026-10-05 kararı (K1): rıza/yaş kapısı ZORUNLUDUR. Faz 5'ten Faz 1'e çekildi.**

1. **Kasa (vault):** mandal kilitliyken dış dünyaya tek bir istek çıkmaz. Bu, hiçbir yetenek için esnetilmez.
2. **Rıza kaydı:** hedef için rıza kaydı (kim, hangi amaç, hangi kapsam, ne zaman, ne zaman silinecek) oluşturulmadan analiz **başlamaz.** Kapı adı: `consent`.
3. **Yaş kapısı:** reşit olmayan olduğuna dair makul şüphede pipeline `halted_consent` ile durur ve gerekçeyi rapora yazar.
4. **Israr takibi:** aynı hedefin tekrar tekrar taranması kaydedilir; eşik aşımında operatöre uyarı gider. Genel rate-limit bunun yerine geçmez.
5. **Retention & silme:** her hedef verisinin saklama süresi vardır; silme talebinde kanıt dosyaları da silinir (`DELETE /api/tasks/{id}`).
6. Kısıtlı yetenekler (`A†`: e-posta varlık taraması, telefon doğrulama vb.) **yalnızca** operatörün kendi kimliği veya rıza kaydı olan hedef için çalışır.

## Madde 5 · Operatör kimliği: taklit yok, kayıt var

> **2026-10-05 kararı (K2): platform sensörleri operatörün KENDİ hesabıyla çalışır.**

1. Oturum gerektiren sensörler (X/Twitter, Instagram, LinkedIn vb.) operatörün **kendi** hesabıyla, izlenebilir biçimde çalışır.
2. Anonim/taklit erişim, bot çiftlikleri, kiralık hesap havuzları, platform imzalarını kırma (X-Bogus/X-Gnarly vb.) **yasaktır.**
3. Kimlik bilgileri yalnızca env/vault'ta tutulur; **log, telemetri, kanıt ve rapora asla sızmaz** (redaction testleri zorunludur).
4. Oturum paylaşımı (operatörün açıkça izin verdiği tarayıcı oturumu) kayıt altındadır: ne zaman, hangi hedef, hangi hesap.
5. Hesap gerektirmeyen, ücretsiz ve açık yollar (SearXNG, public-web araştırma) **önceliklidir**; hesap gereken sensörler ikinci katmandır.

## Madde 6 · Mahremiyet ve yerellik

> **2026-10-05 kararı (K3): yerel çıkarım donanımı mevcut → yerel jüri öne alındı.**

1. **Yerel jüri:** 3'lü hakem paneli yerelde koşar. Hedef verisi makineden çıkmaz, maliyet sıfırdır.
2. Yerel model yoksa dürüst `UNAVAILABLE` döner; **buluta sessiz düşüş yoktur.**
3. Kanıt deposu operatörün cihazındadır; zorunlu olmayan hiçbir veri üçüncü tarafa gönderilmez.
4. Başkasının sistem prompt'u, sızdırılmış model ağırlığı, ihlal veritabanı veya "sansür kaldırma" araçları **kullanılmaz.**
5. Kişi verisi işleyen her yetenek, kendi adına değil **kayıtlı operatör adına** çalışır ve denetim izi bırakır.

## Madde 7 · Tek parça: yetenek omurgası

1. Her yetenek — ister kendi kodumuz ister bir depodan gelsin — **tek sözleşmeden** geçer: `PolicyKernel` → `CapabilityRegistry` → `CapabilityRunner` → `EvidenceItem`.
2. **İkinci kaynak yasağı:** "yetenek var mı / açık mı?" sorusunun cevabı yalnızca `CapabilityRegistry`'dedir. Doğrudan import denemesi, env okuyan ikinci katman, paralel config — yasaktır (kural [009]).
3. **Bilinmeyen kapı = ret.** Bir yetenek çekirdeğin tanımadığı bir kapı bildiriyorsa çalışmaz.
4. İkinci bir platform karar katmanı, ikinci bir orkestrasyon katmanı, ikinci bir kanıt deposu **yoktur.**
5. Güvenlik yamaları hiçbir aracın sürüm pinine rehin değildir (CVE-2026-48710 dersi).

## Madde 8 · Yasaklar (tüzük dışı kullanım)

Bunlar ürüne girmez; karar belgesi §5'te gerekçeleriyle kayıtlıdır:

| Yasak | Örnekler |
|---|---|
| Karanlık ağ tarama & saldırı arsenali | TorBot, darkfox, robin, exploitarium, PayloadsAllTheThings |
| İhlal/şifre verisi ve gizli içerik | WhatBreach, pwnedOrNot, GHunt, InstagramPrivSniffer |
| Ses/yüz klonlama ve kimlik taklidi | RVC, GPT-SoVITS, facefusion, Deep-Live-Cam |
| Jailbreak & sızdırılmış prompt külliyatı | L1B3RT4S, CL4R1T4S, G0DM0D3, heretic, system_prompts_leaks |
| Filtresiz üretim | locally-uncensored, Open-Generative-AI |
| Otomatik mesaj gönderimi | postiz-app (ADR: Pineal taslak üretir, **göndermez**) |
| Konum/canlı izleme | phoneinfoga, osint-X, RuView |
| Platform güvenlik mekanizmasını kırma | tiktok-web-reverse-engineering, webmssdk_patch |

## Madde 9 · Sahalar (kullanım alanları)

| # | Saha | Açıklama |
|---|---|---|
| 1 | **Adli profil & doğrulama** | Kamuya açık kaynaklardan gözlemlenebilir kanıtla profil; iddiaların çapraz doğrulanması. **Asıl saha.** |
| 2 | **Kimlik / catfish teyidi** | Tersine görsel arama, perceptual hash, EXIF, görsel-metin tutarlılığı — "bu kişi iddia ettiği kişi mi?" |
| 3 | **Açık kaynak araştırması** | Kişi, kurum, domain, olay; zaman çizelgesi, ilişki ağı, değişim takibi. |
| 4 | **Rezonans & ilk temas** | *Tarihî çekirdek görev.* Artık **bir saha**: iki profil arası vektörel benzerlik **betimlemedir**, uyum/ilişki hükmü değildir. |
| 5 | **Eğitim & denetim** | Operatör eğitimi, adli rapor üretimi, kendi sisteminin denetimi. |

> Saha 4 notu: rezonans skoru `0.70` eşiği **ölçülmemiş bir sabittir** ve kalibrasyon fazına (Faz 1/Faz 6) bağlıdır. Kalibrasyon verisi olmadan eşik değiştirilemez.

## Madde 10 · Yürürlük ve değiştirme

1. Bu tüzük, **koddaki kapılara** bağlıdır: bir madde ihlal edilirse ilgili capability `PolicyKernel` tarafından kapatılır, uyarı verilmez.
2. Tüzük değişikliği: karar belgesi + `CHANGELOG` kaydı + (gerekiyorsa) test ile yapılır. **Sessiz ilke değişikliği yoktur.**
3. Bir yetenek eklenirken sorulacak tek soru: *"Bu, tüzüğün hangi maddesine hizmet ediyor ve hangi kapılardan geçiyor?"* Cevap yoksa yetenek eklenmez.
4. Denetim: her fazın sonunda tüzük ↔ kod farkı raporlanır (`docs/reports/`).

---

## Kısa form (duvar yazısı)

```
GÖZLEM, HÜKÜM DEĞİLDİR          → fal yok, ölçüm var
KANIT YOKSA İDDİA YOKTUR        → fail-closed
SAHTE IŞIK YOKTUR               → simülasyon yok, gerçek telemetri
KİLİT VE İZİN                   → kasa + rıza + yaş kapısı (ZORUNLU)
TAKLİT YOK, KAYIT VAR           → kendi hesabın, izlenebilir erişim
VERİ SENİN CİHAZINDA            → yerel jüri, maliyet 0, mahremiyet
TEK PARÇA                       → tek sözleşme, tek kayıt, tek kapı
```

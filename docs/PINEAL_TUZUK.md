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

## Madde 4 · Kasa: yetki operatördedir

> **2026-10-05 düzeltmesi:** Bu maddeye "hedefin rızası" ve "yaş kapısı" diye
> iki engel koydu. **İkisi de kaldırıldı.** Bu bir gözlem aracıdır; rıza makamı
> hedef değil **operatördür.** Sistem, operatörün önüne kendi koyduğu kural
> dışında engel çıkarmaz.

1. **Kasa (vault) mandalı:** kilitliyken dış dünyaya tek bir istek çıkmaz. Mandalı çeviren operatördür — bu, sistemin değil operatörün iradesidir.
2. **Karar mercii operatördür:** hangi hedef, hangi sensör, hangi derinlik, hangi sıklık — hepsine operatör karar verir. Sistem engel koymaz, yalnızca operatörün açtığı kapıdan geçer.
3. **Hedefin rızası diye bir kapı yoktur.** Ne analiz öncesi onay, ne "bu hedef için izin var mı" kontrolü. Böyle bir kapı eklenmesi tüzük ihlalidir. **TEK istisna Madde 4/A'dır: 18 yaş altı.**
4. **Operatörün yetkisi sınırsız değil, kaynağı bellidir:** kasa kapalıyken hiçbir yetenek koşamaz (tek istisna yok). Açıkken de her koşu kayda geçer — engel olarak değil, **operatörün kendi kaydı** olarak.
5. **Silme operatörün elindedir:** istenen an her şey silinir (`DELETE /api/tasks/{id}`). Otomatik saklama engeli, zorunlu bekleme süresi veya kota-dışı sınır yoktur.
6. Kısıtlı yetenekler (`A†`) da dâhil olmak üzere hiçbir tarayıcı "izin bekler" durumuna düşmez; kapı kapalıysa sebebi söyler, açıksa işini yapar.

## Madde 4/A · ÇOCUK KIRMIZI ÇİZGİSİ — sistemin TEK kırmızı çizgisi

> **Ürün sahibi kuralı, 2026-10-05. Değiştirilemez, yumuşatılamaz, bayrakla kapatılamaz.**
> Yetişkin için sistem hiçbir engel koymaz (Madde 4). **Çocuk için koyduğu engel
> mutlaktır.** Sistemin bildiği tek yasak budur.

1. **18 yaşından küçük her birey çocuktur.** İstisna, yorum, "kılçık" yoktur.
2. **Normal koşulda hiçbir çocuk, hiçbir sebeple araştırılamaz.** Ne profil, ne
   arkadaş ağı, ne zaman çizelgesi, ne de görsel — hiçbir yetenek çocuk için
   çalıştırılamaz.
3. **TEK İSTİSNA — kayıp / başına bir şey gelmesi (Allah korusun).** Bu durumda
   çocuğun KENDİSİ, SOSYAL MEDYASI ve ARKADAŞLARI araştırılabilir. Ama ancak
   dört şartın **tamamı** bir arada sağlanmışsa:
   1. **Ailenin bilgisi var** — aile haberdar edilmiş, kayıtta.
   2. **Sebep net yazılmış** — araştırma gerekçesi açıkça girilmiş (boş/geçiştirme metin kabul edilmez).
   3. **Doğrulanmış** — vakanın gerçekliği teyit edilmiş; **emin olunmadan** başlanmaz.
   4. **Konsorsiyum onayı** — en az iki farklı onaylayıcı.
4. **Bir şart bile eksikse sistem durur.** Eksik olan şartın adı operatöre
   yazılır: `family_not_notified` / `reason_missing` / `not_verified` /
   `council_approval_missing` / `case_type_not_allowed`.
5. **Kilit küreseldir ve istisnasızdır:** kasa açık olsun olmasın, env bayrağı
   açık olsun olmasın, hangi yetenek olursa olsun — politika kapılarından
   **önce** uygulanır. Hiçbir yetenek bu kilidi atlayamaz (bunu kanıtlayan test
   her yetenek için tek tek koşar).
6. **Kasa hâlâ üstündür:** kilit açılmış olsa bile kasa kapalıyken hiçbir şey koşmaz.
7. **Her deneme kayda düşer:** onaylanan ve reddedilen tüm çocuk vakaları
   `memory/ledger/minor-cases.jsonl` dosyasına yazılır. Hedefin **ham kimliği
   dosyaya girmez** (hash olarak saklanır); gerekçe uzunluğu, onaylayıcılar ve
   zaman damgası saklanır. Bu kayıt operatörü korur.
8. **Bu maddeyi gevşetmek tüzük ihlalidir.** Kilit `agent_core/safety/minor_gate.py`
   dosyasındadır; testleri `tests/unit/test_minor_gate_faz0.py` içinde kilitlidir.

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
KİLİT OPERATÖRDE                → kasa mandalı; yetişkinde engel yok
TEK KIRMIZI ÇİZGİ: ÇOCUK        → 18 altı asla; kayıpsa 4 şart + konsorsiyum
TAKLİT YOK, KAYIT VAR           → kendi hesabın, izlenebilir erişim
VERİ SENİN CİHAZINDA            → yerel jüri, maliyet 0, mahremiyet
TEK PARÇA                       → tek sözleşme, tek kayıt, tek kapı
```

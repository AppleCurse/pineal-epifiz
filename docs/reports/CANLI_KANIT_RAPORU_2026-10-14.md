# Canlı Kanıt Raporu — 2026-10-14

**Sorulan soru:** "Çalışmayan 33 faaliyet rezillik mi?", "bunca canlıya çıkış testi
boş teneke mi?", "yapay zekâ beyni gerçekten çalışıyor mu?"

**Cevap yöntemi:** Lafla değil, **gerçek sunucu + gerçek istekler + gerçek
üretilmiş dosyalar**. Bu rapordaki sayıların hepsi bu turda ölçüldü.

---

## 0 · Ne yapıldı (üç katman)

| Katman | Ne yapıldı | Sonuç |
|---|---|---|
| 1 · Gerçek sunucu | `uvicorn backend.api:app` gerçekten ayağa kaldırıldı (0.0.0.0:8000) | Ayakta · `/health` **200** "ready" |
| 2 · Gerçek HTTP | Canlı `/openapi.json`'dan 70 `/api/` yolundan yolu-parametresiz olanlara **58 istek** atıldı | **0 hata (0×500)** |
| 3 · Gerçek üretim | Kapılar açılıp yetenekler **runner üzerinden koşturuldu**; çıkan dosyalar diskte doğrulandı | **4/5 yetenek gerçek çıktı üretti** |

**Önemli güvenlik kanıtı (0. adım):** Sunucu İLK denemede **başlamayı reddetti**:

```
AUTH_FAIL_CLOSED: PINEAL_ENV set edilmemiş; ortam ÜRETİM varsayıldı.
PRODUCTION_AUTH_REQUIRED: PINEAL_TOKEN must be configured when authentication is required
```

Yani bu sistem "herkesin erişebileceği açık kapı" değil: üretim duruşunda token
yoksa **hiç açılmıyor**. Geliştirme duruşu için `PINEAL_ENV=development` açıkça
verilmek zorunda. Bu bir kusur değil, **fail-closed güvenlik davranışıdır**.

---

## 1 · "Çalışmayan 33 faaliyet" — bu bir YANLIŞ OKUMA

Doğru sayılar (bu tur, canlı `/openapi.json`):

| Ölçüm | Sayı |
|---|---|
| Benzersiz `/api/` yolu | **70** |
| Ön yüzün (arayüzün) çağırdığı | **33** |
| Ön yüzün çağırmadığı | **37** |

"37" ne demek? **"Bozuk" demek DEĞİL.** Anlamı: o işlevin arayüzde **düğmesi
yok**; operatör tarafından API/CLI üzerinden çağrılır. Kanıt: bu uçlara canlı
sunucuda gerçek istek atıldı ve **hiçbiri çökmedi**:

| Durum | Sayı | Ne demek |
|---|---|---|
| **200** | **24** | Gerçek içerik döndü (kimlik bilgisi olmadan!) |
| 422 | 32 | Gövdesiz çağırdım; sözleşme denetimi devrede (dürüst ret, çökme değil) |
| 423 | 1 | Kasa kilitli (güvenlik mandalı çalışıyor: `/api/vault/unlock`) |
| 400 | 1 | Ses dosyası yok — dürüst hata kodu |
| **500** | **0** | **Hiçbir uç çökmedi** |

Kimlik bilgisi girilmeden **gerçek veri döndüren** uçlardan örnekler (hepsi 200):
`/api/agents/status` (ajan rostosu) · `/api/aspasia/state` (kayıtlı ajanlar) ·
`/api/report/status` (hangi format üretilebilir) · `/api/media/status` ·
`/api/jury/status` (dürüst: `no_local_models`) · `/api/language/status` ·
`/api/mcp/status` · `/api/calibration` · `/api/telemetry` · `/api/vault/status` ·
`/api/speech/status` · `/api/experimental/stealth` · `/api/minor/state` …

**Sonuç:** "33 çalışmayan faaliyet" tespiti, raporun "ön yüz kapsaması" satırının
yanlış okunmasıdır. Doğrusu: **70 uçtan 33'ünün arayüz düğmesi var, 37'si
operatör/CLI yüzeyi.** Bozuk olan değil, **arayüzde görünmeyen** işlevlerdir —
ki bu da raporun §6.1 ve B9 bulgusudur (bir ürün kararı, çökme değil).

---

## 2 · "Boş teneke mi?" — Hayır: gerçek çıktılar üretildi

Bu turda kapılar açılıp yetenekler **koşturuldu** ve çıkanlar diskte doğrulandı:

| Yetenek | Koştu mu | Ürettiği gerçek şey |
|---|---|---|
| `renderer.report.pdf` | ✅ | **Gerçek PDF** (1.821 bayt) + markdown + manifest (`sha256` eşleşmesi doğrulandı) |
| `renderer.report.diagram` | ✅ | **Gerçek PNG şema** (4.549 bayt) + mühür |
| `extractor.web.crawl4ai` | ✅ | GitHub sayfasından **8.000 bayt gerçek metin** (1.8 sn) |
| `extractor.text.language` | ✅ | Dil tespiti: `tr`, güven 0.77 |
| `sensor.identity.holehe` | ❌ | Uydurmadı: `scan_unavailable:provider_errors` (dış servis erişilemedi) |

Üretilen dosyalar (diskte, bu makinede): `memory/reports/20261014-*.pdf|.png|.md|.manifest.json`

**En değerli ayrıntı:** Rapora kanıt olarak *yanlış şemalı* iki satır gönderdim;
sistem onları **kabul etmedi, reddetti ve rapora "reddedilen: 2" yazdı**:

> "Bu rapor yalnız kanonik kanıt zaman çizelgesinden üretildi; içerik uydurulmadı."

Yani "boş teneke" değil, **aksine fazla sıkı**: veri uydurmak yerine eksik
bırakıyor. Doğru şemayla tekrar denendiğinde paket tam üretildi (kanıt kayıtları
+ `sha256` mühürleriyle).

---

## 3 · "Beyin (LLM) gerçekten çalışıyor mu?" — dürüst cevap

**Bu ortamda hiçbir sağlayıcı anahtarı yok** (ölçüldü: `OPENROUTER_API_KEY`,
`NINEROUTER_API_KEY`, `NOUS_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`,
`GEMINI_API_KEY` … hepsi YOK). Bu yüzden **canlı LLM çağrısı YAPILAMADI** ve
sonuç uydurulmadı. Sistemin verdiği cevap:

```
RuntimeError: REAL_LLM_CALL_NOT_EXECUTED: Canlı LLM çağrıları kapalı.
Açmak için: (1) Kasa'ya API anahtarı girin, veya
(2) .env dosyasına OPENROUTER_API_KEY yazıp LIVE_LLM_E2E=1 yapıp sunucuyu yeniden başlatın.
```

Bu **istenen davranıştır**: anahtar yokken sessizce sahte yanıt üretmek yerine
açıkça reddediyor. Ayrıca bulgu **B3**'ün doğrulanmış hâli: 9Router yerel servisi
çalışmıyorsa ve `ALLOW_LOCAL_TO_CLOUD_FALLBACK` kapalıysa (varsayılan) istek
buluta **düşmez** — `APIConnectionError`. Bu "beyin yok" demek değil;
"**yerel yönlendirici ayakta değil ve buluta düşme izni verilmemiş**" demektir.

**Siz 1 dakikada bitirebilirsiniz** (anahtar sizde):

```bash
# Gerçek LLM çağrısı kanıtı (ücretli çağrı yapar; anahtar ekrana basılmaz)
curl -s -X POST http://127.0.0.1:8000/api/vault \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"ben","api_key":"<OPENROUTER_ANAHTARINIZ>"}'
curl -s -X POST http://127.0.0.1:8000/api/aspasia/chat \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"ben","message":"tek cümlelik yanıt ver","target_message":"tek cümlelik yanıt ver"}'
```

İlk komut kasayı açar (canlı LLM kilidi açılır), ikincisi gerçek yanıt üretir.
9Router kullanıyorsanız: `NINEROUTER_BASE_URL`/`NINEROUTER_API_KEY` verip
9Router'ı ayağa kaldırın; `pineal-*` rotaları o hub'a bağlıdır (bulgu B4).

---

## 4 · Sizin planınızla bugünkü durum

| Sizin adımınız | Durum |
|---|---|
| 1. LLM bağlantısını gerçek istekle doğrula | **Sizde yapılabilir**; komut §3'te hazır. Bu ortamda anahtar yok → dürüstçe yapılamadı |
| 2. 23 kapalı yeteneği sınıflandır | **Yapıldı**: 19'u "yalnız bayrak", 4'ü bayraktan bağımsız (paket/motor/model). Kalan 13 engelin sınıfı: 7 bağımlılık, 2 motor, 2 yerel uç, 1 ayar, 1 yerel model |
| 3. Değerli olanları aç | **Kısmen kanıtlandı**: rapor/PDF/şema/dil/crawl bugün gerçekten üretti; TTS/STT ve yerel jüri **yerel motor** ister (kod hazır, motor yok) |
| 4. Gerçek senaryoyla test et | **Bu raporun tamamı odur**: gerçek sunucu, gerçek istek, gerçek dosya |

---

## 5 · Kanıt dosyaları (hepsi depoda / üretilebilir)

| Dosya | Ne var |
|---|---|
| `scripts/canli_calisirlik_probe.py` | İki modlu sonda: `sunucu` (gerçek HTTP) · `kanit` (gerçek koşum) |
| `reports/canli_calisirlik_sunucu.json` | 58 isteğin tam dökümü (durum kodu + gövde şekli) |
| `reports/canli_calisirlik_kanit.json` | 8 adımın gerçek sonucu + 5 yetenek koşumu |
| `memory/reports/20261014-*.pdf|.png|.md|.manifest.json` | Motorun ürettiği gerçek dosyalar (sha256'lı) |

Tekrar üretmek için:

```bash
PINEAL_ENV=development python -m uvicorn backend.api:app --port 8000 &
python scripts/canli_calisirlik_probe.py sunucu
python scripts/canli_calisirlik_probe.py kanit
```

---

## 6 · Dürüst sınır (ne KANITLANMADI)

- **"Bütün yetenekler gerçek hayatta çalışıyor"** KANITLANMADI ve bu ortamda
  kanıtlanamaz: sağlayıcı anahtarı, 9Router, yerel TTS/STT/whisper modelleri ve
  bazı dış servisler yok.
- Kanıtlanan şey: **mekanizmalar gerçek çıktı üretiyor**; üretemediğinde
  **uydurmuyor**, makine-okunur sebep veriyor ve **hiçbir uç çökmüyor**.
- Kalan gerçek iş yukarıdaki §4/§8 sırasındadır: yerel motorların kurulumu,
  arayüzde düğmesi olmayan 37 uç için ürün kararı, 9Router yedeği.

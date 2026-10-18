# PINEAL-HERETIC (İçgörü Asistanı)

Merhaba! Pineal-Heretic, sosyal medya (özellikle Instagram ve X) üzerindeki herkese açık profilleri inceleyen, gördüklerini sizin yerinize "insani bir gözle" okuyup analiz eden akıllı bir asistandır.

Bu program **kesinlikle bir hacker aracı değildir**, şifre kırmaz veya gizli hesaplara sızmaz. Sadece internetteki herkese açık resimleri, yazıları ve paylaşım saatlerini alır, tıpkı sizin günlerce ekrana bakarak yapacağınız gibi okur, ancak bunu saniyeler içinde yaparak size anlaşılır, dürüst bir "profil özeti" sunar.
---

```
                       ╔═══════════════════════════════════════════╗
                       ║        P I N E A L   E P İ F İ Z          ║
                       ║      v3.0.0-rc.2 ADLİ BİLİŞSEL İSTASYON   ║
                       ╚═══════════════════════════════════════════╝

    [ 🌐 ÇOK KANALLI OSINT ]       [ 🧠 7 MATEMATİKSEL DALGA MOTORU ]       [ 👁️ ATLAS GÖZLEMEVİ ]
   Instagram (Playwright)         Frequency (FFT) · Seismos · Void           %12.2 Pirinç Halka
   X (twscrape) · Web (SearXNG)   Strata · Gravity · Pulse · Key             Organik Yaşayan Göz
   SOCID · Çapraz Profilleme
               │                                      │                                  │
               └──────────────────────┬───────────────┴──────────────────────────────────┘
                                      │
                         [ ⚡ 13 GÖREV AJANI · IN-PROCESS ]
                  Kural Tabanlı Router · Süreç İçi Yürütme · Canlı Rack
                 (Docker beacon'lar yalnız liveness sinyali yayınlar)
                                      │
                         [ ⚔️ TAKTİK MUHAREBE MASASI ]
                       100% Şeffaf Adli Teftiş & Kara Kutu
                                      │
                   [ 🛡️ ÇOKLU SAĞLAYICI LLM GÜVENLİK HAVUZU ]
               9Router Local Hub + Google Gemini + Groq + DeepSeek
```

---

## 1. Pineal Epifiz Nedir? (Felsefe ve Çekirdek Mantık)

Pineal (Epifiz bezi); biyolojide ışığı, sirkadiyen döngüleri ve görünmeyen zaman frekanslarını algılayan, insan bedeninin ana saat kulesidir. 

**PINEAL-HERETIC**, bu biyolojik ilkeyi dijital adli tıbba uyarlar:
Bir hedefin açık kaynaklı dijital ayak izlerini (sosyal paylaşımları, metinlerini, fotoğraflarını, zamansal etkileşim ritimlerini) toplayan, bunları **yapay zekaya asla fal baktırmadan**, saf matematiksel dalga motorlarıyla analiz eden **yerel bir adli psikodinamik profil ve rezonans istasyonudur**.

### Sistemin 4 Dokunulmaz İlkesi:
> **Tüzük:** bu ilkeler artık [`docs/PINEAL_TUZUK.md`](docs/PINEAL_TUZUK.md) v2 içinde **Madde 1–4** olarak yaşar (2026-10-05). İlkeler değişmedi; bağlamı büyüdü: uyum/ilk temas artık sistemin tanımı değil, **kullanım sahalarından biridir** (tüzük Madde 0 ve Madde 9). Aşağıdaki dört ilke, tüzüğün kısa okumasıdır.
1. **LLM'ler Falcı Değildir:** Karakter analizi, bastırılmış narsisizm veya derin travmalar LLM'lere "tahmin ettirilmez". 7 adet saf matematiksel dalga motoru metin ve zaman serisini doğrudan fizik/istatistik formülleriyle ölçer. LLM'ler yalnızca en son aşamada dil sentezi, diyalog tasarımı ve çapraz denetim için kullanılır.
2. **Kanıt Mührü (Fail-Closed):** Verisi veya kanıtı olmayan hiçbir iddia üretilemez (`InsufficientEvidenceError`). Sistem boşlukları sallayarak doldurmaz; veri yoksa o kanalı dürüstçe kapatır veya işlemi durdurur.
3. **100% Şeffaflık & Sıfır Sahte Simülasyon:** Arayüzde rastgele yanan sahte LED'ler veya yapay zamanlayıcılar (`demoMode`) kesinlikle bulunmaz. Ekranda görülen her durum, güven puanı ve log, doğrudan FastAPI WebSocket, Redis Pub/Sub ve Tauri IPC'den akan gerçek telemetridir.
4. **Kasa (Vault Interlock) Koruması:** Fiziksel anahtar mandalı kilitliyken (`vault_locked: true`), dış dünyaya tek bir OSINT veya scraper isteği çıkamaz. Operatör mandalı çevirmeden dış ağa erişim imkansızdır.

---

## 2. Çift Modlu Taktik Komuta Arayüzü (v5.1 Mimarisi)

> Router tüm ajanları zorunlu sırayla çalıştırmaz. Diyagram, koşullu dalları özetler. Yedi pillar motorunun kendi hesaplamaları LLM çağrısı yapmaz; deterministik kod hesaplarıdır. Sonuçları yine de betimleyici/heuristik kaynak ölçümleridir, psikometrik test değildir.

PINEAL-HERETIC v5.1, operatöre hem derin sinematik sezgi hem de cerrahi şeffaflık sunan **çift modlu (Dual-Mode)** bir komuta köprüsü ile donatılmıştır. İki mod arasında sağ üstteki hap butondan anında geçiş yapılır ve tercih tarayıcıda (`localStorage.pineal_view_mode`) saklanır.

### MOD 1: Atlas Epifiz Gözlemevi (`AtlasPinealCockpit.svelte`)
*Kayıpsız 16:9 Master Şasi Üzerinde Yaşayan Epifiz Gözü ve Sokratik Terminal.*

- **Orijinal %12.2 Pirinç Yuvalı Yaşayan Organik Göz:**
  - Pirinç yuva içinde yaşayan organik epifiz gözü (`living_pineal_disk.png`).
  - Operatörün fare hareketini nazikçe takip eder, arka planda organik drift (`Math.sin`/`Math.cos`) ve operasyon anında hafif bilişsel titreşim (`processingFlutter`) sergiler.
- **Holografik Rezonans Ağı (`HolographicResonanceMesh.svelte`):**
  - Pirinç yuva arkasında dönen üç boyutlu matematiksel tel kafes. Sistem yüküne ve rezonans şiddetine göre form değiştirir.
- **Aspasia Canlı CRT Konsolu (`/api/aspasia/chat`):**
  - Sol alt güvertedeki retro monokrom CRT ekranı. Aspasia üst akıl denetçisiyle doğrudan canlı Sokratik diyalog kurulmasını sağlar.
- **Kasa Güvenlik Mandalı (Vault LED):**
  - Sol alttaki interaktif mandal. Yeşil (`OPEN`) ve kırmızı (`VAULT LOCKED`) durumları arasında anında kilit değiştirir (`POST /api/vault/status`).
- **Canlı Agent Rack Yuvası (`AgentRack.svelte`):**
  - Sağ taraftan açılıp kapanabilen 12 rollü analiz rack'i. Buradaki herhangi bir ajana tıklandığında sistem otomatik olarak Muharebe Masası'na geçer ve o ajanı doğrudan röntgene alır.

---

### MOD 2: Taktik Muharebe Masası (`TacticalWarRoom.svelte`)
*100% Şeffaf, Gerçek Zamanlı Adli Teftiş ve Müdahale Güvertesi.*

1. **12 Rol Kumanda Matrisi (Sol Kolon):**
   - 12 ajanın tamamını anlık durum pilleriyle (`ACTIVE`, `DONE`, `HALTED`, `WAIT`) gösterir.
   - Her ajanın gerçek zamanlı güven barı ve o anda ne yaptığına dair Türkçe operasyonel adım kartları (örn: *"LinkedIn ve Instagram profilleri bağlandı"*, *"3 jürili panelce incelendi"*).
2. **Hedef & Açık Kanıt Radarı (Orta Kolon):**
   - **Tespit Edilen Sosyal Profiller:** Instagram, LinkedIn, X, web siteleri tıklanabilir çipler olarak anında listelenir.
   - **Kişilik Özü Kartı & İlk Temas Köprüsü:** Tespit edilen öz-frekans ve hedefe yönelik sahici açılış mesajı.
   - **Açık Kaynak Kanıt Snippet'ları:** Web taramasından gelen ham metin parçacıkları.
3. **Derin Adli Ajan Röntgeni (Sağ Kolon):**
   - Seçilen ajanı 4 sekmeli derin muayeneye tabi tutar:
     - `[BULGULAR / OUTPUT]`: Ajanın ürettiği özet, ham çıkarımlar, varsa durma/hata nedeni.
     - `[GİRDİ / INPUT]`: Ajanın istemine (prompt) beslenen hedef verileri ve bağlam.
     - `[GÜVEN & KARAR]`: Ajanın matematiksel güven puanı, jüri oyları veya kosinüs benzerliği.
     - `[HAM VERİ / RAW JSON]`: Backend'den dönen birebir JSON sözleşmesi.
4. **Kara Kutu Canlı Uçuş Kaydedicisi (Alt Güverte):**
   - `ALL`, `OSINT`, `LLM`, `DECISION`, `ERRORS` filtreleriyle canlı log akışı sağlayan, otomatik kaydırmalı adli terminal.

---

## Teknik akış, API ve geliştirme

### Temel kod yolları

- API ve görev başlatma: `backend/api.py` → `run_mission()` → `agent_core/task_executor.py`
- Ajan seçimi: `agent_core/services/cognitive_router.py`
- Ajan envanteri ve altı soruluk kod ayrıntısı: [README_TECHNICAL.md](README_TECHNICAL.md)
- **Tam depo envanteri (680+ dosya, klasör klasör, aranabilir): [docs/envanter.html](docs/envanter.html)**
  — üretilen sayfa; `python scripts/generate_inventory_page.py` ile yenilenir,
  CI `--check` ile bayatlamayı yakalar. `.env.example`'ın 98 ayarı ve `config/*`
  içeriği tek tek açıklanmıştır.
- Scraper/görsel/pillar: `agent_core/scraper/`, `agent_core/services/`, `agent_core/engines/`
- UI: `frontend/src/`

### Başlıca yüzeyler

| Yüzey | Rol |
|---|---|
| `POST /api/initiate` | Ana profil görevi; aynı `run_mission` akışını başlatır. |
| `POST /api/aspasia/chat` | Kullanıcıya görev/kanıt durumu yanıtı. |
| `POST /api/aspasia/command` | Sınırlı doğal dil intent'i; desteklenen açık Instagram URL'si doğrulanır ve aynı görev akışına dispatch edilir. |
| `GET /api/media/status` | Medya hattı: yt-dlp/ffmpeg/opencv ve transkript motorunun GERÇEK durumu. |
| `POST /api/media/analyze` | Paylaşılan medyayı indirir, kare kare ölçer, yazıya döker, görsel benzerlik arar. Ölçülmeyen iddia edilmez. |
| `GET /api/report/status` | Hangi rapor formatı GERÇEKTEN üretilebilir (reportlab/Pillow/ffmpeg sebepleriyle). |
| `POST /api/report/build` | Kanıt satırlarından PDF/diyagram/video paketi üretir; manifest eser hash'lerini ve kanıt kimliklerini taşır. |
| `GET /api/company/status` | Kurum hedefi modlarının gerçek durumu (theHarvester · açık SEO · kişi künyesi). Kapı kapalıysa "hazır" denmez. |
| `POST /api/company/scan` | Alan adını omurgadan tarar; mod başına kanıt satırları kaynak URL ile döner. Uydurma SEO puanı yok. |
| `GET /api/jury/status` | Yerel jürinin durumu: kaç BAĞIMSIZ koltuk, uç yerel mi, yeter sayı. Model yoksa `available: false`. |
| `POST /api/jury/vote` | Aynı kanıtı birden çok yerel modele bağımsız oylatır; kural (oybirliği/çoğunluk) ve koltuk dökümü döner. Konsensüs yoksa karar iddia edilmez. |
| `GET /api/mcp/status` | MCP ihracının durumu: kaç yetenek araç olarak açık, hangi protokol sürümleri, kasa mandalı. Yetenek KOŞTURMAZ. |
| `POST /api/experimental/shadow/analyze` | Deneysel Shadow analiz endpoint'i; normal UI akışından ayrı. |
| `POST /api/experimental/shadow/generate` | Deneysel Shadow taslak üretim endpoint'i; normal UI akışından ayrı. |
| `POST /api/experimental/chat/respond` | Deneysel, oturumlu DialogueManager yanıtı; normal UI çağırmaz. |
| `run_lilith.py` | Ana analiz hattı dışında, CLI'dan Lilith içerik paketi üretimi. |
| `/api/experimental/interpreter/execute` | Yalnız opt-in Interpreter yapılandırmasında bulunan deneysel kod görevi yolu. |

### Durum tablosu: ölçülen çalışma ↔ DOĞRULANMADI (2026-10-16 denetimi)

Bu tablo, depodaki iddiaların **gerçekten koşulup koşulmadığını** gösterir. Ölçülmeyen hiçbir şey "çalışıyor" yazılmaz; ölçülemeyenler **DOĞRULANMADI** olarak **sebebiyle** birlikte listelenir. Ham kanıt: `docs/reports/DENETIM_2026-10-16.md` ve `docs/reports/DUZELTME_FAZ2_P*.md`.

**ÖLÇÜLEBİLDİ (gerçekten koşuldu, ham çıktısı görüldü):**

| Ne | Ölçüm |
|---|---|
| API ayakta | Yerel `uvicorn`: `/health` → **200**, `/api/telemetry` → **200** (26 capability) |
| Kasa kilidi | Kasa kilitliyken `POST /api/initiate` → **423 VAULT_LOCKED**; kasa açık → **200** |
| WebSocket akışı | Yerel `websockets` istemcisiyle **63 kare** alındı |
| Yetenek omurgası (mock'suz) | Kasa kilitli → 3/3 `not_run` + `policy:vault_locked`; kasa açık → IG/X `policy:gate_disabled`, socid `extract_unavailable:network_error` |
| Profil derinleştirme (P1) | `detected_urls` → router sınıflandırması → `CapabilityRunner`; kapalı kapı → `not_run` + sebep; arama snippet'ı **gönderi sayılmaz** |
| Çapraz profilleme (P2) | 4 **deterministik** sinyal; skor "kapsam" etiketli (olasılık **değil**); her eşleşme `EvidenceItem` |
| OSINT omurgası (P4) | Biyografideki e-posta → holehe yeteneği **çağrılıyor** → kasa kilitliyken `policy:vault_locked` (dürüst sebep, mühürlü kayıt) |
| Test tabanı | `pytest tests -q` → **2782 passed, 6 skipped** (2026-10-18 ölçümü) · `ruff check .` → **All checks passed!** · `scripts/audit_regression.py` → **✓ BEKÇİ GEÇTİ** |
| Frontend | `npm run check` → **0 hata / 0 uyarı** · `npm run build` → başarılı |
| Model fiyatı | Canlı OpenRouter ölçümü CI'da; **durum-kümesi** bekçisi (bilinmeyen fiyat → `FAIL`, ölçülen durum → `PASS` + uyarı) |

**DOĞRULANMADI (sebebiyle):**

| Ne | Sebep |
|---|---|
| Canlı X (twscrape) kazıma | Sandbox egress'i kapalı; hesap havuzu yok |
| Canlı Instagram / LinkedIn kazıma | Egress kapalı; Playwright kurulumu + cookie gerekiyor |
| Canlı `socid_extractor` | Egress kapalı → `extract_unavailable:network_error` |
| Canlı arama → `detected_urls` → derin tarama (uçtan uca) | Egress kapalı (arama sağlayıcısı **ve** hedef) |
| 9Router (`127.0.0.1:20128`) | Sandbox'tan erişilemiyor (HTTP 000) |
| `ENABLE_*` bayraklarının **tamamı açık** hâli | Kapılar kapalı tutuldu (görev talimatı) — açık hâli ölçülmedi |
| Yerel canlı OpenRouter çağrısı | Egress kapalı |
| Canlı sosyal medya çapraz profil eşleşmesi | Egress kapalı |
| Lilith'in canlı LLM çağrısının ana hat sayacına yazılması | Egress kapalı (CLI canlı çağrı: `ConnectError` → dürüst "FALLBACK") |

---

## Ne İşe Yarar ve Nasıl Çalışır?

Diyelim ki bir hesabı incelemek istiyorsunuz. Programın içinde birbirinden farklı analitik rolleri olan **13 Görev Ajanı** bulunur. Görevi başlattığınızda şunlar olur:
1. **Veri Toplar:** Hedef URL'den (Instagram için Playwright, X için twscrape sensörü) herkese açık verileri toplar; açık web aramasından gelen snippet'lar ise "arama özeti" olarak korunur, sahte gönderi sayılmaz.
2. **Davranış ve Karakter Analizi Yazar:**
   - *Frequency Engine*, paylaşım saatlerini FFT periodogramıyla inceleyerek sirkadiyen ritmi modeller.
   - *İnsan Davranışı Analisti*, açık paylaşımlardan ilgi alanlarını ve davranış kalıplarını inceler.
   - Ajanlar kural tabanlı bir yönlendirici (`CognitiveRouter`) tarafından deterministik olarak sırayla yürütülür; serbest yapay zeka tartışması değil, doğrulanabilir kanıt zinciri oluşturulur.
3. **Kasa (Vault Interlock) Güvenliği:** Ekranda **kasayı kilitle** dediğinizde, sistem dış dünyayla ağ bağlantısını fail-closed olarak tamamen keser ve hiçbir dış OSINT/kazıma çağrısı yapmaz. Kasa açıkken toplanan ham veriler yerel diskte mühürlenir; dil sentezi için yapılandırılmış LLM sağlayıcısına (OpenRouter, Groq, DeepSeek veya yerel 9Router) iletilir.
4. **Çocuk Koruması (Kırmızı Çizgi):** Sistem yapay zekayla otomatik yaş tahmini yapmaz; operatörün açık beyanına dayalı çocuk kilidi (`POST /api/minor/case` veya görev beyanı) verildiğinde fail-closed olarak araştırmayı derhal durdurur ve reddeder (`minor_gate.py`).

---

## 💻 Mühendisler ve Geliştiriciler İçin Kurulum Rehberi

> **Canlıya almadan önce:** [GO_LIVE.md](GO_LIVE.md) — port haritası, mimari
> şema, BLOCKER `.env` tablosu, tek komutla kaldırma ve **ölçülmüş** doğrulama
> sonuçları. Çok operatörlü kurulumda `PINEAL_OPERATOR_TOKENS` zorunludur;
> görev sahipliği mührü (§4) ve açık bulgular listesi (§5) oradadır.
## 4. Epifiz'in Yedi Nöro-Bilişsel Dalga Motoru (LLM'siz Saf Matematik)

Bu motorlar `agent_core/engines/` dizininde bulunur. Sıfır LLM çağrısıyla, deterministik formüllerle çalışırlar:

```
                      ┌── FrequencyEngine  (Sirkadiyen Ritim, Gece/Gündüz Dağılımı)
                      ├── SeismosEngine    (Kutup Değişimi, Davranışsal Fay Kırılmaları)
                      ├── VoidEngine       (Negatif Uzay: 10 Temel Konudan Bilinçli Kaçınma)
PillarOrchestrator ───┼── StrataEngine     (Zaman İçinde Değişen / Sönümlenen Maskeler)
                      ├── GravityEngine    (Anlatı Çekim Merkezleri, Sabit Fikirler)
                      ├── PulseEngine      (Dijital Soluk: Cümle & Noktalama Ritimleri)
                      └── KeyEngine        (6 Motorun Çıktısını Birleştiren Rezonans Vektörü)
```

| Dalga Motoru | Kaynak Dosya | Matematiksel / Analitik Görev |
|---|---|---|
| **Frequency** | `frequency_engine.py` | Paylaşım zaman serisini Lomb-Scargle / FFT periodogramı ile spektral analize tabi tutar; sirkadiyen ritim, periyodisite ve uyku fazını hesaplar (oyuncak sin/cos modeli değildir). |
| **Seismos** | `seismos_engine.py` | Duygusal durumlardaki ani faz sıçramalarını ve sismik kırılma noktalarını (`SeismicEvent`) saptar. |
| **Void** | `void_engine.py` | İnsanın profilde ısrarla bahsetmediği negatif alanları (para, aile, zaaflar) bularak bastırılanı çıkarır. |
| **Strata** | `strata_engine.py` | Yıllar içindeki üslup kaymalarını (`IdentityDrift`) ve terk edilen eski maskeleri ayrıştırır. |
| **Gravity** | `gravity_engine.py` | Kişinin konuşmayı sürekli döndürdüğü ana çekim kuyularını (`GravityWell`) modeller. |
| **Pulse** | `pulse_engine.py` | Metinlerdeki soluk ritmini, virgül, ünlem ve duraksama entropisini sayısallaştırır. |
| **Key** | `key_engine.py` | Tüm motor çıktılarını normalize ederek birleşik `ResonanceVector` sentezler. |

---

## 5. 13 Görev Ajanı — Kanonik Boru Hattı

> **Mimari gerçeği (2026-10-16 denetimi):** `PinealExecutor` içinde **13 görev ajanı** kayıtlıdır (ayrıca opt-in `interpreter`).
> Bunlar Docker'da birbirinden bağımsız çalışan konteynerler **değildir**; çekirdek orkestratör tarafından **in-process (süreç içinde)**
> kural tabanlı `CognitiveRouter` mantığıyla sırayla yürütülür. `docker-compose.yml` içindeki 12 `beacon-*` servisi ise yalnızca
> **canlılık işaretçisidir** (`pineal:agent:beacon` kalp atışı yayını); analiz yürütmez.
> `LilithGrowthAgent` ise online boru hattında **değildir** — **[P3 · 2026-10-16] kararı: CLI-only**. Gerekçe: girdisi profil metnidir ve çıktısı bir **kanıt** değil **üretimdir**; kanıt zincirine karışmamalıdır (ana hatta bağlansaydı "gönderi" alanı snippet tabanlı olurdu ve "hedef" ile "bulunan profil" ayrımı bulanıklaşırdı). Erişim: depo kökündeki `run_lilith.py` (ör. `python run_lilith.py --topic "..." --platform instagram`). CLI, çağrı maliyetini ana hattın sayacına yazdırmak için ana hattın `LLMGateway`'ini kullanır (taşıma sırası `NINEROUTER_* > PINEAL_LLM_* > OPENROUTER_*`, canlı çağrı kapısı `LIVE_LLM_E2E=1` / `PINEAL_ROUTER_LIVE=1`, bütçe/spend sayacı).

Sistemdeki 13 görev ajanı:
1. **OSINT Investigator:** Kullanıcı adı (Maigret) ve e-posta (Holehe) ayak izi çıkarma (açık kaynak / omurga).
2. **Autonomous Verifier:** 3 jürili bağımsız doğrulama paneli ve arama motoru teyidi.
3. **Authenticity Auditor:** Profil ve iddia özgünlük/tutarlılık denetimi.
4. **Human Behavior:** Davranışsal ilgi ve aksiyon kalıpları analizi.
5. **Passion Mapper:** Tutku, ilgi ve akış haritalama.
6. **Friction & Bounds:** Bilişsel sürtünme, sınır ve stres noktaları tespiti.
7. **Cognitive Profiler:** Dilbilimsel ve bilişsel düşünce stili analizi.
8. **Mirror of Truth:** Derin ayna refleksiyonu ve kör nokta tespiti.
9. **Resonance Calculator:** Vektör kosinüs benzerliği ve rezonans hesabı.
10. **Pattern Interrupt:** Beklenti kırma ve temas stratejisi ağacı.
11. **Resonance Synthesizer:** İlk temas ve rezonans köprüsü sentezi.
12. **Depth Analyst:** 7 sütunlu psikodinamik derinlik motoru çıktılarının adli analizi.
13. **Shadow Executor:** Gölge arketip ve bastırılmış motivasyon analizi.

*(Opt-in: `ENABLE_INTERPRETER=true` ise 14. ajan olarak `InterpreterAgent` devreye girer).*

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

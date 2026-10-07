# PINEAL EPİFİZ v5.1 · PINEAL-HERETIC

> **"Kodu okuyanla belgeyi okuyan aynı şeyi görecek."**  
> Bu belge, depodaki canlı koddan iğneden ipliğe doğrulanmış teknik, mimari ve operasyonel kılavuzdur.  
> **Doğrulama Noktası:** HEAD `f8a50d14` (2026-09-23).  
> Bu sürümde yalnızca **kodda birebir karşılığı olan** bileşenler, ajanlar, algoritmalar ve arayüzler anlatılır; hayali iddia, sahte simülasyon veya uydurma rota yer almaz.

---

```
                       ╔═══════════════════════════════════════════╗
                       ║        P I N E A L   E P İ F İ Z          ║
                       ║       v5.1 ADLİ BİLİŞSEL İSTASYON         ║
                       ╚═══════════════════════════════════════════╝

    [ 🌐 ÇOK KANALLI OSINT ]       [ 🧠 7 MATEMATİKSEL DALGA MOTORU ]       [ 👁️ ATLAS GÖZLEMEVİ ]
   Instagram · LinkedIn · X/Web       Frequency · Seismos · Void                 %12.2 Pirinç Halka
   Tavily · Exa · SerpAPI             Strata · Gravity · Pulse · Key             Organik Yaşayan Göz
               │                                      │                                  │
               └──────────────────────┬───────────────┴──────────────────────────────────┘
                                      │
                         [ ⚡ 12 OTONOM AJAN MATRİSİ ]
                       Docker + Redis Pub/Sub Canlı Rack
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
  - Sağ taraftan açılıp kapanabilen 12 ajanlık rack. Buradaki herhangi bir ajana tıklandığında sistem otomatik olarak Muharebe Masası'na geçer ve o ajanı doğrudan röntgene alır.

---

### MOD 2: Taktik Muharebe Masası (`TacticalWarRoom.svelte`)
*100% Şeffaf, Gerçek Zamanlı Adli Teftiş ve Müdahale Güvertesi.*

1. **12 Ajan Kumanda Matrisi (Sol Kolon):**
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

---

## 3. Veri Toplama & Çok Kanallı OSINT Sensörleri

Sistem, hedef hakkındaki verileri tek bir kaynağa bağımlı kalmadan çok kanallı paralel hatlarla toplar:

- **Çoklu Paralel OSINT Motoru (`backend/api.py:2136-2180`):**
  - Hedef ad veya kullanıcı adı verildiğinde eşzamanlı olarak:
    - `site:instagram.com "hedef"`
    - `site:linkedin.com/in "hedef"`
    - `site:x.com "hedef"` / `site:twitter.com "hedef"`
    - Genel web sorgularını **Tavily**, **Exa** ve **SerpAPI** üzerinden paralel olarak koşturur.
- **Instagram Ghost Scraper (`scraper/instagram_ghost.py`):**
  - Playwright tabanlı başsız tarayıcı. Oturumlu çerezlerle profil metinlerini, biyografiyi, gönderi açıklamalarını ve fotoğraf linklerini çıkarır.
- **X / Twitter Direkt Hat:**
  - Operatör politikası gereği aktiftir (`ENABLE_TWITTER=true`, `ENABLE_X=true`).
- **Gelişmiş Ayak İzi Tarayıcıları:**
  - `services/maigret_scanner.py` (Kullanıcı adı korelasyonu)
  - `services/holehe_scanner.py` (E-posta varlık denetimi)
  - Operatör anahtarıyla devreye alınabilir (`ENABLE_MAIGRET=true`, `ENABLE_HOLEHE=true`).

---

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
| **Frequency** | `frequency_engine.py` | Paylaşım zaman damgalarını sinüs/kosinüs dalgasına döker; gece uykusuzluğu ve biyolojik ritmi hesaplar. |
| **Seismos** | `seismos_engine.py` | Duygusal durumlardaki ani faz sıçramalarını ve sismik kırılma noktalarını (`SeismicEvent`) saptar. |
| **Void** | `void_engine.py` | İnsanın profilde ısrarla bahsetmediği negatif alanları (para, aile, zaaflar) bularak bastırılanı çıkarır. |
| **Strata** | `strata_engine.py` | Yıllar içindeki üslup kaymalarını (`IdentityDrift`) ve terk edilen eski maskeleri ayrıştırır. |
| **Gravity** | `gravity_engine.py` | Kişinin konuşmayı sürekli döndürdüğü ana çekim kuyularını (`GravityWell`) modeller. |
| **Pulse** | `pulse_engine.py` | Metinlerdeki soluk ritmini, virgül, ünlem ve duraksama entropisini sayısallaştırır. |
| **Key** | `key_engine.py` | Tüm motor çıktılarını normalize ederek birleşik `ResonanceVector` sentezler. |

---

## 5. 12 Otonom Ajan Kanonik Boru Hattı

Sistemdeki 12 uzman ajan, Docker ve Redis Pub/Sub üzerinden asenkron olarak haberleşir:

```
[ OSINT Investigator ] ──> [ 7-Pillar Forensics ] ──> [ Mirror of Truth ]
          │                                                   │
          ▼                                                   ▼
[ Autonomous Verifier ] ──> [ Human Behavior ] ───> [ Passion Mapper ]
(3 Jürili Hakem Paneli)     (Cold Reading / Aşil)   (Akış & Neşe Haritası)
          │                                                   │
          ▼                                                   ▼
[ Friction & Bounds ]  ───> [ Cognitive Profiler ] ──> [ Resonance Calc ]
(Sınır & Stres Noktası)     (Dilbilimsel Düşünce)     (Numpy Vektör Kosinüs)
          │                                                   │
          ▼                                                   ▼
[ Pattern Interrupt ]  ───> [ Resonance Synth ] ───> [ Depth Analyst ]
(Beklenti Kırma Ağacı)      (İlk Temas Mesajı)        (Gerçeklik Endeksi & Mühür)
```

1. **`osint_investigator`:** Dijital ayak izlerini ve açık profilleri toplar.
2. **`pineal_7pillar`:** Deterministik 7 dalga motorunu çalıştırıp mühür basar.
3. **`mirror_truth`:** Kullanıcının niyeti ile yüzey personasını yüzleştirir.
4. **`autonomous_verifier`:** 3 bağımsız jürili panel (`Google`, `Claude`, `Open`) ile çıkarımları denetler. (Analizi üreten model kendi jürisinde yer alamaz).
5. **`human_behavior`:** Dijital beden dili ve psikolojik aşil tendonu tespiti yapar.
6. **`passion_mapper`:** Hedefin tutkularını ve yüksek enerji tetikleyicilerini haritalandırır.
7. **`friction_detector`:** Savunma mekanizmalarını, mahremiyet sınırlarını ve sürtünme alanlarını bulur.
8. **`cognitive_profiler`:** Soyut/somut, analitik/sezgisel düşünme üslubunu çözer.
9. **`resonance_calc`:** İki zihin arasındaki vektörel uyumu Numpy kosinüs benzerliği ile ölçer (<0.70 ise durur).
10. **`pattern_interrupt`:** Ezber diyalogları kıran sürpriz konuşma dalları üretir.
11. **`resonance_synthesizer`:** Manipülasyondan arındırılmış, sahici ilk temas köprüsünü kurar.
12. **`depth_analyst`:** Tüm veriyi birleştirerek gerçeklik endeksini (`reality_index`) ve adli raporu mühürler.

---

## 6. Çoklu Sağlayıcı LLM Omurgası (Direct MP-Routing + 9Router)

Pineal v5.1, tek bir sağlayıcının çökmesiyle durmayacak şekilde hibrit bir routing mimarisine sahiptir:

1. **Yerel 9Router Omurgası (`http://127.0.0.1:20128/v1`):**
   - Makinede koşan yerel yönlendirici (17 hesap, 130 model, deterministik fallback).
2. **Doğrudan Çoklu Sağlayıcı Havuzu (Direct MP-Routing):**
   - **Google Gemini:** `gemini-3.7-flash`, `gemini-2.5-flash`, Gemini Pro, Vertex token desteği.
   - **Groq:** Llama 3.3, GPT-OSS 120b ultra-hızlı çıkarım.
   - **Nous Research, DeepSeek, Cerebras, Together, SambaNova, Mistral, NVIDIA NIM, iFlow, Kimchi, Fireworks.**
   - **Yerel LLM:** Ollama / LM Studio entegrasyonu (`USE_LOCAL_LLM=true`).
3. **OpenRouter 401 Graceful Fallback:**
   - Harici ağ geçidi 401 veya kota aşımı verirse sistem zincirleme çökmez; doğrudan yerel veya alternatif sağlayıcı zincirine güvenli düşüş yapar.

---

## 7. Kurulum, Yapılandırma ve Çalıştırma

### Hızlı Başlatma (Windows)
```bat
baslat.bat
```
*Sanal ortamı kontrol eder, frontend derlemesini yapar ve API sunucusunu başlatır.*

### Geliştirici Ortamı (Terminal)
Python ve Node sürümlerini repository manifestlerine göre kurun (`package.json` Node `>=20.19 <23` ister). Örnek yerel başlangıç:

```bash
# 1. Python Bağımlılıkları
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium

# 2. Frontend Derlemesi (Svelte 5 + Vite)
cd frontend
npm ci
npm run build
cd ..

# 3. Backend API Sunucusu (FastAPI + WebSocket)
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000

# 4. Canlı Önizleme (Opsiyonel)
cd frontend && npm run preview -- --host 127.0.0.1 --port 4173
```

### Port Haritası

| Port | Servis | Açıklama |
|---|---|---|
| `8000` | FastAPI Backend | REST API, WebSocket uplink, telemetri ve adli bellek |
| `4173` | Frontend Preview | Svelte 5 üretim derlemesi canlı önizleme |
| `5173` | Vite Dev Server | HMR destekli canlı frontend geliştirme |
| `20128` | 9Router Local Hub | Yerel OpenAI-uyumlu çoklu hesap yönlendiricisi |
| `6379` | Redis | Ajanlar arası Pub/Sub durum haberleşmesi |

---

## 8. Test ve Doğrulama Standartları

İki ayrı terminalde çalıştırın:

```bash
# Backend — yerel geliştirme ortamını açıkça seçin
PINEAL_ENV=development python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000

# Frontend — Vite varsayılan olarak 1420 portunu kullanır;
# /api ve /ws isteklerini backend'in 8000 portuna proxy eder.
npm run dev --prefix frontend -- --host 0.0.0.0
```

Sistem her commit öncesinde sıkı kalite kapılarından geçer:

- **Birim ve Entegrasyon Testleri:**
  ```bash
  pytest tests/unit/ tests/integration/
  ```
- **Sözleşme ve Rota Gölgeleri Denetimi:**
  ```bash
  python scripts/generate_routing_shadows.py --check
  ```
- **Frontend Tip ve Derleme Denetimi:**
  ```bash
  cd frontend && npm run build
  ```
- **Canlı 9Router Sağlık Probu:**
  ```bash
  python scripts/preflight_9router.py
  ```

---

## 9. Sıkça Sorulan Sorular (SSS)

**S: Neden hedef hakkında hemen fal gibi analiz üretilmiyor?**  
**C:** Çünkü Pineal Epifiz fal bakmaz. Kanıt Mührü ilkesi gereği, hedef hakkında açık veri toplanmadan hiçbir motor çalıştırılamaz. Veri yoksa sistem dürüstçe durur (`InsufficientEvidenceError`).

**S: Muharebe Masası ile Atlas Kokpiti arasındaki fark nedir?**  
**C:** Atlas Kokpiti, sezgisel ve yaşayan epifiz gözüyle derin sentez sunan estetik komuta merkezidir. Muharebe Masası (Tactical War Room) ise her ajanın girdi ve çıktısını, ham JSON sözleşmesini ve loglarını ameliyat masasına yatıran 100% şeffaf teftiş platformudur.

**S: Kasa (Vault) kilitliyken ne olur?**  
**C:** Kasa güvenlik mandalı kapalıyken dış dünyaya tek bir ağ isteği dahi çıkamaz. Kilit açılmadan sistem hiçbir harici platformu taramaz.

`.env.example` içindeki sağlayıcı, canlı LLM, harcama sınırı, kimlik doğrulama ve deneysel özellik ayarlarını çalıştırmadan önce gözden geçirin. Sunucu anahtarlarını `VITE_*` frontend değişkenlerine koymayın. İsteğe bağlı bağımlılık ve geliştirme kontrolleri için root `package.json`, `requirements-*.txt` ve [frontend notlarına](frontend/README.md) bakın.

### Tüzük

- [Atlas Pineal Tüzüğü (v2, 2026-10-05)](docs/PINEAL_TUZUK.md) — 10 madde, yasaklar, sahalar

### İnceleme raporları

- [Yıldız depo karar ağacı — 325 depo, 8 kapı, 10 faz](docs/reports/YILDIZ_DEPO_KARAR_AGACI_2026-10-05.md) *(entegrasyon hükmü ve yol haritası)*
- [Yedi önerilen eksikliğin kaynak kodu incelemesi](docs/reports/EKSIK_YETENEKLER_2026-09-26.md)
- [C0 salt-okunur veri envanteri](docs/reports/C0_BASELINE_VERI_ENVANTERI_2026-09-26.md)
- [P0 tarihsel baseline altyapısı için açık kapsam kararları](docs/reports/P0_PERSONAL_BASELINE_INFRASTRUCTURE_SCOPE_2026-09-26.md)

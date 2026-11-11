---
title: "Pineal Epifiz Master Hata Avı ve Düzeltme Talimatları Raporu"
tags: [pineal, audit]
status: active
created: 2026-11-09
---

# Pineal Epifiz Master Hata Avı ve Düzeltme Talimatları Raporu

**Hazırlayan:** `writer-audit-master` (`goosetown-writer`)  
**Denetlenen Kod Tabanı:** `C:\Projects\pineal-epifiz` ve `D:\Bilgisayar_Yedek\Projeler\pineal-epifiz` (`HEAD 61c414c5`, sürüm `3.0.0-rc.2`)  
**Denetim Modu:** Salt-Okunur (Read-Only) Derinlemesine Statik, Mimari ve Çalışma Zamanı Yoklama Denetimi  
**Sentezlenen Kaynak Raporlar:**
- `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` — 29 MCP Aracı, Capability Spine, `task_executor.py`, `config_loader.py`, `lifecycle/` ve Sabit Yol Denetimi
- `[RESEARCH/PINEAL_AUDIT_CORE_A.md]` — `agent_core/{agents,aspasia,chat,domain,engines}` (39 dosya) Derin Denetimi
- `[RESEARCH/PINEAL_AUDIT_CORE_B.md]` — `agent_core/{psychology,nlp,safety,shadow,scraper,services,utils,workers}` (89 dosya) Derin Denetimi
- `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` — `backend/`, `frontend/`, `functions/`, `worker.ts`, Dağıtım Yapılandırmaları, `android/` ve `rust_core/` Denetimi

---

## 1. Genel Denetim Özeti ve İstatistikler

Dört bağımsız denetim akışında tespit edilen toplam **91 ham bulgu**, mükerrer kayıtların (`agent_core/services/media_forensics.py` içindeki `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` `BULGU-07` ile `[RESEARCH/PINEAL_AUDIT_CORE_B.md]` `P1-10` bulguları ve `platform_registry.py` sabit yol kaydı) birleştirilmesi sonucunda **90 tekilleştirilmiş, kanıtlı ve doğrudan uygulanabilir düzeltme maddesine** dönüştürülmüştür.

### 1.1. Katmanlara ve Öncelik Seviyelerine (P0 – P3) Göre Hata Dağılımı

| Katman / Alt Sistem | Kaynak Rapor | P0 (Kritik / Engelleyici) | P1 (Yüksek) | P2 (Orta) | P3 (Düşük) | Toplam |
|---|---|---:|---:|---:|---:|---:|
| **MCP, 28 Capability, `task_executor`, `config_loader` ve Betikler** | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` | 4 | 5 | 4 | 1 | **14** |
| **Agent Core A (`agents`, `aspasia`, `chat`, `domain`, `engines`)** | `[RESEARCH/PINEAL_AUDIT_CORE_A.md]` | 5 | 8 | 7 | 4 | **24** |
| **Agent Core B (`services`, `scraper`, `safety`, `shadow`, `psychology`, `nlp`, `utils`, `workers`)** | `[RESEARCH/PINEAL_AUDIT_CORE_B.md]` | 3 | 10* | 6 | 2 | **21** |
| **Backend API (`backend/api.py`, `backend/routes/*`, `checkpoint_store.py`)** | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` | 1 | 6 | 3 | 0 | **10** |
| **Frontend (`frontend/src/components/*`, `store.ts`, `App.svelte`)** | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` | 1 | 2 | 3 | 2 | **8** |
| **Edge Proxy & Dağıtım (`functions/ws/`, `worker.ts`, `Dockerfile`, `docker-compose.yml`, `railway.toml`, `wrangler.toml`, `vercel.json`)** | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` | 1 | 2 | 2 | 0 | **5** |
| **Rust Core & Android (`rust_core/`, `src-tauri/`, `android/`)** | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` | 2 | 4 | 2 | 0 | **8** |
| **GENEL TOPLAM (Tekilleştirilmiş)** | **4 Rapor Sentezi** | **17** | **37** | **27** | **9** | **90** |

*\*Not: `agent_core/services/media_forensics.py` üzerindeki güvenlik, yarış durumu ve bloklama bulguları hem `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` (`BULGU-07`) hem de `[RESEARCH/PINEAL_AUDIT_CORE_B.md]` (`P1-10`) tarafından raporlanmış olup bu master raporda **`P1-04`** kodu altında tekilleştirilmiştir.*

### 1.2. Kritik Mimari ve Sistemik Bulguların Özeti

1. **MCP Şema ve Protokol Kırılması (`P0-01`, `P0-02`, `P1-01`):** `agent_core/mcp/tools.py:45-58` içindeki `default_input_schema` tüm 28 yetenek için `additionalProperties: False` ve yalnızca `{"subject": string}` şeması üretmektedir. Hiçbir adaptör sınıfında `mcp_input_schema` tanımlanmadığından ekstra parametre bekleyen araçlar (`analyzer_local_jury`, `renderer_report_*`, `voice_report_script` vb.) şema doğrulayan MCP istemcilerinde çalışmamakta; `voice_stt_local` ise JSON-RPC üzerinden gelmesi imkânsız olan `isinstance(audio, (bytes, bytearray))` kontrolü nedeniyle %100 başarısız olmaktadır.
2. **Güvenlik, SSRF ve Egress Omurgası İhlalleri (`P0-03`, `P0-07`, `P0-08`, `P0-09`, `P0-12`, `P1-06`, `P1-19`, `P1-20`):**
   - `company_recon.py` içinde `follow_redirects=True` ve doğrulanmamış `robots.txt` (`Sitemap:`) / `sitemap.xml` (`<loc>`) URL'leri üzerinden **4 ayrı SSRF açığı** bulunmaktadır.
   - `osint_investigator.py` merkezi egress omurgasını (`open_client`) atlayarak ham `aiohttp.ClientSession` kullanmakta ve `clean_username` üzerinde URL path injection barındırmaktadır.
   - `lilith_growth.py` içindeki `FreeTextGateway`, *"canlı çağrı yapılmaz"* beyanına rağmen hedef profil verilerini kimlik doğrulamasız `https://text.pollinations.ai/` sunucusuna POST etmektedir.
   - `MinorGate` (reşit olmayan hedef kilidi) yalnızca operatörün manuel beyanına (`subject_is_minor`) bakmakta; `task_executor.py`, `shadow_executor.py`, `run_scraper.py` ve `/api/aspasia/command` yollarında tamamen atlanmaktadır.
   - `vault_gate.py` ile `security.py` arasındaki `PINEAL_ENV` çelişkisi nedeniyle `PINEAL_ENV` tanımsızken Kasa Kilidi varsayılan olarak açık (`dev_boundary_deferred` / fail-open) kalmaktadır.
3. **Doğrulama, Kanıt Kapısı ve Deterministik Motor Hataları (`P0-04`, `P0-05`, `P0-06`, `P0-10`, `P0-11`):**
   - `task_executor.py:1849-1855` içinde görev devam ettirilirken (`resume_from`) geri yüklenen `verifications` ve `claim_gate` verileri silinmekte ve doğrulama kapısı tamamen devre dışı kalmaktadır.
   - `void_engine.py:24-30` ve `strata_engine.py:65-69` kelime sınırı olmadan alt-dize (`c in corpus`) araması yaptığı için Türkçe ekler (`-miş` → `iş`, `-din` → `din`, `artık` → `art`, `başka` → `aşk`) sahte varlık ve fosil sinyali üretmektedir.
   - `autonomous_verifier.py:342` içindeki `claim_support_ratio >= 0.5` kapısı, yalan iddiaları çürüten geçerli `YALAN` ve `ÇELİŞKİLİ` jüri oylarını sistematik olarak `BİLİNMİYOR`'a düşürmektedir.
   - `instagram_ghost.py:_paginate_grid` ilk gönderi detayına giderken ana profil sekmesinden çıktığı için Instagram grid sayfalama ilk gönderiden sonra kırılmaktadır.
   - `HindsightMemory.merge_evidence` üst sınıf `CanonicalMemory.merge_evidence` ile imza uyumsuzluğu (`metadata` parametresi eksikliği) nedeniyle `TypeError` fırlatmaktadır.
4. **Backend, Frontend, Edge Proxy ve Yan Katman Kırılmaları (`P0-13`, `P0-14`, `P0-15`, `P0-16`, `P0-17`):**
   - Windows üzerinde `backend/routes/commander.py` içindeki Unix'e özgü `import fcntl` ve dizin üzerinde `os.open` çağrıları `POST /api/override` ve `POST /api/commander/inject` uçlarını HTTP 500 ile çökertmektedir.
   - `SpiderFootCockpit.svelte` içinde `📡 DERİN KİMLİK RADARI (4 SİLAH)` sekmesinin (`activeTab === 'osint_radar'`) HTML şablon bloğu hiç yazılmadığı için sekme tıklandığında boş ekran çıkmaktadır.
   - Cloudflare Pages proxy'si (`functions/ws/[[path]].ts`) `upstream` henüz `CONNECTING` durumundayken istemcinin gönderdiği ilk `{type: "auth"}` mesajını sessizce çöpe atmakta ve bağlantıyı `1008 First-message auth timeout` ile düşürmektedir.
   - `rust_core/` ve `android/` katmanları Python `backend/` ile entegre değildir; `rust_core/src/agents/autonomous_verifier.rs` `"UNVERIFIED"` atayıp `"DOĞRULANDI"` filtrelediği için %100 hata vermekte, `aspasia.rs` ise sabit `/workspace/agent_core` yolu ve Python kod enjeksiyonu içermektedir.

---

## 2. 29 MCP Aracı (28 Capability + `pineal_status`) ve `skills/` Tam Durum Tablosu

### 2.1. `skills/` Klasörü ile `agent_core/capabilities/` İlişkisi

`C:\Projects\pineal-epifiz\skills\` altında tam **28 alt klasör** (`analyzer_local_jury` ... `voice_tts_local`) yer almaktadır (`[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`):
- **Çalıştırılabilir Kod İçermez:** Bu klasörlerin her birinde yalnızca `SKILL.md` dosyası vardır; içlerinde hiçbir Python kodu yoktur.
- **Otomatik Üretim:** `scripts/export_skills.py:72-127` (`render_skill_md`, `export_all`), `CapabilityRegistry` içindeki 28 yeteneği tarayarak bu `SKILL.md` dosyalarını otomatik üretmektedir (`<!-- AUTO-GENERATED by scripts/export_skills.py ... -->`).
- **29. Araç (`pineal_status`):** `agent_core/mcp/server.py:37-47` (`STATUS_TOOL`) içinde doğrudan sunucu aracı olarak tanımlandığından `skills/` altında klasörü bulunmaz (`28 capability + 1 pineal_status = 29 MCP aracı`).

### 2.2. 29 MCP Aracının Tam Envanteri, Bağımlılıkları ve Şema/Mantık Hataları

| # | MCP Araç Adı | Capability ID | Adaptör Dosyası:Satır | Politika Kapıları (`gates`) | Dış Paket / İkili / API / Env Bağımlılığı | Varsayılan Ortamda Canlı Durum | Mantık / Şema Hatası ve Gerçek Durum (`[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`) |
|---|---|---|---|---|---|---|---|
| 1 | `pineal_status` | *(Sunucu Aracı)* | `agent_core/mcp/server.py:37` & `status.py:29` | Yok (`readOnlyHint=True`) | Opsiyonel: yerel FastAPI `/api/vault/status` (`PINEAL_BACKEND_URL`) | **Çalışıyor (`available=True`)** | **Raporlama Hatası (`P1-02`):** `registry.status()` `_ACTIVE_POLICY_FLAGS` ContextVar'ını set etmediği için `with_operator_consent` ile açılan 15 kapıyı `gate_disabled:ENABLE_*` raporlar. |
| 2 | `sensor_osint_maigret` | `sensor.osint.maigret` | `adapters_osint.py:85` | `vault`, `network`, `ENABLE_MAIGRET` | Python paketi: `maigret` (`requirements-osint.txt`) | **Kapalı (`dependency_missing:maigret`)** | **Paket Eksik + Mimari İhlal (`P0-01`, `P1-02`, `P1-20`):** `maigret` kurulu değil; `maigret_scanner.py` doğrudan çağrıldığında `vault_gate.require_open` kontrolünü atlar ve `is_enabled()` ContextVar yerine `os.getenv` okur. |
| 3 | `sensor_osint_holehe` | `sensor.osint.holehe` | `adapters_osint.py:130` | `vault`, `network`, `ENABLE_HOLEHE` | Python paketi: `holehe` (`requirements-osint.txt`) | **Kapalı (`dependency_missing:holehe`)** | **Paket Eksik + Kapı Hatası (`P0-01`, `P1-02`):** `holehe` kurulu değil; `holehe_scanner.is_enabled()` `runner.run` sırasında `_ACTIVE_POLICY_FLAGS` sıfırlandığı için `os.getenv`'e düşer. |
| 4 | `sensor_osint_socid` | `sensor.osint.socid` | `adapters_osint.py:175` | `vault`, `network`, `ENABLE_CROSS_PLATFORM` | Python paketi: `socid_extractor` | **Kapalı (`dependency_missing:socid_extractor`)** | **Paket Eksik (`P0-01`, `P1-22`):** `socid_extractor` kurulu değil; `deep_profile_resolver.py:244` bu paket eksikse Instagram/X rotalarını da iptal eder. |
| 5 | `sensor_web_crawl4ai` | `sensor.web.crawl4ai` | `adapters_osint.py:216` | `vault`, `network`, `ENABLE_CRAWL4AI` | Python paketi: `crawl4ai` | **Kapalı (`dependency_missing:crawl4ai`)** | **Paket Eksik (`P0-01`, `P1-02`):** DNS-pinned `safe_web_fetch` + `DefaultMarkdownGenerator` kullanır; `crawl4ai` kurulu değil. |
| 6 | `sensor_web_scrapling` | `sensor.web.scrapling` | `adapters_osint.py:260` | `vault`, `network`, `ENABLE_SCRAPLING` | Python paketi: `scrapling` | **Kapalı (`dependency_missing:scrapling`)** | **Paket Eksik (`P0-01`):** `scrapling.parser.Selector` kullanır; `scrapling` kurulu değil. |
| 7 | `sensor_web_trafilatura` | `sensor.web.trafilatura` | `adapters_osint.py:303` | `vault`, `network` | Python paketi: `trafilatura` | **Çalışıyor (`available=True`)** | **Çalışıyor (`P0-01` Şema Kısıtı):** `fetch_safe_html` + `trafilatura.bare_extraction` ile gerçek çıkarım yapar; ancak MCP şeması ekstra parametreleri reddeder. |
| 8 | `sensor_search_searxng` | `sensor.search.searxng` | `adapters_osint.py:345` | `vault`, `network`, `ENABLE_SEARXNG` | Env: `SEARXNG_URL` veya `SEARXNG_BASE_URL` (Dış SearXNG servisi) | **Kapalı (`missing_env:SEARXNG_URL`)** | **Servis/Env Eksik (`P0-01`):** Dış SearXNG sunucusu ve ortam değişkeni gerektirir. |
| 9 | `sensor_social_x_twscrape` | `sensor.social.x.twscrape` | `adapters_osint.py:394` | `vault`, `network`, `ENABLE_X_SENSOR` | Python paketi: `twscrape` + `TWSCRAPE_ACCOUNTS_DB` (SQLite hesap havuzu) | **Kapalı (`dependency_missing:twscrape`)** | **Paket + Hesap DB Eksik (`P0-01`):** Hem `twscrape` paketi hem de aktif X hesap veritabanı gerektirir. |
| 10 | `sensor_social_ig_instagrapi` | `sensor.social.ig.instagrapi` | `adapters_osint.py:454` | `vault`, `network`, `ENABLE_IG_SECONDARY` | Python paketi: `instagrapi` (veya `gallery-dl` CLI) + `IG_SESSION_FILE`/`IG_SESSIONID` | **Kapalı (`dependency_missing:instagrapi_or_gallery_dl`)** | **Paket + Session Eksik (`P0-01`):** `instagrapi` ve `gallery-dl` kurulu değil. |
| 11 | `sensor_social_ig_playwright` | `sensor.social.ig.playwright` | `adapters_osint.py:517` | `vault`, `network` | Python paketi: `playwright` + Chromium binary + `data/ig_session.json` | **Kapalı (`dependency_missing:playwright`)** | **Paket Eksik + Scraper Hatası (`P0-10`, `P1-16`, `P2-11`):** Sistem Python'unda `playwright` kurulu değil; altında çalışan `instagram_ghost.py` içinde `_paginate_grid` P0 hatası ve Türkçe sayı ayrıştırma P1 hatası var. |
| 12 | `sensor_web_agent_reach` | `sensor.web.agent_reach` | `adapters_osint.py:575` | `vault`, `network`, `ENABLE_AGENT_REACH` | CLI binary: `agent-reach` (`AGENT_REACH_BIN`) veya Python modülü `agent_reach` | **Kapalı (`dependency_missing:agent-reach`)** | **Binary/Paket Eksik (`P0-01`).** |
| 13 | `sensor_company_harvester` | `sensor.company.harvester` | `adapters_company.py:98` | `vault`, `network`, `ENABLE_COMPANY_TARGETING` | CLI binary: `theHarvester` (`THEHARVESTER_BIN`) veya yerleşik `crt.sh` + DNS/RDAP HTTP yedek | **Çalışıyor (`available=True`)** (`theHarvester.EXE` PATH'te mevcut) | **Çalışıyor Fakat P0 SSRF Açığı Var (`P0-03`):** `company_recon.py` içinde yönlendirme ve `robots.txt`/`sitemap.xml` SSRF zafiyeti mevcuttur. |
| 14 | `sensor_company_seo` | `sensor.company.seo` | `adapters_company.py:194` | `vault`, `network`, `ENABLE_COMPANY_TARGETING` | `httpx` (`open_client`) | **Çalışıyor (`available=True`)** | **Çalışıyor Fakat P0 SSRF Açığı Var (`P0-03`):** `robots.txt` içindeki `Sitemap:` URL'sini doğrulamadan çeker ve `follow_redirects=True` kullanır. |
| 15 | `sensor_company_people` | `sensor.company.people` | `adapters_company.py:276` | `vault`, `network`, `ENABLE_COMPANY_TARGETING` | `httpx` (`open_client`) | **Çalışıyor (`available=True`)** | **Çalışıyor Fakat P0 SSRF Açığı Var (`P0-03`):** `sitemap.xml` içindeki `<loc>` URL'lerini host kontrolü olmadan `follow_redirects=True` ile çeker. |
| 16 | `sensor_identity_handle_variations` | `sensor.identity.handle_variations` | `adapters_identity.py:72` | `vault`, `network`, `ENABLE_HANDLE_VARIATIONS` | `httpx` (`open_client`) — 12 platform HTTP/API yoklaması | **Çalışıyor (`available=True`)** | **Çalışıyor (`P0-01` Şema Kısıtı):** 12 platforma gerçek HTTP yoklaması yapar; MCP şeması yalnız `subject` kabul eder. |
| 17 | `sensor_identity_phone_probe` | `sensor.identity.phone_probe` | `adapters_identity.py:163` | `vault`, `network` | Python paketi: `phonenumbers` + `httpx` | **Çalışıyor (`available=True`)** (`phonenumbers` kurulu) | **Kısmen Stub & Kırık (`P1-03`):** WhatsApp/Telegram/Viber kontrolü hiçbir ağ isteği yapmadan yalnız link formatlar (`status="candidate"`); DuckDuckGo regex'inde `re.DOTALL` unutulduğu için web araması her zaman `0` sonuç döner. |
| 18 | `analyzer_local_jury` | `analyzer.local.jury` | `adapters_jury.py:42` | `vault`, `network`, `ENABLE_LOCAL_JURY` | Env: `LOCAL_JURY_MODELS` (en az 2 yerel model) + `LOCAL_LLM_URL` (Ollama/vLLM) | **Kapalı (`insufficient_local_models:0<2`)** | **MCP Şemasında Kırık (`P0-01`):** `ctx.params["evidence"]` listesi ister; MCP `default_input_schema` `evidence` parametresini `additionalProperties: False` ile reddeder. |
| 19 | `sensor_media_fetch` | `sensor.media.fetch` | `adapters_media.py:67` | `vault`, `network`, `ENABLE_MEDIA_FORENSICS` | `httpx` veya `yt-dlp` / `gallery-dl` | **Çalışıyor (`available=True`)** (`httpx` mevcut; `yt-dlp` yok) | **P1 Güvenlik/Mantık Hataları Var (`P1-04`):** Keyfi yerel dosya yolu okuma, senkron `subprocess.run` ile event-loop bloklama, `newest` dosya yarış durumu ve `follow_redirects=True` SSRF içerir. |
| 20 | `analyzer_media_frames` | `analyzer.media.frames` | `adapters_media.py:114` | `ENABLE_MEDIA_FORENSICS` | `ffmpeg`/`ffprobe` binary VEYA `PIL`/`cv2` | **Çalışıyor (`available=True`)** (`ffmpeg.EXE`, `ffprobe.EXE`, `PIL`, `cv2` kurulu) | **Bloklayıcı Subprocess & Şema Kısıtı (`P0-01`, `P1-04`):** `ffmpeg`/`ffprobe` senkron `subprocess.run` ile event loop'u bloklar; `sample_every` parametresi MCP şemasında reddedilir. |
| 21 | `extractor_media_transcript` | `extractor.media.transcript` | `adapters_media.py:194` | `ENABLE_MEDIA_FORENSICS` | `faster_whisper` / `whisper` Python paketi VEYA `WHISPER_CPP_BIN` + `WHISPER_CPP_MODEL` | **Kapalı (`no_asr_backend`)** (`whisper.EXE` CLI var ama Python `import whisper` başarısız) | **Kırık / Tutarsız (`P1-04`):** `voice.stt.local` `shutil.which("whisper")` ile CLI'yi bulurken, `media_forensics.has_asr_backend()` yalnız `import faster_whisper`/`import whisper` arar; ayrıca `.pineal-audio.wav` geçici dosyasını silmez. |
| 22 | `analyzer_media_similarity` | `analyzer.media.similarity` | `adapters_media.py:249` | `ENABLE_MEDIA_FORENSICS` | `PIL` + `numpy` (dHash + HSV histogram) | **Çalışıyor (`available=True`)** | **Çalışıyor (`P0-01` Şema Kısıtı):** `data/media_evidence/<task_id>/index.json` üzerinde benzerlik hesaplar; `top_k` MCP şemasından geçirilemez. |
| 23 | `renderer_report_pdf` | `renderer.report.pdf` | `adapters_report_factory.py:68` | `ENABLE_REPORT_FACTORY` | Saf Python PDF 1.4 üreticisi (`report_factory.py`) | **Çalışıyor (`available=True`)** | **P1/P2 Hatalı (`P0-01`, `P1-01`, `P2-01`):** Type1 `Helvetica` kullandığı için Türkçe karakterleri (`ğ, ı, ş, İ, Ğ, Ş`) bozar; MCP'de `args.pop("subject")` yüzünden `ctx.params["subject"]` boş kalır ve `evidence` verilemez (0 kanıtlı sahte başarı döner). |
| 24 | `renderer_report_diagram` | `renderer.report.diagram` | `adapters_report_factory.py:115` | `ENABLE_REPORT_FACTORY` | Saf Python SVG + Mermaid üreticisi (`report_factory.py`) | **Çalışıyor (`available=True`)** | **P1 MCP Parametre Hatası (`P0-01`, `P1-01`):** MCP üzerinden `evidence` dizisi geçirilemez, 0 kanıtlı boş diyagram üretip `ok=True` döner. |
| 25 | `renderer_report_video` | `renderer.report.video` | `adapters_report_factory.py:163` | `ENABLE_REPORT_FACTORY` | `PIL` + `ffmpeg` binary (`shutil.which("ffmpeg")`) | **Çalışıyor (`available=True`)** (`PIL` ve `ffmpeg.EXE` kurulu) | **Bloklayıcı Subprocess + MCP Parametre Hatası (`P0-01`, `P1-01`):** `ffmpeg` senkron çalışır; MCP üzerinden `evidence` geçirilemez. |
| 26 | `voice_tts_local` | `voice.tts.local` | `adapters_voice.py:517` | `ENABLE_LOCAL_TTS` | `PINEAL_TTS_URL` (localhost) veya `PINEAL_TTS_CMD` (`espeak-ng`/`espeak`/`piper`/`say`) | **Görünürde `available=True`** (`piper.EXE` PATH'te) | **Yarı-Kırık (`P0-02`, `P2-01`):** `piper.EXE` model argümanı (`-m <model.onnx>`) olmadan yalnız `--output_file` ile çağrıldığında (`adapters_voice.py:725`) hata verir; `availability()` `ENABLE_LOCAL_TTS` kapısını kontrol etmez. |
| 27 | `voice_stt_local` | `voice.stt.local` | `adapters_voice.py:575` | `ENABLE_LOCAL_STT` | `PINEAL_STT_URL` (localhost) veya `PINEAL_STT_CMD` (varsayılan `whisper`) | **Görünürde `available=True`** (`whisper.EXE` PATH'te) | **MCP Üzerinden %100 Kırık (`P0-02`):** `adapters_voice.py:598-600` içinde `isinstance(audio, (bytes, bytearray))` kontrolü yapılır. JSON-RPC (MCP) protokolünde `bytes` tipi olmadığı için her zaman `empty_audio` ile başarısız olur; `availability()` `ENABLE_LOCAL_STT` kapısını kontrol etmez. |
| 28 | `voice_report_script` | `voice.report.script` | `adapters_report.py:173` | Yok (Saf yerel hesaplama) | Bağımlılık yok | **Görünürde `available=True`** | **MCP Şemasında %100 Kırık (`P0-01`, `P1-01`):** `run()` yalnız `ctx.params["report"]` veya `ctx.params["text"]` okur, `ctx.subject`'e hiç bakmaz; MCP şeması ise yalnız `subject` kabul eder (`empty_report` döner). |
| 29 | `language_detect` | `language.detect` | `adapters_language.py:51` | Yok (Saf yerel analiz) | Bağımlılık yok | **Çalışıyor (`available=True`)** | **Çalışıyor:** Deterministik karakter/stopword/trigram dil tespiti yapar. |
| *(29. Yetenek / 30. Satır)* | `language_translate` | `language.translate` | `adapters_language.py:130` | `ENABLE_LOCAL_TRANSLATE` | `PINEAL_TRANSLATE_URL` (localhost) veya `PINEAL_TRANSLATE_CMD` (varsayılan `trans`) | **Kapalı (`no_engine`)** | **Motor Eksik (`P0-01`):** `trans` CLI kurulu değil ve yerel çeviri ucu yok; ayrıca `target` dil parametresi MCP şemasında tanımlı değil. |

*(Not: Tablodaki 1. satır `pineal_status` + 2..29 arasındaki 28 capability = toplam **29 MCP aracıdır**; tablo numaralandırmasında tüm 28 capability + `pineal_status` eksiksiz listelenmiştir.)*

### 2.3. Ek Dış İkili ve Paketlerin Ortam Durumu (`[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`)
- **`PyYAML` (`yaml`):** Sistem Python'unda (`C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe`) **`PyYAML` kurulu değildir (`yaml: False`)**; `agent_core/config_loader.py:7` (`import yaml`) sistem Python'unda doğrudan `ModuleNotFoundError: No module named 'yaml'` fırlatır.
- **`sherlock`:** Depo içinde gerçek bir adaptörü yoktur (`maigret` ve `handle_variations` kullanılmıştır).
- **`exiftool` / `tesseract` (`pytesseract`):** Kurulu değildir (`False`); MCP aracı olarak kayıtlı değillerdir.
- **`open-interpreter` (`interpreter`) / `chromadb`:** Kurulu değildir (`False`); 28 capability aracından hiçbiri bunları kullanmaz (`interpreter_agent.py` ayrı bir opsiyonel ajandır).

---

## 3. `D:` Sürücüsü ve Sabit Yol (Hardcoded Path) Taraması Sonuçları

Hem `C:\Projects\pineal-epifiz` hem de `D:\Bilgisayar_Yedek\Projeler\pineal-epifiz` dizinlerinin tamamı (`agent_core/`, `backend/`, `frontend/`, `functions/`, `scripts/`, `config/`, `.env.example`, `tests/`, `rust_core/`, `android/`) taranmıştır (`[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`, `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`, `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`).

### 3.1. Kaynak Kod ve Betiklerdeki Tüm Sabit Yollar (Dosya Yolu ve Satır Numaralarıyla)

| # | Dosya Yolu | Satır No | Sabit Yol / Kanıt | Önem | Düzeltme Talimatı | Kaynak Rapor |
|---|---|---:|---|---|---|---|
| 1 | `scripts/apply_p1_fixes.py` | `12` | `path = r"C:\Projects\pineal-epifiz\backend\checkpoint_store.py"` | **P2** | `Path(__file__).resolve().parents[1] / "backend" / "checkpoint_store.py"` ile göreli hale getirin. | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 2 | `scripts/apply_p1_fixes.py` | `54` | `path = r"C:\Projects\pineal-epifiz\agent_core\services\dependency_health.py"` | **P2** | `Path(__file__).resolve().parents[1] / "agent_core" / "services" / "dependency_health.py"` kullanın. | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 3 | `scripts/apply_p1_fixes.py` | `75` | `path = r"C:\Projects\pineal-epifiz\agent_core\capabilities\adapters_identity.py"` | **P2** | `Path(__file__).resolve().parents[1] / "agent_core" / "capabilities" / "adapters_identity.py"` kullanın. | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 4 | `scripts/apply_p1_fixes.py` | `100` | `path = r"C:\Projects\pineal-epifiz\agent_core\services\phone_probe.py"` | **P2** | `Path(__file__).resolve().parents[1] / "agent_core" / "services" / "phone_probe.py"` kullanın. | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 5 | `scripts/audit_capabilities.py` | `2` | `sys.path.insert(0, r"C:\Projects\pineal-epifiz")` | **P2** | `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` kullanın (`audit_capabilities.py` yalnız `C:\Projects\pineal-epifiz\scripts` içinde mevcuttur). | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 6 | `scripts/audit_capabilities.py` | `4` | `env_path = r"C:\Projects\pineal-epifiz\.env"` | **P2** | `env_path = Path(__file__).resolve().parents[1] / ".env"` kullanın. | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 7 | `rust_core/src/aspasia.rs` | `73` | `sys.path.insert(0, '/workspace/agent_core')` | **P0** | Sabit `/workspace/agent_core` konteyner yolunu kaldırın; çalışma dizinine göreli yol veya `PINEAL_AGENT_CORE_PATH` ortam değişkeni kullanın (`P0-17`). | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` |
| 8 | `backend/api.py` vs `docker-compose.yml` & `railway.toml` | `784` vs `32` / `21` | `VAULT_FILE = ".pineal_vault.json"` vs `/app/vault-data` | **P1** | `PINEAL_VAULT_FILE` env değişkenini veya `/app/vault-data/.pineal_vault.json` yolunu otomatik algılayın (`P1-33`). | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` |
| 9 | `android/app/src/main/java/com/example/pineal/engine/backend/PinealBackendClient.kt` | `86-88` | `val baseUrl: String = "http://10.0.2.2:8000/"` | **P1** | Sabit emülatör IP'sini yapılandırılabilir `backendBaseUrl` ayarına taşıyın (`P1-36`). | `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]` |
| 10 | `agent_core/services/platform_registry.py` | `396-399` | `r"C:\Program Files\Google\Chrome\Application\chrome.exe"` ve `r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"` | **P3** | `os.getenv("CHROME_PATH")`, `PROGRAMFILES`, `PROGRAMFILES(X86)` ve `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe` yollarını dinamik olarak çözün (`P3-07`). | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`, `[RESEARCH/PINEAL_AUDIT_CORE_B.md]` |
| 11 | `baslat.bat` vs `scripts/calistir_windows.bat` & `scripts/calistir_windows.ps1` | `26` vs `10` / `19` | `baslat.bat` `venv` oluştururken `calistir_windows.*` `.venv\Scripts\python.exe` arıyor | **P3** | `calistir_windows.bat` ve `.ps1` içinde `.venv` yoksa `venv\Scripts\python.exe` yedeğine düşecek kontrol ekleyin (`P3-01`). | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |
| 12 | `D:\Bilgisayar_Yedek\Projeler\pineal-epifiz\.venv_audit\` | `pyvenv.cfg`, `Scripts\Activate.ps1` | `.venv_audit` sanal ortam kalıntıları içinde `D:\Bilgisayar_Yedek\...` sabit yolları | **Bilgi** | Birincil kaynak kodda (`.py`, `.ts`, `.svelte`, `.rs`, `.kt`, `.yaml`, `.json`) hiçbir `D:\` veya `D:/` bağımlılığı **bulunmamaktadır**. `C:\Projects\pineal-epifiz` içinde sanal ortam (`venv`/`.venv`) henüz oluşturulmamıştır; çalıştırmadan önce temiz bir `venv` kurulmalıdır. | `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]` |

---

## 4. Öncelik Sırasına Göre Tüm Hatalar ve Düzeltme Talimatları (P0 → P1 → P2 → P3)

---

### 4.1. P0 — Kritik ve Engelleyici Hatalar (17 Bulgu)

#### [P0-01 / BULGU-01] MCP `inputSchema` Sözleşmesi Tüm 28 Aracın `params` Parametrelerini Reddediyor (`additionalProperties: False`)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/mcp/tools.py:45-58` (`default_input_schema`)
  - `agent_core/mcp/tools.py:74-106` (`input_schema_for`)
  - `scripts/export_skills.py:72-120`
- **Kanıt / Kök Neden:** `default_input_schema(cap)` fonksiyonu yalnızca `required: ["subject"]`, `properties: {"subject": {"type": "string", "minLength": 1}}` ve `additionalProperties: False` döndürmektedir. `input_schema_for(cap)` (`tools.py:79`) `getattr(cap, "mcp_input_schema", None)` aramasına rağmen `agent_core/capabilities/adapters_*.py` dosyalarının hiçbirinde `mcp_input_schema` tanımlanmamıştır.
- **Etki:** Şema doğrulaması yapan tüm MCP istemcileri `limit`, `sources`, `evidence`, `claim`, `report`, `text`, `target`, `audio`, `sample_every`, `top_k`, `auto_bridge`, `voice`, `rate` parametrelerini reddeder; `subject` kullanmayan araçlar (`voice_report_script`, `voice_stt_local`) sahte bir `subject` verilmeden çağrılamaz.
- **Düzeltme Talimatı (Remediation Instruction):** Her `BaseCapability` alt sınıfına kendi kabul ettiği parametreleri (`limit`, `sources`, `evidence`, `text`, `report`, `target`, `audio_base64` vb.) tanımlayan açık bir `mcp_input_schema` sözlüğü ekleyin; yalnızca `params` bekleyen araçlarda `subject` alanını opsiyonel yapın ve `scripts/export_skills.py` betiğini yeniden çalıştırarak 28 `SKILL.md` dosyasını güncelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P0-02 / BULGU-02] `voice_stt_local` (`voice.stt.local`) MCP Üzerinden %100 Çağrılamaz (`isinstance(audio, bytes)` Hatası ve Eksik Kapı Kontrolü)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/capabilities/adapters_voice.py:59, 533-536, 592-604`
- **Kanıt / Kök Neden:** `LocalSTTCapability.run()` (`adapters_voice.py:598-600`) içinde `audio = ctx.params.get("audio") or b""` ve `if not isinstance(audio, (bytes, bytearray)) or not audio:` kontrolü yapılmaktadır. JSON-RPC 2.0 (MCP) protokolünde ham `bytes`/`bytearray` veri tipi mevcut değildir. Ayrıca `LocalSTTCapability.availability()` (`592-594`) ve `LocalTTSCapability.availability()` (`533-536`) kendi beyan ettikleri `ENABLE_LOCAL_STT` / `ENABLE_LOCAL_TTS` kapılarını hiç kontrol etmez.
- **Etki:** İstemci `audio` parametresini Base64 string veya yerel dosya yolu olarak gönderdiğinde `voice_stt_local` her zaman `unavailable_reason="empty_audio"` ile başarısız olur; kapı bayrakları kapalıyken bile araçlar `available=True` raporlar.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `LocalSTTCapability.run()` içinde `audio` parametresi `str` ise Base64 (`base64.b64decode`) olarak çözülmesini veya izin verilen çalışma dizinindeki güvenli bir ses dosyası yolu ise okunmasını sağlayın.
  2. `LocalSTTCapability.availability()` ve `LocalTTSCapability.availability()` içinde `state.flag_enabled("ENABLE_LOCAL_STT")` / `state.flag_enabled("ENABLE_LOCAL_TTS")` kontrolünü ekleyin ve `adapters_voice.py:59` satırındaki ölü `_flag` fonksiyonunu `agent_core.capabilities.state.flag_enabled` ile değiştirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P0-03 / BULGU-05] `company_recon.py` İçinde 4 Ayrı SSRF (Server-Side Request Forgery) Güvenlik Açığı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/company_recon.py:439, 449, 488-492, 619, 627, 633-650`
- **Kanıt / Kök Neden:**
  1. **Redirect SSRF (`449, 627`):** `open_client(purpose="osint", timeout=timeout, follow_redirects=True)` kullanıldığı için genel bir alan adından (`evil.com`) `http://127.0.0.1:8000/api/vault/status` veya `http://169.254.169.254/latest/meta-data/` adresine yapılan `302` yönlendirmeleri doğrudan takip edilir.
  2. **`robots.txt` `Sitemap:` SSRF (`488-492`):** Hedef sitenin `robots.txt` dosyasındaki `Sitemap: http://127.0.0.1:8000/...` satırı hiçbir host/IP doğrulamasından geçirilmeden `_fetch` ile çekilir.
  3. **`sitemap.xml` `<loc>` SSRF (`633-650`):** `people_scan` fonksiyonu `sitemap.xml` içindeki `<loc>` URL'lerini (`_TEAM_PATH_HINTS` eşleşmesi olan herhangi bir iç ağ URL'si) hedef domain veya `_is_private_target` kontrolü yapmadan çeker.
  4. **`base_url` Bypass (`439, 619`):** `if not base_url and _is_private_target(clean):` koşulu nedeniyle `base_url` verildiğinde özel IP kontrolü tamamen atlanır.
- **Etki:** Saldırgan kontrolündeki bir hedef domain taranırken sunucunun yerel API uçlarına (`127.0.0.1:8000`, `127.0.0.1:20128`) ve bulut metadata servislerine SSRF saldırısı yapılabilir.
- **Düzeltme Talimatı (Remediation Instruction):** `company_recon.py` içindeki tüm HTTP çağrılarını `follow_redirects=False` ve `agent_core.utils.security.safe_get` (DNS-pinning + her redirect adımında IP doğrulaması) üzerinden geçirin; `robots.txt` ve `sitemap.xml` içinden çıkan URL'lerin hem `is_safe_url()` kontrolünden geçmesini hem de hedef alan adıyla (`clean`) aynı host/alt-alan adına ait olmasını zorunlu kılın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P0-04 / BULGU-09] `task_executor.py` İçinde Görev Devam Ettirme (`resume_from`) Sırasında `claim_gate` ve `verifications` Verilerinin Silinmesi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/task_executor.py:1815-1855, 2405-2407, 2795-2820`
- **Kanıt / Kök Neden:** Satır 1815-1818'de `resume_from` ile devam ettirilen görevde `status.ingested_outputs` içinden `input_data`'ya geri yüklenen `verifications` ve `claim_gate`, hemen 30 satır aşağıda (`1849-1855`) *"Caller spoofing önlemi"* adına `input_data.pop(_derived, None)` ile koşulsuz olarak silinmektedir. Satır 2405'te `if self._resume_done(status, agent_name): continue` çalıştığı için `autonomous_verifier` yeniden çalıştırılmaz.
- **Etki:** Görev `autonomous_verifier` sonrasında duraklatılıp `resume_from` ile devam ettirildiğinde `input_data.get("claim_gate")` `None` olur ve ertelenmiş ajanlar (`pattern_interrupt`, `resonance_synthesizer`, `shadow_executor`) için `claim_decision_gate` / doğrulama kapısı tamamen bypass edilir.
- **Düzeltme Talimatı (Remediation Instruction):** Satır 1849-1855'teki `input_data.pop(_derived, None)` temizliğini `if resume_from is not None:` bloğundan **önce** (yalnızca ham çağıran girdisi üzerinde) çalıştırın; checkpoint'ten geri yüklenen doğrulanmış `status.ingested_outputs` verilerinin silinmesini engelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P0-05 / CORE-A-01] `void_engine.py` ve `strata_engine.py`: Kelime Sınırı Olmayan Alt-Dize (`c in corpus`) Eşleşmesi Nedeniyle Türkçe Eklerin Sahte Varlık ve Fosil Üretmesi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/void_engine.py:10-30, 54-60`
  - `agent_core/engines/strata_engine.py:12, 65-80`
- **Kanıt / Kök Neden:** `_presence(corpus, cues)` fonksiyonu kelime sınırı (`\b`) veya token listesi yerine birleştirilmiş `corpus` karakter dizisi üzerinde doğrudan `c in corpus` ve `corpus.count(c)` çalıştırmaktadır:
  - `"iş"` (`career`): Türkçe `-miş` geçmiş zaman ekinde (`gelmiş`, `gitmiş`, `demiş`) ve `kişi`, `işte`, `ilişki`, `gelişim` kelimelerinde eşleşir.
  - `"din"` (`religion`): Türkçe `-din` 2. tekil şahıs ekinde (`geldin`, `gittin`, `dedin`) ve `kendin`, `şimdiden`, `aydın` kelimelerinde eşleşir.
  - `"art"` (`art_creation`): `artık`, `şart`, `kart`, `mart`, `parti`, `tartışma` kelimelerinde eşleşir.
  - `"aşk"` (`romance`): `başka`, `başkan`, `şaşkın` kelimelerinde eşleşir.
  - `"para"` (`money`): `numara`, `parantez`, `paragraf` kelimelerinde eşleşir.
- **Etki:** 40+ kelimelik sıradan bir Türkçe metinde `career`, `religion`, `art_creation`, `romance` kategorileri gerçekte hiç konuşulmasa bile `actual_presence ≈ 0.90-1.00` alır; gerçek `VoidSignal` sinyalleri bastırılır ve `strata_engine.py` içinde sahte `FossilRecord` kayıtları üretilir.
- **Düzeltme Talimatı (Remediation Instruction):** `void_engine.py:24-30` içindeki `_presence(corpus, cues)` fonksiyonunu ham alt-dize araması yerine `tokens = re.findall(r"[^\W\d_]+", corpus.lower())` üzerinden tam kelime eşleşmesi (veya 4+ harfli kökler için kontrollü önek eşleşmesi `any(t == c or (len(c) >= 4 and t.startswith(c)) for t in tokens)`) kullanacak şekilde değiştirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P0-06 / CORE-A-02] `autonomous_verifier.py`: `claim_support_ratio >= 0.5` Kapısının `YALAN` ve `ÇELİŞKİLİ` Oylarını İptal Etmesi ve Olumsuzlamayı Görmezden Gelmesi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/autonomous_verifier.py:118-136, 308-345`
- **Kanıt / Kök Neden:**
  1. `_audit_vote` (`341-345`) her oy türü için `support = claim_support_ratio(claim_text, content)` hesaplayıp `if support < MIN_CLAIM_SUPPORT_RATIO: return VOTE_UNKNOWN` uygular. Bir iddia yalan olduğunda (örn. `"Harvard mezunu ve Nobel ödüllü fizikçi"`), gerçek kaynakta kişinin gerçek bilgisi (`"Ankara Lisesi mezunu, muhasebeci"`) yer alır ve uydurma kelimeler kaynakta geçmediği için `support < 0.5` çıkar; böylece geçerli `YALAN` / `ÇELİŞKİLİ` oyları `VOTE_UNKNOWN`'a düşürülür.
  2. `claim_support_ratio` (`135`) `t in corpus` ile alt-dize araması yapar ve olumsuzlama kelimelerini (`değil`, `değildir`, `yok`, `asla`, `not`, `never`) kontrol etmez (`"Harvard mezunu değildir"` cümlesi `support = 1.0` ile `DOĞRULANDI` kapısından geçer).
- **Etki:** Doğrulayıcı jüri yalan iddiaları neredeyse hiçbir zaman çürütemez (`_direct_refutation_is_audited` çalışmaz) ve olumsuzlanmış kaynak metinlerini doğrulama kanıtı sanabilir.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `_audit_vote` içinde `support < MIN_CLAIM_SUPPORT_RATIO` kontrolünü yalnızca `vote == VOTE_VERIFIED` için zorunlu tutun; `vote in {VOTE_FALSE, VOTE_CONTRADICTED}` durumunda `evidence_url` eşleşmesi, `quote_matches` doğrulaması ve `contradiction_detail` varlığı yeterli olmalıdır.
  2. `claim_support_ratio` içinde `t in corpus` alt-dize kontrolünü token kümesi kontrolüne (`corpus_tokens = set(_claim_tokens(source_text))`) çevirin ve olumsuzlama kontrolü ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P0-07 / CORE-A-03] `osint_investigator.py`: `aiohttp` ile Egress/SSRF Omurgası Bypass'ı, URL Path Injection ve Başarılı Tarama Sonrası Silinmeyen `fallback_reason`/`error_code`
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/osint_investigator.py:18, 162-169, 228-237, 289-295, 442, 451-460, 496-498, 532-539`
- **Kanıt / Kök Neden:**
  1. Satır 496-498'de merkezi `agent_core.capabilities.egress.open_client` yerine doğrudan `aiohttp.ClientSession` kullanılmakta ve `clean_username = username.lstrip("@")` URL'ye (`https://api.osint.industries/v1/user/{clean_username}`) kaçışsız gömülmektedir.
  2. `_apply_username_scan` satır 166'da `"fallback_reason": None if not profile.fallback_reason else profile.fallback_reason` koşulu ters yazılmıştır! `OSINT_INDUSTRIES_KEY` yokken başlangıçta atanan `fallback_reason="provider_credentials_unavailable"`, Maigret/Holehe/handle_probe başarılı olup `data_confidence=True` ürettikten sonra bile silinmemektedir (`_apply_cross_platform_probe:233` ve `_apply_email_scan:289` ise bu alanları hiç güncellemez).
- **Etki:** Merkezi egress/kasa politikası bypass edilir, `username` üzerinden URL path/query injection yapılabilir ve başarılı bağımsız OSINT taramaları bile üst katmana `fallback_reason="provider_credentials_unavailable"` / `"api_error"` ile hatalı raporlanır.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `aiohttp` importunu kaldırın; `open_client(purpose="osint", timeout=15.0)` kullanın ve `clean_username` değerini `re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", clean_username)` + `urllib.parse.quote(clean_username, safe="")` ile doğrulayın.
  2. `_apply_username_scan`, `_apply_cross_platform_probe` ve `_apply_email_scan` içinde `found_sites` bulunduğunda (`data_confidence=True`) `"fallback_reason": None, "error_code": None` ataması yapın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P0-08 / CORE-A-04] `dialogue_manager.py`: Prompt Injection, LLM Hatasında Diyalog Geçmişi Bozulması ve Sabit Uzunluk Sınırı Uyuşmazlığı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/chat/dialogue_manager.py:8, 51, 95-97, 192, 196-232`
- **Kanıt / Kök Neden:**
  1. `ctx.target_profile`, `ctx.user_profile` ve `target_message` hiçbir `<UNTRUSTED_...>` kafesi veya rol öneki temizliği olmadan doğrudan prompt'a gömülmektedir.
  2. `self.add_message(task_id, "target", target_message)` (`196`), `await self.llm.query_json(...)` (`228`) çağrısından **önce** çalıştırılmaktadır.
  3. `DialogueResponse.next_move` (`51`) modül yükleme anındaki sabit `MAX_DIALOGUE_MESSAGE_CHARS = 4000` sınırını kullanırken, `self.max_message_chars` (`95`) `PINEAL_MAX_DIALOGUE_MESSAGE_CHARS` env değişkenini okur.
- **Etki:** `target_message` içinden `\nAGENT: ...\nGÖREV: ...` ile prompt injection yapılabilir; LLM hata verdiğinde veya env sınırı `< 4000` olduğunda hedef mesajı diyalog geçmişinde asılı kalarak oturumu bozar.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `self.add_message(task_id, "target", target_message)` çağrısını `await self.llm.query_json(...)` başarılı olduktan **sonra** (`add_message(task_id, "agent", ...)` ile atomik olarak) çalıştırın.
  2. `response.next_move` değerini `self.max_message_chars` sınırına göre doğrulayın/kırpın ve `target_profile` ile `history_str` bloklarını `<UNTRUSTED_...>` etiketleriyle kafesleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P0-09 / CORE-A-05] `lilith_growth.py`: "Canlı Çağrı Yapılmaz" Beyanına Rağmen `FreeTextGateway` Üzerinden Üçüncü Taraf Sunucuya (`text.pollinations.ai`) Veri Gönderilmesi ve Yutulan CLI Argümanları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/lilith_growth.py:13-14, 221-251, 313-349`
- **Kanıt / Kök Neden:**
  1. Dosya başındaki *"api_key yoksa sıfır-maliyet FreeTextGateway'e düşülür (canlı çağrı yapılmaz)"* (`13-14, 334-335`) beyanına rağmen `FreeTextGateway.chat()` (`231-251`) `https://text.pollinations.ai/` adresine canlı HTTP POST isteği atarak hedef profil verilerini göndermektedir.
  2. `from_cli_credentials` (`337-340`) içinde `use_main_line_gateway=True` iken `LLMGateway()` argümansız çağrılmakta ve çağıranın verdiği `api_key`, `base_url`, `model` parametreleri tamamen yutulmaktadır.
- **Etki:** Operatör API anahtarı vermediğinde hedef kişinin biyografisi, gönderileri ve psikolojik analiz verileri kimlik doğrulamasız üçüncü taraf `text.pollinations.ai` sunucusuna sızar.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `FreeTextGateway.chat()` içindeki `https://text.pollinations.ai/` canlı ağ çağrısını kaldırın; API anahtarı yokken deterministik olarak `RuntimeError("llm_credentials_unavailable")` fırlatın.
  2. `from_cli_credentials` içinde `api_key`, `base_url` ve `model` parametrelerini `LLMGateway` örneğine aktarın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P0-10 / CORE-B P0-1] `InstagramGhostScraper._paginate_grid`: İlk Gönderi Detayına Gidildiğinde Ana Profil Sayfasından Çıkılması (Grid Pagination Tamamen Kırık)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/scraper/instagram_ghost.py:884-892, 944-992`
- **Kanıt / Kök Neden:** `_paginate_grid` fonksiyonu profil sayfasını aşağı kaydırıp (`window.scrollTo`) gönderi linklerini toplarken, döngünün ilk turunda bulunan ilk `shortcode` için `await self._post_from_detail_page(playwright_page, code)` çağrısını **aynı `playwright_page` sekmesi** üzerinde yapar (`988`). `_post_from_detail_page` (`888`) `await playwright_page.goto(f"{self.base_url}/p/{shortcode}/")` çalıştırdığı için sekme profil grid'inden çıkarak tekil gönderi sayfasına gider.
- **Etki:** İlk gönderiden sonraki tüm `scrollTo` ve `query_selector_all("a[href]")` işlemleri profil yerine tekil gönderi sayfasında çalışır; Instagram grid sayfalama ilk gönderiden sonra tamamen bozulur.
- **Düzeltme Talimatı (Remediation Instruction):** `_paginate_grid` içinde önce tüm `max_scrolls` boyunca yalnızca profil sayfasında kalıp (`goto` yapmadan) `ordered_codes` listesini `target_count` sınırına kadar toplayın; kaydırma döngüsü bittikten **sonra** (veya `playwright_page.context.new_page()` ile açılan ayrı bir sekmede) her `code` için `_post_from_detail_page` çağrısını çalıştırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P0-11 / CORE-B P0-2] `HindsightMemory.merge_evidence`: Üst Sınıf `CanonicalMemory.merge_evidence` ile İmza Uyumsuzluğu (`TypeError`)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/hindsight_memory.py:194-199`
  - `agent_core/services/canonical_memory.py:181-186`
- **Kanıt / Kök Neden:** `CanonicalMemory.merge_evidence(self, task_id: str, evidence_chain: List[Dict], metadata: Optional[Dict] = None)` imzasına sahipken, alt sınıf `HindsightMemory.merge_evidence(self, task_id: str, evidence_chain: List[Dict])` `metadata` parametresini kabul etmez ve `super().merge_evidence` çağrısına iletmez.
- **Etki:** `PINEAL_MEMORY_ENGINE=hindsight` etkinleştirildiğinde `metadata` geçiren herhangi bir `merge_evidence` çağrısı çalışma zamanında `TypeError` ile çöker.
- **Düzeltme Talimatı (Remediation Instruction):** `HindsightMemory.merge_evidence` imzasını `async def merge_evidence(self, task_id: str, evidence_chain: List[Dict], metadata: Optional[Dict] = None) -> Dict[str, Any]:` olarak güncelleyin ve `await super().merge_evidence(task_id, evidence_chain, metadata=metadata)` çağrısı yapın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P0-12 / CORE-B P0-3] `MinorGate` (Çocuk Koruma Kırmızı Çizgisi): Yalnızca Operatör Beyanına Bağlı Olması ve CLI / Shadow / TaskExecutor Yollarında Devre Dışı Kalması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/safety/minor_gate.py:177-178`
  - `agent_core/capabilities/runner.py:78-102`
- **Kanıt / Kök Neden:** `MinorGate.evaluate()` (`177-178`) içinde `if case is None or not case.subject_is_minor: return MinorDecision.allow("not_minor")` kontrolü vardır; kazınan biyografi/gönderi metinlerinden otomatik yaş sinyali tespiti yapılmaz. Ayrıca `MinorGate` yalnızca `CapabilityRunner.run` ve `backend/api.py` (bazı uçlar) içinde çağrılmakta; `task_executor.py`, `shadow/shadow_executor.py` ve `scraper/run_scraper.py` yollarında hiç çağrılmamaktadır.
- **Etki:** Operatör `subject_is_minor=True` bayrağını manuel olarak göndermediği sürece 18 yaş altı hedefler tespit edilmez ve CLI / Shadow / doğrudan TaskExecutor akışlarında çocuk koruma kilidi hiç çalışmaz.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `task_executor.py`, `shadow/shadow_executor.py` ve `scraper/run_scraper.py` giriş noktalarına zorunlu `MinorGate.evaluate` kontrolü ekleyin.
  2. Kazınan profil biyografisi/gönderilerinde yaş sinyali (`<18` yaş ifadeleri, lise/ortaokul ibareleri, doğum yılı `> current_year - 18`) yakalayan deterministik bir `detect_minor_signals(profile_data)` ön-denetleyicisi yazarak eşleşme halinde otomatik `MinorGate` kilidi tetikleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P0-13 / B-01] Windows Üzerinde `fcntl` İçe Aktarımı ve Dizin `os.open`/`os.fsync` Çağrısı Nedeniyle Çökme (`HTTP 500`)
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/commander.py:57-66` (`locked_learnings`), `72-102` (`_store_evidence`)
  - `backend/api.py:3353-3372` (`POST /api/override`)
- **Kanıt / Kök Neden:**
  1. `locked_learnings` (`commander.py:60`) yalnızca Unix/POSIX sistemlerde bulunan `import fcntl` modülünü çağırır.
  2. `_store_evidence` (`commander.py:92-95`) dizin üzerinde `os.open(os.path.dirname(mem_path), os.O_RDONLY)` ve `os.fsync` çağırır (Windows'ta `PermissionError: [Errno 13] Permission denied`).
  3. `_store_evidence` sabit `.pineal_memory/learnings.json` yoluna yazarken (`73`), `api_override` (`api.py:3360`) `memory/learnings.json` yoluna yazar.
- **Etki:** Windows üzerinde `POST /api/override` ve `POST /api/commander/inject` uçları %100 oranında HTTP 500 (`ModuleNotFoundError: No module named 'fcntl'` / `EVIDENCE_STORE_FAILED`) ile çöker.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `locked_learnings` içinde POSIX'te `fcntl.flock`, Windows'ta (`os.name == "nt"`) `msvcrt.locking` veya süreç içi `threading.RLock` + atomik `os.replace` kullanın.
  2. Dizin `os.open`/`os.fsync` bloğunu yalnızca `os.name != "nt"` koşulunda çalıştırın ve `_store_evidence` yolunu odanın `executor.memory.storage_path` diziniyle birleştirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P0-14 / F-01] `SpiderFootCockpit.svelte` İçinde `📡 DERİN KİMLİK RADARI (4 SİLAH)` (`osint_radar`) Sekmesinin Şablonunun Tamamen Eksik Olması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SpiderFootCockpit.svelte:118, 276-298, 1214-1326, 1720-1724, 1758-2563`
- **Kanıt / Kök Neden:** Satır 1720-1724'te üst sekme çubuğunda `on:click={() => activeTab = 'osint_radar'}` düğmesi ve `<script>` bloğunda `runMaigretScan()`, `runHoleheScan()`, `runSocidScan()`, `runCrawlFetch()` fonksiyonları tanımlanmış olmasına rağmen, `1758-2563` satırları arasındaki `{#if activeTab === ...}` şablon zincirinde **`{:else if activeTab === 'osint_radar'}` bloğu hiç yazılmamıştır**.
- **Etki:** Kullanıcı `📡 DERİN KİMLİK RADARI (4 SİLAH)` sekmesine tıkladığında çalışma alanı tamamen boş (siyah ekran) kalır ve 4 OSINT aracının hiçbirine arayüzden erişilemez.
- **Düzeltme Talimatı (Remediation Instruction):** `SpiderFootCockpit.svelte` içinde `{:else if activeTab === 'opening_hook'}` bloğundan sonra `{:else if activeTab === 'osint_radar'}` şablon bloğunu ekleyerek `osintSubTool` (`maigret`, `holehe`, `socid`, `crawl`) seçicilerini ve `runMaigretScan`, `runHoleheScan`, `runSocidScan`, `runCrawlFetch` formlarını/sonuç tablolarını bağlayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P0-15 / D-01] Cloudflare Edge WebSocket Proxy (`functions/ws/[[path]].ts`) İçinde İlk Mesaj Kimlik Doğrulama (`auth`) Çerçevesinin Kaybolması
- **Dosya Yolu ve Satır Numarası:**
  - `functions/ws/[[path]].ts:61-66, 109-128`
  - Karşı taraf: `backend/routes/websocket.py:133-163` ve `frontend/src/App.svelte:192-199`
- **Kanıt / Kök Neden:** `const upstream = new WebSocket(wsTarget)` henüz el sıkışmasını tamamlamadan (`upstream.readyState === WebSocket.CONNECTING (0)` iken) `pipeEnd.accept()` çağrılıp istemciye `101` dönülmektedir. İstemci (`App.svelte:192`) bağlantı açılır açılmaz ilk mesaj olarak `{type: "auth", token: tok}` gönderir; ancak `pump` içindeki `if (to.readyState !== WebSocket.OPEN) return;` (`111`) bu mesajı `upstream` henüz `CONNECTING` olduğu için sessizce çöpe atar.
- **Etki:** Cloudflare Pages üzerinden yapılan tüm WebSocket bağlantılarında ilk `auth` mesajı kaybolur ve backend 5 saniye sonra bağlantıyı `1008 First-message auth timeout` ile kapatır.
- **Düzeltme Talimatı (Remediation Instruction):** `functions/ws/[[path]].ts` içinde `upstream.readyState === WebSocket.CONNECTING` iken `pipeEnd` üzerinden gelen mesajları bir `pendingQueue: any[] = []` dizisinde tamponlayıp `upstream.addEventListener("open", ...)` tetiklendiğinde sırayla `upstream.send(...)` ile iletin (veya `await fetch(httpTarget, { headers: { Upgrade: "websocket" } })` sonrası `accept()` başlatın).
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P0-16 / R-01] `rust_core/src/agents/autonomous_verifier.rs` İçinde `"UNVERIFIED"` vs `"DOĞRULANDI"` Etiket Uyumsuzluğu Nedeniyle %100 Hata
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/agents/autonomous_verifier.rs:138-145, 168-190`
- **Kanıt / Kök Neden:** `AutonomousVerifierAgent` Tavily sonuçlarını eklerken `truth_status: "UNVERIFIED".to_string()` (`140`) atamakta, hemen ardından `170.` satırda `.filter(|v| v.truth_status == "DOĞRULANDI").count()` ile doğrulananları saymaktadır.
- **Etki:** `confirmed` her zaman `0` çıkar ve Rust doğrulayıcı ajanı %100 oranında `Err(HaltReason::InsufficientEvidence)` döndürerek boru hattını durdurur.
- **Düzeltme Talimatı (Remediation Instruction):** Tavily sonuçlarını hedef kimliği ve kanıt kriterleriyle karşılaştırarak eşleşen sonuçlara tutarlı bir durum enum'u / `"DOĞRULANDI"` değeri atayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P0-17 / R-02] `rust_core/src/aspasia.rs` İçinde Sabit `/workspace/agent_core` Yolu, Python Kod Enjeksiyonu (`self.api_key`) ve Boş API Anahtarı
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/aspasia.rs:70-105`
  - `rust_core/src-tauri/src/lib.rs:286`
- **Kanıt / Kök Neden:** `aspasia.rs:70-101` içinde `python3 -c` ile çalıştırılan betik metnine `sys.path.insert(0, '/workspace/agent_core')` sabit yolu ve kaçışsız (unescaped) `self.api_key` ile `summary.status_message` (`format!(..., self.api_key, ...)`) doğrudan gömülmektedir. Ayrıca `lib.rs:286` `AspasiaEngine::new(chief, String::new())` ile boş anahtar vermekte ve kasa açıldığında bu anahtarı hiç güncellememektedir.
- **Etki:** Tek tırnak içeren girdi rastgele Python kodu çalıştırır (RCE / Code Injection); masaüstü ortamında `/workspace/agent_core` bulunmadığı için `ModuleNotFoundError` oluşur.
- **Düzeltme Talimatı (Remediation Instruction):** Parametreleri Python kodu içine `format!` ile gömmek yerine `Command::new(...).env("OPENROUTER_API_KEY", &self.api_key)` ve `sys.argv` / `stdin` üzerinden güvenli aktarın; `/workspace/agent_core` yerine çalışma dizinine göreli yol kullanın ve `open_vault` içinde `aspasia.api_key` alanını güncelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

---

### 4.2. P1 — Yüksek Öncelikli Hatalar (37 Bulgu)

#### [P1-01 / BULGU-03] `voice_report_script` ve `renderer_report_*` Araçlarında `subject` / `params` Uyuşmazlığı ve 0-Kanıtlı Sahte Başarı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/capabilities/adapters_report.py:193-207`
  - `agent_core/capabilities/adapters_report_factory.py:45-64, 77-112, 124-159, 176-205`
  - `agent_core/mcp/tools.py:173-184`
- **Kanıt / Kök Neden:**
  1. `ReportScriptCapability.run` (`adapters_report.py:193-205`) yalnızca `ctx.params.get("report")` ve `ctx.params.get("text")` okur, `ctx.subject` alanına hiç bakmaz.
  2. `adapters_report_factory.py:47` satırında `subject = str(ctx.params.get("subject") or "").strip()` okunur; ancak `mcp/tools.py:176` `subject = args.pop("subject", "")` yaptığı için `ctx.params["subject"]` her zaman boştur. Dahası, girdi `evidence` listesi boş (`[]`) geldiğinde bile `render_pdf`/`render_diagram`/`render_video` 0 kanıtlı boş dosya üretip kendi manifest öğesini `items_out`'a ekleyerek `result.ok == True` döner.
- **Etki:** MCP üzerinden `voice_report_script` her zaman `empty_report` ile başarısız olur; `renderer_report_*` araçları ise 0 kanıtla sahte başarılı (`ok=True`) boş raporlar üretir.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `ReportScriptCapability.run()` içinde `raw_text = str(params.get("text") or ctx.subject or "").strip()` yedeğini ekleyin.
  2. `adapters_report_factory.py:47` satırında `subject = str(ctx.params.get("subject") or ctx.subject or "").strip()` yapın ve girdi `items` listesi boşsa (`if not items:`) `available=False, unavailable_reason="empty_evidence"` döndürün.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P1-02 / BULGU-04] `registry.status()` ve `runner.run()` Arasında `_ACTIVE_POLICY_FLAGS` ContextVar Tutarsızlığı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/capabilities/registry.py:97-132`
  - `agent_core/capabilities/runner.py:123-157`
- **Kanıt / Kök Neden:**
  1. `registry.py:106-116` içinde `status(self, state: PolicyState, ...)` fonksiyonu `cap.availability()` metodunu çağırırken `_ACTIVE_POLICY_FLAGS.set(frozenset(state.enabled_flags))` işlemini yapmaz.
  2. `runner.py:126-132` içinde `_ACTIVE_POLICY_FLAGS` yalnızca `cap.availability()` süresince set edilir ve `finally:` bloğunda (`132`) sıfırlanır; hemen ardından `line 156`'da çağrılan `await cap.run(ctx)` sırasında `_ACTIVE_POLICY_FLAGS` tekrar `None` olur. `maigret_scanner.is_enabled()` ve `holehe_scanner.is_enabled()` ise ContextVar yerine doğrudan `os.getenv` okur.
- **Etki:** `PolicyState.from_env().with_operator_consent(enable_gates=True)` kullanıldığında `pineal_status` 15 yeteneği yanlışlıkla `gate_disabled:ENABLE_*` olarak raporlar ve `runner.run()` sırasında alt servislerin iç kapı kontrolleri `disabled` hatasıyla başarısız olur.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `registry.py:106` içinde `cap.availability()` çağrısını `_ACTIVE_POLICY_FLAGS` context yönetimi içine alın.
  2. `runner.py:126` içindeki `_ACTIVE_POLICY_FLAGS` kapsamını `await asyncio.wait_for(cap.run(ctx), ...)` (`156`) tamamlanana kadar koruyun ve `maigret_scanner.is_enabled()` ile `holehe_scanner.is_enabled()` fonksiyonlarını `agent_core.capabilities.state.flag_enabled` kullanacak şekilde birleştirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P1-03 / BULGU-06] `phone_probe.py` İçinde Sahte (Stub) Mesajlaşma Yoklaması, Kırık DuckDuckGo Regex'i (`re.DOTALL` Eksikliği) ve Tek Varyant Sorgusu
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/phone_probe.py:159, 172, 197-220`
  - `agent_core/capabilities/adapters_identity.py:167-170, 193-199`
- **Kanıt / Kök Neden:**
  1. `_build_messaging_probes` (`phone_probe.py:197-220`) hiçbir ağ/protokol isteği yapmadan numarayı `https://wa.me/{digits}`, `https://t.me/+{digits}`, `viber://chat?number=+{digits}` içine yerleştirip `status="candidate"` döner.
  2. `phone_probe.py:172` satırındaki `findall(r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^>]*>(.*?)</a>', html)` çağrısında `re.DOTALL` bayrağı unutulmuştur; DuckDuckGo HTML çıktısı çok satırlı olduğundan `.*?` asla eşleşmez.
  3. Satır 159 yalnızca `query_variants[0]` için istek atar, `query_variants[1:]` varyantlarını hiç kullanmaz.
- **Etki:** `sensor_identity_phone_probe` web ayak izi aramasında her zaman `0` sonuç (`web_footprint_hits = []`) döner ve mesajlaşma varlık kontrolü gerçekte çalışmaz.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `phone_probe.py:172` satırındaki `findall` çağrısına `flags=re.DOTALL | re.IGNORECASE` ekleyin.
  2. Mesajlaşma linklerinin ağ yoklaması yapmadığını, yalnız operatör doğrulaması için üretilmiş aday bağlantılar olduğunu `PhoneProbeCapability.description` ve kanıt açıklamasında açıkça belirtin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P1-04 / BULGU-07 & CORE-B P1-10] `media_forensics.py`: Keyfi Yerel Dosya Okuma, Event-Loop Bloklama, `newest` Yarış Durumu, Redirect SSRF, Temizlenmeyen WAV Dosyası ve Whisper CLI Tutarsızlığı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/media_forensics.py:92-104, 151-163, 184-199, 211, 439, 466-468, 495`
- **Kanıt / Kök Neden:**
  1. **Keyfi Yerel Dosya Erişimi (`151-163`):** `fetch_media(source)` `if "://" not in value:` kontrolüyle herhangi bir yerel dosya yolunu (`.env`, `.pineal_vault.json`, `C:\Windows\win.ini`) kabul edip SHA-256 ve boyutunu hesaplar; `extract_frames` ve `transcribe` yerel yolları kısıtlamasız işler.
  2. **Async Event-Loop Bloklama (`184, 439, 495`):** `async def fetch_media` ve `async def transcribe` içinde `subprocess.run(..., timeout=600)` doğrudan çağrılarak `asyncio` döngüsü 10 dakikaya kadar dondurulur.
  3. **Yarış Durumu (`193`):** `newest = max(target_dir.glob("*"), key=lambda p: p.stat().st_mtime)` aynı dizindeki `index.json` dosyasını veya eşzamanlı başka bir görevin dosyasını seçebilir.
  4. **Redirect SSRF (`211`):** `open_client(..., follow_redirects=True)` nedeniyle `.jpg`/`.mp4` uzantılı genel URL `302` ile iç ağa yönlendirilebilir.
  5. **Temizlenmeyen WAV (`466-468`):** `_extract_audio` tarafından oluşturulan `.pineal-audio.wav` geçici dosyası `transcribe()` sonunda silinmez.
  6. **Whisper CLI Tutarsızlığı (`92-104`):** Sistemde `whisper.EXE` CLI kurulu olduğu halde `has_asr_backend()` yalnız Python `import faster_whisper`/`import whisper` aradığı için `no_asr_backend` döner.
- **Etki:** Yerel dosya sızıntısı, sunucu yanıt vermeme (DoS), görevler arası medya karışması, SSRF ve `extractor_media_transcript` aracının sistemde `whisper.EXE` varken çalışmaması.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. Yerel dosya yollarını yalnızca izin verilen `data/media_evidence` diziniyle sınırlandırın (`Path.resolve().is_relative_to(...)`).
  2. `yt-dlp` çağrısında `--print after_move:filepath` kullanın ve `index.json` dosyasını glob dışında tutun.
  3. `follow_redirects=False` kullanın; tüm `subprocess.run` çağrılarını `await asyncio.to_thread(subprocess.run, ...)` içine alın; `.pineal-audio.wav` dosyasını `finally:` bloğunda silin ve `has_asr_backend()` içine `shutil.which("whisper")` desteğini ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`, `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-05 / BULGU-10] `task_executor.py` İçinde %100 Ulaşılamaz Ölü Kod (`resonance_synthesizer` İçin `outreach_intent` Hazırlığı)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/task_executor.py:2411-2413, 2437-2454, 2822-3187`
- **Kanıt / Kök Neden:** Birincil ajan döngüsünde satır 2411'de `if agent_name in ["pattern_interrupt", "resonance_synthesizer"]: deferred.append(agent_name); continue` çalıştırılmaktadır. Aynı döngünün 24 satır altındaki (`2437-2454`) `if agent_name == "resonance_synthesizer" and not input_data.get("outreach_intent"):` bloğu %100 ulaşılamaz ölü koddur; ertelenmiş ajan döngüsünde (`2822-3187`) ise bu hazırlık kodu yoktur.
- **Etki:** `resonance_synthesizer` hiçbir zaman otomatik `outreach_intent` alamaz ve `outreach_config` ayarları işlevsiz kalır.
- **Düzeltme Talimatı (Remediation Instruction):** Satır 2437-2454 arasındaki `outreach_intent` oluşturma bloğunu birincil döngüden çıkarıp ertelenmiş ajan döngüsünün (`for agent_name in deferred:` — satır 2822 sonrası) içine taşıyın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P1-06 / BULGU-11] `task_executor.py` İçinde `target_profile["images"]` Alanının Geçici Dosya Yollarıyla Ezilmesi (`_timestamp_crosscheck_probe` Kırılması) ve `_current_target_profile` Yarış Durumu
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/task_executor.py:880-896, 1641, 1737, 2099-2104, 2337`
- **Kanıt / Kök Neden:**
  1. Satır 2099-2104'te `input_data['target_profile']['images']` içindeki orijinal Instagram URL'leri silinip yerine yerel geçici dosya yolları (`C:\Users\...\tmpXXXX.jpg`) yazılmaktadır. Satır 2337'de çağrılan `_investigate_life_rupture` -> `_timestamp_crosscheck_probe` (`880-896`) `profile.get("images")` üzerinde `shortcode_from_url(str(url))` çalıştırdığında yerel dosya yollarından shortcode çıkaramaz.
  2. Ayrıca `self._current_target_profile` (`1641, 1737`) örnek (instance) değişkeni olarak tutulduğu için aynı `TaskExecutor` üzerinde eşzamanlı görevlerde birbirini ezer.
- **Etki:** Yaşam kırılması (`life_rupture`) zaman damgası çapraz doğrulaması her zaman `None` döner ve eşzamanlı görevlerde hedef profil verisi karışır.
- **Düzeltme Talimatı (Remediation Instruction):** `_timestamp_crosscheck_probe` (`884`) içinde `profile.get("images")` yerine satır 2096'da saklanan `(input_data.get("_frame_sources") or {}).get("images") or profile.get("images") or []` listesini kullanın; `_current_target_profile` durumunu örnek değişkeni yerine `ContextVar` veya yerel parametre olarak taşıyın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P1-07 / CORE-A-06] `human_behavior.py`: Kırık Zaman Forensiği (`_temporal_forensics`), Sinyal Tipi Uyuşmazlığı (`visual_edge_density` vs `tension`) ve Ölü Köprü Metodları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/human_behavior.py:341-342, 423-451, 456-488, 507-556`
- **Kanıt / Kök Neden:**
  1. `_temporal_forensics` (`428-436`) `int(str(value).strip().split(":", 1)[0])` kullandığı için gerçek kazıyıcılardan gelen ISO-8601 (`"2026-09-20T23:45:00Z"`) ve Unix epoch (`1726875900`) zaman damgalarını %100 reddeder.
  2. `_analyze_visual_micro_img` (`342`) `signal_type="visual_edge_density"` üretirken, `_mine_contradictions` (`463`) `s.signal_type in ("tension", "void")` arar; `478.` satır ise hiçbir zaman üretilmeyen `"contradiction"` sinyal tipini bekler.
  3. `_identify_wound_as_bridge` ve `_calculate_resonance_potential` (`507-556`) hiçbir yerden çağrılmayan sabit/ölü metodlardır.
- **Etki:** Gece paylaşım/uykusuzluk forensiği ve görsel gerginlik çelişki madenciliği üretimde hiçbir zaman tetiklenmez.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `_temporal_forensics` içinde `from agent_core.engines.frequency_engine import parse_timestamp` kullanarak önce tam zaman damgasından `.hour` değerini çıkarın.
  2. Satır 463'teki koşulu `s.signal_type in ("tension", "visual_edge_density", "void")` olarak güncelleyin ve ölü metodları (`507-556`) kaldırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-08 / CORE-A-07] `resonance_calculator.py`: Ortak Sınırların Çatışma (`contradicted`) Sayılması, `BaseModel` Girdilerinin Yutulması ve `bool`/`NaN` Vektör Hatası
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/resonance_calculator.py:203-230, 286-309, 360-383`
- **Kanıt / Kök Neden:**
  1. `kind == "boundary"` (`360-374`) değerlendirmesinde `matches = sorted(user_terms & target_terms)` kesişimi bulunduğunda doğrudan `state="contradicted"` döndürülür; kullanıcı ve hedef aynı hassasiyeti/sınırı paylaştığında sistem bunu çatışma sayar. Ayrıca `_META_KEYS` içinde `"evidence_quotes"` olmadığı için alıntı cümlelerdeki sıradan kelimeler de sahte sınır çatışması üretir.
  2. `_collect_terms` (`286-309`) yalnız `str, dict, list, tuple` kabul eder; Pydantic `BaseModel` örneklerini sessizce yutar.
  3. `_has_required_dimensions` ve `_cosine_similarity` (`206-218`) `not isinstance(v, bool)` ve `math.isfinite(v)` kontrolü yapmaz.
- **Etki:** Ortak sınırlara sahip uyumlu profiller `"contradicted"` ilan edilir; `BaseModel` girdilerinde `0 anlamlı terim` nedeniyle `inference_gap` oluşur; `NaN` değerler uyumluluk skorunu bozar.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `_collect_terms` başına `if isinstance(node, BaseModel): node = node.model_dump()` ekleyin ve `_META_KEYS` kümesine `"evidence_quotes"` alanını dahil edin.
  2. `frictions` (`kind == "boundary"`) değerlendirmesinde hedefin sınırlarını kullanıcının tüm kelimeleriyle değil, yalnızca çatışan aktif eğilim terimleriyle karşılaştırın.
  3. Sayısal boyut kontrollerinde `isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)` doğrulaması yapın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-09 / CORE-A-08] `autonomous_verifier.py`: Tekil Arama Hatasında Tüm Doğrulama Döngüsünün İptali ve Azınlık Jüri Kanıtının Çoğunluk Kararına Yazılması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/autonomous_verifier.py:416-419, 448-472, 734-764`
- **Kanıt / Kök Neden:**
  1. `for claim in claim_data.claims:` döngüsünde (`747-764`) N iddiadan birinin arama çağrısı `not outcome.available` dönerse, satır 756'da doğrudan `return VerifierReport(..., status="UNVERIFIED", fallback_reason="search_unavailable")` çalıştırılarak doğrulanmış diğer tüm iddialar çöpe atılır.
  2. `_verify_with_panel` (`416-419`) içinde `evidence_url`, `evidence_quote` ve `contradiction_detail` ilk koltuktan `or` operatörüyle alındığı için, Koltuk 1 `YALAN` ve Koltuk 2+3 `DOĞRULANDI` dediğinde çoğunluk hükmü `DOĞRULANDI` olurken kanıt ve çelişki açıklaması `YALAN` diyen azınlık koltuğundan yazılır.
- **Etki:** Tek bir geçici arama hatası tüm doğrulama raporunu sıfırlar; jüri çoğunluk kararıyla kanıt alıntısı birbiriyle çelişir.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. Satır 756'daki erken `return` ifadesini kaldırıp başarısız aramayı `VOTE_UNKNOWN` (`decision_rule="arama_kullanilamadi"`) olarak kaydederek sonraki iddiaya `continue` ile geçin.
  2. `_verify_with_panel` içinde `verdict` (`top_status`) belirlendikten sonra `evidence_url`, `evidence_quote` ve `contradiction_detail` alanlarını yalnızca `votes.get(seat) == verdict` olan koltuklardan seçin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-10 / CORE-A-09] `aspasia_chief.py`: `"yerel"`/`"local"` Kelimesiyle İstenmeyen Model Override (Routing Bypass), Çok Turlu Hafıza Kaybı ve Sessiz Yutulan TasteFilter
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/aspasia/aspasia_chief.py:78-95, 322-360, 378-389, 399-404`
- **Kanıt / Kök Neden:**
  1. Satır 341-342'de `if not selected_model and any(w in user_message.lower() for w in ["yerel", "local", "kısıtlamasız", "ollama", "lmstudio"]): selected_model = "local"` kontrolü vardır.
  2. Satır 402-403'te `room_state["aspasia_session"].add_message(...)` çağrılmasına rağmen `chat()` içinde `conversation_history` hiç okunmaz ve `context_prompt` içine eklenmez.
  3. Satır 93-94 ve 388-389'daki `except Exception: pass` blokları hataları loglamadan yutar.
- **Etki:** Kullanıcı mesajında `"yerel"` geçen herhangi bir soru (`"Yerel saatle kaçta paylaşım yapıyor?"`) `AGENT_CHAINS["aspasia"]` zincirini bypass edip olmayan yerel modele giderek çöker; Aspasia önceki mesajları tamamen unutur.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. Satır 341-342'deki otomatik `"yerel"`/`"local"` kelime taramasını kaldırın.
  2. `room_state.get("aspasia_session")` içindeki son 8 mesajı `context_prompt` içine ekleyin ve `AspasiaSession.add_message` içine maksimum 40 mesaj sınırı koyun.
  3. `taste_filter` redlerini ve istisnalarını `logger.info` / `logger.warning` ile loglayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-11 / CORE-A-10] `frequency_engine.py` ve `gravity_engine.py`: Sınırsız Zaman Kovası Döngüsü (DoS/OOM), `posts` Dict Etkileşim Kaybı ve `content_basis` İhlali
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/frequency_engine.py:37-61, 81-103`
  - `agent_core/engines/gravity_engine.py:27-39`
  - `agent_core/domain/content_basis.py:28-29, 130-139`
- **Kanıt / Kök Neden:**
  1. `FrequencyEngine._sync` (`86-103`) içindeki `while t <= max(grids):` döngüsünde üst sınır yoktur; yıllara yayılan zaman damgası farklarında yüz binlerce `WaveSample` üretilir.
  2. `extract_post_series` (`46-58`) ve `GravityEngine._sync` (`29`) `posts[i]` bir `dict` olduğunda zaman damgasını `posts[i]`'den okurken `like_count`/`comment_count` alanlarını yalnızca ayrı `posts_meta` listesinden okur (`posts_meta` yoksa `GravityEngine` her zaman `INSUFFICIENT_DATA` döner).
  3. Motorlar `target_profile.get("post_evidence_types")` içindeki `"search_snippet"` kayıtlarını filtrelemez.
- **Etki:** Eski/hatalı zaman damgalarında CPU ve bellek tükenmesi (DoS/OOM); `posts` dict formatındaki profillerde etkileşim metriklerinin sıfırlanması ve `GravityEngine` kırılması.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `(max(grids) - start) // step > 2000` durumunda pencereyi son 2000 kovayla sınırlandırın veya `bucket_hours` değerini dinamik büyütün.
  2. `posts_meta[i]` boş olduğunda `posts[i]` bir `dict` ise `like_count`/`likes` ve `comment_count`/`comments` alanlarını `posts[i]` üzerinden okuyun.
  3. Motorlarda `post_evidence_types` dizisinde `"search_snippet"` olan indeksleri filtreleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-12 / CORE-A-11] `resonance_synthesizer.py` ve `memory_models.py`: `has_valid_evidence=False` İken Sıfırlanmayan `confidence`/`resonance_score` ve Eksik Şema Kısıtları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/resonance_synthesizer.py:154-169`
  - `agent_core/domain/memory_models.py:63, 135`
- **Kanıt / Kök Neden:** `resonance_synthesizer.py:154-169` içinde `has_bridge` `False` olduğunda (`has_valid_evidence = False`), `confidence` alanı `0.0`'a çekilmeden doğrudan `conf` olarak bırakılmakta ve `result.resonance_score` ne doğrulanmakta ne de sıfırlanmaktadır. Ayrıca `AuthenticBridge.resonance_score` (`memory_models.py:135`) `Field(ge=0.0, le=1.0)` kısıtına sahip değildir.
- **Etki:** Kanıtsız çıktılarda yüksek güven (`confidence`) ve rezonans skoru (`resonance_score`) üst katmana sızar.
- **Düzeltme Talimatı (Remediation Instruction):** `has_valid_evidence == False` olduğunda `confidence=0.0` ve `resonance_score=0.0` atayın; `AuthenticBridge.resonance_score` alanına `Field(default=0.0, ge=0.0, le=1.0)` ve `PassionProfile.sentiment_polarity` (`63`) alanına `Field(default=0.0, ge=-1.0, le=1.0)` kısıtlarını ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-13 / CORE-A-12] `target_psyche_profiler.py`: Yokluktan Sınır Uyduran Prompt Talimatı, Taban Confidence (`0.1`) Zorlaması ve Boş `visual_evidence` Dict Hatası
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/target_psyche_profiler.py:81-83, 175-177, 193, 205, 265`
- **Kanıt / Kök Neden:**
  1. `profile_frictions` satır 193'te *"Profil az paylaşımlı, ketum veya mesafeli ise, bu mahremiyet ve sessizlik tercihini doğrudan somut bir sınır sinyali (boundary_signals) olarak işle"* ve satır 205'te *"confidence alanını ... 0.1 ile 1.0 arasında ölç"* talimatı bulunmaktadır.
  2. Satır 83, 177 ve 265'teki `if not bio and posts_text == "Gönderi metni bulunamadı." and not visual_evidence:` kontrolünde `visual_evidence = {"detected_objects": [], "aesthetic_style": ""}` gibi içi boş bir sözlük `bool(visual_evidence) == True` döndürür.
- **Etki:** Hiçbir verisi olmayan profillerde bile LLM çağrısı yapılır ve model minimum `0.1` güvenle uydurma `boundary_signals` üretmeye zorlanarak `has_valid_evidence = True` döner.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `profile_frictions` satır 205'teki confidence kuralını `0.0 ile 1.0 arasında ölç; kanıt yetersizse 0.0 ve data_confidence=false döndür` olarak düzeltin ve satır 193'teki yokluktan sınır üretme talimatını kaldırın.
  2. `visual_evidence` sözlüğünün gerçekten dolu bir sinyal taşıyıp taşımadığını `authenticity_auditor.py:62-72`'deki gibi kontrol edin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-14 / CORE-A-13] `interpreter_agent.py`: Global Singleton Mutasyonu, Arka Plan Thread'inde `input()` Deadlock'u ve `LLMGateway` Bypass'ı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/interpreter_agent.py:37-65, 84-99`
- **Kanıt / Kök Neden:**
  1. `from interpreter import interpreter` ile global singleton nesne import edilip mutasyona uğratılır ve `interpreter.messages` sıfırlanmaz.
  2. `interpreter.auto_run = False` (`41`) yapıldıktan sonra `asyncio.to_thread` içinde `interpreter.chat(prompt, display=False)` (`85`) çağrıldığında, `open-interpreter` kod çalıştırma onayı için standart girdiden (`input()`) onay bekler.
  3. Satır 48-54'te `LLMGateway` bütçe/kota sistemi atlanarak doğrudan `https://openrouter.ai/api/v1` adresine bağlanılır.
- **Etki:** Sunucu ortamında worker thread'i `input()` beklerken sonsuza dek kilitlenir (deadlock) veya `EOFError` verir; oturum geçmişleri görevler arasında birbirine karışır.
- **Düzeltme Talimatı (Remediation Instruction):** Global singleton yerine izole örnek oluşturun veya geçmişi temizleyin; interaktif `input()` onayını tetikleyen akış yerine insan onayını API katmanında (`awaiting_authorization`) alan mimariyi ve merkezi `LLMGateway` yapılandırmasını kullanın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P1-15 / CORE-B P1-1] `vault_gate.py` vs `security.py`: `PINEAL_ENV` Ortam Tespiti Çelişkisi (Varsayılan Durumda Kasa Kilidi Fail-Open)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/scraper/vault_gate.py:171-185`
  - `agent_core/utils/security.py:77-86`
  - `agent_core/workers/agent_worker.py:134`
- **Kanıt / Kök Neden:** `security.py:77-86` içinde `PINEAL_ENV` tanımsız (`""`), `prod` veya `staging` olduğunda sistem **production (fail-closed)** kabul edilirken; `vault_gate.py:171` yalnızca `os.getenv("PINEAL_ENV", "").strip().lower() == "production"` koşulunu üretim sayar ve aksi halde `return True, "dev_boundary_deferred"` (`185`) döner.
- **Etki:** `PINEAL_ENV` ayarlanmamış bir sunucuda `.pineal_vault.json` hiç olmasa veya kilitli olsa bile `vault_gate.check()` açık dönerek tüm OSINT/scraper çıkışlarına izin verir.
- **Düzeltme Talimatı (Remediation Instruction):** `utils/security.py` içindeki `_is_production()` fonksiyonunu `is_production()` olarak dışa aktarın ve `vault_gate.py:171` ile `workers/agent_worker.py:134` içinde tek kaynak olarak bu fonksiyonu çağırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-16 / CORE-B P1-2] `InstagramGhostScraper`: Türkçe Binlik/Ondalık Sayı Ayrıştırma Hatası, 24 Gönderi Tavanı ve Bozuk DOM Bio/Link Enjeksiyonu
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/scraper/instagram_ghost.py:325-327, 367-402, 413, 1074-1092`
- **Kanıt / Kök Neden:**
  1. `_parse_num` (`367-376`) önce virgülü siler (`s.replace(",", "")`); Türkçe `"1,5M Takipçi"` ifadesi `"15M"` -> **15.000.000** (10 kat şişirme!) olur, Türkçe `"12,4B"` (Bin) soneki ise tanınmadığı için `ValueError` ile `0` döner.
  2. `DEFAULT_MAX_POSTS = 48` olmasına rağmen `_collect_structured_posts` (`325`) `if len(found) >= 24: return` ile 24'te durur.
  3. `dom_bio_text` (`1082`) içindeki `&` karakteri kaçırılmaz ama satır 413'teki regex `([^&]*)` kullandığı için biyografi ilk `&` karakterinde kesilir; `dom_ext_links` için eklenen `<link rel="me">` etiketlerini ise okuyan hiçbir kod yoktur.
- **Etki:** Türkçe Instagram profillerinde takipçi sayıları 10 kat şişirilir veya `0` olur; gönderi sayısı 24'te kesilir; `&` içeren biyografiler kırpılır ve harici linkler kaybolur.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `_parse_num` içinde Türkçe ondalık virgülü (`1,5M` -> `1.5M`) ve Türkçe `"B"` / `"BİN"` sonekini (`* 1_000`) destekleyin.
  2. Satır 325'teki `24` sabitini `self._max_posts()` ile değiştirin.
  3. `dom_bio_text` ve `dom_ext_links` değerlerini HTML'e sahte meta/link etiketi olarak gömmek yerine doğrudan `_parse_real_profile(..., dom_bio=dom_bio_text, dom_links=dom_ext_links)` parametreleri olarak geçirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-17 / CORE-B P1-3] `LLMGateway`: `query_json` 9Router/Vision Model Seçimini Eziyor ve `route_diagnostics` ile `agent_route_variants` Birbirini Tutmuyor
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/llm_gateway.py:1798-1810, 1993-1995, 2934-2939, 3370-3393`
- **Kanıt / Kök Neden:**
  1. `query_json` (`3385`) `model=None` geldiğinde `selected_model = model or (self.TIER_1_MODEL if tier == 1 else self.TIER_2_MODEL)` atayıp `self.query(..., model=selected_model)` çağırır; bu yüzden `self.query` (`2934`) içindeki `if "20128" in self.openrouter_base_url and not model:` dalına asla girilemez.
  2. `agent_route_variants` (`1993`) `_tier_route_decision` kullanırken, `route_diagnostics` (`1798`) `_active_agent_tier` bağlamını yoksayarak yalnız `paid_escalation_enabled()` kontrolü yapar.
- **Etki:** 9Router (`:20128`) kullanıldığında `query_json` çağrıları `free-unlimited`/`pineal-quick` yerine OpenRouter model kimliği gönderir; kokpit rota tanılaması gerçek yürütme rotalarıyla uyuşmaz.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `query_json` içinde `model=model` (yani `None` ise `None`) değerini doğrudan `self.query` fonksiyonuna iletin.
  2. `route_diagnostics` içinde `self._tier_route_decision(variant)` çağrısını kullanın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-18 / CORE-B P1-4] `HindsightMemory.semantic_search`: Görevler Arası (`task_id=None`) Aramada `task_id` Bilgisinin Kaybolması (`None` Dönmesi)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/hindsight_memory.py:64, 242-258, 283-294`
- **Kanıt / Kök Neden:** `_fetch_rows` (`249-258`) SQL sorgusunda `task_id` sütununu seçmez ve `semantic_search` (`288`) sonuç sözlüğüne `"task_id": task_id` (yani parametre `None` ise her zaman `None`) yazar.
- **Etki:** Görevler arası çapraz semantik aramada bulunan kanıtların hangi görevden (`task_id`) geldiği tamamen kaybolur.
- **Düzeltme Talimatı (Remediation Instruction):** `_fetch_rows` içindeki her iki `SELECT` sorgusuna `task_id` sütununu ekleyin ve sonuç sözlüğünde `"task_id": row[6]` olarak gerçek veritabanı değerini döndürün.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-19 / CORE-B P1-5] `BrowserSession`: Alan Adı Beyaz Listesi (`_ALLOWED_DOMAINS`) Kontrolünün `goto` Sonrasında Yapılması ve `click`/`press` Navigasyonlarında Hiç Yapılmaması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/browser_session.py:131-141, 203-236`
- **Kanıt / Kök Neden:** `open()` (`131-139`) içinde hedef URL izin verilmeyen bir alana yönlendirildiğinde `ValueError` fırlatılır ancak `self._page` o yasaklı sayfada açık bırakılır; ayrıca `click()`, `press()` ve `back()` metodlarında `_domain_ok(page.url)` hiç kontrol edilmez.
- **Etki:** Sayfa içi tıklama veya yönlendirmeyle tarayıcı izin verilen sosyal medya alan adlarından çıkıp iç ağ veya yasaklı sitelere geçebilir ve `state()`/`_snapshot()` üzerinden ekran görüntüsü/DOM okunabilir.
- **Düzeltme Talimatı (Remediation Instruction):** `_domain_ok(page.url)` kontrolünü `_snapshot()` öncesinde merkezi bir `_enforce_domain_guard(page)` yardımcı metoduna taşıyın; ihlal durumunda `await page.goto("about:blank")` çalıştırıp `ValueError` fırlatın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-20 / CORE-B P1-6] `maigret_scanner.py`: Egress Omurgası ve `vault_gate` (Kasa Kilidi) Tamamen Atlanarak Doğrudan Ağ Taraması Yapılması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/maigret_scanner.py:202-216, 219-265`
- **Kanıt / Kök Neden:** `holehe_scanner.py:113-115` içinde `require_open(purpose="osint")` zorunlu tutulurken, `maigret_scanner.py` kendi `aiohttp` istemcisini kullanan `maigret_fn` çağrısından önce `vault_gate.require_open(purpose="osint")` kontrolünü hiç çağırmaz ve `egress` Sorumluluk Zinciri'ne iz bırakmaz.
- **Etki:** `scan_username` doğrudan çağrıldığında Kasa kilitli olsa dahi dış ağa yüzlerce HTTP isteği çıkar.
- **Düzeltme Talimatı (Remediation Instruction):** `scan_username` içinde `_run_library_scan` çağrısından hemen önce `from agent_core.scraper.vault_gate import require_open; require_open(purpose="osint")` kontrolünü ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-21 / CORE-B P1-7] `frame_evidence.py`: `decode_image` İçinde `.convert("RGB")` Çağrısının EXIF Verisini Silmesi (`extract_exif` Her Zaman Boş)
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/frame_evidence.py:242-248, 343-355`
- **Kanıt / Kök Neden:** `decode_image` (`242-248`) içinde `with Image.open(io.BytesIO(data)) as image: image.load(); return image.convert("RGB")` çalıştırılmaktadır. Pillow'da `image.convert("RGB")` yeni bir `Image` nesnesi döndürür ve orijinal JPEG/TIFF `_getexif` okuyucusunu düşürür.
- **Etki:** `extract_frame_features` içindeki `extract_exif(image)` (`351`) gerçek fotoğraflarda bile EXIF etiketlerini (`DateTimeOriginal`, `Make`, `Model`, GPS) her zaman boş (`{}`) döndürür.
- **Düzeltme Talimatı (Remediation Instruction):** `decode_image` içinde `with Image.open(...) as image:` bloğu kapanmadan önce EXIF bilgisini okuyun veya `rgb = image.convert("RGB"); rgb.info["exif"] = image.info.get("exif")` ile EXIF verisini koruyun.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-22 / CORE-B P1-8] `deep_profile_resolver.py`: Tek Bir Rotada `socid_extractor` Eksikse Tüm Derin Profil Tarama Planının İptal Edilmesi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/deep_profile_resolver.py:243-253`
- **Kanıt / Kök Neden:** `if needs_socid and not module_available("socid_extractor"): return DeepProfileResolution(records={}, channel_status=not_run(...))` kontrolü döngüye girmeden önce tüm planı iptal eder.
- **Etki:** `plan.routes` içinde hem Instagram/X (`profile.deep.instagram`, `profile.deep.x`) hem de genel bir URL (`osint.socid.extract`) bulunduğunda, `socid_extractor` kurulu değilse Instagram ve X taramaları da hiç çalıştırılmaz.
- **Düzeltme Talimatı (Remediation Instruction):** Erken dönüşü kaldırın; `socid_extractor` kontrolünü yalnızca `route.capability_id == CAPABILITY_SOCID` olan rotalar için döngü içinde uygulayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-23 / CORE-B P1-9] `ShadowExecutor` ve `DarkTriadAnalyzer`: LLM Çöktüğünde veya Kanıt Alıntısı Yokken Sahte/Statik Çıktının `measured=True` / `data_confidence=True` Olarak İşaretlenmesi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/shadow/shadow_executor.py:345-378`
  - `agent_core/psychology/dark_triad.py:67-101`
- **Kanıt / Kök Neden:**
  1. `ShadowExecutor.execute` (`357-376`) içinde hem Mirror hem PatternInterrupt LLM çağrısı hata verdiğinde kod statik `"Doğal ve dengeli ilk temas."` metnine düşmekte fakat `data_confidence=True, fallback_reason=None` döndürmektedir.
  2. `DarkTriadAnalyzer.analyze` (`70-72, 100`) içinde `evidence_quotes` boş olduğunda profilin ilk 3 rastgele cümlesini (`texts[:3]`) kanıt alıntısı olarak atayıp `measured=True` yapmaktadır.
- **Etki:** Anti-halüsinasyon sözleşmesi delinir; statik şablonlar ve rastgele profil cümleleri doğrulanmış psikolojik kanıt gibi sunulur.
- **Düzeltme Talimatı (Remediation Instruction):**
  1. `shadow_executor.py` içinde her iki LLM çağrısı da başarısız olduğunda `self._fallback("llm_synthesis_failed", ...)` (`data_confidence=False`) döndürün.
  2. `dark_triad.py:70-72` içindeki rastgele metin dilimleme (`texts[:3]`) yedeklemesini kaldırın; gerçek kanıt alıntısı yoksa `measured=False` olarak işaretleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P1-24 / B-02] Görev Değişiklikleri (`/api/tasks/{task_id}/changes`) ve Hafıza (`/api/tasks/{task_id}/memory`) Uçlarında Görev Sahipliği (IDOR) Kontrolü Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py:4955-5006` (`GET /api/tasks/{task_id}/changes`)
  - `backend/api.py:5191-5257` (`GET /api/tasks/{task_id}/memory`)
- **Kanıt / Kök Neden:** `GET /api/tasks/{task_id}` ve `/graph` uçları `_task_access(task_id, request)` ile sahip kontrolü yaparken, `/changes` ve `/memory` uçları hiçbir `_task_access` / `guard_task` kontrolü yapmadan tüm `execution_rooms` sözlüğünü ve diskteki `memory/` dizinini tarar.
- **Etki:** Herhangi bir istemci `task_id` değerini bilerek başka bir operatörün görev değişikliklerini ve hedef hafıza kristalini okuyabilir (IDOR).
- **Düzeltme Talimatı (Remediation Instruction):** Her iki uca `request: Request` parametresi ekleyin ve işleme başlamadan önce `err = _task_access(task_id, request); if err is not None: return err` kontrolünü zorunlu kılın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-25 / B-03] `POST /api/aspasia/command` Ucunda Reşit Olmayan Hedef Kilidi (`_require_minor_clearance`) ve Kasa Kilidi (`_require_vault_open`) Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py:4399-4445` (`_aspasia_command_dispatch`), `4448-4471` (`POST /api/aspasia/command`)
- **Kanıt / Kök Neden:** `POST /api/initiate` ve `POST /api/commander/dispatch` uçları `_require_minor_clearance` ve `_require_vault_open` kontrollerini zorunlu tutarken, `_aspasia_command_dispatch` komuttan hedef URL/`@kullanici` çıkardığında doğrudan `asyncio.create_task(run_mission(...))` başlatır.
- **Etki:** Aspasia sohbet komutu üzerinden başlatılan görevlerde Reşit Olmayan Hedef Kilidi (HTTP 451) ve Kasa Kilidi (HTTP 423) tamamen atlanır.
- **Düzeltme Talimatı (Remediation Instruction):** `_aspasia_command_dispatch` içinde `target` tespit edildiğinde `run_mission` çağrısından önce `_require_minor_clearance(target, room=room, extra_texts=[text])` ve `_require_vault_open(room)` kontrollerini çalıştırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-26 / B-04] `POST /api/hook/generate` ve `POST /api/mobile/coach` Uçlarında Güvenlik Kapısı Eksikliği ve Yanlış LLM Nesnesi (`aspasia_chief.llm`) Kullanımı
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py:3617-3618, 4329-4356`
  - `backend/routes/hook_studio.py:133-250, 304-316`
  - `backend/routes/mobile_coach.py:57-116, 150-162`
- **Kanıt / Kök Neden:**
  1. Her iki uç `llm_getter=lambda: aspasia_chief.llm` ile kaydedilmiştir (`api.py:3617-3618`). Oysa `POST /api/vault` (`4329-4356`) ile girilen API anahtarları yalnızca odanın `room["executor"].llm` nesnesine yazılır; `aspasia_chief.llm.api_key` hiç güncellenmez.
  2. Her iki uçta da `_require_vault_open`, `_require_minor_clearance` ve `rate_limit` kontrolleri yoktur.
- **Etki:** `.env` içinde anahtar yoksa kasa açılsa bile `/api/hook/generate` ve `/api/mobile/coach` her zaman `LLM_NOT_CONFIGURED` ile şablon fallback'e düşer; güvenlik kapıları ve hız sınırı uygulanmaz.
- **Düzeltme Talimatı (Remediation Instruction):** `llm_getter` fonksiyonunu ilgili odanın `get_room(client_id)["executor"].llm` nesnesini döndürecek şekilde güncelleyin (ve `POST /api/vault` içinde `aspasia_chief.llm` nesnesini de senkronize edin); her iki uca `rate_limit`, `_require_vault_open` ve `_require_minor_clearance` ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-27 / B-05] `hook_studio.py` İçinde `final_conf == 0.0` Olduğunda Epistemik Kelepçenin (Clamp) Devre Dışı Kalması
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/hook_studio.py:374-393`
- **Kanıt / Kök Neden:** Satır 386'daki `"confidence": final_conf if final_conf > 0.0 else (conf if valid else 0.85)` ifadesi, `clamp(..., epistemic_state)` fonksiyonu güven skorunu `0.0`'a indirdiğinde (`final_conf == 0.0`) kelepçelenmiş değeri çöpe atıp LLM'in ham `conf` değerini veya `0.85` sabitini geri yükler.
- **Etki:** Kanıtsız (`UNVERIFIED`) durumlarda bile `hook_studio` yüksek güven skoru (`0.85`) döndürerek epistemik tavanı deler.
- **Düzeltme Talimatı (Remediation Instruction):** `backend/routes/hook_studio.py:386` satırını doğrudan `"confidence": final_conf,` olarak değiştirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-28 / B-06] `DELETE /api/tasks/{task_id}` Ucunun Checkpoint Dosyasını ve Sahiplik Kaydını Silmemesi
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/tasks.py:131-180` (`delete_task`)
- **Kanıt / Kök Neden:** `delete_task` yalnızca `room["task_history"]` listesinden görevi çıkarır ve `memory/{task_id}.json` dosyasını siler; ancak `checkpoint_store.delete(task_id)`, `room["tasks_by_id"]`, `room["support_by_task"]` ve `task_owners.db` kayıtlarını silmez.
- **Etki:** Silinmiş bir görev `POST /api/tasks/{task_id}/resume` ile diskteki `memory/checkpoints/{task_id}.json` dosyasından tekrar diriltilebilir ve disk/bellek sızıntısı oluşur.
- **Düzeltme Talimatı (Remediation Instruction):** `delete_task` içinde `checkpoint_store.delete(safe_id)`, `room["tasks_by_id"].pop(safe_id, None)` ve `room["support_by_task"].pop(safe_id, None)` çağrılarını ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-29 / B-07] `GET /api/speech/tts` Ucunda Bulut TTS (`edge_tts`) Kullanımı, Rate Limit ve Kasa Kilidi Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/speech.py:236-267` (`legacy_speech_tts`)
- **Kanıt / Kök Neden:** `POST /api/speech/synthesize` yerel öncelikli (local-first) politikasını ve `rate_limit` kontrolünü uygularken, eski `GET /api/speech/tts` ucu hiçbir `rate_limit` veya `_require_vault_open` kontrolü yapmadan doğrudan Microsoft bulut servisine (`edge_tts.Communicate`) metin gönderir.
- **Etki:** Kasa kilitli (`VAULT_LOCKED`) olsa dahi hedefe dair hassas analiz metinleri Microsoft bulut sunucularına sızar ve uç hız sınırına tabi değildir.
- **Düzeltme Talimatı (Remediation Instruction):** `legacy_speech_tts` ucuna `_rate_identity(request)` tabanlı `rate_limit` ve `_require_vault_open` kontrolü ekleyin; kasa kilitliyken yalnızca yerel TTS sağlayıcılarına izin verin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-30 / F-02] `SupportPanel.svelte` ve `store.ts` İçinde Destek Yanıtlama ve Görev Sürdürme (`/resume`) Çağrılarında `client_id` Gönderilmemesi
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SupportPanel.svelte:31-36` (`submit`), `53-58` (`resumeTask`)
  - `frontend/src/store.ts:72-74, 166-175` (`refreshSupport`)
  - Karşı taraf: `backend/routes/support.py:189, 293, 341`
- **Kanıt / Kök Neden:** Tarayıcı oturumu görevleri `client_xxxxxxx` odasında başlatmasına rağmen `SupportPanel.svelte` içindeki `/support/{sid}` ve `/resume` `POST` istekleri ile `store.ts:169` içindeki `/support` `GET` isteği `client_id` göndermez; backend varsayılan `"default"` odasına bakar.
- **Etki:** Duraklatılmış görevler için operatör destek sağlama ve görevi kaldığı yerden sürdürme (`/resume`) akışı arayüzden çalışmaz (`404` / yanlış oda).
- **Düzeltme Talimatı (Remediation Instruction):** `SupportPanel.svelte` içindeki her iki `POST` gövdesine `client_id: get(clientId) || 'default'` alanını ekleyin; `store.ts:169` içindeki `GET` çağrısına `?client_id=${encodeURIComponent(get(clientId) || 'default')}` sorgu parametresini ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-31 / F-03] `TacticalWarRoom.svelte` İçinde Görev Durdurma (`/halt`) Çağrısında `client_id` Eksikliği ve Hatanın Yutulması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/TacticalWarRoom.svelte:257-266` (`haltTask`)
  - Karşı taraf: `backend/api.py:4861-4895` (`POST /api/tasks/{task_id}/halt`)
- **Kanıt / Kök Neden:** `TacticalWarRoom.svelte:262` `await apiFetch(\`/api/tasks/${taskId}/halt\`, { method: 'POST' })` çağrısında `?client_id=...` göndermez; backend `"default"` odasında görevi bulamayıp `404` dönerken `haltTask` yanıtı kontrol etmeden `isProcessing.set(false)` yapar.
- **Etki:** Savaş Odası görünümünde durdurma düğmesine basıldığında arayüzde görev durmuş görünür ancak arka planda görev çalışmaya ve LLM bütçesi harcamaya devam eder.
- **Düzeltme Talimatı (Remediation Instruction):** `TacticalWarRoom.svelte:262` satırında `?client_id=${encodeURIComponent(get(clientId) || 'default')}` parametresini gönderin ve yalnızca `res.ok || res.status === 409` olduğunda `isProcessing.set(false)` yapın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-32 / D-02] `Dockerfile` İçinde `VERSION` Dosyasının ve `skills/` Dizinlerinin İmaja Kopyalanmaması
- **Dosya Yolu ve Satır Numarası:**
  - `Dockerfile:53-58`
  - Karşı taraf: `agent_core/version.py:26-44`
- **Kanıt / Kök Neden:** `agent_core/version.py:26` sürüm bilgisini `/app/VERSION` dosyasından okur; ancak `Dockerfile:54-57` yalnızca `backend/`, `agent_core/`, `config/` ve `frontend/dist` dizinlerini kopyalar (`VERSION` ve `skills/` kopyalanmaz).
- **Etki:** Docker ve Railway dağıtımlarında `get_version()` her zaman `"unknown"` döner ve `/api/health` ile `/api/version` sürüm doğrulaması bozulur.
- **Düzeltme Talimatı (Remediation Instruction):** `Dockerfile:56` satırından sonra `COPY VERSION ./VERSION` ve `COPY skills/ ./skills/` satırlarını ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-33 / D-03] `docker-compose.yml` ve `railway.toml` İçindeki Kasa Hacmi (`/app/vault-data`) ile `backend/api.py` (`VAULT_FILE`) Arasındaki Yol Uyumsuzluğu
- **Dosya Yolu ve Satır Numarası:**
  - `docker-compose.yml:31-33`
  - `railway.toml:19-21`
  - `backend/api.py:784`
- **Kanıt / Kök Neden:** `docker-compose.yml:32` ve `railway.toml:21` kalıcı disk hacmini `/app/vault-data` dizinine bağlarken, `backend/api.py:784` `VAULT_FILE = ".pineal_vault.json"` diyerek kasa dosyasını `/app/.pineal_vault.json` yoluna yazar.
- **Etki:** Konteyner her yeniden başlatıldığında mühürlenen kasa anahtarları silinir ve kalıcı hacim (`/app/vault-data`) boş kalır.
- **Düzeltme Talimatı (Remediation Instruction):** `backend/api.py:784` satırını `VAULT_FILE = os.environ.get("PINEAL_VAULT_FILE", "/app/vault-data/.pineal_vault.json" if os.path.isdir("/app/vault-data") else ".pineal_vault.json")` olarak güncelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-34 / R-03] `rust_core/src-tauri/src/lib.rs` İçinde `query_aspasia` Komutunun Kullanıcı Sorusunu LLM'e Göndermemesi
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src-tauri/src/lib.rs:212-222`
- **Kanıt / Kök Neden:** `query_aspasia` komutu `user_message` parametresini hiçbir zaman `aspasia` motoruna iletmez; yalnızca `aspasia.report_system_overview().await` çıktısının başına `format!("[Mosyo sorusu: {}]\n\n{}", msg, report)` ekleyip döndürür.
- **Etki:** Tauri masaüstü uygulamasında Aspasia sohbeti kullanıcı sorularına yanıt vermez, her seferinde aynı statik sistem özetini tekrarlar.
- **Düzeltme Talimatı (Remediation Instruction):** `AspasiaEngine` içine kullanıcı mesajını ve mevcut görev bağlamını alan gerçek bir `chat(user_message)` metodu ekleyin ve `query_aspasia` komutundan bu metodu çağırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-35 / R-04] `rust_core/src/agents/mirror_truth.rs` İçinde Sürekli Hata Dönen `call_llm` İskeleti ve Yanlış `duration_ms` (`0ms`) Ölçümü
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/agents/mirror_truth.rs:37-43, 140-150`
- **Kanıt / Kök Neden:** `call_llm` (`37-43`) her zaman sabit `Err("LLM_UNAVAILABLE...")` döndürür; ayrıca `let started = std::time::Instant::now();` (`140`) tüm işlemler bittikten hemen sonra tanımlanıp `150.` satırda `started.elapsed().as_millis()` okunur.
- **Etki:** Rust `MirrorTruthAgent` hiçbir zaman başarılı olamaz ve telemetride çalışma süresi her zaman `0ms` raporlanır.
- **Düzeltme Talimatı (Remediation Instruction):** `started` zamanlayıcısını `execute` fonksiyonunun en başına (`51.` satır) taşıyın ve `call_llm` metodunu gerçek HTTP LLM istemcisine bağlayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-36 / A-01] `PinealBackendClient.kt` İçinde Sabit Emülatör IP'si (`10.0.2.2:8000`) ve Kimlik Doğrulama Başlığı (`X-API-Key`) Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `android/app/src/main/java/com/example/pineal/engine/backend/PinealBackendClient.kt:26-30, 86-93`
- **Kanıt / Kök Neden:** `PinealBackendClient` varsayılan olarak yalnızca Android Emülatör'de geçerli olan `http://10.0.2.2:8000/` adresini kullanır, ayarlarda URL değiştirme alanı yoktur ve `PinealBackendApi.getCoachReply` (`26-30`) hiçbir `X-API-Key` veya `Authorization` başlığı göndermez.
- **Etki:** Gerçek Android cihazlarda backend bağlantısı %100 başarısız olur; `PINEAL_API_TOKEN` aktif olan sunucularda ise istekler `401 Unauthorized` ile reddedilir.
- **Düzeltme Talimatı (Remediation Instruction):** Android ayar ekranına yapılandırılabilir `backendBaseUrl` ve `backendApiToken` alanları ekleyin; `PinealBackendApi` arayüzüne `@Header("X-API-Key") apiToken: String?` parametresini dahil edin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P1-37 / A-02] `PinealViewModel.kt` İçinde Aspasia Sohbetinde Görsel (`imageBitmap = null`) Gönderiminin Devre Dışı Bırakılmış Olması
- **Dosya Yolu ve Satır Numarası:**
  - `android/app/src/main/java/com/example/pineal/ui/PinealViewModel.kt:353-361`
- **Kanıt / Kök Neden:** `sendMessage()` fonksiyonu `aspasiaEngine.generateResponse(...)` çağrısında `hasImage = image != null` göndermesine rağmen `imageBitmap = null // simplified for now due to context issues` sabit değerini iletir.
- **Etki:** Kullanıcı galeriden görsel seçse bile `AspasiaChatEngine.kt:129` içindeki `if (hasImage && imageBitmap != null)` koşulu hiçbir zaman sağlanmaz ve görsel işlenmez.
- **Düzeltme Talimatı (Remediation Instruction):** `selectedChatImageUri` değerini `ContentResolver` + `BitmapFactory` ile `Bitmap` nesnesine dönüştürüp `imageBitmap` parametresine gerçek `Bitmap` olarak iletin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

---

### 4.3. P2 — Orta Öncelikli Hatalar (27 Bulgu)

#### [P2-01 / BULGU-08] `report_factory.py` PDF Üreticisinde Türkçe Karakter Bozulması (Type1 `Helvetica`) ve `voice_tts_local` `piper.EXE` Model Argümanı Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/report_factory.py:198-243`
  - `agent_core/capabilities/adapters_voice.py:517, 725`
- **Kanıt / Kök Neden:**
  1. `_write_pdf` (`report_factory.py:214`) PDF 1.4 içerik akışını UTF-8 baytlarıyla yazarken font olarak yalnızca WinAnsi/StandardEncoding destekleyen standart Type1 `/BaseFont /Helvetica` (`222-223`) tanımlar.
  2. `adapters_voice.py:725` içinde `piper.EXE` çağrılırken zorunlu `-m <model.onnx>` argümanı olmadan yalnız `--output_file` geçirilir.
- **Etki:** Üretilen PDF raporlarında Türkçe karakterler (`ğ, ı, ş, İ, Ğ, Ş, ö, ü, ç`) bozuk (mojibake) görünür; `piper` tabanlı yerel TTS hata verir.
- **Düzeltme Talimatı (Remediation Instruction):** `reportlab` kuruluysa Unicode TTF font gömerek PDF üretin, saf-Python yedek yolunda ise CP1254/WinAnsi dönüşümü veya karakter normalizasyonu uygulayın; `adapters_voice.py` içinde `PINEAL_PIPER_MODEL` (`-m`) argümanını destekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P2-02 / BULGU-12] `config_loader.py` Docstring Sözleşmesi ile Gerçek Davranış Çelişkisi, Boş YAML Çökmesi ve Sistem Python'unda Eksik `PyYAML`
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/config_loader.py:7-9, 54-65`
- **Kanıt / Kök Neden:** Modül docstring'i (`8-9`) *"Dosya yoksa/bozuksa varsayılanlar kullanılır"* demesine rağmen `load_decision_config` dosya yoksa `FileNotFoundError` fırlatır (`58`) ve dosya boşsa `yaml.safe_load(f)` `None` döndüğü için `raw.get('decision_matrix', {})` (`63`) üzerinde `AttributeError` ile çöker. Ayrıca sistem Python'unda `PyYAML` kurulu değildir.
- **Etki:** Boş veya yorum satırlı `decision_matrix.yaml` dosyası sistemi çökertir; sanal ortam dışında `import yaml` `ModuleNotFoundError` verir.
- **Düzeltme Talimatı (Remediation Instruction):** `raw = yaml.safe_load(f) or {}` ve `if not isinstance(raw, dict): raise ValueError(...)` kontrolü ekleyin; docstring ile fonksiyon davranışını hizalayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P2-03 / BULGU-13] `mcp/state_bridge.py`, `mcp/server.py` ve `capabilities/egress.py`: Kilitsiz `_vault_cache`, Eksik Bütçe Kapısı ve Sınırsız Büyüyen Egress ContextVar'ı
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/mcp/state_bridge.py:56-57, 102-133, 180-196`
  - `agent_core/mcp/server.py:124, 140-141, 202-214`
  - `agent_core/capabilities/egress.py:71-73, 162`
  - `agent_core/task_executor.py:1405`
- **Kanıt / Kök Neden:**
  1. `_vault_cache` sözlüğü `asyncio.to_thread(vault_state)` ile arka plan thread'lerinden `threading.Lock` olmadan okunup yazılır.
  2. `policy_state_for_call()` (`state_bridge.py:180-196`) `budget_usd` ve `spent_usd` alanlarını hiç doldurmaz (`None` kalır).
  3. `egress.py:71-73` içindeki `_attempts` ContextVar'ı `task_executor.py` tarafından hiçbir yerde `drain_egress_attempts()` ile boşaltılmaz.
- **Etki:** Thread yarış durumu, MCP üzerinden çağrılan araçlarda bütçe kapısının devre dışı kalması ve görev boyunca büyüyen ContextVar bellek sızıntısı.
- **Düzeltme Talimatı (Remediation Instruction):** `_vault_cache` erişimini `threading.Lock()` ile koruyun; `OPENROUTER_MAX_SPEND_USD` değerini `PolicyState.budget_usd` alanına aktarın ve `task_executor.py` `finally:` bloğunda `drain_egress_attempts()` çağırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P2-04 / PATH-01] `scripts/apply_p1_fixes.py` ve `scripts/audit_capabilities.py` İçinde Sabit `C:\Projects\pineal-epifiz` Yolları
- **Dosya Yolu ve Satır Numarası:**
  - `scripts/apply_p1_fixes.py:12, 54, 75, 100`
  - `scripts/audit_capabilities.py:2, 4`
- **Kanıt / Kök Neden:** Her iki betikte dosya yolları `r"C:\Projects\pineal-epifiz\..."` olarak sabit kodlanmıştır.
- **Etki:** Depo başka bir dizinde, yedek sürücüde (`D:\...`) veya CI/Docker ortamında çalıştırıldığında betikler yanlış dizine erişir veya `FileNotFoundError` verir.
- **Düzeltme Talimatı (Remediation Instruction):** Tüm sabit yolları `ROOT = Path(__file__).resolve().parents[1]` üzerinden göreli hale getirin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P2-05 / CORE-A-14] `depth_analyst.py`: `DepthReport` Şemasında Eksik `data_confidence`/`fallback_reason`, Loglanmadan Yutulan İstisna ve Kafeslenmemiş Prompt Girdileri
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/depth_analyst.py:35-49, 146-152, 167-189`
- **Kanıt / Kök Neden:** `DepthReport` modelinde `data_confidence`, `confidence` ve `fallback_reason` alanları tanımlı değildir; satır 179'daki `except Exception:` hatayı loglamadan yutar; satır 146-150'de `tp` ve `osint` verileri `<UNTRUSTED_...>` kafesi olmadan prompt'a gömülür.
- **Etki:** Başarılı çalışmalarda `DepthReport` üzerinde `data_confidence` bulunmaz, LLM hataları iz bırakmadan yutulur ve prompt injection riski doğar.
- **Düzeltme Talimatı (Remediation Instruction):** `DepthReport` şemasına `confidence`, `data_confidence` ve `fallback_reason` alanlarını ekleyin; `except Exception as exc:` içinde `logger.warning` çağırın ve `tp`/`osint` bloklarını `<UNTRUSTED_...>` etiketleriyle sarın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-06 / CORE-A-15] `pattern_interrupt.py`: Yakalanmayan LLM İstisnası, 50 Karakterde Kesilen Kanıt Metni ve Birebir Kopya Ölü Metodlar
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/pattern_interrupt.py:95-96, 147-151, 217-267`
- **Kanıt / Kök Neden:** Satır 147'deki `await llm_gateway.query_json_chain(...)` çağrısı `try/except` bloğuna alınmamıştır; `_extract_micro_signal` (`251`) `return evidence[:50]` ile kanıt metnini 50 karakterde keser; `_extract_specific_detail` (`217-236`) ve `_extract_temporal_signal` (`255-267`) ölü koddur.
- **Etki:** Geçici LLM hatası `self._unavailable("llm_unavailable")` yerine yakalanmayan istisna fırlatır; prompt'a yarım cümle gider.
- **Düzeltme Talimatı (Remediation Instruction):** `query_json_chain` çağrısını `try/except Exception:` içine alıp `self._unavailable("llm_unavailable", ...)` döndürün; ölü metodları silin ve `evidence[:50]` sınırını `evidence[:240]` yapın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-07 / CORE-A-16] `aspasia/interface.py`: `build_oversight_digest` İçinde `has_content` Bayrağının `unknown` Kotaları Yazdırması ve Büyük Harf / HTTP URL Reddi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/aspasia/interface.py:48-59, 457-465, 896-906`
- **Kanıt / Kök Neden:**
  1. Satır 896-906'da kota kontrolü fonksiyon genelindeki `has_content` bayrağını kullanır; `ROUTING` veya `MALİYET` zaten `has_content = True` yaptığı için `"KOTA: groq:unknown | cerebras:unknown"` satırı her zaman yazdırılır.
  2. `_normalize_target_url` (`56-59`) `http://` URL'lerini ve büyük harf içeren domain'leri (`https://Instagram.com/...`) reddeder.
- **Etki:** Gözetim özetinde anlamsız `unknown` kota satırları görünür; büyük harfli veya `http://` şemalı geçerli hedef URL'leri reddedilir.
- **Düzeltme Talimatı (Remediation Instruction):** Kota döngüsü için yerel `has_quota_content = False` bayrağı kullanın; `_normalize_target_url` içinde `http` şemasını `https`'e dönüştürün ve `parts.netloc.lower()` uygulayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-08 / CORE-A-17] `aspasia/mobile_coach.py`: İstemciden Gelen Dark Triad ve Manipülasyon Alanlarının Sistem Prompt'una "Sunucudan Gelen Bağlam" Olarak Enjekte Edilmesi
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/aspasia/mobile_coach.py:38-47, 109-112, 126`
- **Kanıt / Kök Neden:** `_ALLOWED_CONTEXT_FIELDS` içinde `"narcissism"`, `"machiavellianism"`, `"psychopathy"`, `"manipulation_strategy"` alanları yer almakta ve istemciden gelen doğrulanmamış sözlük `"BİLİŞSEL PROFİL ÖZETİ (sunucudan gelen yapılandırılmış bağlam):"` başlığıyla sistem prompt'una yazılmaktadır.
- **Etki:** İstemci tarafından sahtelenebilen klinik/manipülatif etiketler sunucu onaylı gerçek bağlam gibi modele enjekte edilir.
- **Düzeltme Talimatı (Remediation Instruction):** `_ALLOWED_CONTEXT_FIELDS` içindeki Dark Triad ve manipülasyon anahtarlarını kaldırın ve başlığı `"İSTEMCİ TARAFINDAN SAĞLANAN PROFİL ÖZETİ"` olarak güncelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-09 / CORE-A-18] `pulse_engine.py` ve `strata_engine.py`: Dar Emoji Regex'i (`[😀-🙏]`), Yanlış `emoji_diversity` Hesabı ve Sabit Z-Skor Referansları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/pulse_engine.py:29-50`
  - `agent_core/engines/strata_engine.py:48-53`
- **Kanıt / Kök Neden:** `re.findall("[😀-🙏]", x)` yalnızca `U+1F600..U+1F64F` aralığını yakalar (`🔥, ❤️, 💀, 🚀, 🤣, 🥰, ☀️, ✅` emojilerini kaçırır); `pulse_engine.py:30` çeşitlilik yerine gönderi başına ham emoji sayısını `emoji_diversity` olarak kaydeder.
- **Etki:** Yaygın emojilerin büyük çoğunluğu sayılmaz ve `emoji_diversity` metriği çeşitlilik yerine ham adet ölçer.
- **Düzeltme Talimatı (Remediation Instruction):** Emoji regex'ini `r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"` olarak genişletin ve benzersiz emoji oranını doğru hesaplayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-10 / CORE-A-19] `seismos_engine.py`: 15 Kelimelik Çekimsiz ve Olumsuzlamasız `POS`/`NEG` Sözlüğü Nedeniyle Kırık `polarity()` Hesabı ve Kodlanmamış `SeismicKind` Türleri
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/engines/seismos_engine.py:13-15, 31-36, 82-105`
  - `agent_core/domain/pillar_models.py:80-86`
- **Kanıt / Kök Neden:** `POS` ve `NEG` kümeleri yalnızca 15 yalın kelimeden oluşur (`mutluyum`, `üzgünüm`, `yoruldum` eşleşmez; `"mutlu değilim"` `+1.0` pozitif çıkar). Ayrıca `SeismicKind` enum'undaki 6 değerden 4'ü (`ACTIVITY_BURST`, `STYLE_INVERSION`, `ENGAGEMENT_SHOCK`, `CADENCE_BREAK`) hiç kodlanmamıştır.
- **Etki:** Duygu kırılması (`POLARITY_SNAP`) Türkçe çekimli ve olumsuz cümlelerde yanlış çalışır; 4 sismik kırılma türü hiçbir zaman üretilmez.
- **Düzeltme Talimatı (Remediation Instruction):** `polarity(t)` fonksiyonuna Türkçe kök/önek eşleşmesi ve olumsuzlama penceresi (`değil`, `yok`, `hiç`, `not`, `never`) ekleyin; diğer `SeismicKind` türlerini `SeismosEngine._sync` içinde hesaplayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-11 / CORE-A-20] `task_execution_state.py` ve `responsibility.py`: `dict` Snapshot'ta `"unknown"` Dönen `task_state_fields`, Sabit `decision_state="unknown"` ve `seal_trail` Boşlukları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/domain/task_execution_state.py:26-49`
  - `agent_core/domain/responsibility.py:180-197`
- **Kanıt / Kök Neden:** `task_state_fields` içinde `getattr(snapshot, "status", snapshot)` çağrısı `snapshot` bir `dict` olduğunda tüm sözlüğü döndürür ve `task_phase="unknown"` üretir; `decision_state` her zaman `"unknown"` sabittir. `seal_trail` (`180-185`) içinde `claimed` değeri `"halted_frequency"` veya `"unavailable"` olduğunda hem `if` hem `elif` atlanarak `violation: None, sealed: True` dönülür.
- **Etki:** Sözlük tabanlı görev özetlerinde durum alanları `"unknown"` olur; hatalı `claimed` durumları ihlal bayrağı olmadan mühürlenir.
- **Düzeltme Talimatı (Remediation Instruction):** `snapshot.get(...) if isinstance(snapshot, dict) else getattr(snapshot, ...)` kullanın ve `seal_trail` içinde tüm geçerli/geçersiz `claimed` durumlarını açıkça denetleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P2-12 / CORE-B P2-1] `InstagramGhostScraper._parse_dt`: Milisaniye (ms) Unix Epoch Zaman Damgalarında Çökme
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/scraper/instagram_ghost.py:204-225`
- **Kanıt / Kök Neden:** Docstring hem saniye hem milisaniye (`sn/ms`) desteklediğini belirtmesine rağmen `datetime.fromtimestamp(float(value), tz=timezone.utc)` çağrısında `value > 1e11` (ms) `1000.0`'a bölünmez ve Windows'ta `OSError`/`ValueError` fırlatarak `None` döner.
- **Etki:** Milisaniye cinsinden gelen Instagram zaman damgaları kaybedilir (`None`).
- **Düzeltme Talimatı (Remediation Instruction):** `ts = float(value); ts = ts / 1000.0 if ts > 1e11 else ts` dönüşümünü ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P2-13 / CORE-B P2-2] `LLMGateway.start_chat_stream`: Async Generator `finally` Bloğunda `GeneratorExit` Hatası (Bütçe Sızıntısı) ve Eksik RTK Sıkıştırması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/llm_gateway.py:3000-3030, 3273-3280`
- **Kanıt / Kök Neden:** İstemci SSE akışını erken kapattığında Python async generator içine `GeneratorExit` fırlatır; `finally:` bloğunda (`3273-3280`) `await close_upstream()` çalıştırıldığında `RuntimeError: async generator ignored GeneratorExit` oluşur ve altındaki `await self._settle_budget(...)` çağrısına ulaşılamaz. Ayrıca `start_chat_stream` `_compress_chat_messages` (RTK) çağırmaz.
- **Etki:** Yarıda kesilen her akışta bütçe rezervasyonu açık kalır (bütçe sızıntısı) ve akışlı sohbetlerde RTK token tasarrufu çalışmaz.
- **Düzeltme Talimatı (Remediation Instruction):** `close_upstream()` ve `_settle_budget()` işlemlerini `asyncio.create_task(...)` ile arka plana alın; `start_chat_stream` başında `messages = self._compress_chat_messages(messages, ...)` çağrısını ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P2-14 / CORE-B P2-3] `HindsightMemory`: `semantic_search` ve `merge_evidence` İçinde `SentenceTransformer` Yükleme ve Embedding İşlemlerinin Event Loop'u Bloklaması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/hindsight_memory.py:130-156, 205, 271`
- **Kanıt / Kök Neden:** `async def semantic_search` ve `async def merge_evidence` içinden çağrılan `self._embed(...)`, model yükleme ve CPU vektör hesaplamasını doğrudan `asyncio` ana döngüsünde senkron çalıştırır.
- **Etki:** İlk model yüklemesinde ve yoğun kanıt indekslemesinde tüm FastAPI event loop'u saniyelerce donar.
- **Düzeltme Talimatı (Remediation Instruction):** `self._embed` ve `self._index_evidence_chain` çağrılarını `await asyncio.to_thread(...)` üzerinden çalıştırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P2-15 / CORE-B P2-4] `memory_crystal.py`: Eşzamanlı Görevlerde Hedef Kristal Dosyası (`memory/crystals/<slug>.json`) İçin Kilit Eksikliği
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/memory_crystal.py:282-340`
- **Kanıt / Kök Neden:** Aynı hedef (`target`) için çalışan iki paralel görev kilitsiz okuma-değiştirme-yazma yapar ve aynı `<slug>.json.tmp` geçici dosya adını kullanır.
- **Etki:** Eşzamanlı görevlerde veri kaybı veya Windows'ta `os.replace` sırasında `PermissionError` oluşur.
- **Düzeltme Talimatı (Remediation Instruction):** Hedef `slug` başına bir `threading.Lock()` tablosu ekleyin ve geçici dosya adına `uuid4().hex[:8]` soneki verin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P2-16 / CORE-B P2-5] `redis_bus.py`: Senkron `redis` Paketine Düşüldüğünde `disconnect()` Bağlantıyı Kapatmıyor
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/redis_bus.py:59, 189-196`
- **Kanıt / Kök Neden:** `disconnect()` yalnızca `if self._client and aioredis:` koşulunda kapanış yapar; senkron `redis` istemcisi açık kalır ve `self._use_redis` `False` yapılmaz.
- **Etki:** Senkron Redis yedek modunda soket sızıntısı oluşur.
- **Düzeltme Talimatı (Remediation Instruction):** `disconnect()` içinde `aioredis` yoksa `self._client.close()` çağırın ve `self._client = None`, `self._use_redis = False` atamalarını her durumda yapın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P2-17 / CORE-B P2-6] `workers/agent_worker.py` ve `scraper/run_scraper.py`: Sinyal ve Çıkış Kodu Yönetim Hataları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/workers/agent_worker.py:349-371`
  - `agent_core/scraper/run_scraper.py:55-61`
- **Kanıt / Kök Neden:** `agent_worker.py` içinde `SIGTERM` geldiğinde `loop.stop()` çağrıldığı için `except asyncio.CancelledError:` bloğu çalışmaz ve Redis'e son `alive=False` sinyali gönderilmez. `run_scraper.py` ise hata durumunda JSON basıp `exit(0)` ile çıkar.
- **Etki:** Kapatılan işçiler kokpitte çevrimiçi görünmeye devam eder; alt süreç olarak çağrılan `run_scraper.py` hataları üst süreç tarafından başarılı (`returncode == 0`) sanılır.
- **Düzeltme Talimatı (Remediation Instruction):** `agent_worker.py` içinde ana görevi `task.cancel()` ile iptal edin; `run_scraper.py` hata bloklarının sonuna `sys.exit(1)` ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P2-18 / B-08] Çoklu Uçlarda Rate Limit Eksikliği veya İstemci Tarafından Sahtelenebilir `req.client_id` Anahtarı Kullanımı
- **Dosya Yolu ve Satır Numarası:**
  - `backend/routes/commander.py:117-227`
  - `backend/routes/speech.py:123`
  - `backend/routes/company.py:62`
  - `backend/routes/language.py:67`
  - `backend/api.py:4551, 4668, 4700, 4800`
- **Kanıt / Kök Neden:** `_rate_identity(request)` (`api.py:854`) yerine doğrudan istemcinin JSON gövdesinde gönderdiği `req.client_id` değeri `rate_limit(...)` anahtarı olarak kullanılmaktadır; `commander.py` uçlarında ise hiç `rate_limit` yoktur.
- **Etki:** Saldırgan her istekte rastgele bir `client_id` göndererek hız sınırını (rate limit) tamamen atlatabilir.
- **Düzeltme Talimatı (Remediation Instruction):** Tüm `rate_limit(...)` çağrılarında ikinci parametre olarak `_rate_identity(request)` kullanın ve `commander.py` uçlarına da `rate_limit` ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-19 / B-09] `POST /api/agents/status/{agent_id}` Ucunda Rastgele `agent_id` Enjeksiyonu ve Tüm Odalara Yayın
- **Dosya Yolu ve Satır Numarası:**
  - `backend/api.py:3425-3454` (`update_agent_status`)
- **Kanıt / Kök Neden:** `agent_id` değerinin `AGENT_RACK_SLOTS` içinde olup olmadığı doğrulanmaz ve güncelleme `for cid, room in list(execution_rooms.items()):` döngüsüyle tüm odalara uygulanır.
- **Etki:** Bellek içi `agent_statuses` sözlüğüne sınırsız rastgele anahtar enjekte edilebilir ve bir istemcinin durum güncellemesi tüm operatörlerin odalarını etkiler.
- **Düzeltme Talimatı (Remediation Instruction):** `agent_id` değerini `AGENT_RACK_SLOTS` kümesiyle, `status` değerini izin verilen durumlarla sınırlandırın ve güncellemeyi yalnızca ilgili odaya uygulayın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-20 / B-10] `checkpoint_store.py` İçinde Zaman Aşımı (`TIMED_OUT_CHECKPOINT_S`) Sonrası Yarım Kalan İndeks Temizliği
- **Dosya Yolu ve Satır Numarası:**
  - `backend/checkpoint_store.py:198-211` (`mark_timed_out_all`)
- **Kanıt / Kök Neden:** `mark_timed_out_all` süresi dolan görevlerin diskteki JSON dosyasını `TIMED_OUT` olarak günceller ancak `self._index` ve `self._support_to_task` bellek içi indekslerinden temizlemez.
- **Etki:** `resolve_support_id(support_id)` süresi dolmuş görevleri döndürmeye devam eder.
- **Düzeltme Talimatı (Remediation Instruction):** `mark_timed_out_all` içinde `self._write_atomic(task_id, doc)` sonrasında `_support_to_task` ve `_index` kayıtlarını güncelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-21 / F-04] `LiveControlPanel.svelte` İçinde `scanned_urls` Nesne Dizisinin `string[]` Sanılarak `[object Object]` Olarak Çizilmesi
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/LiveControlPanel.svelte:101-104, 477-481`
- **Kanıt / Kök Neden:** `TargetProfile.scanned_urls` `{ url, platform, status, ... }` nesnelerinden oluşurken `LiveControlPanel.svelte:103` diziyi `string[]` olarak alıp `{u}` şeklinde doğrudan ekrana basar.
- **Etki:** Canlı kontrol panelinde URL rozetleri yerine `[object Object]` yazıları görünür.
- **Düzeltme Talimatı (Remediation Instruction):** `LiveControlPanel.svelte:103` satırını `...(($taskStatus?.target_profile?.scanned_urls || []).map((s: any) => typeof s === 'string' ? s : s?.url).filter(Boolean))` olarak düzeltin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-22 / F-05] `SpiderFootCockpit.svelte` İçinde `selectedMode` (`TAM ADLİ TARAMA` vs `HIZLI RADAR`) Seçiminin Görev Başlatırken Hiç Kullanılmaması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SpiderFootCockpit.svelte:116, 789-842, 1540-1553`
- **Kanıt / Kök Neden:** Üst barda kullanıcıya `selectedMode = 'full'` ve `selectedMode = 'probe'` seçenekleri sunulmasına rağmen `startMission()` (`789-842`) içinde `selectedMode` hiç okunmaz.
- **Etki:** Kullanıcı `HIZLI RADAR` seçse bile her zaman tam tarama başlatılır.
- **Düzeltme Talimatı (Remediation Instruction):** `/api/initiate` yüküne `mode: selectedMode` alanını ekleyin veya `probe` modunda hızlı yoklama akışını çağırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-23 / F-06] `SpiderFootCockpit.svelte` İçinde Ölçüm Yokken Sabit `%82` Zaafiyet Skoru ve Kurgusal Psikodinamik Metin Gösterilmesi
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/SpiderFootCockpit.svelte:2085, 2097, 2109, 2118-2121, 2163, 2168`
- **Kanıt / Kök Neden:** `activeDarkTriad` boşken bile `2118.` satırda `'%82'`, çubuklarda sabit `0.15/0.25/0.08/0.82` genişlikleri ve `2163, 2168` satırlarında kurgusal psikodinamik cümleler gösterilir.
- **Etki:** Hiçbir analiz çalışmamışken operatöre uydurma `%82` zaafiyet skoru ve kurgusal analiz metni gerçek sonuç gibi gösterilir.
- **Düzeltme Talimatı (Remediation Instruction):** Analiz verisi yokken `'Ölçümlenmedi (Veri Yok)'` ve `0%` çubuk genişliği gösterin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-24 / D-04] `wrangler.toml` İçinde Referans Verilen `wrangler.pages.toml` Dosyasının Depoda Bulunmaması ve SPA Fallback Hatası
- **Dosya Yolu ve Satır Numarası:**
  - `wrangler.toml:18-23`
  - `worker.ts:45`
- **Kanıt / Kök Neden:** `wrangler.toml` yorumunda belirtilen `wrangler.pages.toml` dosyası depoda yoktur; ayrıca `PINEAL_BACKEND_ORIGIN` tanımlı olmadığında `worker.ts:45` tüm `/api/*` isteklerine SPA `index.html` döndürür.
- **Etki:** Cloudflare Pages dağıtım yapılandırması eksiktir ve yanlış yapılandırmada API çağrıları sessizce HTML döndürerek JSON hatası üretir.
- **Düzeltme Talimatı (Remediation Instruction):** Depoya `wrangler.pages.toml` ekleyin ve `worker.ts` içinde `/api/` veya `/ws/` isteklerinde `PINEAL_BACKEND_ORIGIN` eksikse `502 Bad Gateway` JSON hatası döndürün.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-25 / D-05] `vercel.json` İçinde `/api/*` ve `/ws/*` Yönlendirme (`rewrites`) Kurallarının Bulunmaması
- **Dosya Yolu ve Satır Numarası:**
  - `vercel.json:1-6`
- **Kanıt / Kök Neden:** `vercel.json` yalnızca statik derleme tanımlar; hiçbir `rewrites` kuralı içermez.
- **Etki:** `VITE_API_BASE` derleme zamanında verilmemişse Vercel üzerindeki tüm `/api/*` istekleri `404 Not Found` döner.
- **Düzeltme Talimatı (Remediation Instruction):** `vercel.json` içine backend sunucusuna yönlendiren `rewrites` kurallarını ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-26 / R-05] `rust_core/src/` Altında Derlenmeyen Ölü Modüller (`aspasia_bridge.rs`, `llm_client.rs`, `scrapers/`) ve Kod Enjeksiyonu
- **Dosya Yolu ve Satır Numarası:**
  - `rust_core/src/lib.rs:1-14`
  - `rust_core/src/aspasia_bridge.rs:70-120`
  - `rust_core/src/llm_client.rs:1-120`
  - `rust_core/src/scrapers/mod.rs`
- **Kanıt / Kök Neden:** `aspasia_bridge.rs`, `llm_client.rs` ve `scrapers/` klasörü `lib.rs` içinde bildirilmemiştir; `aspasia_bridge.rs:78` içinde `data = json.loads('{}')` ile Python enjeksiyonu ve `115.` satırda var olmayan `state.aspasia_bridge` erişimi vardır.
- **Etki:** Depoda derlenmeyen, kırık ve güvenlik açığı barındıran ölü Rust modülleri bulunmaktadır.
- **Düzeltme Talimatı (Remediation Instruction):** Kullanılmayan ölü Rust modüllerini temizleyin veya derleme ağacına dahil edip kırık referanslarını düzeltin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P2-27 / A-03] Android `TargetInputCard.kt` ve `PinealViewModel.kt` İçindeki OSINT ve Model Ayarlarının Analiz Motorunda Hiç Kullanılmaması
- **Dosya Yolu ve Satır Numarası:**
  - `android/app/src/main/java/com/example/pineal/ui/components/TargetInputCard.kt:31, 104-123`
  - `android/app/src/main/java/com/example/pineal/ui/PinealViewModel.kt:44-49, 282-304`
- **Kanıt / Kök Neden:** `"DEEP_OSINT_EXTRACTION"` anahtarı yerel bir değişkende kalır; `SettingsDialog.kt` içinde alınan `osintApiKey`, `cookie`, `selectedModel` ve `useCloudApi` değerleri `PinealAnalyzerEngine` tarafından hiç okunmaz.
- **Etki:** Android uygulamasındaki ayar kontrolleri tamamen işlevsizdir (ölü UI).
- **Düzeltme Talimatı (Remediation Instruction):** Ayar parametrelerini analiz motoruna bağlayın veya işlevsiz kontrolleri arayüzden kaldırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

---

### 4.4. P3 — Düşük Öncelikli Hatalar ve Kod Hijyeni Bulguları (9 Bulgu)

#### [P3-01 / BULGU-14] Kök Betiklerde (`run_lilith.py`, `scripts/export_skills.py`, `calistir_windows.*`) Kalıntı Şablon Logları ve `venv` vs `.venv` Uyuşmazlığı
- **Dosya Yolu ve Satır Numarası:**
  - `run_lilith.py:32-34, 53-57, 88-91`
  - `scripts/export_skills.py:39-41`
  - `scripts/calistir_windows.bat:10`, `scripts/calistir_windows.ps1:19` vs `baslat.bat:26`
- **Kanıt / Kök Neden:** `run_lilith.py:33` ve `export_skills.py:40` içinde `"[<modül>] beklenmeyen hata..."` şablon metni kalmıştır; `run_lilith.py:53, 88` `.pineal_vault.json` dosyasını yalnız çalışma dizininde arar; `baslat.bat` `venv` oluştururken `calistir_windows.*` `.venv` arar.
- **Etki:** Loglarda `[<modül>]` yer tutucusu görünür ve Windows başlatma betikleri birbirinin oluşturduğu sanal ortamı bulamaz.
- **Düzeltme Talimatı (Remediation Instruction):** `[<modül>]` metinlerini gerçek modül adlarıyla değiştirin, `PINEAL_VAULT_PATH` env değişkenini destekleyin ve `.venv` yoksa `venv\Scripts\python.exe` yedeğine düşün.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`

#### [P3-02 / CORE-A-21] `memory_models.py`: Docstring'deki `extra="forbid"` Beyanına Rağmen `extra="allow"` Kullanılması ve `model_copy` Alias Senkronizasyon Hatası
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/domain/memory_models.py:9-11, 52, 69, 74-90, 102, 107-116`
- **Kanıt / Kök Neden:** `PassionProfile._sync_aliases` ve `FrictionProfile._sync_aliases` yalnızca alanlardan biri boşken kopyalama yapar; `model_copy(update={"core_passions": ["yeni"]})` çağrıldığında `passion_anchors` eski değerinde kalır.
- **Etki:** `model_copy` sonrasında alias alanları (`core_passions` vs `passion_anchors`, `sensitivities` vs `friction_vectors`) tutarsızlaşır.
- **Düzeltme Talimatı (Remediation Instruction):** `model_copy` içinde `update` sözlüğünde açıkça güncellenen alanın alias karşılığını da `update` sözlüğüne yansıtın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P3-03 / CORE-A-22] `mirror_truth.py`: Kanıt Yokken Üretilen `"bilinmeyen_caba"` / `"belirsiz_frekans"` Yer Tutucularının Prompt'a ve `ResonanceCalculator`'a Sızması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/mirror_truth.py:71-72, 100-101, 147-155, 182, 201`
- **Kanıt / Kök Neden:** `_find_anchors` kelime bulamadığında `["bilinmeyen_caba"]`, `_extract_core_frequency` ise `"belirsiz_frekans"` döndürür ve bu değerler `ResonanceCalculator._user_evidence_terms` havuzuna gerçek kanıt terimi gibi girer.
- **Etki:** Yer tutucu kelimeler kullanıcı kanıt terimi sayılarak sahte terim kesişimlerine yol açabilir.
- **Düzeltme Talimatı (Remediation Instruction):** `_find_anchors` kelime bulamadığında `[]`, `_extract_core_frequency` ise `""` döndürmelidir.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P3-04 / CORE-A-23] `target_psyche_profiler.py`: `profile_all` Metodunun Paralel (`asyncio.gather`) Yerine Sıralı Çalışması
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/target_psyche_profiler.py:8, 341-346`
- **Kanıt / Kök Neden:** `profile_all` üç lensi (`profile_passions`, `profile_frictions`, `profile_cognitive`) sıralı olarak `await` etmektedir.
- **Etki:** `profile_all` çağrılarında gecikme süresi 3 katına çıkar.
- **Düzeltme Talimatı (Remediation Instruction):** `return await asyncio.gather(self.profile_passions(payload), self.profile_frictions(payload), self.profile_cognitive(payload))` olarak güncelleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P3-05 / CORE-A-24] `osint_investigator.py` ve `pillar_models.py`: Hiçbir Zaman Doldurulmayan Şema Alanları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/agents/osint_investigator.py:30-31`
  - `agent_core/domain/pillar_models.py:59`
- **Kanıt / Kök Neden:** `OsintProfile.digital_footprint_score`, `OsintProfile.dark_web_hits` ve `FrequencyReport.phase_shifts` alanları hiçbir kod yolunda doldurulmaz.
- **Etki:** Şemada her zaman varsayılan (`0.0` / `[]`) kalan ölü alanlar bulunur.
- **Düzeltme Talimatı (Remediation Instruction):** `digital_footprint_score` değerini gözlenen platform/e-posta/telefon sayısından deterministik olarak hesaplayın veya kullanılmayan alanları şemadan kaldırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_A.md]`

#### [P3-06 / CORE-B P3-1] `nlp/dark_nlp.py` ve `services/memory_injector.py`: Bozuk Girdi Tiplerinde `TypeError`
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/nlp/dark_nlp.py:96-101`
  - `agent_core/services/memory_injector.py:102-103`
- **Kanıt / Kök Neden:** `dark_nlp.py:98` içinde `beliefs` elemanlarının `str` olduğu doğrulanmaz; `memory_injector.py:102-103` içinde `"hash"` alanı olmayan bir kuralda `"fact"` liste/sözlük ise `unique_rules[rule.get("fact")]` `TypeError: unhashable type` fırlatır.
- **Etki:** Bozuk girdi veya `learnings.json` kaydında beklenmeyen `TypeError` oluşur.
- **Düzeltme Talimatı (Remediation Instruction):** `dark_nlp.py` başında `beliefs = [str(b).strip() for b in beliefs if isinstance(b, str) and b.strip()]` filtrelemesi yapın; `memory_injector.py:102` içinde anahtar olarak `str(rule.get("fact") or "")` kullanın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P3-07 / CORE-B P3-2 & PATH-02] `services/platform_registry.py`: Sabit Kodlanmış `C:\Program Files\Google\Chrome\...` Windows Yolları
- **Dosya Yolu ve Satır Numarası:**
  - `agent_core/services/platform_registry.py:394-401`
- **Kanıt / Kök Neden:** `win_paths` yalnızca `C:\Program Files\...` ve `C:\Program Files (x86)\...` sabit yollarını kontrol eder; `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe` veya `CHROME_PATH` env değişkenine bakmaz.
- **Etki:** Kullanıcı bazlı (`AppData\Local`) Chrome kurulumları tespit edilemez.
- **Düzeltme Talimatı (Remediation Instruction):** `os.getenv("CHROME_PATH")` ve `os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")` yollarını arama listesine ekleyin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_29_TOOLS_AND_EXECUTOR.md]`, `[RESEARCH/PINEAL_AUDIT_CORE_B.md]`

#### [P3-08 / F-07] `App.svelte` İçinde `telemetryVisible` Değişkeninin Yorumla Çelişecek Şekilde `onMount` İçinde Kapatılması
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/App.svelte:122-126, 363`
- **Kanıt / Kök Neden:** Satır 122-126'daki yorum başlangıçta telemetri şeridinin açık olduğunu belirtip `let telemetryVisible = true;` tanımlar; ancak `onMount` içindeki `363.` satırda `telemetryVisible = false;` yapılır.
- **Etki:** Telemetri şeridi açılışta hemen kapanır.
- **Düzeltme Talimatı (Remediation Instruction):** `App.svelte:363` satırındaki `telemetryVisible = false;` atamasını kaldırın.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

#### [P3-09 / F-08] `AtlasPinealCockpit.svelte` ve `SpiderFootCockpit.svelte` İçinde Sabit/Tekrarlanan Şablon Hataları
- **Dosya Yolu ve Satır Numarası:**
  - `frontend/src/components/AtlasPinealCockpit.svelte:960-976`
  - `frontend/src/components/SpiderFootCockpit.svelte:2699-2715`
- **Kanıt / Kök Neden:** `AtlasPinealCockpit.svelte:960-976` kasa kilitli veya WebSocket kopukken bile sabit yeşil aktif etiketleri gösterir; `SpiderFootCockpit.svelte:2699-2715` içinde `<div class="chat-header">ASPASIA CANLI ANALİZ DANIŞMANI</div>` başlığı alt alta iki kez yazılmıştır.
- **Etki:** Yanıltıcı durum göstergesi ve arayüzde çift başlık görünümü.
- **Düzeltme Talimatı (Remediation Instruction):** Durum etiketlerini `$vaultLocked` ve `$uplinkStatus` mağazalarına bağlayın; `SpiderFootCockpit.svelte:2712-2715` satırlarındaki mükerrer başlığı silin.
- **Kaynak Rapor:** `[RESEARCH/PINEAL_AUDIT_BACKEND_API.md]`

---

## 5. Önerilen Düzeltme Sırası (Uygulama Yol Haritası)

1. **Faz 1 — Güvenlik, Veri Sızıntısı ve Kırmızı Çizgi Yamaları (İlk 24 Saat):**
   - `company_recon.py` SSRF açıklarının kapatılması (`P0-03`), `osint_investigator.py` `aiohttp`/URL injection düzeltmesi (`P0-07`), `lilith_growth.py` `FreeTextGateway` dış veri sızıntısının kaldırılması (`P0-09`), `dialogue_manager.py` prompt injection ve geçmiş bozulması yaması (`P0-08`).
   - `MinorGate` otomatik yaş sinyali tespiti ve tüm giriş noktalarına (`task_executor`, `shadow_executor`, `run_scraper`, `/api/aspasia/command`, `/api/hook/generate`, `/api/mobile/coach`) kasa/minor kapılarının eklenmesi (`P0-12`, `P1-15`, `P1-20`, `P1-24`, `P1-25`, `P1-26`, `P1-29`).
2. **Faz 2 — Çalışma Zamanı Çökmeleri ve Çekirdek Boru Hattı Kırılmaları:**
   - Windows `fcntl` / `os.open` çökmesinin giderilmesi (`P0-13`), Cloudflare WebSocket `auth` mesajı kuyruklaması (`P0-15`), `task_executor.py` `resume_from` `claim_gate` silinmesi (`P0-04`), `outreach_intent` ölü kodu (`P1-05`) ve `_timestamp_crosscheck_probe` görsel URL ezilmesi (`P1-06`).
   - `void_engine.py` kelime sınırı düzeltmesi (`P0-05`), `autonomous_verifier.py` `YALAN`/`ÇELİŞKİLİ` oy kapısı düzeltmesi (`P0-06`, `P1-09`), `instagram_ghost.py` `_paginate_grid` ve Türkçe sayı ayrıştırma düzeltmeleri (`P0-10`, `P1-16`), `HindsightMemory.merge_evidence` imza düzeltmesi (`P0-11`).
3. **Faz 3 — MCP Araçları, Kokpit Arayüzü ve Dağıtım Bütünlüğü:**
   - 28 capability için `mcp_input_schema` tanımlanması (`P0-01`), `voice_stt_local` Base64/dosya yolu desteği (`P0-02`), `voice_report_script` ve `renderer_report_*` düzeltmeleri (`P1-01`), `_ACTIVE_POLICY_FLAGS` ContextVar kapsamının düzeltilmesi (`P1-02`).
   - `SpiderFootCockpit.svelte` `osint_radar` sekmesinin bağlanması (`P0-14`), `SupportPanel.svelte` ve `TacticalWarRoom.svelte` `client_id` düzeltmeleri (`P1-30`, `P1-31`), `Dockerfile` (`VERSION`, `skills/`) ve `/app/vault-data` uyumsuzluğunun giderilmesi (`P1-32`, `P1-33`).
4. **Faz 4 — Sabit Yollar, Yan Katmanlar (`rust_core/`, `android/`) ve Kod Hijyeni:**
   - `scripts/apply_p1_fixes.py` ve `scripts/audit_capabilities.py` içindeki sabit `C:\Projects\pineal-epifiz` yollarının göreli hale getirilmesi (`P2-04`).
   - `rust_core/` (`P0-16`, `P0-17`, `P1-34`, `P1-35`, `P2-26`) ve `android/` (`P1-36`, `P1-37`, `P2-27`) katmanlarının mimari karara göre ya tamamen temizlenmesi/arşivlenmesi ya da ilgili yamalarının uygulanması.




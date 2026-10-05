# RUNBOOK — Kurulum, Çalıştırma, Sorun Giderme

## Başlatma
| Yöntem | Komut | Not |
|---|---|---|
| Windows | `baslat.bat` | venv + temel/OSINT pip paketleri + Playwright Chromium + frontend build (dist yoksa) + uvicorn:8000 |
| Docker | `docker compose up --build` | Playwright/Chromium dahil; `pineal_memory` volume |
| Manuel | `pip install -r requirements.txt && pip install -r requirements-osint.txt` → `cd frontend && npm ci && npm run build` → `uvicorn backend.api:app --port 8000` | İkinci dosya crawl4ai içindir (psutil meta-çatışması nedeniyle iki adım) |
| Dev (vite) | `frontend/.env`: `VITE_API_BASE=http://127.0.0.1:8000` → `npm run dev` | :5173 → :8000 |

## Anahtarlar (`.env` veya UI Kasası)
- `OPENROUTER_API_KEY` + `LIVE_LLM_E2E=1` → canlı bulut LLM.
- Yerel: `USE_LOCAL_LLM=true`, `LOCAL_LLM_URL=http://localhost:11434/v1`, `LOCAL_LLM_MODEL=...` (anahtar gerekmez).
  Not: API sunucusunda Kasa'daki "yerel model" seçimi (`use_local`) bu env'i ezer; env varsayılanı yalnız Kasa seçimi yapılmamışsa geçerlidir.
- `TAVILY_API_KEY`, `SERPAPI_API_KEY`, `EXA_API_KEY` → AutonomousVerifier web doğrulaması (yoksa DuckDuckGo yedeği).
- Vision: `OPENROUTER_VISION_MODEL` — varsayılan `google/gemini-3.7-flash`; VisionAnalyzer (profil fotoğrafları) ve görselli Aspasia isteklerinde kullanılır.
- Model varsayılanları (2026-09-02 karar matrisi):
  Tier-1 `anthropic/claude-sonnet-5` (`OPENROUTER_TIER_1_MODEL`),
  Tier-2 `deepseek/deepseek-v4-flash` (`OPENROUTER_TIER_2_MODEL`),
  Vision `google/gemini-3.7-flash` (+ yedek `x-ai/grok-4.6`).
  Koddaki gerçek zincirler: depth `claude-sonnet-5 → deepseek-v4-pro → gemini-3.7-flash` ·
  dialogue `claude-sonnet-5 → gemini-3.7-flash` · fast `deepseek-v4-flash →
  gemini-3.7-flash` · vision `gemini-3.7-flash → grok-4.6`
  (env: `OPENROUTER_CHAIN_<TASK>`; ajan: `OPENROUTER_AGENT_CHAIN_<AJAN>`).
  Emekli promo slug'lar (`solar-pro4`, `ling-3.0-flash`, `glm-5.2`) varsayılan zincirde yok.
- Token kipi: `PINEAL_TOKEN=x` (HTTP `X-API-Key`; WS ilk auth mesajı). UI token'ı YALNIZ çalışma zamanında Kasa → "API ERİŞİM ANAHTARI" alanından girer (localStorage); build-time gömme yoktur (AUDIT 2026-09-11 P0: `VITE_PINEAL_TOKEN` kaldırıldı). `PINEAL_ENV=production` tokensız başlatılamaz; Docker varsayılanı production'dır.
- Harcama tavanı: `OPENROUTER_MAX_SPEND_USD` (0=kapalı; env tanımsızsa da 0). Aşılırsa `SpendCapExceeded`.
- Native yönlendirici: `PINEAL_LLM_BACKEND=legacy|unified` + `PINEAL_ROUTER_CONFIG` (şablon: `config/router.example.json`). `unified` seçilip config verilmezse startup **çökmez**: legacy'ye düşer, `/health` `UNIFIED_ROUTER_CONFIG_MISSING` ile DEGRADED döner (fail-safe; fail-closed değil).

## Sık sorunlar
| Belirti | Neden → Çözüm |
|---|---|
| `Görev durumu: failed`, 0 kanıt | LLM yok: anahtar + `LIVE_LLM_E2E=1` veya yerel model ayarla |
| Aspasia "bağlantıda kırılma" yanıtı | Aynı — zarif fallback; anahtar girilince gerçek yanıt |
| Tarayıcı boş | `frontend/dist` yok → build et; `/src/main.ts` 404 çıkarsa dist eski demektir |
| 429 (initiate/aspasia) | Rate limit — 1 dk bekle (bilinçli koruma) |
| 401 tüm API çağrıları | `PINEAL_TOKEN` tanımlı ama UI göndermiyor → arayüzde Kasa → "API ERİŞİM ANAHTARI (PINEAL_TOKEN)" alanına gir (çalışma zamanı, yeniden derleme gerekmez; build-time gömme yolu yoktur — AUDIT 2026-09-11 P0) — ya da token'ı kaldır |
| Scrape 429/403 (Instagram) | Platform limit/cookie: Kasaya güncel cookie gir |
| X (Twitter) hedefi | Gerçek sensör: `sensor.x.twscrape` (kapı: `ENABLE_X_SENSOR=true` + kasa + hesap havuzu). Sensör kanıt üretirse **gerçek zaman damgalı gönderi serisi** çıkar. Sensör kapalı/kanıtsızsa profil UYDURULMAZ: logda `X SENSÖRÜ KANIT ÜRETEMEDİ` görünür, açık kaynak dosyası (`platform: web_dossier`, takipçi `None`) ile devam edilir; `scripts/run_task.py` ise `halted_evidence` + exit 3 döner. Eski `awaiting_authorization` yolu kaldırıldı (Faz A · Retina) |
| WS bağlanmıyor | Token kipinde istemci bağlantıdan sonra ilk JSON mesajında `{type:"auth",token:"..."}` göndermeli; token URL/query'ye yazılmaz. Sunucu ~5 sn içinde auth mesajı almazsa 1008 ile kapatır (UI artık bunu "UPLINK YETKİ HATASI" diye loglar ve otomatik yeniden bağlanır). Port 8000 dışındaysa `VITE_API_BASE` tanımla |

## Görev verisi
- Başlatma: `POST /api/initiate` immutable `task_id` döndürür.
- Çalışan görevi iptal/durdurma: `POST /api/tasks/{task_id}/cancel?client_id=...` veya `/halt` (terminal ve idempotent).
- Liste: `GET /api/tasks?client_id=...`
- Kalıcı silme (retention): `DELETE /api/tasks/{task_id}?client_id=...` (json kanıt dosyası + aktif snapshot)

## Test / Kalite kapıları
```
ruff check .          # gerçek hata kapısı (E9+F)
pytest -q             # unit+integration+e2e+ws sıra+güvenlik+protokol
                      # güncel sayı: pytest --collect-only -q | tail -1
cd frontend && npm run check && npm run build   # 0 hata + gerçek-app kilidi
```
CI: `.github/workflows/ci.yml` — her push'ta otomatik çalışır: backend (ruff + pytest + coverage), frontend (check + build + dist doğrulama), Rust (`cargo check` + `cargo test`), Android (lint + unit + assemble) ve smoke (uvicorn + curl).

Disaster recovery / volume persistence (manuel; Docker daemon gerekir):
```
bash scripts/test_disaster_recovery.sh              # DR_WAIT_TIMEOUT=600 ile yavaş makine toleransı
```
Konteyneri hard-kill edip siler (`down`, `-v` bilinçli YOK) ve sıfırdan yaratır; `pineal_memory` + `pineal_vault` verisinin hayatta kaldığını doğrular. İmaj production'da tokensuz açılmadığından script geçici `PINEAL_TOKEN` override'ı uygular (`.env`'e dokunmaz). Kapsam: compose named-volume persistence — gerçek yedek/geri yükleme ve Railway volume davranışı bu testin dışındadır.

Süitte kalıcı korumalar: `test_no_mock_in_production.py` (production'da mock yasağı,
AST-bazlı; dedektör canlılık kanıtı içerir), `test_consolidation_faz1_5.py`
(default-kapı sözleşmesi + beyan→kurulu zinciri).

## Deneysel OSINT kapıları (FAZ 1-5)
- `ENABLE_MAIGRET` / `ENABLE_HOLEHE` / `ENABLE_CRAWL4AI` — **default KAPALI**;
  kapalıyken davranış değişmez (uçlar dürüst `disabled` döner). Ayrıntılı alt
  değişkenler `.env.example`'da; kurulum ikinci adım dosyası:
  `pip install -r requirements-osint.txt` (crawl4ai; psutil meta-çatışması).
- `STEALTH_PROVIDER=playwright_stealth|invisible|cloak|none` — seçici kapı DEĞİL:
  default bugünkü davranış. invisible/cloak binary İNDİRMEZ; `INVISIBLE_BROWSER_BINARY`
  / `CLOAK_BROWSER_EXECUTABLE` yolu gösterilmezse dürüst `binary_missing` döner
  (`GET /api/experimental/stealth` ile sorgulanır).
- Dürüstlük sözleşmesi: tarama kullanılamazsa `available:false` + makine-okunur
  sebep; "iz/kayıt yok" iddiası yalnız sıfır-hata taramada; mock/uydurma yasak
  (testle korunur).

Canlı LLM gate (manuel, gerçek anahtar gerektirir):
```
OPENROUTER_API_KEY=sk-or-v1-... LIVE_LLM_E2E=1 python live_llm_gate.py
```
Kriterler: `completed` + dolu evidence + kritik ajanlarda sıfır UNAVAILABLE
fallback + dolu HolisticProfile + hakem onayı (varsayılan hakem:
`openai/gpt-5.6-sol-pro`; `OPENROUTER_JUDGE_MODEL` ile ezilebilir).
Bu script 360° zincirinin gerçek LLM ile uçtan uca doğrulamasıdır.

## Yedekleme ve Geri Yükleme
```bash
# Yedek oluştur (memory/ + cache/ → tar.gz + SHA-256)
bash scripts/backup_restore.sh backup

# Yedekleri listele (SHA-256 bütünlük kontrolüyle)
bash scripts/backup_restore.sh list

# Geri yükle (restore öncesi mevcut memory/ otomatik pre-backup alınır)
bash scripts/backup_restore.sh restore backups/pineal_20260901_120000.tar.gz

# Yedek bütünlüğünü doğrula
bash scripts/backup_restore.sh verify backups/pineal_20260901_120000.tar.gz
```
Docker volume ortamında:
```bash
docker run --rm \
  -v pineal_memory:/app/memory \
  -v pineal_cache:/app/cache \
  -v "$(pwd)/backups:/app/backups" \
  pineal bash scripts/backup_restore.sh backup
```
`memory/` — görev kanıt zinciri. **Kayıp geri alınamaz.**
`cache/` — SQLite response cache. Kaybedilirse yeniden doldurulur.

## ⚠ Multi-Replica / Yatay Ölçekleme
`app.state.rooms` ve `_rate_buckets` **process-local** bellekte tutulur.
2+ instance aynı anda çalıştırılmamalıdır:
- Farklı replica'daki aynı `client_id` → ayrı room state → WebSocket kopukluğu
- Rate-limit sayaçları replica başına bağımsız → gerçek limitin N katı istek geçebilir

**İlk production release için `replicas: 1` zorunludur.**
Yatay ölçekleme: paylaşımlı session store (Redis vb.) + sticky session gerektirir.

## Production Kontrol Listesi
| # | Kontrol | Nasıl Doğrulanır |
|---|---|---|
| 1 | `/app/memory` kalıcı volume'a bağlı | Container yeniden başlatma sonrası `GET /api/tasks` aynı görevleri döndürüyor |
| 2 | `PINEAL_TOKEN` tanımlı | `PINEAL_ENV=production` ile tokensız start etmez (`PRODUCTION_AUTH_REQUIRED`) |
| 3 | `OPENROUTER_MAX_SPEND_USD` > 0 | `/health → spend_cap_unlimited: false` |
| 4 | `LIVE_LLM_E2E=1` | Aspasia gerçek yanıt veriyor; telemetride `gateway: true` |
| 5 | `PINEAL_ALLOWED_ORIGINS` explicit | Localhost dışı origin için açıkça belirt |
| 6 | Tek instance | `railway.toml → numReplicas=1` / `docker-compose → replicas: 1` |
| 7 | Yedek alındı ve doğrulandı | `bash scripts/backup_restore.sh backup && verify` |
| 8 | Chromium kurulu | `python -c "from playwright.async_api import async_playwright; print('ok')"` |
| 9 | `/health` HTTP 200 `status: ready` | `curl -sf http://localhost:8000/health \| python3 -m json.tool` |
| 10 | Canlı LLM gate geçti | `OPENROUTER_API_KEY=... LIVE_LLM_E2E=1 python live_llm_gate.py` |

## Routing zinciri: source-of-truth ve operasyon düğmeleri (MP-ROUTING / FINAL-SPEC)

<!-- ROUTING-GENERATED-START do-not-edit -->
**BU BÖLÜM OTOMATİK ÜRETİLİR — ELLE DÜZENLEMEYİN.** Kaynak: `LLMGateway.effective_routing_snapshot()` + `scripts/generate_routing_shadows.py`.

**Sıra sözleşmesi (precedence):**

1. `env_override` — `OPENROUTER_AGENT_CHAIN_<AJAN>` — açık operasyon/acil override; verildiği an o ajan için her şeyi geçersiz kılar.
2. `task_routing` — `config/task_routing.json` — config delta (fail-closed; bozuk girdi matrix'e düşer).
3. `agent_matrix` — `LLMGateway.AGENT_CHAINS` — varsayılan tablo.
4. `task_chain` — `CHAINS[task]` — kayıtlı olmayan isimler için görev fallback'i.

**Ajan↔zincir (çözünmüş, 21 ajan, override'sız baz):**

| agent | tier | chain | source |
|---|---|---|---|
| aspasia | heavy | claude-sonnet-5 → gemini-3.7-flash | agent_matrix |
| authenticity_auditor | heavy | deepseek-v4-flash → gemini-3.7-flash → claude-sonnet-5 | agent_matrix |
| autonomous_verifier | verify | claude-sonnet-5 → gemini-3.7-flash → grok-4.6 | agent_matrix |
| autonomous_verifier_extract | simple | gpt-oss-120b → laguna-s-2.1:free | agent_matrix |
| cognitive_profiler | heavy | gpt-oss-120b → gemini-3.7-flash → deepseek-v4-flash | agent_matrix |
| depth_analyst | heavy | deepseek-v4-pro → claude-sonnet-5 → gemini-3.7-flash | task_routing |
| dialogue_manager | simple | gpt-oss-120b → laguna-s-2.1:free | task_routing |
| friction_detector | heavy | claude-sonnet-5 → gemini-3.7-flash → deepseek-v4-pro | agent_matrix |
| human_behavior | heavy | gpt-oss-120b → gemini-3.7-flash | agent_matrix |
| interpreter | simple | gpt-oss-120b → laguna-s-2.1:free | task_routing |
| lilith_growth | simple | gpt-oss-120b → laguna-s-2.1:free | agent_matrix |
| mirror_truth | heavy | claude-sonnet-5 → gemini-3.7-flash | agent_matrix |
| osint_investigator | heavy | gemini-3.7-flash → grok-4.6 → deepseek-v4-pro | agent_matrix |
| passion_mapper | simple | gpt-oss-120b → laguna-s-2.1:free | agent_matrix |
| pattern_interrupt | simple | gpt-oss-120b → laguna-s-2.1:free | agent_matrix |
| pineal_juror_claude | jury | pineal-juror-claude | agent_matrix |
| pineal_juror_google | jury | pineal-juror-google | agent_matrix |
| pineal_juror_open | jury | pineal-juror-open | agent_matrix |
| resonance_synthesizer | heavy | gpt-5.6-luna → gemini-3.7-flash → claude-sonnet-5 | agent_matrix |
| shadow_executor | heavy | deepseek-v4-flash → gemini-3.7-flash | task_routing |
| vision_analyzer | vision | gemini-3.7-flash → grok-4.6 | agent_matrix |

**Tier ihlalleri (bilgilendirme, v1 — CI kırmaz, düzeltme turu bekler):**

- ⚠️ `cognitive_profiler` [heavy_without_frontier] zincirde frontier (claude/pro/grok) yok: ['openai/gpt-oss-120b', 'google/gemini-3.7-flash', 'deepseek/deepseek-v4-flash']
- ⚠️ `human_behavior` [heavy_without_frontier] zincirde frontier (claude/pro/grok) yok: ['openai/gpt-oss-120b', 'google/gemini-3.7-flash']
- ⚠️ `shadow_executor` [heavy_without_frontier] zincirde frontier (claude/pro/grok) yok: ['deepseek/deepseek-v4-flash', 'google/gemini-3.7-flash']
<!-- ROUTING-GENERATED-END -->

**Sağlayıcı merdiveni (her model için):** `agent_route_variants()` aynı modeli
doğrudan sağlayıcı API'lerinde (GROQ/CEREBRAS/NOUS/DEEPSEEK anahtarları +
provider_catalog) arar; adaylık için DÖRT kapı birden gerekir: credential var,
katalog modeli sunuyor, FINAL politikası izin veriyor (ücretli rota ancak
`PINEAL_ALLOW_PAID_ESCALATION=1`), kota EXHAUSTED değil. Sıralama
**free → indirimli → fiyatlandırılmış**; OpenRouter indirimli rota yoksa kendi
fiyatıyla birincildir. Fiyatı izlenemeyen rota spend-cap aktifken teklif
edilmez. OpenRouter santral değil havuzun üyesidir.

**Fiyat muhasebesi:** spend cap/reservasyon/settlement daima route'un
**effective** fiyatından yürür (ör. `claude-sonnet-5@nous-research` = $1.6/$8,
liste $2/$10 DEĞİL); telemetri `route_key`, `pricing_in/out`,
`list_pricing_in/out`, `discount_pct` taşır. Kanıt:
`tests/unit/test_final_spec_compliance.py::test_nous_sonnet_effective_price_and_zero_openrouter_calls`.

**Bilinçli redler (bypass yok):** provider istenen model yerine başka model
dönerse `MODEL_SUBSTITUTION_DENIED` — ic retry de zincir fallback'i de YOK;
spend-cap, paid-escalation, unknown-pricing, auth redleri merdiveni DURDURUR.
Reddin detayı (`requested → returned` model çifti) artık `call_log` kaydının
içindedir (`MODEL_SUBSTITUTION_DENIED::...`) — Aspasia denetim katmanı buradan
açıklar; ayrı bir hata kaynağı yoktur.

## 9Router Yerel Yönlendirme (Local Gateway & Canlı Rotalar — 9Router v0.5.81)
Pineal, yerel 9Router proxy'si (`http://127.0.0.1:20128/v1`, v0.5.81) ile entegredir. Tüm çağrılarda `X-9Router-Token-Saver: off` başlığı zorunludur.
Tüm combolar ve global strateji `fallback` olarak sabitlenmiştir (`comboStrategy: fallback`, `fallbackStrategy: fallback`).

### Canlı 9Router Comboları (200 OK Doğrulanmış — v0.5.81)
| Rota | Birincil Model | Yedek 1 | Yedek 2 | Açıklama |
|---|---|---|---|---|
| `pineal-deep-reasoning` | `ag/claude-sonnet-4-6` | `ag/gemini-3.8-flash` | `gemini/gemini-3.8-flash` | Ağır muhakeme (Kiro kotalı olduğu için bu hattan çıkarıldı) |
| `pineal-general-reasoning` | `ag/gemini-3.8-flash` | `gemini/gemini-3.8-flash` | `kimchi/qwen3.8-27b` | Genel davranış & bilişsel analiz (~0.72s warm) |
| `pineal-fast-extract` | `groq/openai/gpt-oss-120b` | `ag/gpt-oss-120b-medium` | `kimchi/qwen3.8-27b` | Hızlı veri/tutku çıkarımı (~0.41s) |
| `pineal-vision` | `ag/gemini-3.8-flash` | `gemini/gemini-3.8-flash` | `kimchi/qwen3.8-27b` | Görsel adli analiz (Cross-family Qwen Vision yedeği dahil) |
| `pineal-juror-google` | `ag/gemini-3.8-flash` | `gemini/gemini-3.8-flash` | — | Jüri: Google ailesi |
| `pineal-juror-claude` | `ag/claude-sonnet-4-6` | — | — | Jüri: Anthropic ailesi (Antigravity OAuth) |
| `pineal-juror-open` | `groq/openai/gpt-oss-120b` | `kimchi/qwen3.8-27b` | — | Jüri: Açık model ailesi (Groq / Qwen) |
| `pineal-claude-scarce` | `kr/claude-sonnet-4.5` | — | — | Yalnızca manuel eskalasyon (Kiro kotalı ~50 kredi/ay bütçeli) |

### Otomasyon & Preflight Sağlık Denetimi
Sistem sağlığı ve 7 rotanın canlılığı `scripts/preflight_9router.py` ile denetlenir. CI ortamında `.github/workflows/preflight.yml` ile her 6 saatte bir otomatik probe çalıştırılır.

### Pineal Ajan & Rota Eşleşmesi (UI & Runbook SoT)
- `mirror_truth`: `pineal-deep-reasoning` (yedek: `(combo)`)
- `autonomous_verifier`: `pineal-verifier-panel` (yedek: `(3 jüri)`) — *Not: `pineal-verifier-panel` Pineal içi paralel 3 jüri orkestrasyonudur (`pineal-juror-google`, `pineal-juror-claude`, `pineal-juror-open`). 9Router'da tek bir combo değildir. Üretici model Claude ise jüriden Claude çıkarılır (Claude, Claude'u onaylayamaz).*
- `human_behavior`: `pineal-general-reasoning` (yedek: `(combo)`)
- `passion_mapper`: `pineal-fast-extract` (yedek: `(combo)`)
- `friction_detector`: `pineal-general-reasoning` (yedek: `(combo)`)
- `cognitive_profiler`: `pineal-general-reasoning` (yedek: `(combo)`)
- `resonance_calc`: `local-numpy` (yedek: `—`)
- `pattern_interrupt`: `pineal-fast-extract` (yedek: `(combo)`)
- `resonance_synthesizer`: `pineal-deep-reasoning` (yedek: `(combo)`)
- `vision_analyzer`: `pineal-vision` (yedek: `(combo)`)
- `osint_investigator`: `pineal-osint-pipeline` (yedek: `(pipeline)`) — *Not: Pineal iç arama ve web kazıma orkestrasyonudur (`SearchEngine` + Tavily/SerpAPI). 9Router combo'su değildir.*
- `authenticity_auditor`: `pineal-vision` (yedek: `(forensic)`)
- `depth_analyst`: `pineal-deep-reasoning` (yedek: `(combo)`)

## Aspasia komut katmanı (ASPASIA-PROMOTION)
Aspasia merkezi doğal-dil arayüzüdür; **orchestrator değildir.** Görev
yaratma/planlama politikası değişmedi: plan = `CognitiveRouter`, yürütme =
`PinealExecutor`, yaşam döngüsü = `TaskLifecycleRegistry`, routing/kota/spend
= `LLMGateway` + `final_routing_policy`.

- **Okuma:** `agent_core/aspasia/interface.py` salt-okur denetçiler
  (`RoutingInspector`, `TelemetryReader`, `QuotaReader`, `CostReader`,
  `AgentInspector`) mevcut SoT nesnelerini okur; yeni telemetri/kota defteri
  TUTMAZ. Okunamayan alan uydurulmaz: `unknown`/`unavailable`/boş digest.
- **Yazma:** TEK kanal `AspasiaCommandGateway.submit()` → LLM niyeti
  `AspasiaIntent` (extra=forbid) olarak çıkarılır (gerçek `aspasia` dialogue
  zincirinden geçer, `capture_calls` ile `agent_id=aspasia` etiketlenir), hedef
  URL gerçek scraper host sözleşmesiyle doğrulanır, dispatch `api.py` içindeki
  `/api/initiate` ile birebir aynı akışı çağırır (rate limit, lifecycle,
  mission_tasks). Ajan listesi/model/quota niyete yazılamaz — şema reddeder.
- **Uçlar:** `POST /api/aspasia/command` (komut), `GET /api/aspasia/state`
  (salt-okur denetim görünümü). `chat()` sözleşmesi (AspasiaResponse, pin,
  image_data) geriye dönük uyumludur; DENETİM KATMANI bloğu yalnız gerçek
  içerik varsa prompt'a eklenir.
- **Amaç (goal) katmanı — TRUE CHIEF LAYER:** sozluk TEK kaynak
  `CognitiveRouter.GOAL_FOCUS`; `AspasiaIntent.goals` oradan turetilir
  (ikinci sozluk yok, drift testli). Aim akisi:
  `Aspasia goals → InitiatePayload.aspasia_goals → input_data["aspasia_goals"]
  → CognitiveRouter`. Goal yalniz KULLANICI TERCIH bacaklarini daraltir;
  `autonomous_verifier` (policy bacagi) ve kanit-kapili bacaklar (visual
  evidence -> authenticity) goal ile EKLENMEZ/SILINMEZ; kanit yoksa honest-skip
  notu. Goal yoksa/eski istemciyse plan birebir eskisi gibi.
- **Sonuc dongusu (kanonik):** `MissionResultReader` yalniz
  `CanonicalMemory.get_task_memory()` okur — yeni store yok. Terminal
  durumdaki `active_tasks` snapshot'i digest'te `BAYAT-snapshot` olarak
  etiketlenir; bozuk kanonik kayit "kurtarma gerekir" diye tasinir (sokus
  edilmez). chat promptu ayrica `SUBSTITUTION DENIED: istenen/donen` ayrintisini
  mevcut call_log'dan gosterir.
- **Frontend:** ASPASIA secili serbest metin ONCE `/api/aspasia/command`;
  `accepted && task_id` varsa gorev kartina baglanir, degilse chat fallback.
  Yapilandirilmis form (URL/ritual) bilincli olarak `/api/initiate`'te kalir:
  programatik giris Aspasia'siz olabilir, KULLANICI dogal dili olamaz.
- **Extension noktasi (simdilik YOK):** cancel/halt intent'leri —
  lifecycle.terminate'a baglanacak; bu fazda kasten yok.

## Bilinçli sınırlar
- Veritabanı yok (JSON bellek) — çoklu kullanıcı/geçmiş sorgulama gerekirse Store soyutlaması eklenecek.
- **FAZ 9 Karar B:** `rust_core/` experimental/optional'dır. CI'da bağımsız derlenip test edilir; Python ürün yoluna bağlı değildir, Docker'a paketlenmez, aktivasyon bayrağı ve ürün karar etkisi yoktur. `/health` ile `/api/telemetry` bu statüyü raporlar. Tauri masaüstü taslağı release ürünü değildir.
- Deneysel API'ler (`/api/experimental/*`) ürün sözleşmesi dışıdır.
- X (Twitter) kazıması devre dışıdır (B4). Instagram kazıması tarayıcı kurulumuna bağlıdır: manuel kurulumda ZORUNLU adım: `python -m playwright install chromium` (Docker imajı otomatik kurar).
- Docker build `playwright install chromium` adımında düşüyorsa: Dockerfile 3 deneme + 300 sn t/o ile retry eder; süreklileşirse DNS/VPN'i kontrol edin veya `.env`'e `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright` yazıp `docker compose build pineal` çalıştırın (compose bu build-arg'ı otomatik geçirir).

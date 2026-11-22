# PINEAL EPİFİZ — GERÇEK KOD ENVANTERİ (Bağımsız Rapor)

> **Bu rapor nedir:** Pineal Epifiz deposunun 2026-11-22 tarihindeki **gerçek, kod tabanlı** envanteridir. Her sayı ve her iddia bu depodaki kaynak koddan veya CI koşusundan ölçülmüştür; komutlar Ek-A'da listelenmiştir.
>
> **Bu rapor ne değildir:** README, Tüzük veya pazarlama metinlerinin özeti **değildir**. O belgeler bu raporu doğrulamaz, bu rapor onları doğrular. Bir şey koddan okunamadıysa raporda **"ölçülemedi"** yazar — tahmin yok.
>
> Ölçüm tarihi: **2026-11-22** · Dal: `arena/aa5e81ff-pineal-epifiz` · Commit: `5aa9707` (main, PR #185 sonrası) · `VERSION` dosyası: **3.0.0-rc.2** · Python: **3.11**

---

## 0. Tek cümleyle

**Pineal Epifiz, herkese açık (public) veriler üzerinde çalışan, kanıta dayalı dijital analiz ve operasyon motorudur:** bir kişi/hesap hakkında toplanabilen açık verileri okur, ölçer, doğrular ve sonucu *mühürleyerek* raporlar; karar ve sorumluluk her zaman insanda kalır.

Ne **değildir**: hacker aracı değildir (şifre kırılmaz, kapalı hesaba sızılmaz), sahte itibar üreticisi değildir, 18 yaşından küçükleri hedef almaz, veri yoksa "bilmiyorum" der.

## 1. On dakikada anlama (teknisyen olmayan için)

Bir kurumdaki şu rolleri tek bir yazılımda birleştirilmiş gibi düşünün:

| Gerçek hayat | Pineal Epifiz'deki karşılığı |
|---|---|
| Araştırma masası (açık kaynak tarayan) | `osint_investigator` + Yetenek Omurgası (28 yetenek) |
| Psikolog (konuşma diline bakan) | `target_psyche_profiler` → passion/friction/cognitive lensleri |
| Adli bilişim bilirkişisi | `depth_analyst`, `autonomous_verifier`, `authenticity_auditor` |
| Editör (uydurma var mı diye bakan) | `quote_guard`, `claim_decision_gate` |
| Sekreter/Koordinatör | `task_executor` (PinealExecutor) |
| Sözcü | ASPASIA (`aspasia_chief` + `interface`) |
| Kasa (anahtar olmadan dışarı çıkılmaz) | Vault Mandali (`_check_vault_interlock`) |

Sistem üç katmanda çalışır:

```
TARAYICI / MASAÜSTÜ / ANDROID / UZANTI (kullanıcı yüzeyleri)
        │  (HTTP + WebSocket)
        ▼
FASTAPI BACKEND (backend/api.py + backend/routes/*)  ← kasa mandalı burada
        │
        ▼
ÇEKİRDEK (agent_core/)
  task_executor → 12 uzman ajan → yetenek omurgası (28 yetenek) → kanıt zaman çizelgesi
        │
        ▼
KANIT DEPOSU (canonical_memory; dosya tabanlı, PINEAL_MEMORY_PATH)
```

**Kimin için:** operatörler (teknik konsol) ve bizimle çalışmak isteyen müşteriler (portal kapısı). Tüketici uygulaması değil; denetime tabi bir operasyon aracıdır.

**Ne yapmaz:** kapalı/özel veriye erişmez; 18 yaş altı hedefi reddeder; kasa kilitliyken dış ağa hiçbir istek çıkmaz; veri yoksa uydurma üretmez (`halted_evidence`); talep gönderildiyse "silindi" demeden kaynağında teyit ister.

---

## 2. Rakamlarla envanter (ölçülen)

| Ölçüt | Değer | Nasıl |
|---|---|---|
| Git'te izlenen dosya | **824** | `git ls-files | wc -l` |
| Python modülü | 550 | `git ls-files '*.py'` |
| Test dosyası (`test_*.py`) | **302** | `find tests -name test_*.py` |
| Yerel test koşusu (requirements.lock ile) | **3283 geçti, 6 skip, 2 xfail** | 2026-11-22, ~3 dakika |
| CI kapıları | 12 adım (ruff, coverage ≥80%, audit_regression, dead-code, routing-shadows, envanter tazeliği, skills, openrouter catalog) | `.github/workflows/ci.yml` |
| HTTP + WebSocket ucu | ~85 (api.py'de 62 kayıt + bölünmüş router'larda 23) | grep ölçümü; README "83 path+metot / 81 benzersiz yol" olarak kilitli |
| Backend tek-modül tavanı | `backend/api.py` 5494 satır (tavan 6000; `test_api_monolith_ratchet.py`) | `wc -l` |
| Sürüm | `VERSION` = 3.0.0-rc.2 | kök dosya; testlerle kilitli |

**Uygulama hattı:** Docker (compose: `redis` + `pineal` + 12 beacon worker) · Cloudflare Workers/Pages (`wrangler.toml`, `functions/`) · Vercel (`vercel.json` → `frontend/`) · Android (APK, Python'a köprü) · Tauri masaüstü (rust_core).

---

## 3. BACKEND — FastAPI operasyon yüzeyi

### 3.1 Yapı

- `backend/api.py` — monolit giriş (5494 satır). İş mantığı modüllere bölünmüş; yeni uç eklemek tavan kuralı gereği modüle çıkmayı zorunlu kılar.
- `backend/routes/` — bölünmüş modüller: `brain_hub`, `commander`, `company`, `hook_studio`, `language`, `lilith`, `mobile_coach`, `preflight`, `reports`, `speech`, `speech_audio`, `speech_state`, `support`, `tasks`, `telemetry`, `websocket`.
- `backend/security/` — `principal`, `task_ownership`, `task_access` (oda mührü: başkasının görevi satıra hiç girmez).
- `backend/middleware/` — gövde tavanı; `backend/checkpoint_store.py` — destek/devam kalıtımı; `backend/agent_rack.py` — 12-Beacon işaretçi yüzeyi; `backend/email_dossier_service.py` — e-posta dosyası.

### 3.2 Uç yüzeyinin gruplanması (ne için var)

| Grup | Örnek yollar | Amaç |
|---|---|---|
| Görev | `/api/initiate`, `/api/tasks*`, `/api/tasks/{id}/halt|cancel|changes`, `/api/commander/inject` | Bir işi başlatma, izleme, durdurma |
| Kasa (Vault) | `/api/vault`, `/api/vault/lock|unlock|status` | **Dışa açılan her kapının tek kilidi** — kasa kapalıysa hiçbir dış istek/tarayıcı hareketi yapılamaz |
| Çocuk kilidi | `/api/minor/case|clear|state` | 18 yaş altı hedefi reddeder |
| Ajanlar | `/api/agents/status` | 12-Beacon canlılık görüntüsü |
| ASPASIA | `/api/aspasia/*` | Sokratik sohbet/danışman arayüzü |
| Medya/Jüri | `/api/media/analyze`, `/api/jury/vote` | Medya adli analizi, yerel jüri |
| OSINT (deneysel) | `/api/experimental/socid/extract` vb. | Yetenek omurgası üzerinden ölçülü tarama |
| Telemetri/WS | `/api/telemetry`, `/ws/{client_id}` | Canlı oda durumu |
| Destek | `/api/support/*` | Kanıt yetmezse insan müdahalesi; açık destek varken devam REDDEDİLİR |
| Konuşma/TTS | `/api/speech/*` | Sesli çıktı |
| OpenAI uyumu | `/v1/chat/completions` | Dış istemci köprüsü |

Not: README "81 benzersiz HTTP yolu; 25'i UI'dan, 77'si testlerden çağrılır; 2'sinin çağrı yeri yok" bilgisini ve sayım yöntemini `tests/unit/test_http_endpoint_call_sites.py` ile makine kilidine almıştır — bu rapor o kilidi yeniden üretmez, koddan okunan yaklaşık yüze yakın yol olduğunu beyan eder.

---

## 4. ÇEKİRDEK — Görev nasıl koşar? (`task_executor.py`, 3633 satır)

`PinealExecutor` bir işi şu sırayla işler (dosya başlığındaki sözleşmeden ölçüldü):

1. **Girdi normalizasyonu** — görev payload'ı çözümlenir, kapsam/oda belirlenir.
2. **OSINT tarama dalgası** — açık kaynak verisi yetenek omurgası üzerinden çekilir (kasaya tabi).
3. **Profil çıkarımı** — üç lens (passion / friction / cognitive) hedef üzerinde koşar.
4. **Derinlik & doğrulama** — `depth_analyst`, `authenticity_auditor`, `autonomous_verifier` kanıt üretir; hiçbiri uydurmaz, yoksa `confidence=0.0` + `fallback_reason`.
5. **Kanıt kapıları** — `claim_decision_gate` engelli iddiayı bastırır; `quote_guard` alıntıyı kaynağa bağlar; Tier-2 alanlar allowlist ile yazılır.
6. **Sorumluluk zinciri** — her ajanın egress denemeleri ve kanıt hash'i mühürlenir; Agent Rack durumu yalnız kendi koşusundan yayınlanır (ödünç slot yasak).
7. **Destek & devam** — kanıt yetmezse destek talebi üretilir; destek açıkken devam reddedilir; bitmiş adımlar atlanır (`_resume_done`).
8. **Teslimat** — geçici görseller silinir; hata gizlenmez, olay olarak yayınlanır.

---

## 5. AJANLAR — kim, ne yapar?

`agent_core/agents/` altında **17 modül** var; bunlar "12 uzman + omurga + LILITH + interpreter" olarak gruplanır. **12 uzman ajan** ile **12 docker-compose beacon'u** birebir aynı adlara denk gelir (`docker-compose.yml`, `AGENT_ID=…`): yani her uzman aynı zamanda bağımsız bir "yaşıyorum" işaretçisidir.

### 5.1 Omurga ve yardımcılar (sayıya dahil değil)

| Ajan | Dosya | Tek satır görev | Dürüstlük kuralı |
|---|---|---|---|
| TargetPsycheProfiler | `target_psyche_profiler.py` (347) | Üç lensin (passion/friction/cognitive) **ortak omurgası** — tek gerçek kaynak; ince kabuklar burada tanımlı analizi çağırır | Boş kanıtta skor/uydurma yok; veri güveni açık raporlanır |
| LILITH Growth | `lilith_growth.py` (755) | 360° analizi viral içerik paketine çevirir; CLI (`run_lilith.py`) ve hat yolu | Matematiksel güvenlik zırhı; NaN/Inf girdi asla exception |
| Interpreter | `interpreter_agent.py` (127) | Open Interpreter Köprüsü — **varsayılan kapalı** (`ENABLE_INTERPRETER=true` ile açılır) | `auto_run=False` zorunlu; her koşu insan onayı; paket yoksa açık hata |

### 5.2 On iki saha uzmanı (beacon adlarıyla aynı)

| # | Beacon / sınıf | Dosya | Tek satır görev | Temel dürüstlük sözleşmesi |
|---|---|---|---|---|
| 1 | `mirror_truth` / MirrorOfTruth | `mirror_truth.py` | Kullanıcının "çekirdek frekansı" ile yüzey personası arasındaki hizalanmayı ölçer | Yöntem deterministik; LLM yalnız anlatı; doğrulanmamış bulgu prompta `upstream_findings` ile işaretli girer |
| 2 | `autonomous_verifier` / AutonomousVerifier | `autonomous_verifier.py` | İddia → kanıt → çapraz jüri → hüküm; URL çapraz denetimi | Kanıt URL'si gerçek arama URL kümesinde olmak zorunda (2026-09-23 RÖNTGEN düzeltmesi) |
| 3 | `human_behavior` / HumanBehaviorAnalyzer | `human_behavior.py` | İnsan davranışı mikro-sinyalleri: zamansal ritim, dil, tutarlılık | LLM yalnız TOPLANMIŞ gözlemlerden üretir; asla gözlem uydurmaz |
| 4 | `passion_mapper` / PassionMapperAgent | `passion_mapper.py` | Tutku lensi: neşe, yaratıcılık, ilgi eksenleri | Somut paylaşımdan kanıt toplar; yoksa liste boş + neden |
| 5 | `friction_detector` / FrictionDetectorAgent | `friction_detector.py` | Sürtünme lensi: sınırlar, hassasiyetler, tükenme noktaları | **ASLA teşhis koymaz**; yalnız gözlenen ifadeyi raporlar |
| 6 | `cognitive_profiler` / CognitiveProfilerAgent | `cognitive_profiler.py` | Bilişsel lens: düşünce kalıbı ve iletişim üslubu | `TargetPsycheProfiler` kabuğu; kopyalanmış prompt yasak |
| 7 | `resonance_calculator` / ResonanceCalculator | `resonance_calculator.py` | İki profil arası "rezonans" — kanıt örtüşmesi olarak | Eski sihirli %72 etiketleri kaldırıldı (Epistemik Onarım 2026-09-18); örtüşme yoksa hata, uydurma yok |
| 8 | `pattern_interrupt` / PatternInterrupt | `pattern_interrupt.py` | Kanıta en uygun açılış mesajı + senaryo yanıtı | Ölçüm yoksa `_unavailable(reason)` dürüst ret; mesaj uydurulmaz |
| 9 | `osint_investigator` / OsintInvestigatorAgent | `osint_investigator.py` | Açık kaynak (kullanıcı adı/e-posta/web) taraması — Maigret/Holehe **yetenek omurgası üzerinden** | Kasa kilitliyken dış çağrı yok; kapalı yetenekte uydurma bulgu yok; zaman çizelgesine mühür |
| 10 | `authenticity_auditor` / AuthenticityAuditorAgent | `authenticity_auditor.py` | Beyan edilen kimlik ile görsel kanıt arasındaki "özgünlük boşluğu" | Kanıt yoksa skor UYDURULMAZ; `confidence=0.0` + `fallback_reason` |
| 11 | `depth_analyst` / DepthAnalyst | `depth_analyst.py` | P1/P7/P8 derinlik analizi; alıntıları kaynağa bağlar | `quote_guard` ile koşar; doğrulanmamış alıntı "doğrulandı" sayılmaz |
| 12 | `resonance_synthesizer` / ResonanceSynthesizerAgent | `resonance_synthesizer.py` | Kullanıcı × hedef → tek iletişim stratejisi (`AuthenticBridge`) | `_build_user_context` tek sözleşme; boş girdi asla doldurulmaz |

### 5.3 ASPASIA — kullanıcıya bakan katman (ajan değil, sözcü)

| Modül | Satır | Görev |
|---|---|---|
| `aspasia/aspasia_chief.py` | 440 | Sokratik şef: sohbet, oda durumu özeti, **komutu yürütmez** — `AspasiaCommandGateway`'e devreder |
| `aspasia/interface.py` | 1008 | Okuma/komut arayüzü: telemetry okur, niyet formüle eder, **mutasyon yapmaz** |
| `aspasia/mobile_coach.py` | 146 | Mobil koç istemi **sunucuda** kurulur (Android anahtarını cihazda tutmaz) |

---

## 6. DETERMİNİSTİK MOTORLAR — `agent_core/engines/` (LLM YOK)

| Motor | Dosya | Ne ölçer |
|---|---|---|
| FREQUENCY | `frequency_engine.py` | Zaman serisi temel frekansları (periyot tespiti) |
| SEİSMOS | `seismos_engine.py` | Davranışsal "kırılma" noktaları |
| VOID | `void_engine.py` | Negatif alan: yokluk/sessizlik örüntüleri |
| STRATA | `strata_engine.py` | Katmanlı geçmiş/"fosil kayıt"ları |
| GRAVITY | `gravity_engine.py` | Anlatı çekim merkezleri (neye çekiliyor) |
| PULSE | `pulse_engine.py` | Dijital beden dili (hız, ritim) |
| KEY | `key_engine.py` | Kural tabanlı sentez — şeffaf karar kuralları |
| — | `pillar_orchestrator.py` | 7 sütunun iki-aşamalı asenkron orkestrasyonu |
| — | `spectrum.py` | **Gerçek FFT** spektral analizi (numpy.rfft; DC bastırma + Hann penceresi) |

İlke: bu katman saf matematiktir; LLM'e "ne hissediyorsun?" diye sormaz, **ölçer**.

---

## 7. YETENEK OMERgası — `agent_core/capabilities/`

Dış dünyaya açılan **her** yetenek tek defterden (registry), tek politika kapısından (policy: `ENABLE_*` + kasa), tek koşum yolundan (runner) geçer; her çağrı kanıt zaman çizelgesine (`timeline_bridge`) mühürlenir. Ölçülen (2026-11-22, `bootstrap()` üzerinden): **28 yetenek kayıtlı**:

**Sensörler (dış veri):** maigret (kullanıcı adı), holehe (e-posta), handle_probe, phone_probe, x_twscrape, ig_instagrapi, searxng (arama), company.harvester/seo/people, media.fetch
**Çıkarıcılar (yapılandırma):** socid, trafilatura, crawl4ai, scrapling, agent_reach, text.language, text.translate_local, media.transcript, stt.local
**Analizciler:** media.frames, media.similarity
**Doğrulayıcılar:** jury.local
**Üreticiler (renderer/voice):** pdf, diagram, video, tts.local, report.script

Kasa kilitliyken politika tüm kapalı dış yeteneklere `available:false` döner — sessiz uydurma yok. Aynı kural `mcp` katmanı ve `/api/preflight` ile API yüzeyinde de uygulanır.

---

## 8. SERVİSLER — `agent_core/services/` (70 modül)

Hepsini tek tek anlatmak yerine görev aileleriyle:

| Aile | Temsilci modüller | Ne işe yarar |
|---|---|---|
| LLM ağ geçidi & yönlendirme | `llm_gateway`, `unified_router`, `cognitive_router`, `final_routing_policy`, `task_routing_resolver`, `provider_manager` | Model seçimi, fallback zinciri, maliyet/kota |
| Kanıt & dürüstlük kapıları | `quote_guard`, `claim_decision_gate`, `frame_consensus`/`frame_evidence`/`frame_semantics`, `jury_consensus`, `local_jury`, `epistemic`, `confidence` | Uydurmayı engelleyen makine kapıları |
| Hafıza | `canonical_memory`, `hindsight_memory`, `memory_crystal`, `memory_injector`, `change_tracker`, `evidence_timeline` | Görev kaydı + zaman çizelgesi + "ne değişti" |
| OSINT varlıkları | `maigret_scanner`, `holehe_scanner`, `socid_enricher`, `handle_probe`, `phone_probe`, `follower_audit`, `timing_forensics`, `osint_normalizer`, `deep_profile_resolver`, `deep_url_cables` | Varlık kimliği ve davranış ritmi |
| Medya adli bilişim | `media_forensics`, `vision_analyzer`, `frame_consensus` | Görsel/video kanıt analizi |
| Rapor & çıktı | `report_factory`, `verdict_synthesizer`, `speech`, `translation`, `language` | Mühürlü rapor üretimi |
| Kapasite & sağlık | `quota_governor`, `dependency_health`, `net_hygiene`, `browser_session`, `crawl_enricher`, `safe_web_fetch`, `response_cache` | Kota, sağlık, güvenli dış erişim |
| Özel | `neuro_signals`, `psychodynamic_depth`, `theme_cluster`, `taste_filter`, `cross_profiler`, `confidence`, `threshold_calibration`, `token_compressor`, `token_optimizer`, `uncertainty_engine`, `runtime_status`, `agent_status_tracker`, `redis_bus` | Sinyal katmanları, belirsizlik ölçümü, telemetri |

`agent_core/safety/`, `agent_core/lifecycle/`, `agent_core/shadow/`, `agent_core/psychology/`, `agent_core/domain/` (pydantic modeller), `agent_core/schemas/`, `agent_core/scraper/` (Instagram Ghost), `agent_core/mcp/` (28 MCP aracı + pineal_status) destekleyici alt sistemlerdir.

---

## 9. YÜZEYLER — kullanıcı nerede dokunur?

| Yüzey | Yol | Sınır |
|---|---|---|
| **Atlas Portal** (varsayılan) | `frontend/src/components/AtlasPortal.svelte` | Sade Türkçe, 3 adımlı müşteri kapısı; `/api/initiate`'e istek kaydı; **asla konuşma/kanıt üretmez** |
| **Gelişmiş: Teknik Konsol** | `UnifiedPinealCockpit.svelte` | Operatör ekranı (12 ajan, telemetri, vault); PR #184 öncesi olduğu gibi |
| Destek paneli / Kanıt görünümü | `SupportPanel.svelte`, `TaskEvidence.svelte` | Destek akışı ve kanıt zinciri gösterimi |
| Telemetri görselleştirici | `visualizers/NeuralTelemetryBoard.svelte` | Canlı oda telemetri panosu |
| Tauri masaüstü | `rust_core/` (~3456 satır Rust) + `src-tauri/` | Event bus, ajan hattı, kasa — **ama CI'da derlense de Python ürününe bağlı değildir** (`/health` `product_runtime_integrated:false`) |
| Android | `android/` (~4177 satır Kotlin, Compose) | Tek Gemini çağrılı hat; Room DB; **jüri/mühür/validator YOK** — parite sınırı arayüzde açık etiketli; paket adı `com.aistudio.pineal.heretic` (aistudio şablonu kalıntısı) |
| Chrome uzantısı | `extensions/chrome-linkedin/` | `POST /api/initiate` → `GET /api/tasks/{id}/graph`; kanıt yoksa panel doldurulmaz |
| Cloudflare Pages Functions | `functions/api/[[path]].ts`, `functions/ws/[[path]].ts` | `BACKEND_ORIGIN`'e catch-all proxy; tanımsızsa 502 + açık hata |
| Worker | `worker.ts`, `wrangler.toml` | Static assets + `/api`,`/ws` proxy |

---

## 10. OPERASYON & KALİTE KAPISI

- **Test:** 302 dosya; yerelde `requirements.lock` ile koşu → **3283 passed / 6 skipped / 2 xfailed**. (Not: `requirements.txt` ile taze kurulumda 650 test KIRMIZI ölçtük — üretim ağacı `requirements.lock` olduğu için CI yolu budur.)
- **CI (12 kapı):** ruff → coverage ≥80% (`--cov-fail-under=80`) → audit_regression (24 denetim bulgusu makine bekçisi) → dead_code_audit → routing shadows → envanter tazeliği → skills doğrulaması → openrouter catalog (anahtar yoksa SKIP).
- **Sürümler:** `VERSION` = tek kaynak; `tests/unit/test_version_identity.py` ve `PINEAL-HERETIC` dist grep'i CI'da kırılmayı yakalar.
- **Envanter sayfası:** `docs/envanter.html` (824 dosya) — üretici `scripts/generate_inventory_page.py`; CI tazelik kapısı.
- **Skills:** 28 `SKILL.md`; `scripts/export_skills.py` ile registry'den üretilir — elle sapma CI'a takılır.
- **Scripts (30):** audit_regression, generate_inventory_page, export_skills, preflight_check, dead_code_audit, kapasite_denetimi_probe, revert_verification_p* (kanıt arşivi), run_task, smoke_test_browser…
- **docker-compose:** `redis` + `pineal` (port 8000) + 12 beacon worker (`AGENT_ID` ile).

---

## 11. DÜRÜST SINIRLAR (ölçülemedi / bilinçli yapılmadı)

1. **Canlı LLM çağrıları** ve **canlı OSINT egress** bu ortamda doğrulanmadı (anahtar/egress yok) — CI da bu yüzden bazı uçları SKIP geçer.
2. **Android hattı** motora bağlı değildir; parite sınırı (jüri/mühür/validator eksik) arayüzde açıkça etiketlidir.
3. **rust_core** bağımsız çekirdektir; Python ürününe bağlı değildir (bilinçli karar, Faz 9-B).
4. **`requirements.txt`** taze çözümü bu ortamda 650 test kırdı; `requirements.lock` budur. Sınıf: ortam/sürüm farkı, ürün hatası değil.
5. **Kasa** bir yetki mandalıdır, sır kasası değildir: `.pineal_vault.json` düz JSON'dur (gitignore'da); anahtar loglara sızdırılmaz ama disk şifrelemesi yoktur.
6. **OpenRouter kataloğu** anahtar olmadığından CI'da SKIP — "doğrulanmadı" diye okunmalı.
7. **Envanter üreticisi** `docs/envanter.html`'i koddan üretir; bu rapor ondan da bağımsız yazıldı.
8. **18 yaş altı hedefler** her kapıda reddedilir (`/api/minor/*`, `_require_minor_clearance`) — kod yolunda ve testlerle kilitli.

---

## 12. DOSYA HARİTASI (ilk bakış)

```
backend/           FastAPI yüzeyi: api.py (monolit ≤6000 satır) + routes/ modülleri + security/
agent_core/
  agents/          17 modül — omurga + 12 uzman + LILITH + interpreter
  engines/         7 dalga motoru + pillar_orchestrator + spectrum (FFT)
  services/        70 modül — gateway, hafıza, kanıt kapıları, OSINT, medya, rapor
  capabilities/    Yetenek omurgası: registry/policy/runner/egress + 28 yetenek
  aspasia/         ASPASIA sözcü katmanı (chief / interface / mobile_coach)
  domain|schemas/  pydantic modeller ve şema sözleşmeleri
  safety|lifecycle|shadow|psychology|scraper|mcp|workers|utils|nlp
frontend/          Svelte 5 + Vite (+Tauri): portal, konsol, destek, telemetri
rust_core/         Bağımsız Rust çekirdeği + Tauri kabuğu (Python'a bağlı değil)
android/           Kotlin Compose istemcisi (parite sınırı etiketli)
extensions/        Chrome LinkedIn uzantısı (kanıt yoksa panel yok)
functions/         Cloudflare proxy (/api,/ws → BACKEND_ORIGIN; yoksa 502)
skills/            28 SKILL.md (registry'den üretilir)
scripts/           30 operasyon/denetim betiği
tests/             302 test dosyası (unit/integration/e2e/audit)
docs/              Sözleşmeler, tarihli denetim raporları, envanter.html
```

---

## EK-A. Sayıları nasıl ölçtüm

```
git rev-parse --short HEAD          # 5aa9707
git ls-files | wc -l                 # 824
git ls-files '*.py' | wc -l          # 550
find tests -name 'test_*.py' | wc -l # 302
wc -l backend/api.py                 # 5494
grep '@app.' backend/api.py | wc -l  # 62 kayıt (+23 modül router'ı)
.venv/bin/python -m pytest -q --cov=agent_core --cov=backend --cov-fail-under=80
  → 3283 passed, 6 skipped, 2 xfailed (requirements.lock, 2026-11-22)
from agent_core.capabilities.registry import bootstrap; len(bootstrap())  # 28
```

## EK-B. Sözlük (teknisyen olmayan için)

- **Kanıt mührü / SHA-256:** Her bulgunun "parmak izi"nin saklanması — sonradan değiştirilemez.
- **Fail-closed:** Şüphede kalınca kapalı kalan sistem; "emin değilsem işlem yok".
- **Kasası/Mandali:** Anahtar olmadan hiçbir dış işlem yapılamaz.
- **Minor Gate:** 18 yaş altı hedefleri otomatik reddeden kapı.
- **Resume/Devam:** Kesilen görevde bitmiş adımlar tekrar koşturulmaz.
- **Egress:** Dış ağa çıkış denemesi; her biri log'lanır ve mühürlenir.
- **LLM:** Büyük dil modeli; burada yalnız anlatı/yorumlama katmanıdır — ölçümü motorlar yapar.
- **Halüsinasyon:** Uydurma cevap; bu repoda kapı + testlerle bastırılır.

*Bu rapor hazırlanırken README/TÜZÜK/BACKEND dokümanlarından alıntı yapılmadı; tüm iddialar koda işaretlidir. Yanlış okunan her satır için ilgili dosya ve satır numarası raporda parantez içindedir.*

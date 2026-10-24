# GÖLGE DENETİMİ — hiçbir şey gölgede kalmasın

> Bu dosya `scripts/golge_denetimi.py` tarafından ÜRETİLİR. Elle yazılmış sayı yoktur;
> yeniden çalıştırıldığında depo neyse rapor odur.

- Ölçüm anı: 2026-10-24T00:13:04Z · Python 3.11.2 · platform `linux`
- **Kritik uyarı:** `dependency_missing` / `no_engine` gibi sebepler ÖLÇÜLDÜĞÜ MAKİNEYE bağlıdır.
  Bu raporu kendi ortamınızda üretmek için: `python scripts/golge_denetimi.py`.

## 1 · Yetenek defteri

- Defterde **27** yetenek var; bu ortamda **3** tanesi kullanılabilir.

- Uyanma sınıfı: **3** hazır, **7** yalnız kapı kapalı olduğu için duruyor, **17** kapı açılsa da kurulum/hesap/uç istiyor.

| Yetenek | Tür | Kapılar | Şimdi | Kapılar açıkken | Sebep (kapılar açıkken) |
| --- | --- | --- | --- | --- | --- |
| `analyzer.media.frames` | ANALYZER | ENABLE_MEDIA_FORENSICS | KAPALI | AÇIK | — |
| `analyzer.media.similarity` | ANALYZER | ENABLE_MEDIA_FORENSICS | KAPALI | AÇIK | — |
| `extractor.identity.socid` | EXTRACTOR | — | KAPALI | KAPALI | dependency_missing:socid_extractor |
| `extractor.media.transcript` | EXTRACTOR | ENABLE_MEDIA_FORENSICS | KAPALI | KAPALI | no_engine |
| `extractor.text.language` | EXTRACTOR | — | AÇIK | AÇIK | — |
| `extractor.text.translate_local` | EXTRACTOR | ENABLE_LOCAL_TRANSLATE | KAPALI | KAPALI | no_engine |
| `extractor.web.crawl4ai` | EXTRACTOR | ENABLE_CRAWL4AI | KAPALI | KAPALI | dependency_missing:crawl4ai |
| `extractor.web.scrapling` | EXTRACTOR | ENABLE_SCRAPLING | KAPALI | KAPALI | dependency_missing:scrapling |
| `extractor.web.trafilatura` | EXTRACTOR | — | KAPALI | KAPALI | dependency_missing:trafilatura |
| `renderer.report.diagram` | RENDERER | ENABLE_REPORT_FACTORY | KAPALI | AÇIK | — |
| `renderer.report.pdf` | RENDERER | ENABLE_REPORT_FACTORY | KAPALI | AÇIK | — |
| `renderer.report.video` | RENDERER | ENABLE_REPORT_FACTORY | KAPALI | KAPALI | dependency_missing:ffmpeg |
| `sensor.company.harvester` | SENSOR | ENABLE_COMPANY_TARGETING | KAPALI | KAPALI | dependency_missing:theHarvester |
| `sensor.company.people` | SENSOR | ENABLE_COMPANY_TARGETING | KAPALI | AÇIK | — |
| `sensor.company.seo` | SENSOR | ENABLE_COMPANY_TARGETING | KAPALI | AÇIK | — |
| `sensor.identity.handle_probe` | SENSOR | ENABLE_CROSS_PLATFORM | AÇIK | AÇIK | — |
| `sensor.identity.holehe` | SENSOR | ENABLE_HOLEHE | KAPALI | KAPALI | dependency_missing:holehe |
| `sensor.identity.maigret` | SENSOR | ENABLE_MAIGRET | KAPALI | KAPALI | dependency_missing:maigret |
| `sensor.ig.instagrapi` | SENSOR | ENABLE_IG_SECONDARY | KAPALI | KAPALI | dependency_missing:instagrapi |
| `sensor.media.fetch` | SENSOR | ENABLE_MEDIA_FORENSICS | KAPALI | AÇIK | — |
| `sensor.search.searxng` | SENSOR | ENABLE_SEARXNG | KAPALI | KAPALI | config_missing:SEARXNG_BASE_URL |
| `sensor.web.agent_reach` | EXTRACTOR | ENABLE_AGENT_REACH | KAPALI | KAPALI | dependency_missing:agent-reach |
| `sensor.x.twscrape` | SENSOR | ENABLE_X_SENSOR | KAPALI | KAPALI | dependency_missing:twscrape |
| `verifier.jury.local` | VERIFIER | ENABLE_LOCAL_JURY | KAPALI | KAPALI | no_local_models |
| `voice.report.script` | RENDERER | — | AÇIK | AÇIK | — |
| `voice.stt.local` | EXTRACTOR | ENABLE_LOCAL_STT | KAPALI | KAPALI | no_local_endpoint |
| `voice.tts.local` | RENDERER | ENABLE_LOCAL_TTS | KAPALI | KAPALI | no_local_endpoint |

## 2 · Zincir: yetenek → backend → SKILL → arayüz

| Yetenek | HTTP ucu | Hatta çağıran | MCP aracı | SKILL.md | Arayüz tetikliyor |
| --- | --- | --- | --- | --- | --- |
| `analyzer.media.frames` | `GET /api/media/status`<br>`POST /api/media/analyze` | **yok** | var | var | **hayır** |
| `analyzer.media.similarity` | `GET /api/media/status`<br>`POST /api/media/analyze` | **yok** | var | var | **hayır** |
| `extractor.identity.socid` | `POST /api/experimental/socid/extract` | 4 dosya | var | var | **hayır** |
| `extractor.media.transcript` | `GET /api/media/status`<br>`POST /api/media/analyze` | **yok** | var | var | **hayır** |
| `extractor.text.language` | `GET /api/language/status`<br>`POST /api/language/detect`<br>`POST /api/language/translate` | **yok** | var | var | **hayır** |
| `extractor.text.translate_local` | `POST /api/language/translate` | **yok** | var | var | **hayır** |
| `extractor.web.crawl4ai` | **uç yok** | **yok** | var | var | **hayır** |
| `extractor.web.scrapling` | **uç yok** | **yok** | var | var | **hayır** |
| `extractor.web.trafilatura` | **uç yok** | **yok** | var | var | **hayır** |
| `renderer.report.diagram` | `GET /api/report/status`<br>`POST /api/report/build` | **yok** | var | var | **hayır** |
| `renderer.report.pdf` | `GET /api/report/status`<br>`POST /api/report/build` | **yok** | var | var | **hayır** |
| `renderer.report.video` | `GET /api/report/status`<br>`POST /api/report/build` | **yok** | var | var | **hayır** |
| `sensor.company.harvester` | `GET /api/company/status`<br>`POST /api/company/scan` | **yok** | var | var | **hayır** |
| `sensor.company.people` | `GET /api/company/status`<br>`POST /api/company/scan` | **yok** | var | var | **hayır** |
| `sensor.company.seo` | `GET /api/company/status`<br>`POST /api/company/scan` | **yok** | var | var | **hayır** |
| `sensor.identity.handle_probe` | **uç yok** | 1 dosya | var | var | **hayır** |
| `sensor.identity.holehe` | `POST /api/experimental/holehe/scan` | 2 dosya | var | var | **hayır** |
| `sensor.identity.maigret` | `POST /api/experimental/maigret/scan` | 3 dosya | var | var | **hayır** |
| `sensor.ig.instagrapi` | **uç yok** | 3 dosya | var | var | **hayır** |
| `sensor.media.fetch` | `POST /api/experimental/crawl/fetch`<br>`GET /api/media/status`<br>`POST /api/media/analyze` | **yok** | var | var | **hayır** |
| `sensor.search.searxng` | **uç yok** | 1 dosya | var | var | **hayır** |
| `sensor.web.agent_reach` | **uç yok** | 1 dosya | var | var | **hayır** |
| `sensor.x.twscrape` | **uç yok** | 3 dosya | var | var | **hayır** |
| `verifier.jury.local` | `GET /api/jury/status`<br>`POST /api/jury/vote` | **yok** | var | var | **hayır** |
| `voice.report.script` | **uç yok** | 1 dosya | var | var | **hayır** |
| `voice.stt.local` | **uç yok** | 1 dosya | var | var | **hayır** |
| `voice.tts.local` | **uç yok** | 1 dosya | var | var | **hayır** |

## 3 · Ajanlar

- Yürütücüye kayıtlı: **13** — `authenticity_auditor`, `autonomous_verifier`, `cognitive_profiler`, `depth_analyst`, `friction_detector`, `human_behavior`, `mirror_truth`, `osint_investigator`, `passion_mapper`, `pattern_interrupt`, `resonance_calc`, `resonance_synthesizer`, `shadow_executor`
- Kapı arkasında kayıtlı: `interpreter`

| Modül | Sınıf(lar) | Yürütücü anahtarı | Rack slotu | Router'da | Arayüzde | Test |
| --- | --- | --- | --- | --- | --- | --- |
| `agent_core/agents/authenticity_auditor.py` | AuthenticityProfile, AuthenticityAuditorAgent | `authenticity_auditor` | authenticity_auditor | evet | evet | evet |
| `agent_core/agents/autonomous_verifier.py` | Claim, VerificationResult, CanonicalObservationCheck, VerifierReport, AutonomousVerifier | `autonomous_verifier` | autonomous_verifier | evet | evet | evet |
| `agent_core/agents/cognitive_profiler.py` | CognitiveProfilerAgent | `cognitive_profiler` | cognitive_profiler | evet | evet | evet |
| `agent_core/agents/depth_analyst.py` | DepthFinding, DepthReport, DepthAnalyst | `depth_analyst` | depth_analyst | hayır | evet | evet |
| `agent_core/agents/friction_detector.py` | FrictionDetectorAgent | `friction_detector` | friction_detector | evet | evet | evet |
| `agent_core/agents/human_behavior.py` | HumanBehaviorPayload, MicroSignal, DigitalColdReading, HumanBehaviorAnalyzer | `human_behavior` | human_behavior | evet | evet | evet |
| `agent_core/agents/interpreter_agent.py` | InterpreterResult, InterpreterAgent | **bağlı değil** (kapı arkasında) | — | hayır | hayır | evet |
| `agent_core/agents/lilith_growth.py` | NeurochemicalProfile, NeuroMetrics, LilithGenerationResponse, LilithContentPackage, _ChatMessage, _ChatChoice, _ChatResponse, FreeTextGateway, OpenAICompatibleGateway, LilithGrowthAgent | **bağlı değil** | — | hayır | hayır | evet |
| `agent_core/agents/mirror_truth.py` | MirrorReflection, MirrorOfTruth | `mirror_truth` | mirror_truth | evet | evet | evet |
| `agent_core/agents/osint_investigator.py` | OsintProfile, OsintInvestigatorAgent | `osint_investigator` | osint_investigator | hayır | evet | evet |
| `agent_core/agents/passion_mapper.py` | PassionMapperAgent | `passion_mapper` | passion_mapper | evet | evet | evet |
| `agent_core/agents/pattern_interrupt.py` | ScenarioResponse, GeneratedMessage, PatternInterrupt | `pattern_interrupt` | pattern_interrupt | evet | evet | evet |
| `agent_core/agents/resonance_calculator.py` | ResonanceCalculationError, EvidenceOverlap, ResonanceProfile, ResonanceCalculator | `resonance_calc` | resonance_calculator | hayır | evet | evet |
| `agent_core/agents/resonance_synthesizer.py` | ResonanceSynthesizerAgent | `resonance_synthesizer` | resonance_synthesizer | evet | evet | evet |
| `agent_core/agents/target_psyche_profiler.py` | TargetPsycheProfiler | **bağlı değil** | — | hayır | hayır | evet |

## 4 · HTTP uçları

- Toplam **70** uç; arayüzde referansı olmayan **49**, deneysel **9**.

### Arayüzden çağrılmayan uçlar

- `POST /api/browser/back`
- `POST /api/browser/click`
- `POST /api/browser/close`
- `POST /api/browser/open`
- `POST /api/browser/press`
- `POST /api/browser/save`
- `GET /api/browser/shot`
- `GET /api/browser/state`
- `POST /api/browser/type`
- `POST /api/calibration/adjudicate`
- `POST /api/calibration/observations`
- `POST /api/company/scan`
- `GET /api/dialogue/sessions`
- `POST /api/experimental/chat/respond`
- `POST /api/experimental/crawl/fetch`
- `POST /api/experimental/holehe/scan`
- `POST /api/experimental/interpreter/execute`
- `POST /api/experimental/maigret/scan`
- `POST /api/experimental/shadow/analyze`
- `POST /api/experimental/shadow/generate`
- `POST /api/experimental/socid/extract`
- `GET /api/experimental/stealth`
- `POST /api/jury/vote`
- `POST /api/language/detect`
- `POST /api/language/translate`
- `POST /api/media/analyze`
- `GET /api/media/status`
- `GET /api/memory/{target}`
- `GET /api/memory/{target}/recall`
- `POST /api/minor/case`
- `POST /api/minor/clear`
- `GET /api/minor/state`
- `POST /api/mobile/coach`
- `POST /api/report/build`
- `GET /api/report/status`
- `POST /api/scraper/authorize-alternative`
- `GET /api/speech/audio/{name}`
- `POST /api/speech/say`
- `GET /api/speech/status`
- `POST /api/tasks/{task_id}/cancel`
- `GET /api/tasks/{task_id}/changes`
- `GET /api/tasks/{task_id}/graph`
- `POST /api/tasks/{task_id}/halt`
- `GET /api/tasks/{task_id}/memory`
- `GET /api/telemetry/taste`
- `POST /api/vault/lock`
- `POST /api/vault/unlock`
- `POST /v1/chat/completions`
- `GET /v1/models`

## 5 · Kapılar (env)

- Yönetilen kapı: **17**
- Kodda okunan ama YÖNETİLMEYEN: —
- Yönetilen ama `.env.example`'da olmayan: —
- Örnekte olup yönetilmeyen: —

## 6 · Erişilemeyen modüller (giriş noktalarından AST ile)

- 180 modülden **180** tanesi giriş noktalarından erişilebilir; **0** tanesi değil.
- Giriş noktası listesi `scripts/golge_denetimi.py` içinde BEYAN edilir (8 adet). Yeni bir CLI eklenip buraya yazılmazsa betik onu ölü kod sanar — yani bu bölümün tek zayıf noktası, listeyi güncel tutmaktır.

## 7 · Uyanma planı — sebebe göre ne gerekiyor

| Sebep | Yetenek sayısı | Ne gerekiyor |
| --- | --- | --- |
| `config_missing` | 1 | eksik yapılandırma → ilgili env değeri (ör. `SEARXNG_BASE_URL`) |
| `dependency_missing` | 11 | Python/CLI bağımlılığı kurulu değil → `requirements-osint.txt` / `requirements-retina.txt` / `requirements-ml.txt` içindeki paket |
| `gate_disabled` | 7 | yalnız şalter: `.env` içinde ilgili `ENABLE_*` = true |
| `no_engine` | 2 | yerel motor yok → `PINEAL_TRANSLATE_CMD` / `PINEAL_STT_CMD` gibi bir CLI ya da yerel HTTP ucu tanımla |
| `no_local_endpoint` | 2 | yerel uç tanımlı değil → `PINEAL_TTS_URL` / `PINEAL_STT_URL` (yalnız 127.0.0.1) |
| `no_local_models` | 1 | yerel model yok → `ENABLE_LOCAL_JURY` için yerel LLM bitiş noktası |

- **config_missing**: `sensor.search.searxng`
- **dependency_missing**: `extractor.identity.socid`, `extractor.web.crawl4ai`, `extractor.web.scrapling`, `extractor.web.trafilatura`, `renderer.report.video`, `sensor.company.harvester`, `sensor.identity.holehe`, `sensor.identity.maigret`, `sensor.ig.instagrapi`, `sensor.web.agent_reach`, `sensor.x.twscrape`
- **gate_disabled**: `analyzer.media.frames`, `analyzer.media.similarity`, `renderer.report.diagram`, `renderer.report.pdf`, `sensor.company.people`, `sensor.company.seo`, `sensor.media.fetch`
- **no_engine**: `extractor.media.transcript`, `extractor.text.translate_local`
- **no_local_endpoint**: `voice.stt.local`, `voice.tts.local`
- **no_local_models**: `verifier.jury.local`

## 8 · Depoda duran gömülü varlıklar

_Not: son sütun gevşek bir metin sayımıdır (ad, kod dosyalarında kaç yerde geçiyor);
'bağlı' kanıtı değil, 'anılıyor' göstergesidir._

| Yol | Ne | Var | Ürün kodunda kaç dosya anıyor |
| --- | --- | --- | --- |
| `rust_core` | Rust çekirdeği (cargo) | evet | 4 |
| `android` | Android kabuğu | evet | 1 |
| `functions` | Cloudflare/Vercel edge fonksiyonları | evet | 4 |
| `worker.ts` | Edge worker | evet | 8 |
| `scraper.py` | Kök scraper | evet | 26 |
| `live_llm_gate.py` | Canlı LLM kapısı | evet | 4 |
| `release` | Sürüm kilit dosyaları | evet | 5 |
| `skills` | SKILL.md araç defteri | evet | 4 |
| `docs/envanter.html` | Envanter sayfası | evet | 12 |
| `config/agent_tiers.json` | Ajan kademe planı | evet | 3 |

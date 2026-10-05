# MİMARİ (koddan doğrulanmış çalışma zamanı grafiği)

> Bu belge röntgen (adli analiz) sonrası gerçek mimariyi anlatır — README iddiaları değil.

## Bileşen haritası

| Katman | Konum | Sorumluluk |
|---|---|---|
| UI | `frontend/` (Svelte 5 + Vite) | Vault, görev başlatma, Aspasia sohbeti, agent deck, 360° panel, 6 Forensik Damga Paneli, i18n (TR/EN) |
| API | `backend/api.py` (FastAPI) | Oda yönetimi, WebSocket, scraping orkestrasyonu, auth/limit |
| Orchestrator | `agent_core/task_executor.py` | Görev durum makinesi + ajan zinciri + kanıt biriktirme |
| Router | `agent_core/services/cognitive_router.py` | Girdiye göre ajan rotası (kural tabanlı, LLM'siz) |
| Ajanlar | `agent_core/agents/*` | OSINTInvestigator, AuthenticityAuditor dahil kayıtlı ajanlar (`resonance_calc` saf numpy) |
| LLM | `agent_core/services/llm_gateway.py` | OpenRouter/Ollama; tier'lar, retry, circuit breaker, JSON tamiri, vision |
| Bellek | `agent_core/services/canonical_memory.py` | Görev başına `memory/<task_id>.json` (bilinçli: DB yok) |
| Telemetri | `agent_core/schemas/telemetry.py` + api.py kuyruğu | Pydantic event şemaları → FIFO → WebSocket (Snapshot + SearchEngine ayrımı) |
| Aspasia | `agent_core/aspasia/aspasia_chief.py` | Gözlemci persona; telemetri özeti + sohbet (karar verici DEĞİL) |
| Tüzük | `docs/PINEAL_TUZUK.md` | **Ürün anayasası (v2, 2026-10-05):** 10 madde. Maddeler kodda `PolicyKernel` kapıları olarak çalışır (vault/consent/rate/budget). Uyum/ilk temas tanım değil **sahadır** (Madde 9) |
| Yetenek omurgası | `agent_core/capabilities/` | **Capability Spine (Faz 0):** tek sözleşme (`base.py`) + tek kayıt defteri (`registry.py`) + politika kapısı (`policy.py`) + tek koşucu (`runner.py`). Yeni bir yetenek eklemek = `BaseCapability` yaz + `register()`. İkinci bir "yetenek var mı?" katmanı YOKTUR (kural [009]) |
| Scraper | `agent_core/scraper/instagram_ghost.py` (IG) | Playwright+stealth; Pydantic V2 şema; kanıt yoksa HALT. X (`scraper.py`) **devre dışı** — `XScraperUnsupportedError` (B4) |
| Rust Core | `rust_core/` | **FAZ 9 Karar B — experimental/optional:** Python ürün yoluna bağlı değil, Docker'a paketlenmez ve karar etkisi yoktur; CI `rust-core` job'u yalnız bağımsız derleme/test yapar |

## Çalışma zamanı zincirleri

### 1) Analiz akışı
```
UI (apiFetch) ──POST /api/initiate──► FastAPI run_mission
   └─ (url varsa) Playwright+stealth scrape ─► target_profile
PinealExecutor.execute_task [processing]
   ├─ CognitiveRouter.analyze → rota
   ├─ her ajan: execute → UncertaintyEngine (güven<0.6 → halted_evidence)
   │            resonance<0.70 → halted_frequency
   ├─ 6 Forensik Damga: follower_audit · timing_forensics · depth_report
   │   · visual_evidence · shadow_profile · osint_footprint
   ├─ kanıt → evidence_chain + CanonicalMemory (json; hindsight ile anlamsal)
   ├─ LLM yanıt önbelleği (exact-key, model/system/sıcaklık dahil)
   └─ 360° HolisticProfile (passions+frictions+cognitive+bridge)
Telemetry: _emit → asyncio.Queue (FIFO) → _room_sender → WebSocket
UI: snapshot_update / event / result → paneller
```

### 2) Durum makinesi (Python — `agent_core/domain/pipeline_status.py`; `rust_core/` bu akışa bağlı değildir)
`initialized → processing → completed | failed | halted_evidence | halted_frequency`

### 3) Aspasia akışı
```
UI ──POST /api/aspasia/chat──► room.aspasia.chat(msg, room, model?, image?)
   ├─ build_telemetry_summary(room.active_tasks)  ← canlı snapshot'lar
   └─ LLMGateway.query(system=ASPASIA_PERSONA, images?) ─► yanıt / zarif fallback
```

## Alınan mimari kararlar (ADR özeti)
| Karar | Neden |
|---|---|
| **Rust için Karar B: experimental/optional** | `rust_core/` bağımsız CI kapısına sahiptir; Python ürün bağımlılığı, aktivasyon bayrağı, Docker paketi veya API/pipeline karar etkisi yoktur. Rust CI PASS, ürün entegrasyonu sayılmaz |
| **Masaüstü Tauri ürün dışında** | Kaynak taslağı mevcut olsa da Tauri kabuğu build/release/runtime ürün grafiğinde değildir; ayrı faz ve E2E olmadan ürün özelliği sayılamaz |
| **Görev verisi için SQLite yok** | Kanıt belleği JSON dosyasıdır (`memory/<task_id>.json`); SQLite yalnızca LLM yanıt önbelleğinde (`cache/responses.db`) ve opsiyonel hindsight anlamsal indeksinde kullanılır |
| **LIVE_LLM_E2E kapısı** | Anahtarsız/halüsinasyonlu koşular kodda reddedilir (bilinçli tasarım) |
| **D5: deneysel API'ler** | shadow/chat/interpreter → `/api/experimental/*` (UI çağrıcısı yok) |
| **Otomatik mesaj gönderimi yok** | Sistem hiçbir platforma mesaj göndermez; deterministik shadow analizi (dark-triad + NLP dizisi) pipeline'da forensik damga olarak kaydedilir; mesaj/kontra-hamle üretim araçları yalnız `/api/experimental/*` altında kullanıcı çağrısıyla çalışır |

## Android İstemcisi (Bağımsız Ürün)

`android/` — Kotlin/Jetpack Compose Android uygulaması. Python backend'e **hiç bağlanmaz.**

```
Android App
   └─ AspasiaChatEngine / PinealAnalyzerEngine
        └─ GeminiClient (Retrofit)
             └─► https://generativelanguage.googleapis.com/
                  Header: x-goog-api-key: <GEMINI_KEY>   ← query param değil
```

CI `android` job'u: lint + unit test + assemble. Bu, backend pipeline entegrasyonu
kanıtı değildir. Android ve backend ayrı release döngülerine sahiptir.

## Güvenlik yüzeyi
`PINEAL_ENV=production` için zorunlu `PINEAL_TOKEN` (HTTP `X-API-Key`; WebSocket ilk auth mesajı, URL'de sır yok) · CORS localhost kümesi · rate limit (initiate 5/dk, aspasia 20/dk, experimental 10/dk) · hata modeli: uygulama hataları `{error:{code,message}}`, şema doğrulama (422) standart FastAPI `{detail:[...]}` · DNS-pinned SSRF/redirect koruması · sırlar yalnız gateway belleğinde (log/event/yanıt redaction testli) · containment kontrollü retention: `DELETE /api/tasks/{id}`

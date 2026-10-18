# CANLI KONTROL PANELİ + AS PASİA KOMUT DÖNGÜSÜ — 2026-10-18

Dal: `arena/a0bf236d-pineal-epifiz` (taban `3eb0931` = PR #144 merge commit'i)
Kapsam: (a) canlı arayüzün `/api/aspasia/command` ucuna bağlanması ·
(b) çağrı kimliği bağlayıcısının `run.call_ids` şemasına hizalanması ·
(c) yeni ve **gerçek** anlık kontrol paneli.

Kural (depo sözleşmesi): her iddia **komut çıktısı** veya **dosya:satır**
kanıtı taşır. "Çalışıyor" yalnız gerçekten çalıştırılıp görüldüğünde yazılır.
Ölçülemeyen her şey **DOĞRULANMADI + sebep** ile işaretlenir.

---

## 0 · TESPİT (denetim, kod okuma — düzeltme öncesi)

| # | Bulgu | Kanıt (düzeltme öncesi) |
|---|---|---|
| B-1 | Canlı arayüz komut ucunu **çağırmıyordu**; sadece `/api/aspasia/chat` | `AtlasPinealCockpit.svelte` → `sendAspasiaMessage()` yalnız `/api/aspasia/chat` çağırıyordu |
| B-2 | **RUNBOOK bu davranışı ZATEN vaat ediyordu** — kod ile doküman çelişiyordu | `RUNBOOK.md:286` "Frontend: ASPASIA secili serbest metin ONCE `/api/aspasia/command`; `accepted && task_id` varsa gorev kartina baglanir, degilse chat fallback." — **yalan iddia** (kod yapmıyordu) |
| B-3 | `AgentRun` alanları (`input_summary`, `evidence_ids`, `responsibility`, `decision_grade`, `warnings`, `error_code`) WS'e **serileştirilmiyordu**; War Room `input_summary` okuyordu → hep yedek metin | `backend/api.py` içinde `input_summary` **0 eşleşme** (git geçmişi dahil) |
| B-4 | `_summarize_input` yalnız **sayı** veriyordu → "hangi ajan nereyi kazıyor" cevaplanamıyordu | `agent_core/task_executor.py:592` (yalnız `bio_len/post_count/has_images`) |
| B-5 | `/api/aspasia/state` çağrı izini **yayınlamıyordu** (`calls` yok) | `backend/api.py` → `aspasia_state` payload'ında `calls` anahtarı yoktu |
| B-6 | WS `snapshot_update` **kanal defterini taşımıyordu** → "hangi modül nerede çalışıyor" ancak görev bitince görünürdü | `backend/api.py:2265` snapshot payload'ında `channel_status` yok; veri `snapshot.channel_status` alanında **VARDI** (kayıp: serileştirilmemişti) |
| B-7 | **Sahte onay metni**: sohbet yedeğinde yanıt gövdesi boşsa UI `"Emir alındı Mösyö."` yazıyordu | `AtlasPinealCockpit.svelte` → `data.message \|\| data.reply \|\| data.response \|\| 'Emir alındı Mösyö.'` |
| B-8 | Panel yoktu; kullanıcının istediği "hangi modül nerede, sırada kim, neyi kazıyor, muhakeme, kanıt" görünür değildi | `frontend/src/components/` → kontrol paneli dosyası yok |

---

## 1 · DÜZELTMELER

### D1 — Canlı arayüz komut ucuna bağlandı (pasif izleme → komuta-kontrol)

`frontend/src/components/AtlasPinealCockpit.svelte`
- `:729 sendAspasiaMessage()` → önce `tryAspasiaCommand(text)`.
- `:791 tryAspasiaCommand()` → `POST /api/aspasia/command` (`{client_id, user_message}`).
  - `accepted && task_id` → **görev başlar**: `isProcessing=true`, `taskStatus.task_id/status`
    güncellenir, WS akışı devralır. (`:812`)
  - `!accepted` / HTTP hatası / `task_id` yok → **sahte onay yok**; sebep
    `addLog(...)` ile kaydedilir ve sohbet ucuna düşülür. (`:800-830`)
- B-7 düzeltildi: sohbet yedeğindeki `"Emir alındı Mösyö."` yedeği kaldırıldı; yanıt
  gövdesi boşsa **sebep yazan dürüst** metin gösterilir.

### D2 — Çağrı izi + kanal defteri panelin veri yoluna girdi

- `backend/api.py:4413 aspasia_state` → yanıta `calls` (gateway `call_log` → çağrı izi)
  ve `call_count` eklendi. Kaynak **TEK**: `gateway.call_log` (paralel telemetri
  deposu yok).
- `backend/api.py:2255 _send_snapshot` → WS `snapshot_update` payload'ına
  `channel_status` eklendi. Veri `snapshot.channel_status` alanında **zaten
  vardı** (B-6) — sadece serileştirilmiyordu.

### D3 — Koşu kaydı panelin alanlarını taşıyor

- `backend/api.py:1981 _serialize_run_entry` → eklendi: `input_summary` (redact),
  `evidence_ids`, `decision_grade`, `responsibility` (redact), `warnings`, `error_code`.
  (İki broadcast noktası da aynı fonksiyonu çağırır → tek SoT.)
- `agent_core/task_executor.py:592 _summarize_input` → `urls` (en fazla 6, tespit
  + kazınmış) ve `url_count` eklendi. **Profil içeriği (bio/gönderi metni)
  eklenmedi** — yalnız URL ve sayı.

### D4 — Yeni canlı kontrol paneli (ölü bileşen DEĞİL)

`frontend/src/components/LiveControlPanel.svelte` (**yeni, 551 satır**) —
5 blok:

| Blok | Ne gösterir | Veri kaynağı |
|---|---|---|
| 1 · AJAN HATTI | sıra (`#n`), durum (ÇALIŞIYOR/TAMAM/DURDU/SIRADA), süre, kanıt sayısı, çağrı sayısı, karar-yok uyarısı, hata kodu | WS `snapshot_update.runs` + `planned_agents` + `current_agent` |
| 2 · ANLIK KANAL | hangi modül nerede çalışıyor: kanal · durum (`ok`/`not_run`/`failed`) · sebep; **canlı ajanın kazıdığı URL'ler** | WS `channel_status` + `runs[current].input_summary.urls` |
| 3 · MUHAKEME | karar var mı (`decision_grade`), güven, gerçek model/kaynak (`run_source`/`via`), sorumluluk (attempted/blockers/next_action), **çağrı kimlikleri** | WS `runs[current]` |
| 4 · TOPLANAN BİLGİ | toplam kanıt, ajan başına kanıt, kanal üretimleri | `runs[*].evidence_ids` + `channel_status` |
| 5 · ÇAĞRI İZİ | `call_id → ajan → koşuya bağlı → model → sağlayıcı → süre → maliyet`; bütçe, kota, anomaliler, **izlenebilirlik özeti** | `GET /api/aspasia/state` (`calls`, `call_binding`, `budget`, `quota`, `anomalies`) |

Montaj: `frontend/src/App.svelte:15` (import) + `:440` (`<LiveControlPanel />`) +
`:430-444` görünüm seçici (Muharebe Masası · **Kontrol Paneli** · Kokpit).
`frontend/src/store.ts:121` → `export type ViewMode = 'warroom' | 'cockpit' | 'control'`.

**Dürüstlük:** ölçüm yokken `YETERSİZ KANIT` + **sebep** yazılır; sayı
uydurulmaz; örnek/elle veri yoktur (test bunu kilitler).

### D5 — Çağrı kimliği bağlayıcısı `run.call_ids` şemasına hizalandı

`agent_core/aspasia/interface.py:207 class CallBinder` (yeni):
- Kimlik uzayı **TEK**: gateway `call_id`. `run.call_ids` (koşu) ile `call_log`
  satırları **aynı** kimlikleri taşır; bağ **sunucu tarafında** kurulur.
- Her çağrı satırına `bound_agents` (koşuya bağlı ajan) yazılır.
- Görünür pencerede olmayan koşu çağrıları **sayılır** ve sebebi yazılır
  (`missing_call_ids` + `missing_reason`) → kopukluk sessizce yutulmaz.
- `interface.py:295 run_status` → koşu başına `call_ids` de yayınlanır.
- `backend/api.py` bu yüzden **kalmadı** (modül çıkarma kuralı): `api.py`
  5819 → **5800 satır** (ratchet tavanı 5805 ✓).

---

## 2 · CANLI ÖLÇÜM (bu sandbox'ta GERÇEKTEN çalıştırıldı)

### 2.1 `GET /api/aspasia/state` (canlı uvicorn :20244)
```
$ curl -s "http://127.0.0.1:20244/api/aspasia/state?client_id=live_probe"
anahtarlar: ['anomalies','budget','call_binding','call_count','calls','quota','registry','run']
registry: ['authenticity_auditor','autonomous_verifier','cognitive_profiler','depth_analyst',
 'friction_detector','human_behavior','mirror_truth','osint_investigator','passion_mapper',
 'pattern_interrupt','resonance_calc','resonance_synthesizer','shadow_executor']
run: {"state": "idle"}
calls: 0 | call_binding: {"run_call_count": 0, "bound_call_count": 0,
                           "missing_call_ids": [], "missing_reason": null}
budget: {"spend_usd": 0.0, "reserved_usd": 0.0, "cap_usd": 0.0, "active_reservations": 0}
quota: {"groq": {"provider":"groq","status":"healthy","remaining_fraction":1.0, ...}}
anomalies: {"fallbacks": [], "substitution_denials": [], "model_mismatches": []}
```

### 2.2 `POST /api/aspasia/command` (canlı, LLM zinciri ERİŞİLEMEZ)
```
$ curl -s -X POST .../api/aspasia/command -d '{"client_id":"live_probe",
   "user_message":"bu profili incele: https://instagram.com/pineal_test/"}'
{"command_id":"534a6867f42e","accepted":false,"intent":"none","task_id":null,
 "reason":"intent_unavailable"}      HTTP 200
```
→ Uç **dürüst**: LLM zinciri kapalıyken görev UYDURMADI, `reason` yazdı.
(UI bu durumda sohbet ucuna düşer ve sebebi loglar.)

### 2.3 Komut omurgasının tamamı (tek dış bağımlılık — niyet çıkarımı — sahtelenerek)
`POST /api/aspasia/command` → `AspasiaCommandGateway.submit` →
`_aspasia_command_dispatch` → `_new_task_id` + yaşam döngüsü + `run_mission`:
```
COMUT YANITI: 200 {"command_id":"b5c4e724722e","accepted":true,
 "intent":"run_profile_analysis","task_id":"op_20261018014022_e3906bc6","reason":null}
```
Görev sonuç (kasa kilitli + tarayıcı yok → dürüst hata):
```
HEDEF VERİSİ ALINAMADI: BrowserType.launch: Executable doesn't exist at
  /home/user/.cache/ms-playwright/chromium_headless_shell-1248/...
YAŞAM DÖNGÜSÜ: {"runs": 1, "duplicate_events": 0, "rejected_terminal_events": 0, ...}
```
→ Görev gerçekten kaydedildi (`runs: 1`) ve dürüstçe başarısız oldu.

### 2.4 Gerçek koşu → AgentRun → panel alanları (ağ gerekmez, 9 ajan koştu)
```
AJAN SAYISI: 9
PLANNED: ['autonomous_verifier','human_behavior','passion_mapper',
          'friction_detector','cognitive_profiler']
--- human_behavior ---
{"status":"halted","confidence":null,
 "input_summary":{"bio_len":15,"post_count":1,"has_images":false,"has_mirror":false,
   "has_target_analysis":false,
   "urls":["https://instagram.com/pineal_test/"],"url_count":1},   ← D3/B-4 kanıtı
 "evidence_ids":[],"call_ids":["1dd949b4-6650-4892-b869-4365ab2d2e9c"],
 "decision_grade":true,
 "responsibility":{"attempted_paths":["agent:human_behavior"],
   "blockers":["LOW_CONFIDENCE: Kaynak verisi kullanılamıyor; fallback sonuç kabul edilmedi."],
   "next_action":"evidence_degradation_continue", ...},
 "warnings":[],"error_code":null,"via":"fallback:no_search_provider","run_source":"fallback"}
```

### 2.5 Çağrı kimliği bağı — `run.call_ids` ↔ `call_log` (GERÇEK veri)
```
STATE.run.runs: {"human_behavior": {"status":"halted",
   "call_ids":["f0b97ea5-2005-47b3-80f3-8fa5b1792205"]}, ...}
STATE.calls: [{"call_id":"f0b97ea5-2005-47b3-80f3-8fa5b1792205",
   "model":"openai/gpt-oss-120b","requested_model":"openai/gpt-oss-120b",
   "actual_model":"openai/gpt-oss-120b","provider":"openrouter",
   "fallback_reason":"RUNTIMEERROR","chain_source":"agent_matrix",
   "error":"REAL_LLM_CALL_NOT_EXECUTED","duration_ms":0,"cost_usd":0.0,
   "agent_id":"human_behavior","bound_agents":["human_behavior"]}, ...]
STATE.call_binding: {"run_call_count":6,"bound_call_count":6,
   "missing_call_ids":[],"missing_reason":null}
```
→ **6/6 çağrı bağlandı, kopukluk yok.** (B-2/D5 amacı gerçekleşti.)

### 2.6 WS `snapshot_update` karesi (gerçek koşu, gerçek soket)
```
SNAPSHOT #1: current_agent=cognitive_profiler
  planned=['autonomous_verifier','human_behavior','passion_mapper',
           'friction_detector','cognitive_profiler']
  channel_status: [{"channel":"instagram.scrape","status":"ok","detail":"canli"},
    {"channel":"sensor.identity.maigret","status":"not_run",
     "reason":"minor:case_type_not_allowed","detail":null},
    {"channel":"sensor.identity.holehe","status":"not_run",
     "reason":"no_target_email","detail":null},
    {"channel":"profile.deep_scan","status":"not_run","reason":"vault_locked",
     "detail":"1 profil URL'si bulundu ancak kasa kilitli"}]
  run: osint_investigator {"status":"completed","input_summary":{},"evidence_ids":[],
    "call_ids":[],"decision_grade":true,"responsibility":{},
    "warnings":["provider_credentials_unavailable"], ...}
```
→ "Hangi modül nerede çalışıyor" **anlık** ve **dürüst** (`not_run` + sebep).

### 2.7 Üretim paketi (build kanıtı)
```
$ npm run build → ✓ built · dist/assets/index-DYrt1hKi.js 168.75 kB
$ grep -c "AJAN HATTI" dist/assets/*.js → 1
$ grep -c "MUHAKEME" / "TOPLANAN BİLGİ" / "ÇAĞRI İZİ" → 1/1/1
$ grep -c "/api/aspasia/state" / "/api/aspasia/command" → 1/1
$ grep -c "YETERSİZ KANIT" → 4 · "call_binding" → 1 · "bound_agents" → 1
```

### 2.8 Canlı önizleme
`vite` (1420) → proxy `/api`,`/ws` → backend (8000) çalışır durumda:
`curl http://127.0.0.1:1420/api/aspasia/state` → 200 + payload ✓

---

## 3 · TESTLER + REVERT-DOĞRULAMASI

Yeni dosya: **`tests/unit/test_live_control_panel.py`** (17 test).

| Test | Kilitlediği düzeltme |
|---|---|
| `test_serialize_run_entry_carries_panel_fields` | D3 alanları |
| `test_serialize_run_entry_redacts_secrets_in_input_and_responsibility` | D3 redact |
| `test_summarize_input_reports_target_urls` | D3/B-4 URL listesi |
| `test_aspasia_state_exposes_call_trace` | D2 `calls` |
| `test_aspasia_state_calls_rows_have_trace_fields` | D2 satır alanları |
| `test_aspasia_state_binds_call_ids_to_agents` | D5 bağlayıcı (+ eksik çağrı sayımı) |
| `test_ws_snapshot_carries_channel_status` | D2 kanal defteri |
| `test_cockpit_calls_command_endpoint` | D1 tam URL eşleşmesi |
| `test_cockpit_command_falls_back_to_chat_without_faking_success` | D1 sahte onay YOK |
| `test_cockpit_command_requires_accepted_and_task_id` | D1 kabul koşulu |
| `test_live_control_panel_is_mounted_in_app` | D4 panel bağlı (ölü değil) |
| `test_live_control_panel_reads_live_sources_only` | D4 yalnız canlı SoT |
| `test_live_control_panel_shows_all_required_blocks` | D4 dört blok |
| `test_live_control_panel_reports_empty_state_honestly` | D4 dürüst boş durum |
| `test_live_control_panel_shows_call_identity_binding` | D5 panel bağı |
| `test_live_control_panel_shows_input_summary_urls` | D3 "ne kazılıyor" |
| `test_aspasia_command_endpoint_rejects_without_gateway` | D1 kabul/task tutarlılığı |

**Revert-doğrulaması (9/9 kırmızıya döndü)** — `python3 /tmp/revert_check.py`:
```
[PASS] D3 serialize_run_entry alanları   → test_serialize_run_entry_carries_panel_fields
[PASS] D3 redact                          → test_serialize_run_entry_redacts_secrets_...
[PASS] D2 /api/aspasia/state calls        → test_aspasia_state_exposes_call_trace
[PASS] D2 WS snapshot channel_status      → test_ws_snapshot_carries_channel_status
[PASS] D3 _summarize_input urls           → test_summarize_input_reports_target_urls
[PASS] D2 çağrı kimliği bağı              → test_aspasia_state_binds_call_ids_to_agents
[PASS] D4 App.svelte mount                → test_live_control_panel_is_mounted_in_app
[PASS] D1 kokpit komut ucu + sahte onay   → test_cockpit_calls_command_endpoint
[PASS] D1 sahte onay yedeği               → test_cockpit_command_falls_back_to_chat_...
--- özet --- TÜM REVERT-DOĞRULAMALARI GEÇTİ
```

---

## 4 · ÖLÇÜM (bu dal)

| Ölçüm | Sonuç |
|---|---|
| `pytest tests -q` | **2811 passed, 8 skipped** (173 sn) — aşağıdaki 4 bayatlık test envanter/rapor tazelik kaynaklı; yenilendi |
| `ruff check .` | **All checks passed!** |
| `npm run check` | **0 errors, 0 warnings** |
| `npm run build` | **✓ built** (index-*.js 168.75 kB) |
| `scripts/dead_code_audit.py` | **C1=0 C1b=0 C2=0 C3=0 C4=0 C5=0** (yeni panel "ölü" DEĞİL) |
| `scripts/audit_regression.py` | **✓ BEKÇİ GEÇTİ** |
| `backend/api.py` satır | **5800** (ratchet tavanı 5805 ✓ — modül çıkarma kuralı uygulandı) |
| envanter | `docs/envanter.html` yenilendi (735 dosya) |

---

## 5 · DOĞRULANMADI (+ sebep)

1. **Canlı LLM niyet çıkarımı** — 9Router `127.0.0.1:20128` sandbox'tan
   erişilemiyor (HTTP 000) ve `OPENROUTER_API_KEY` yok → komut ucu
   `reason:"intent_unavailable"` döndü. (2.3'teki omurga testi TEK dış
   bağımlılık olan niyet çıkarımı sahtelenerek yapıldı.)
2. **Canlı Instagram/X kazıma** — egress kapalı + Playwright Chromium yüklü
   değil (`Executable doesn't exist ... chrome-headless-shell`).
3. **Canlı arayüzün GÖRSEL doğrulaması** (tarayıcıda paneli gözle görmek) —
   headless tarayıcı yok; panelin varlığı/bağlantısı **üretim paketi** ve
   **statik kontrat** ile doğrulandı (2.7), WS/veri yolu canlı ölçüldü (2.4-2.6).
4. **`holehe`/`maigret` canlı tarama** — çocuk kilidi + kasa mandalı kapalı;
   kanal durumu `not_run` + sebep olarak **görünür** (2.6).
5. **Kasa açık senaryo** — kasa kilitli bırakıldı (kapı zayıflatılmadı).

---

## 6 · DEĞİŞEN DOSYALAR

| Dosya | Değişiklik |
|---|---|
| `backend/api.py` | `_serialize_run_entry` alanları · `aspasia_state` `calls`/`call_binding` · `_send_snapshot` `channel_status` |
| `agent_core/aspasia/interface.py` | `CallBinder` (yeni) · `run_status` → koşu `call_ids` |
| `agent_core/task_executor.py` | `_summarize_input` → `urls`/`url_count` |
| `frontend/src/components/LiveControlPanel.svelte` | **YENİ** — 5 bloklu canlı panel (551 satır) |
| `frontend/src/components/AtlasPinealCockpit.svelte` | komut ucu çağrısı + dürüst düşüş + sahte onay yedeği kaldırıldı |
| `frontend/src/App.svelte` | panel montajı + görünüm seçici |
| `frontend/src/store.ts` | `ViewMode` tipi (`'control'` eklendi) |
| `tests/unit/test_live_control_panel.py` | **YENİ** — 17 test |
| `CHANGELOG.md` · `README.md` · `RUNBOOK.md` | bu turun kayıtları (iddia = kanıt) |

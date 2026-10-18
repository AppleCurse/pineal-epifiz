# P8 · CANLI KONTROL PANELİ — "EN DONANIMLI" SÜRÜM — 2026-10-18

Dal: `arena/ef194da9-pineal-epifiz` (taban `74d7c7f5` = PR #146 merge commit'i = `origin/main`)
Kapsam: **(A)** muhakeme/kanıt içeriği · **(B)** canlı komut döngüsü doğrulama komutu ·
**(C)** ajan detayı + filtre · **(D)** çağrı izi geçmişi sayfalaması.

Kural (depo sözleşmesi): her iddia **komut çıktısı** veya **dosya:satır** kanıtı
taşır. "Çalışıyor" yalnız gerçekten çalıştırılıp görüldüğünde yazılır.
Ölçülemeyen her şey **DOĞRULANMADI + sebep** ile işaretlenir. Örnek/mock veri
üretilmez.

---

## 0 · TESPİT (P7'den devam — panel çalışıyordu ama "en donanımlı" DEĞİLDİ)

| # | Bulgu | Kanıt (P8 öncesi durum) |
|---|---|---|
| B-1 | Panelde **muhakeme içeriği** yoktu: ajanın kararı/güveni/modeli/sorumluluğu gösteriliyordu ama **çıktısı** (`output_summary`) görünmüyordu | `LiveControlPanel.svelte` (P7 sürümü): `output_summary` **yok**; `grep -c output_summary` → 0 |
| B-2 | **Kanıt zinciri** panelde hiç yoktu → "toplanan bilgilerin toplanma düşünceli yapısı" görünmüyordu | Aynı dosyada `evidence_chain` **yok** (`grep -c evidence_chain` → 0) |
| B-3 | Çağrı izi **yalnız son 40 kaydı** gösteriyordu; `call_log` 500 kayıtla sınırlı → geçmiş **erişilemez** idi | `agent_core/aspasia/interface.py` → `TelemetryReader.recent()` → `call_log[-40:]`; `limit=40` sabit |
| B-4 | Panelde **filtre** yoktu: 13 ajan arasından tek ajanı odaklanmanın yolu yoktu | Aynı dosyada `filterText`/`statusFilter` **yok** |
| B-5 | **Ajan detayı** görünümü yoktu (kuyrukta sırasını bekleyen ajanın girdisi/kanıtı/sorumluluğu görünmüyordu) | Aynı dosyada ajan detayı bloğu **yok** |
| B-6 | Komut→görev→çağrı izi zincirini **çalıştıran ve kanıtlayan** bir komut yoktu (P7'de elle prob ile ölçüldü, tekrarlanabilir değildi) | `scripts/` altında döngü doğrulayıcı **yok** (`ls scripts/verify_*` → eşleşme yok) |
| B-7 | `/api/aspasia/state` gövdesi `backend/api.py` içindeydi → P8'in sayfalama parametreleri monolit dosyaya satır ekleyecekti (tavan ihlali) | `backend/api.py:4387 aspasia_state` → gövde ~40 satır; `wc -l backend/api.py` → **5772** |

---

## 1 · DÜZELTMELER

### A · MUHAKEME + KANIT İÇERİĞİ (panel yeniden yazıldı)

`frontend/src/components/LiveControlPanel.svelte` — **920 satır**, 6 blok:

1. **AJAN HATTI** — kuyruk + anlık ajan (`#1 … #n`, durum, süre, kanıt/çağrı sayısı)
2. **ANLIK KANAL** — kanal defteri + **SIRADAKİ AJAN** + **NE KAZILIYOR** (canlı ajanın URL girdisi)
3. **MUHAKEME** — karar (VAR/KAR YOK), güven %, model/kaynak/via, **sorumluluk**
   (`attempted/blockers/next_action`), çağrı kimlikleri + **"İZ PENCERESİ DIŞINDA"**
   işareti, ve **ÇIKTI (`output_summary`) satır satır**
4. **TOPLANAN BİLGİ** — toplam kanıt kimliği, ajan→kanıt akışı, **KANIT ZİNCİRİ**
   (ajan→kanıt **gruplu**; her satır `evidence_type`/`timestamp`/`result`/`provenance`),
   kanal yapısı
5. **ÇAĞRI İZİ** — `call_id → ajan → koşuya bağlı → model → sağlayıcı → süre → maliyet`
   + bütçe/kota|anomali + **sayfalama**
6. **AJAN DETAYI** — seçili ajanın tam dökümü (girdi, kanıt kimlikleri, çağrı kimlikleri,
   sorumluluk, uyarılar, hata)

Dürüstlük sözleşmesi korundu: ölçüm yoksa `YETERSİZ KANIT` + **sebep**
(`test_live_control_panel.py::test_live_control_panel_reports_empty_state_honestly`).

**Ölçülen veri şekli (probu: `/tmp/shape_probe.py`, canlı koşu kayıtlarından):**
- `output_summary` = ajan başına **alan-sozluk** (`osint_investigator`: 14 alan ·
  `pineal_7pillar`: 7 · `human_behavior`: 0 · `passion_mapper`: 0) → panel boş
  ajanda **"ajan çıktı üretmedi"** yazar (uydurma satır yok).
- `evidence_chain` satırı = `{agent, evidence_type?, provenance?, result:dict, timestamp}`
  (**`EvidenceItem` DEĞİL** — 7 satır ölçüldü) → panel bu şekli okur.
- `autonomous_verifier.canonical_observation_checks[].evidence_id` = `ev_...` (derin JOIN).

### B · CANLI KOMUT DÖNGÜSÜ DOĞRULAMA KOMUTU

`scripts/verify_command_loop.py` (**YENİ**, 390 satır) — `komut → görev → ajan →
kanıt → çağrı izi` zincirini **canlı** API'ye karşı çalıştırır ve **ham çıktıyı**
basar. stdlib `urllib` (dış bağımlılık yok); `websockets` **isteğe bağlı** (WS kanıt
zinciri yakalama; prod imajında kurulu — `Dockerfile:41`, CI'da kurulu değil →
betik WS'siz de çalışır ve bunu **açıkça yazar**).

Çıkış kodları: `0` = döngü kanıtlandı · `1` = döngü KIRIK (sebeple) · `2` = ön koşul
sağlanmadı (API'ye ulaşılamadı) · `Ctrl-C` = `DOĞRULANMADI — döngü tamamlanmadı`.

### C · AJAN DETAYI + FİLTRE

- `selectedAgent` + `activeAgent` fallback zinciri: **seçili ajan → canlı ajan →
  kuyruğun ilk ajanı** (panel hiçbir zaman "ajan yok" deyip susmaz; sebep yazar).
- `filterText` (ajan/model/via/kaynak/hata kodu/URL/uyarı) + `statusFilter`
  (`all|running|queued|done|failed`) → `filteredLane`.
- Filtre boş sonucu: `YETERSİZ KANIT — filtreye uyan ajan yok. Neden: …` (sessiz
  boş kalmak yasak).
- Ajan detayı bloğu: girdi özeti, kanıt kimlikleri, çağrı kimlikleri, sorumluluk,
  uyarılar, hata — hepsi **canlı SoT**'tan (`$taskStatus.runs`).

### D · ÇAĞRI İZİ GEÇMİŞİ SAYFALAMASI

- **Backend:** `agent_core/aspasia/interface.py` →
  `TelemetryReader.window(offset, limit)` (ofset **yeniye doğru** sayar: `offset=0`
  en yeniler), `TelemetryReader.total()`, `TelemetryReader.log_call_ids()`.
- `CallBinder.bind(run_view, offset, limit)` → **üç küme AYRI**:
  `bound_call_count` (günlükte var mı?) · `page_call_count` (bu sayfada kaç?) ·
  `page_missing_call_ids` (günlükte var ama başka sayfada) · `missing_call_ids`
  (günlükte **hiç** yok → gerçek kopukluk, `missing_reason` yazılır).
- **Uç:** `GET /api/aspasia/state?client_id=…&offset=…&limit=…` → `calls`,
  `call_window` (`offset`/`limit`/`total`), `call_binding`.
- **Panel:** `← DAHA ESKİ` · `DAHA YENİ →` · `CANLIYA DÖN` düğmeleri; durum ucuna
  `&offset=${callOffset}&limit=${CALL_PAGE}` gider. Kayıt **uydurulmaz** — pencere
  kayar.

### E · MONOLİT KIRMA (tavan YÜKSELTİLMEDİ)

`backend/api.py` → **`backend/services/aspasia_state.py`** (`build_state_payload`):
state gövdesi modüle taşındı; `api.py` yalnız `app.get(...)` ile kaydeder ve
bağımlılıkları **enjekte** eder (dairesel bağımlılık yok).

```
$ wc -l backend/api.py
5760 backend/api.py          # P8 öncesi: 5772  →  -12 satır
```

Tavan: `tests/unit/test_api_monolith_ratchet.py` → `MAX_LINES = 5772 → 5760`
(ölçülebilir ilerleme: `MEASURED_AFTER_SIXTH_SPLIT = 5760`).

---

## 2 · CANLI ÖLÇÜM (bu sandbox'ta GERÇEKTEN koşturuldu)

### 2.1 Doğrulama betiği — erişilemeyen API ( dürüst hata yolu)

```
$ .venv/bin/python scripts/verify_command_loop.py --url https://instagram.com/x/ \
      --base-url http://127.0.0.1:9 --timeout 5 ; echo "RC=$?"
[1/5] ÖN KOŞUL: API'ye ulaşılamadı → URLError: <urlopen error [Errno 111] Connection refused>
  Sebep: sunucu çalışmıyor ya da adres/port yanlış.
  Çözüm: uvicorn ile API'yi başlat (bkz. RUNBOOK 'Başlatma').
RC=2
```

### 2.2 Doğrulama betiği — CANLI API (uvicorn `0.0.0.0:8000`)

```
$ .venv/bin/python scripts/verify_command_loop.py --url https://instagram.com/test_user/ --timeout 20
[1/5] ÖN KOŞUL: API erişilebilir · kayıtlı ajan: 13

[2/5] KOMUT: POST /api/aspasia/command
  HTTP 200 · gövde: {'command_id': '54596c512a11', 'accepted': False, 'intent': 'none',
                    'task_id': None, 'reason': 'intent_unavailable'}

[3/5] GÖREV DURUMU (poll)
  görev durumu: ÖLÇÜLEMEDİ (boş)
  canlı ajan: ÖLÇÜLEMEDİ (boş)
  planlanan ajanlar: ÖLÇÜLEMEDİ (boş)
  ajan koşu kayıtları:
    - ÖLÇÜLEMEDİ (koşu kaydı yok)

[4/5] ÇAĞRI İZİ + KİMLİK BAĞI
  görünen çağrı: 1 · günlük toplamı: 1 · koşu çağrısı: 0 · bağlı çağrı: 0
  günlükte olmayan kimlik: yok
    - 0f18a38d-… · ajan=aspasia · model=anthropic/claude-sonnet-5 · süre=0 ms ·
      maliyet=$0.000000 · bağlı=koşuya bağlı değil
  NOT: 1 çağrı hiçbir koşuya bağlı değil (koşu dışı çağrı — ör. aspasia niyet çağrısı)
  — bu bir kopukluk DEĞİLDİR.

[5/5] PANELİN GÖRDÜĞÜ ALANLAR
  bütçe (harcanan): $0.000000
  kota: {'groq': 'healthy', 'cerebras': 'healthy'}
  anomaliler: {'fallbacks': [{'model': 'anthropic/claude-sonnet-5',
                              'provider': 'openrouter', 'reason': 'RUNTIMEERROR'}], …}
  WS snapshot sayısı: 0 · WS sonuç karesi: 0 · kanıt zinciri satırı: 0

========================================================================
SONUÇ: DÖNGÜ KIRILDI
  - komut kabul edilmedi (reason=intent_unavailable)
  Kanıt yukarıdaki ham çıktılardır; hiçbir değer uydurulmadı.
```

**Bu çıktı neden "KIRIK" diyor?** Çünkü 9Router/LLM bu sandbox'ta
erişilemiyor (`fallbacks: … RUNTIMEERROR`) → Aspasia **niyet çıkaramadı** →
komut reddedildi (`accepted:false`). Betik **görevi uydurmadı**, `task_id`
uydurmadı; gerçek `reason`'u bastı. (P7'de aynı komut, niyet akışı canlıyken
`accepted:true` + gerçek `task_id` üretti — o kanıt P7 raporundadır.)

### 2.3 WS kanıt zinciri yakalama (gerçek kare biçimiyle doğrulandı)

`WsCapture` sınıfı backend'in **gerçek** kare biçimini taklit eden ayrı bir WS
sunucusuyla doğrulandı (kare şekli `backend/api.py:2225` ve `:2876`'dan kopyalandı):

```
$ .venv/bin/python /tmp/ws_capture_probe3.py
WS başlatıldı: True | hata: None
snapshot sayısı: 1
sonuç karesi: 1
kanıt zinciri satırı: 2
  zincir: mirror_truth | mirror | {'status': 'ok', 'notlar': 'örnek'}
  zincir: human_behavior | None | {'status': 'ok'}
snapshot.current_agent: osint_investigator
snapshot.channel_status: [{"channel": "instagram.scrape", "status": "ok", …}]
```

Yani: WS karesi alınıyor, `evidence_chain` satırları ayrıştırılıyor, ajan bazında
gruplanabiliyor.

---

## 3 · TEST + KALİTE ÖLÇÜMÜ

| Ölçüm | Komut | Sonuç |
|---|---|---|
| Panel testleri | `pytest tests/unit/test_live_control_panel.py -q` | **29 passed** (P7'de 17 → **+12 yeni P8 testi**) |
| Monolit tavanı | `pytest tests/unit/test_api_monolith_ratchet.py -q` | **18 passed** (+2) |
| Lint | `ruff check .` | **All checks passed!** (P8 başlangıcında 2× F541 → düzeltildi) |
| Frontend tip kontrolü | `npm run check` | **0 errors / 0 warnings** |
| Frontend derleme | `npm run build` | ✓ built (index **180.53 kB**) |
| Tam koşu | `pytest tests -q --cov --cov-fail-under=80` | **Aşağıdaki "tam koşu" bölümü** |
| Revert-doğrulama | `/tmp/revert_check.py` | **10/10 PASS** |

### 3.1 Yeni testler (12 panel + 2 ratchet)

**Backend (canlı çalıştırılır):**
- `test_state_endpoint_paginates_call_trace` — sayfalama gerçekten kaydırıyor
  (5 kayıt → `offset=0` → son 2 · `offset=2` → ortadaki 2 · `offset=50` → **boş liste**;
  `call_window.total` kırpılmıyor).
- `test_call_binder_separates_log_missing_from_page_missing` — üç küme ayrımı.
- `test_telemetry_window_returns_older_records` — pencere kayması + `total()` +
  `log_call_ids()`.
- `test_aspasia_state_body_lives_in_its_own_module` (ratchet) — gövde `api.py`
  içinde **kopyalanmış** değil; import satırı birebir doğrulanır.
- `test_api_shrank_after_sixth_split` (ratchet) — tavan 5760.

**Frontend (statik kontrat + dürüstlük):**
- `test_panel_renders_output_summary_line_by_line`
- `test_panel_renders_evidence_chain_grouped_by_agent`
- `test_panel_has_agent_filter`
- `test_panel_paginates_call_trace`
- `test_panel_shows_next_agent_and_agent_detail_block`
- `test_panel_marks_call_ids_outside_visible_window`
- `test_panel_reports_empty_output_summary_honestly`

**Betik (gerçekten çalıştırılır):**
- `test_verify_command_loop_script_reports_unreachable_api` — **subprocess** ile
  betik koşturulur, `rc=2` ve "ulaşılamadı" çıktısı doğrulanır.
- `test_verify_command_loop_script_has_no_fabricated_rows` — uydurma veri kalıbı
  yasak.

### 3.2 Revert-doğrulama (her düzeltme geri alınınca test KIRMIZI)

`/tmp/revert_check.py` → **10/10 PASS** (her vaka: revert uygula → test KIRMIZI →
geri yükle → test YEŞİL):

| Vaka | Revert | Kırmızıya düşen test |
|---|---|---|
| R1 | state ucu `offset`'i yok sayıyor | `test_state_endpoint_paginates_call_trace` |
| R2 | `TelemetryReader.window` ofseti yok sayıyor | `test_telemetry_window_returns_older_records` |
| R3 | `CallBinder` sayfa/günlük ayrımını yapmıyor | `test_call_binder_separates_log_missing_from_page_missing` |
| R4 | Panel `output_summary` başlığını düşürüyor | `test_panel_renders_output_summary_line_by_line` |
| R5 | Panel zinciri gruplamıyor | `test_panel_renders_evidence_chain_grouped_by_agent` |
| R6 | Panel filtresi kaldırılıyor | `test_panel_has_agent_filter` |
| R7 | Panel ofseti göndermiyor | `test_panel_paginates_call_trace` |
| R8 | Betik erişilemeyen API'de de `rc=0` diyor | `test_verify_command_loop_script_reports_unreachable_api` |
| R9 | `api.py` state modülünü içe aktarmıyor | `test_aspasia_state_body_lives_in_its_own_module` |
| R10 | `api.py` 6 satır büyüyor (tavan aşımı) | `test_api_module_is_within_the_size_ceiling` |

> R5/R6/R9 ilk denemede **yeşil kaldı** (test, revert'in kaldırdığı şeyi değil
> başka bir işareti ölçüyordu) → testler, revert'in tam olarak söktüğü ifadeyi
> ölçecek şekilde **sıkılaştırıldı** (`Object.keys(evidenceByAgent)`,
> `agentLane.filter((run) =>`, `^… import build_state_payload$`).

### 3.3 Tam koşu

```
$ .venv/bin/python -m pytest tests -q --cov --cov-fail-under=80
2840 passed, 8 skipped, 322 warnings in 220.85s (0:03:40)
Required test coverage of 80% reached. Total coverage: 92.58%
```

> Not: ilk koşuda **3 kırmızı** vardı — `test_inventory_page.py` (2) ve
> `test_audit_regression.py` (1): envanter **bayattı** (yeni dosyalar: modül +
> betik + rapor). Kural uygulandı: kod → envanter/audit yenile → tam koşu.
> Yenileme sonrası final koşu **2840 passed, 8 skipped** (tamamen yeşil).

---

## 4 · DEĞİŞEN DOSYALAR

| Dosya | Değişiklik |
|---|---|
| `backend/services/aspasia_state.py` | **YENİ** (84 satır) — `build_state_payload` (state gövdesi; `offset`/`limit` sayfalama) |
| `backend/api.py` | **5772 → 5760 satır** — state gövdesi modüle taşındı; uç `offset`/`limit` parametrelerini kabul ediyor |
| `agent_core/aspasia/interface.py` | `TelemetryReader.window/total/log_call_ids` · `CallBinder.bind(run_view, offset, limit)` (3 küme ayrımı) |
| `frontend/src/components/LiveControlPanel.svelte` | **P8 ile yeniden yazıldı** (920 satır): 6 blok, filtre, ajan seçimi, `output_summary`, `evidence_chain`, sayfalama |
| `scripts/verify_command_loop.py` | **YENİ** (390 satır) — canlı komut döngüsü doğrulayıcı (WS kanıt yakalama opsiyonel) |
| `tests/unit/test_live_control_panel.py` | 17 → **29** test (+12 P8) |
| `tests/unit/test_api_monolith_ratchet.py` | 16 → **18** test (+2) · `MAX_LINES` 5772 → **5760** |
| `docs/envanter.html` · `reports/audit_regression.json` | yeniden üretildi |
| `README.md` · `RUNBOOK.md` · `CHANGELOG.md` | P8 kayıtları |

**Değişmeyenler (bilinçli):** kasa (vault) kapıları, çocuk kilidi, `ENABLE_*`
bayrakları, egress politikası, ajan listesi, model seçimi, fiyat mantığı.

---

## 5 · DOĞRULANMADI (sebebiyle)

| Ne | Sebep |
|---|---|
| Panelin **görsel** doğrulaması (tarayıcıda gerçek görevle) | Sandbox'ta headless tarayıcı/Playwright chromium binary yok; panel **statik kontrat + derleme** ile doğrulandı, **görsel olarak görülmedi** |
| Canlı **9Router/LLM** niyet çıkarımı → `accepted:true` → gerçek görev → **kanıt zincirinin canlı görevden** okunması | 9Router `127.0.0.1:20128` bu sandbox'tan erişilemiyor (HTTP 000) → `intent_unavailable`; komut **reddedildi** (dürüst yol kanıtlandı). P7'de canlı komut→görev→9 ajan→kanıt ölçülmüştü; P8'de **aynı zincir canlı olarak TEKRARLANAMADI** |
| WS kanıt zincirinin **gerçek görevden** gelen kareyle okunması | Bölüm 2.3'te kare **biçimi** gerçek koddan kopyalanarak doğrulandı; canlı görevden gelen kare **görülmedi** (komut reddedildi) |
| Canlı Instagram/X kazıma | Playwright chromium binary yok + egress kapalı |
| `websockets` paketinin **CI** ortamında kurulu olması | `requirements.lock` içinde yok; prod imajında `Dockerfile:41` ile kuruluyor. CI'da betik WS yakalamayı **açıkça kapatıp** sebebini yazar (sessizce boş geçmez) |
| Panelde `ENABLE_*` bayraklarının tamamı açık hâli | Kapılar kapalı tutuldu (görev talimatı) |

---

## 6 · KANIT ÖZETİ (tek satır)

P8: panel 6 bloklu "en donanımlı" sürüme çıktı (muhakeme + satır satır çıktı +
gruplu kanıt zinciri + ajan detayı + metin/durum filtresi + çağrı izi sayfalaması),
canlı komut döngüsünü çalıştıran **dürüst** doğrulayıcı betik eklendi
(erişilemeyen API'de `rc=2`, kırık döngüde `rc=1`, sebeple birlikte),
`backend/api.py` **5772 → 5760** satıra indi (tavan yükseltilmedi; yeni modül
`backend/services/aspasia_state.py`), **12 yeni test** eklendi ve
**revert-doğrulama 10/10 PASS** ile her düzeltmenin kırmızıya döndüğü kanıtlandı.

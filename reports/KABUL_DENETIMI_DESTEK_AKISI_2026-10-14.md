# KABUL DENETİMİ — “Kanıtsız başarı yasak; görev sahipsiz bırakılmaz”
**Tarih:** 2026-10-14 · **Repo:** AppleCurse/pineal-epifiz (yerel checkout) · **Dal:** `arena/9f569e49-pineal-epifiz`
**Başlangıç commit:** `5a6886cfa4275756437bba193b0944b7fdfcea35` (main'den ayrılma noktası) · **Bu oturumda commit/push/PR/dağıtım YAPILMADI.**
**Sürüm bağlamı:** Python 3.11.2 · ana venv `/home/user/.venv-pineal` · kilit venv `/home/user/.venv-lock`

---

## 1. DEĞİŞİKLİK ENVANTERİ

### 1.1 Bu turda değişen dosyalar (A-path üstünde, asgari bağlantı)

| Dosya | Amaç | Kanıt |
|---|---|---|
| `agent_core/domain/memory_models.py` | `TaskSnapshot`'a **ekleyici** iki alan: `support_requests` (:129), `ingested_outputs` (:132) | JSON uyumu: eski alanlara dokunulmadı |
| `agent_core/task_executor.py` | (a) `execute_task(..., resume_from=)` (:936) + tohumlama bloğu (seed + destek `resolved` :1040-1055, `RESUME:` logu :1051); (b) yardımcılar `_resume_done` (:648), `_record_ingested` (:654), `_request_support` (:665) — kayıt + `AwaitingHumanEvent` + `DESTEK TALEBİ` logu (:703); (c) iki rota döngüsünde atlanma koruması (:1526, :1900); (d) `copy.deepcopy` işaretçisi + yutulan-çıktı farkı (:1871, :2241); (e) 6 destek çağrısı (:1627, :1714, :1766, :2039, :2110, :2158); (f) ana döngü deep-fail “zombi koşu” onarımı (durum+mühür+talep); (g) döngü-dışı osint/depth/shadow bloklarında resume koruması (:1152, :2287, :2364) | AST-parse her adımda OK |
| `agent_core/agents/osint_investigator.py` | `aiohttp.ClientSession` (:299) ÖNCESİ kasa kapısı (:281-285): kilitliyken istek hiç kurulmaz, dürüst `vault_locked` profili döner (geniş `except` yutması önlenir) | test E |
| `agent_core/services/search_engine.py` | Kilitli-kasa logu hassas sorgu içermez (:111) | test E caplog |
| `scripts/run_task.py` | stdin `"resume"` anahtarı → `execute_task(resume_from=...)` (:120-133); `"resume"` asla `input_data`'ya girmez | test CLI |
| `tests/audit/test_support_flow_acceptance.py` | **YENİ** — A–I + CLI resume halkası (10 test) | bölüm 3 |
| `tests/audit/test_responsibility_rules.py` | Sayımlar güncellendi (6 mühür, 6 destek çağrısı) + şema/davranış kilitleri eklendi | 22/22 |

Önceki A-path değişkileri (25 dosya, egress/vault_gate/responsibility/testler) korunmuştur; `backend/api.py` = **5997/6000** (ratchet: `tests/unit/test_api_monolith_ratchet.py`, 6 passed).

### 1.2 Çalıştırılan komutlar, ortamlar, çıkış kodları

| # | Komut | Ortam | Sonuç / EXIT |
|---|---|---|---|
| 1 | `python -m pytest tests -q -p no:cacheprovider` | `.venv-pineal` | **2431 passed, 0 failed, 8 skipped — EXIT 0** |
| 2 | `python -m pytest tests/audit/test_support_flow_acceptance.py -q` | `.venv-pineal` | **10 passed — EXIT 0** |
| 3 | `ruff check agent_core scripts tests --select E9,F` | `.venv-pineal` | **All checks passed — EXIT 0** |
| 4 | `python3 scripts/audit_regression.py` | sistem py | **BEKÇİ GEÇTİ, açık:0 — EXIT 0** |
| 5 | `python -m pytest tests/unit/test_api_monolith_ratchet.py` | `.venv-pineal` | **6 passed — EXIT 0** |
| 6 | Negatif matris (bkz. §4.2): 5× (kopya repo + hata geri + bekçi + hedefli test) | `/tmp/negmat/*` | Her 5'inde **bekçi EXIT 1 + test EXIT 1** |
| 7 | `python -m venv ~/.venv-lock && pip install -r requirements.lock` | temiz venv | **INSTALL EXIT 0** (166 sabit) |
| 8 | `pip install pytest==9.1.1 pytest-asyncio==1.4.0` | `.venv-lock` (yalnız test aracı; ana env ile birebir sürüm) | EXIT 0 |
| 9 | `python -m pytest tests -q -p no:cacheprovider -rs` | **`.venv-lock`** | **2437 passed, 0 failed, 2 skipped — EXIT 0** |

### 1.3 Eski bulgu kimlikleri → bu tur onarımları

| Eski revize kontrol | Ne ölçüyor (eski model `audit_verify_stale` ile) | Bu turdaki durum |
|---|---|---|
| **E-GÖZ1-1** | Tek satır `logger.warning.*fallback` kalıbı → çok satırlı log + `pass`'siz istisna | Kapalı; §4.2 negatif 1-1 |
| **E-GÖZ1-3** | `^import httpx$` satır başı sayımdı → artık **inşa** ölçülüyor (`httpx.AsyncClient(` yalnız egress) | Kapalı; negatif 1-3 |
| **E-GÖZ1-6** | `await tracker.set_wait(...)` kalıbı yasaktı → kapanış arızası `logger.error+exc_info` ile ölçülüyor | Kapalı; negatif 1-6 |
| **E-GÖZ2-3** | Tek taraflı ölçüm (holehe tek kelime kapatıyordu) → **iki yaprak + kapı çağrısı** şart | Kapalı; negatif 2-3 |
| **E-GÖZ3-2** | Dosya geneli kelime araması → `PRODUCTION_REQUIRES_REDIS` ret + `DEGRADED_MODE` izi + beacon bayrağı | Kapalı; negatif 3-2 |
| **(yeni)** “destek akışı” açıkları | `support_requested` yazıyordu, **tüketen yoktu**; resume yoktu; osint aiohttp kapısızdı; kilitli-log sorgu sızdırıyordu | Bu turda onarıldı: §2-3 |

> Bu tur eski E-GÖZ kimliklerini **geri açmadı**; revize 5 kontrolün kalıpları yeniden yazıldıktan sonra **negatif geri-getirme** ile kırılabildiği gösterildi (§4.2). Kontrol/meta-testler tek başına bağımsız doğrulama olarak sunulmaz.

---

## 2. SORUMLULUK ZİNCİRİNİN GERÇEK DAVRANIŞI

### 2.1 Çağrı zincirleri (dosya:satır)

1. **Sözleşme/mühür:** `_responsibility_trail` (`task_executor.py:730`) → `agent_core.domain.responsibility.build_trail` → `seal_trail` kuralları; ihlalde **“SORUMLULUK İHLALİ”** ERROR + `integrity.violation`. `AgentRun.responsibility` alanı `memory_models`'da; başarı kanıtı `evidence_chain[*].responsibility` mührü.
2. **Kanıt yetersizliği:** belirsizlik düşük güven → mühür `evidence_recorded=False` + `InsufficientEvidenceError` (kritik ajan / `graceful_degradation:false`) → `_execute_task_impl` kuyruğu hatayı **yakalar**, `halted_evidence` döndürür (çıkış: dürüst durak, sahte `completed` YOK).
3. **Destek üretimi (YENİ, tüketici bağlı):** `_request_support` (`:665`) → ① `status.support_requests` kaydı (owner, options, next_action, pending), ② `AwaitingHumanEvent` (`schemas/telemetry.py:47`) → `execute_task` emit zinciri → `backend/api.py:1117-1119` (`sync_event` → `broadcast_event` :2120) → **WS ile operatöre ulaşır (backend'e dokunmadan)**, ③ `DESTEK TALEBİ` WARNING logu.
4. **Devam (resume):** `execute_task(..., resume_from=TaskStatus)` → tamamlananlar atlanır, `ingested_outputs` `input_data`'ya geri yüklenir, pending destekler `resolved` (`RESUME:` logu :1051); CLI: `scripts/run_task.py:120` (`"resume"` girdiden okunur).

**Önceki durum (ispat):** `support_requested` yalnızca mühür alanına yazıyordu (eski çağrı yerleri; tüketici grep ile 0) ve deep-fail ana döngüde koşuyu **işaretsiz** bırakıyordu (zombie run). Artık her destek kaydının `owner` + `next_action` + çözüm adımı (`resolution: resumed_with_support`) vardır.

### 2.2 Destek “gerçekten başlatıyor mu?” / eksik kanıt “sonlandırıyor mu?”

| Koşul | Davranış (kanıt) |
|---|---|
| Alternatif araç yetersiz (arama omurgası) | `asyncio.gather` ile izinli kardeş sağlayıcı denenir, hata `PARTIAL+error` ile dürüst yüzeye çıkar (`search_engine.py:114-160`; test A) |
| Belirsizlik + deep-research başarısız | Koşu `halted+SUSPICIOUS_EVIDENCE` mühürlenir + **destek talebi açılır** (test B); kritikte `InsufficientEvidenceError` |
| Düşük güven, `graceful=true` | destek talebi + göreve devam (kayıt dürüst) — test B dalı |
| Düşük güven, kritik/`graceful=false` | görev `halted_evidence` — test C 1. koşu |
| **Destek sağlandı** | `resume_from` ile devam; yan etki tekrarı yok — test C 2. koşu + I |
| VaultLocked / SpendCap / Timeout | özel seçenek listesi (`open_vault`/`raise_spend_cap`/`extend_timebox`) + sahipli bekleme — test E-3, G |
| Kanıt yetersiz → ek doğrulama | `deep_research` gerçekten çağrılır, kanıt zincirine `deep_research` kimliğiyle girer — test D |

### 2.3 Görev sahibi / sonraki adım / yeniden başlatma koşulu (açık)

- **Sahip:** `support_requests[*].owner = agent_name`; koşu sahibi `AgentRun.agent_name`.
- **Sonraki adım:** `support_requests[*].next_action` (örn. `task_halted_critical`, `rerun_deep_research_or_operator_review`) + mühürde `integrity.next_action`.
- **Yeniden başlatma koşulu:** operatör düzeltmeyi uygular (yetki/bütçe/süre/güven) ve **önceki TaskStatus JSON'unu** `resume` anahtarıyla geri verir; görev tamamlananlardan devam eder.

### 2.4 Durum makinesi: mevcut makine kullanıldı, yeni durum YOK

- **Yeni durum eklenmedi.** Mevcut `PipelineStatus` yeterli: `halted_evidence`, `halted_critical`, `timed_out`, `awaiting_authorization` (önceden var). Eklenenler yalnızca **alan**: `support_requests`, `ingested_outputs` (ekleyici JSON).
- **API/UI etkisi:** `backend/api.py`'e hiç dokunulmadı (ratchet 5997/6000); WS `AwaitingHumanEvent` şemada zaten vardı (`telemetry.py:47`) ve emit→WS bağlantısı mevcut. **Doğrulanmalı:** UI tarafının bu olayı görsel olarak işleyip işlemediği (bu oturumda arayüz tarafı çalıştırılmadı).

---

## 3. DAVRANIŞ TESTLERİ A–I

Dosya: `tests/audit/test_support_flow_acceptance.py` · Komut: `python -m pytest tests/audit/test_support_flow_acceptance.py -q` · **10 passed, EXIT 0**

| Senaryo | Test (satır) | Ne kanıtlıyor |
|---|---|---|
| **A** Birincil araç hata → izinli alternatif | `test_a_primary_tool_fails_alternative_serves` (:83) | SearXNG (birincil) düşer → DDG ayağa kalkar; `PARTIAL+error` saklanmaz |
| **B** Alternatif de düşer → destek **gerçekten** oluşur | `test_b_alternative_fails_real_support_request_created` (:125) | pending kayıt + `AwaitingHumanEvent` + mühür; sahte kanıt zincire girmez |
| **C** Destek geldi → görev kaldığı yerden devam | `test_c_support_arrives_task_resumes_where_it_left_off` (:166) | 1. koşu `halted_evidence`+pending; 2. koşu `resume_from` ile: tamamlanan atlandı, engelli çalıştı, destekler `resolved`, kanıt zinciri korundu |
| **C-CLI** resume halkası | `test_c_cli_resume_passthrough` (:523) | `run_task` `"resume"` → `RESUME:` akışı, exit 0 |
| **D** Kanıt yetersiz → sahte başarı yok + ek doğrulama | `test_d_insufficient_evidence_starts_extra_verification` (:237) | `deep_research` `awaited_once` + kanıt zincirinde |
| **E** Kasa kilitli → dış çağrı yok + yetki desteği | `test_e_locked_vault_no_external_call_and_authority_support` (:269) | arama: `VAULT_LOCKED`, 0 istemci, sorgu logda YOK; osint: `ClientSession` asla kurulmaz (`vault_locked` profil); görev: `open_vault/grant_boundary_authority` talebi |
| **F** Yetki → işaretsiz yeniden kontrol + temizlik | `test_f_authorization_is_request_scoped_and_rechecked` (:329) | child+grandchild devri görür; yeni görev `VaultLockedError`; test bağlamında işaret sızmaz |
| **G** Süre/maliyet sınırı → sınırsız tekrar yok | `test_g_time_and_cost_limits_hold_without_unbounded_retry` (:375) | execute 1×; `timed_out`/`SpendCapExceeded` mührü + owner + next_action + `extend_timebox`/`raise_spend_cap` talebi |
| **H** Eşzamanlı iki görev → izler karışmaz | `test_h_concurrent_tasks_isolate_authority_and_attempts` (:426) | işaretli görev yalnız kendi izini görür; işaretsiz kilitli; ana bağlam temiz |
| **I** Yeniden denemede yan etki tekrarı yok | `test_i_rerun_skips_completed_side_effects` (:466) | execute sayacı 1'de kalır; kanıt devralınır |

Ek doğrulamalar: `tests/audit/test_responsibility_rules.py` **22 passed** (mühür/destek/şema sayımları), `tests/unit/test_egress_single_spine.py`, `tests/integration/test_run_task_cli.py` — hepsi yeşil.

---

## 4. DENETÇİYİ DENETLE

### 4.1 Revize 5 kontrol: eski vs yeni ölçüt

| Kontrol | Eski ölçüt (hatalı model) | Yeni ölçüt (revize) | Bugünkü durum |
|---|---|---|---|
| 1-1 | tek satır `.*fallback` kalıbı | “backend sondası başarısız” log izi VAR + sessiz `except:pass` YOK | KAPALI |
| 1-3 | satır başı `import httpx` dosya sayısı | satır başı import **+** `httpx.AsyncClient(` inşası (egress dışı = 0), omurgaya bağlı 15 dosya | KAPALI |
| 1-6 | `set_wait` kalıp araması | AST'de `tracker.set_wait*` yasağı + “KAPANIŞ İZİ YAYINLANAMADI” log izi, `exc_info` | KAPALI |
| 2-3 | genel `is_locked` kelimesi + tek dosya | scraper **ve** holehe yapraklarında **kapı çağrısı** (`require_open`/`VaultLockedError`) | KAPALI |
| 3-2 | “production+raise” kelime araması | `PRODUCTION_REQUIRES_REDIS` ret + `DEGRADED_MODE` izi + beacon `degraded_mode` bayrağı birlikte | KAPALI |

**Testler “yeni implementationsa uyarlanmış” mı?** Hayır: §4.2'de bu testler, uygulamadan **bağımsız** olarak kopya depolara geri getirilen eski hatalarla kırıldı. Bekçinin kendisi de geri-getirilen her hatada EXIT 1 verdi.

### 4.2 Negatif geri-getirme matrisi (test VE bekçi kırılmalı)

Her satır: `/tmp/negmat/<id>` kopya repo → eski hata geri getirildi → `python3 scripts/audit_regression.py` + hedefli pytest.

| Check | Geri getirilen hata | Bekçi | Hedefli test (EXIT 1 alanlar) |
|---|---|---|---|
| **1-1** | `agent_worker` probe istisnası → `pass  # Backend yoksa sessizce devam` | **EXIT 1**, `E-GÖZ1-1 AÇIK ⟵ REGRESYON` | `test_responsibility_rules::TestNoSilentFallback::test_probe_failure_logs_fallback` (**ürün-sözleşme**) + `test_audit_regression` ×6 (meta) |
| **1-3** | `translation.py` başına satır başı `import httpx` | **EXIT 1**, `E-GÖZ1-3 AÇIK` | `test_egress_single_spine::test_no_line_start_httpx_import_outside_egress` (statik omurga kilidi) |
| **1-6** | kapanış `logger.error(exc_info)` bloğu → `pass` | **EXIT 1**, `E-GÖZ1-6 AÇIK` | `test_responsibility_rules::test_closure_publish_failure_logs_error` + meta ×6 |
| **2-3** | `run_scraper` + `holehe_scanner` kapı çağrıları silindi | **EXIT 1**, `E-GÖZ2-3 AÇIK` | `test_responsibility_rules::TestLeafVaultDoors::test_run_scraper_cli_gate_is_strict` + `::test_holehe_scan_gates_after_enabled_and_sanitize` |
| **3-2** | `PRODUCTION_REQUIRES_REDIS` raise'leri yumuşak fallbacke çevrildi | **EXIT 1**, `E-GÖZ3-2 AÇIK` | `test_responsibility_rules::test_production_fallback_is_hard_refusal` |

**Dürüst sınıflandırma (kontrol/meta-test bağımsız doğrulama sayılmaz):**
- 1-1, 1-6, 3-2, 2-3 asıl olarak **statik/kayıt sözleşmesi testleriyle** kilitli; 3-2'nin davranışsal ikizi `test_task_lifecycle` bu negatifte **kırılmadı** → **açık kapsam notu:** üretim-ret davranış testi geri-getirilen raise varyantını birebir kapsamıyor (kayıt altında “doğrulanmalı”).
- 1-3'ün tek kilidi omurga statik taramasıdır; davranışsal ayrım (egress üzerinden giden çağrılar) `test_egress_single_spine` içindeki üretim-kilitli-vault testleriyle desteklenir.
- Tüm matriste **asla** “bekçi geçti = doğrulandı” sunulmadı; her satırda test de kırıldı.

---

## 5. DIŞ ÇIKIŞ KAPSAMI

**“httpx import sayısı sıfır” ≠ “tüm dış çıkışlar denetimli”** — iki ayrı iddia; ölçüm ayrımı:

| Yol | Envanter (dosya:satır) | Denetim durumu |
|---|---|---|
| **httpx** | `httpx.AsyncClient(` inşası **yalnız** `capabilities/egress.py`; satır başı `import httpx` egress dışı **0** dosya (1-3 negatifi) | ✅ tek sırt (`open_client`, 15 bağlı dosya) |
| **aiohttp** | `osint_investigator.py:299` tek `ClientSession` | ✅ **bu turda** kapıyla sarıldı (:281-285); kilitliyken oturum kurulmaz, `VAULT_LOCKED` profili döner — test E (`ClientSession` bilinçli patlatılır, hiç girilmez) |
| **urllib** | `mcp/state_bridge.py:102` `_opener.open(...)` **omurga dışı tek çağrı** | ⚠️ **KISMEN KONTROLLÜ:** `api_base_url` yalnız `LOCAL_API_HOSTS` (yerel API) kabul eder, scheme+host doğrular, kilit okunamazsa fail-closed. Genel internete açık değil ama **egress sırtının dışında** → raporlanan eksik halka |
| **requests** | dosya içi `requests.get/post/urlopen` çağrı taraması **0 isabet**; kalan kullanımlar yalnız `urllib.parse` (lilith_growth, provider_manager, security, adapters_voice) | ✅ ayrım: “import var, çağrı yok” |
| **playwright/tarayıcı** | `run_scraper.py:33` (strict `require_open` ÖNCESİ — sözleşmesi testli), `browser_session.py:157` (`vault_guard` api:1278-1293), `platform_registry.py:280` (`vault_locked` politikası) | ✅ katmanlı (yaprak+politika); “tüm tarayıcı yolları” iddiası **yalnız bu üç giriş için** geçerli |
| **subprocess** | media_forensics (ffmpeg), report_factory, translation, company_recon, adapters_sensors/voice — **yerel alt süreç**, ağ çağrısı yok | ✅ ağ egressi sayılmaz; envanter olarak kayıtlı |

**Reddedilen girişimlerin denetim izi (dışarıya hiçbir şey çıkmaz):**
- `egress_attempts()` kilitli aramada **boş** (istemci hiç kurulmaz) — test E-1.
- osint kilitli log yalnızca `amaç=osint` içerir, kullanıcı adı **yok** — test E-2 (`hedef_kullanici not in caplog`).
- arama kilitli logunda sorgu terimi **yok** (`search_engine.py:111`).

**ContextVar (yetki/deneme) yayılımı, geç kilit, temizlik:** test F (child→grandchild devri + yeni görevde eski işarete güvenmeyip yeniden kontrol + test sonunda `vault_egress_authorized() is False`) ve test H (eşzamanlı iki görevde izler ayrık, ana bağlam boş).

**Açık halkalar (destek akışında eksik bağlantılar):**
1. **Resume endpoint'i YOK** — backend'de görev deposu yok (`sync_snapshot` yayınlayan, saklamayan tek yönlü akış) + api.py'de yalnız 3 satır ratchet payı. Uygulama **bilinçli** olarak yalnızca executor-kwarg + CLI `resume` ile kapatıldı; kalıcı depolu HTTP devam noktası **büyük mimari refaktör** gerektirdiğinden yapılmadı (kapsam dışı bırakıldı, burada kayıtlı).
2. **UI tarafı `AwaitingHumanEvent` işleme** — sunucu yolu hazır, istemci işleyişi **doğrulanmalı**.

---

## 6. TAM ORTAM (requirements.lock)

### 6.1 Kurulum ve çalıştırma

```
python3 -m venv /home/user/.venv-lock
pip install --no-cache-dir -r requirements.lock     → INSTALL_EXIT=0 (166 pin)
pip install pytest==9.1.1 pytest-asyncio==1.4.0     → test aracı (ana env ile birebir sürüm)
python -m pytest tests -q -p no:cacheprovider -rs   → LOCK_SUITE_EXIT=0
```

**Sonuç: 2437 passed, 0 failed, 2 skipped (131,2 s).** `python-multipart`, `crawl4ai`, `aiohttp`, `playwright`, `opencv-headless 4.14` dahil ürün zorunlu paketler lock'tan kuruldu (`import aiohttp,httpx,requests,cv2,multipart,fastapi` OK).

### 6.2 Sekiz atlanan testin TEKER TEKER gerekçesi (ana env − kilit env farkı dahil)

| # | Atlanan (ana env) | Gerekçe | Kilit envde |
|---|---|---|---|
| 1-4 | `test_speech_api_faz_c` ×4 — `No module named 'multipart'` | ana env test eklentisi eksikti; **ürün zorunlu** `python-multipart` lock:122'de | ✅ **çalıştı (skip yok)** |
| 5 | `test_consolidation_faz1_5:153` — crawl4ai yok | ana envde eksik; lock'ta var | ✅ **çalıştı** |
| 6 | `test_gorev2_artiklar:158` — “PIL kurulu; None-dali bu ortamda calismaz” | Testin PİLSİZ ortam dalı; PIL kurulu olduğu için bu dal **çalıştırılamaz** (dal davranışının PIL-sız koşu için) | ⏭️ kaldı — gerekçeli |
| 7-8 | `test_no_mock_in_production` ×2 — “open-interpreter opsiyonel katmandır (requirements-interpreter.txt)” | Opsiyonel eklenti katmanı, kilit kapsamı dışında; çekirdek ürüne ait değil | ⏭️ kaldı — gerekçeli |

Ürün için zorunlu olup **çalıştırılmadan “geçti” sayılan test YOKTUR** (4+2 ürün testi lock ortamında fiilen geçti; kalan 2 skip gerekçeli opsiyonel/dal testleridir). **Kilit ortam kuruldu ve tam paket EXIT 0 ile bitti.**

---

## KABUL HÜKMÜ

1. **Doğrulanmış sonuçlar:** A–I + CLI resume senaryolarının tamamı gerçek yürütme akışında geçti (10/10); sorumluluk mühür sözleşmeleri 22/22; tam paket ana ortamda 2431/0, **kilit ortamda 2437/0**; bekçi açık:0 EXIT 0; ruff E9+F temiz; ratchet 5997/6000. Beş revize kontrolün beşi de geri-getirme ile **hem bekçi hem hedefli test düzeyinde** kırıldı.
2. **Yalnızca bildirilen (çalıştırılmayan):** UI'da `AwaitingHumanEvent` görsel işlenişi; 3-2'nin davranışsal görev testinin raise varyantı kapsamaması; state_bridge yerel-urllib yolu — hepsi bu raporda “doğrulanmalı” işaretli.
3. **Destek akışında eksik halkalar:** kalıcı depolu resume **endpoint'i** (kapsam dışı, gerekçe §5) ve istemci tarafı olay işleme.
4. **Komut+sonuç kanıtları:** §1.2 tablosu (hepsi bu oturumda çalıştırıldı, exit kodları kayıtlı).
5. **HÜM:** **KABUL** — ana hedef (kanıtsız başarı yasak; görev sahipsiz bırakılmaz; destekle kaldığı yerden devam) asgari değişikliklerle, mevcut durum makinesi ve mevcut WS/API yüzeyi kullanılarak kapatıldı; güvenlik kapıları **gevşetilmedi** (kapılar eklendi, loglar temizlendi), büyük mimari refaktör **yapılmadı**, commit/push/PR/dağıtım/ücretli dış çağrı **yapılmadı**.

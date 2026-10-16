# DUZELTME · FAZ 2 · P0 — "DÜRÜST DURUM" (2026-10-16)

Faz 1 denetimi: `docs/reports/DENETIM_2026-10-16.md` (10 bölüm, 718 satır).
Bu belge **yalnız P0** düzeltmelerini kapsar (onay sırası: P0 → P1 → P2 → P3 → P4).

Taban (düzeltme öncesi): `2628 passed, 4 skipped` · `ruff check .` → `All checks passed!`
Düzeltme sonrası: `2658 passed, 4 skipped` · `ruff check .` → `All checks passed!`

> **Kanıt kuralı:** Bu belgedeki her satır bir komut çıktısına veya `dosya:satır`
> referansına dayanır. Çalıştırılamayan hiçbir şey "DOĞRULANMADI" olarak
> işaretlenmiştir; tahminle doldurulmamıştır.

---

## 0. Özet — P0'da değişen 5 gerçek

| # | Bulgu (Faz 1) | Düzeltme | Kanıt |
|---|---|---|---|
| B-2 | Arama sonucu (snippet) `target_profile.posts` alanına yazılıyordu; 9 tüketici onu "gönderi" diye okuyordu | `posts` artık yalnız platform gönderileri; snippet'lar `search_snippets` altında **kanıt tipiyle** (`search_snippet`) | `backend/services/web_dossier.py:80-113` · `agent_core/domain/content_basis.py:112-220` |
| B-1 | X sensörü boş twscrape havuzunda sebebi `user_not_found` (yani "kullanıcı yok") yazıyordu | Havuz ölçülür; boşsa sebep `no_session_pool` | `agent_core/capabilities/adapters_sensors.py:176-192` |
| B-2b | UI "N sosyal profil ve açık veri bağlandı" / "BAĞLANAN CANLI PROFİLLER" yalanı | Metinler ölçülen gerçeğe bağlandı; "ÇALIŞMADI: sebep" bloğu eklendi | `frontend/src/components/TacticalWarRoom.svelte` |
| B-3 | `/api/telemetry` "kapalı" diyordu, **NEDEN** yoktu | `capabilities[]` (her satırda `reason`) + `x_scraper_reason` | `backend/routes/telemetry.py:91-133` |
| B-4 | `twscrape.API()` çalışma dizinine `accounts.db` yazıyordu → depo kökü kirleniyordu | DB yolu yapılandırılabilir (`PINEAL_X_ACCOUNTS_DB`, varsayılan `cache/x_accounts.db`) | `agent_core/capabilities/adapters_sensors.py:72-135` |

Ek P0 teslimatı: **kanal durumu defteri** (`ok` / `not_run`+sebep / `failed`) →
WebSocket telemetrisi, görev snapshot'ı, hüküm belgesi, rapor paketi ve UI'a
taşındı. Boş liste dönmek artık mümkün değil.

---

## 1. Kanıt tipi ayrımı — "gönderi" ile "arama sonucu" AYRI

### 1.1 Gerçek (Faz 1) — düzeltme öncesi

`backend/api.py` (eski `:2575` → `:2596`):

```
snippets.append(f"[{r.provider.upper()}] {c}")
...
"posts": snippets or [],
```

9 tüketici bu alanı "hedefin gönderileri" diye okuyordu:
`target_psyche_profiler.py:47,64` ("Gönderi metni"), `authenticity_auditor.py:51`,
`human_behavior.py:92`, `resonance_synthesizer.py:62`, `lilith_growth.py:570`,
`frequency_engine.py:39`, `gravity_engine.py:27`, `void_engine.py:47`,
`pillar_evidence_adapter.py:53,352`.

### 1.2 Düzeltme — tek sözleşme modülü

Yeni: **`agent_core/domain/content_basis.py`** (220 satır).

| Alan | Anlam |
|---|---|
| `posts` | YALNIZCA platformdan kazınmış gönderi metni |
| `post_evidence_types` | `posts` ile **paralel** liste; her öğenin kanıt tipi |
| `search_snippets` | Arama sonucu snippet'ları (`{text, provider, source_url}`) |
| `content_basis` | Corpus'un TEK beyanı: `platform_post` \| `search_snippet` \| `mixed` \| `none` |

Kanıt tipleri: `platform_post` · `search_snippet` · `agent_reach_text` · `none`.

Tüketici kuralı (sözleşmede yazılı, kodda uygulanmış):

* **Hedefin kendi beyanı** iddiası kuran yerler (`authenticity_auditor`,
  `human_behavior`) YALNIZCA `platform_post` türünü okur — arama sonucu üçüncü
  taraf metnidir, hedefin beyanı DEĞİLDİR.
* **Genel muhakeme** yapan yer (`target_psyche_profiler`) snippet'ı da kullanır
  ama ETİKETİYLE: prompt'ta `[arama sonucu (hedefin gönderisi DEĞİLDİR)]`.
* **Ölçüm motorları** (`frequency`/`gravity`/`void`) yalnız `posts` okur →
  snippet koşusunda frekans iddiası ÜRETİLMEZ (dürüst boş).

### 1.3 Değişen dosya/satır kanıtı

```
agent_core/domain/content_basis.py             (YENİ, 220 satır; sözleşme :57-66)
agent_core/agents/target_psyche_profiler.py    :21, :45-65, :105-107, :196-198, :279-281
agent_core/agents/authenticity_auditor.py      :24, :50-60
agent_core/agents/human_behavior.py             :24, :91-101
agent_core/services/pillar_evidence_adapter.py :20, :108-115
agent_core/services/platform_registry.py       :213-215, :397-399, :450-451, :497-499
backend/services/web_dossier.py                (YENİ, 184 satır; :69-113 profil, :136-172 kanal)
backend/api.py                                 (web dosyası bloğu → modüle taşındı)
```

### 1.4 Canlı doğrulama

`content_basis` üretimi (örnek çalıştırma, `tests/unit/test_p0_honest_status.py`
içindeki testlerle aynı sözleşme):

```
$ .venv/bin/python -m pytest tests/unit/test_p0_honest_status.py -q -p no:cacheprovider
..............................                                           [100%]
30 passed in 1.96s
```

### 1.5 Test

```
tests/unit/test_p0_honest_status.py::test_search_snippet_is_not_a_post
tests/unit/test_p0_honest_status.py::test_platform_post_keeps_its_own_type
tests/unit/test_p0_honest_status.py::test_corpus_block_labels_snippet_and_does_not_call_it_post
tests/unit/test_p0_honest_status.py::test_web_dossier_never_marks_snippets_as_posts
tests/unit/test_p0_honest_status.py::test_target_psyche_profiler_labels_snippet_in_prompt
tests/unit/test_p0_honest_status.py::test_authenticity_auditor_ignores_snippets_as_self_declaration
tests/unit/test_p0_honest_status.py::test_human_behavior_reads_only_platform_posts
tests/unit/test_p0_honest_status.py::test_pillar_adapter_declares_content_basis
```

---

## 2. Kanal durumu defteri — "koşmadı" ile "bulunamadı" AYRI

Yeni: **`agent_core/domain/channel_status.py`** (182 satır).

```
ok       → çalıştı (kanıt üretti / kanıt üretmedi ama koştu)
not_run  → ÇALIŞMADI + ZORUNLU sebep (bayrak kapalı / kasa kilitli /
           bağımlılık yok / hesap havuzu boş)
failed   → çalışmayı denedi, hata/timeout oldu + sebep
```

`from_engine_result()` ayrım kuralı (kanıt sayısına göre):

| Durum | Sonuç |
|---|---|
| `available=True` | `ok` |
| `available=False` **ve** `scanned_count == 0` | `not_run` (kapı kapalı / kasa kilitli) |
| `available=False` **ve** `scanned_count > 0` | `failed` (koştu, sağlayıcı hataları) |

### 2.1 Nereye bağlandı

| Katman | Dosya:satır | Ne taşır |
|---|---|---|
| Görev payload'ı | `backend/api.py` (`payload["channel_status"]`) | X sensörü / web araması / IG kazıma satırları |
| Görev snapshot | `agent_core/domain/memory_models.py:141-145` (`TaskSnapshot.channel_status`) | kalıcı görev durumu |
| Görev yürütücüsü | `agent_core/task_executor.py:129-137, :1089-1091, :1292-1307` | maigret/holehe satırları |
| WebSocket | `backend/api.py` (`broadcast_result` → `"channel_status"`) | UI'ya anlık |
| Hüküm belgesi | `agent_core/services/verdict_synthesizer.py:37-52, 86-95` | "KOŞMAYAN KANALLAR:" bloğu |
| Rapor paketi | `agent_core/services/report_factory.py:153-196, 438` | "## Koşmayan kanallar" bölümü |
| Telemetri | `backend/routes/telemetry.py:91-133` | `capabilities[]` + `x_scraper_reason` |
| UI | `frontend/src/components/TacticalWarRoom.svelte` | "ÇALIŞMAYAN KANALLAR" bloğu |

### 2.2 Ölçülen çıktı (P0 testi, web dosyası koşusu)

`tests/unit/test_p0_honest_status.py::test_web_dossier_reports_channel_reasons`:
`search.web` → `ok`; `profile.deep_scan` → `not_run` (`reason` dolu).

### 2.3 Test

```
tests/unit/test_p0_honest_status.py::test_channel_status_never_returns_empty_reason
tests/unit/test_p0_honest_status.py::test_channel_summary_counts_and_lists_reasons
tests/unit/test_p0_honest_status.py::test_engine_result_mapping_distinguishes_not_run_from_failed
tests/unit/test_p0_honest_status.py::test_task_snapshot_carries_channel_status
tests/unit/test_p0_honest_status.py::test_verdict_digest_lists_channels_that_did_not_run
tests/unit/test_p0_honest_status.py::test_report_markdown_lists_channels_that_did_not_run
tests/unit/test_p0_honest_status.py::test_task_executor_carries_osint_channels
```

---

## 3. X sensörü — `no_session_pool` (Bulgu B-1)

Faz 1 ölçümü: boş havuzda twscrape `user_not_found` döndürüyordu → kullanıcı
"hedef yok" sanıyordu. Gerçek: **oturum hesabı yok**.

Düzeltme (`agent_core/capabilities/adapters_sensors.py:176-192`):

```python
api = _make_twscrape_api(API, _x_accounts_db_path())
pool_state = await _x_pool_state(api)
if pool_state is not None and pool_state["accounts_active"] == 0:
    return CapabilityResult(
        capability_id=self.id,
        available=False,
        unavailable_reason="no_session_pool",
        notes={"accounts_total": ..., "accounts_active": 0, "accounts_db": ...},
    )
```

* `_x_pool_state` (`:89-121`; `None` döner → havuz ÖLÇÜLEMEDİ → kapı uygulanmaz;
  ölçülmeyen şey "yok" diye yazılmaz).
* Makine-okunur sebep istisnaya taşınır:
  `platform_registry.scrape_x` → `setattr(error, "channel_reason", reason)` →
  `backend/api.py` kanal satırına `reason=reason` + `detail=insan-okunur metin`.
* **"Kullanıcı yok" ayrımı korunur**: havuzda AKTİF hesap varken
  `user_not_found` aynen durur (test: `test_x_sensor_keeps_user_not_found_when_pool_has_active_account`).

### 3.1 Bayrak kapalıyken sebep

Politika çekirdeği kapıyı `availability()`'den ÖNCE reddeder; bu yüzden sebep
`policy:gate_disabled` + `denied_by="ENABLE_X_SENSOR"` olur (mevcut
`policy:gate_disabled` sözleşmesi bozulmadı — `tests/unit/test_local_jury_capability.py`
aynı biçimi kilitliyor).

### 3.2 Test

```
tests/unit/test_p0_honest_status.py::test_x_sensor_reports_no_session_pool_not_user_not_found
tests/unit/test_p0_honest_status.py::test_x_sensor_keeps_user_not_found_when_pool_has_active_account
tests/unit/test_p0_honest_status.py::test_x_sensor_gate_disabled_reports_reason
```

---

## 4. `accounts.db` kirliliği (Bulgu B-4)

Faz 1: `twscrape.API()` → `AccountsPool(db_file="accounts.db")` → **çalışma
dizinine** yazıyordu; depo kökü kirleniyor, envanter testi kırmızıya dönüyordu.

Düzeltme (`agent_core/capabilities/adapters_sensors.py:72-135`):

| | |
|---|---|
| Env | `PINEAL_X_ACCOUNTS_DB` (tam yol) |
| Varsayılan | `cache/x_accounts.db` — `.gitignore`'daki `cache/` altında |
| Çağrı | `API(pool=db_path)` |
| Uyumluluk | `pool` kabul etmeyen uygulamalar için `TypeError` yakalanır → `API()` |

`.gitignore:59` `cache/` zaten ignore ediliyor → depo kökü artık kirlenmiyor.

### 4.1 Test

```
tests/unit/test_p0_honest_status.py::test_x_accounts_db_path_is_configurable_and_not_repo_root
tests/unit/test_p0_honest_status.py::test_x_sensor_does_not_write_accounts_db_into_cwd
```

---

## 5. Telemetri — "kapalı" değil, "NEDEN kapalı" (Bulgu B-3)

`GET /api/telemetry` yanıtına eklendi:

```json
{
  "capabilities": [
    {"id": "sensor.x.twscrape", "kind": "sensor", "license": "MIT",
     "available": false, "reason": "gate_disabled:ENABLE_X_SENSOR",
     "gates": ["ENABLE_X_SENSOR", "rate", "vault"],
     "policy_allowed": false, "policy_reason": "gate_disabled",
     "policy_gate": "ENABLE_X_SENSOR"}
  ],
  "capabilities_unavailable_reason": {"sensor.x.twscrape": "gate_disabled:ENABLE_X_SENSOR"},
  "x_scraper_reason": "gate_disabled:ENABLE_X_SENSOR"
}
```

Kaynak: **TEK kayıt defteri** — `agent_core/capabilities/registry.py:97-128`
(`registry.status(state)`). Kasa kilitliyse `vault_locked=True` ile
değerlendirilir; `gate_disabled:ENABLE_*` ile `vault_locked` birbirinden
AYIRT EDİLEBİLİR.

### 5.1 Test

```
tests/unit/test_p0_honest_status.py::test_telemetry_exposes_capability_table_with_reasons
tests/unit/test_p0_honest_status.py::test_telemetry_payload_has_capabilities_and_x_reason
```

---

## 6. UI — yalan metinlerin yerine ölçüm

`frontend/src/components/TacticalWarRoom.svelte`:

| Eski (yalan) | Yeni (ölçüm) |
|---|---|
| `N sosyal profil ve açık veri bağlandı` | `N gönderi kazındı · M arama sonucu (snippet — gönderi değil) · K profil URL'si bulundu (kazınmadı)` |
| `K PROFİL BULUNDU` | `N GÖNDERİ · K PROFİL (KAZINMADI) · M ARAMA SONUCU` / `KANAL ÇALIŞMADI` |
| `BAĞLANAN CANLI PROFİLLER:` | yalnız gerçek kazıma varsa; aksi hâlde `TESPİT EDİLEN PROFİL URL'LERİ (KAZINMADI):` |
| — | YENİ: `ÇALIŞMAYAN KANALLAR:` bloğu — kanal + sebep |

`frontend/src/lib/channelStatus.ts` (YENİ, 112 satır): makine-okunur sebebi
okunur Türkçeye çevirir; **bilinmeyen token aynen bırakılır** (yanlış çeviri
yanlış güven üretir).

`frontend/src/components/visualizers/NeuralTelemetryBoard.svelte`: `ÇALIŞMAYAN
YETENEKLER (n)` paneli — `capabilities[]` tablosundan beslenir.

`frontend/src/components/UnifiedCompactPanel.svelte` + `frontend/src/lib/telemetry.ts`:
`X SENSOR` ibresi kapalıyken `ÇALIŞMADI: <sebep>` basar.

### 6.1 Ölçüm — tip denetimi

```
$ cd frontend && npm ci --no-audit --no-fund
added 51 packages in 2s
$ npm run check
> svelte-check --tsconfig ./tsconfig.app.json && tsc -p tsconfig.node.json
Getting Svelte diagnostics...
svelte-check found 0 errors and 0 warnings
```

### 6.2 Test

```
tests/unit/test_p0_honest_status.py::test_ui_does_not_claim_profiles_were_linked
tests/unit/test_p0_honest_status.py::test_ui_shows_channel_reason_labels
tests/unit/test_p0_honest_status.py::test_telemetry_board_shows_unavailable_capabilities
```

---

## 7. `api.py` tavanı (ratchet) — geri çıkış yok

P0 düzeltmeleri `backend/api.py`'yi tavanın üstüne çıkardı (6.021 satır / tavan
5.916). Repo kuralı: **satır eklemek yerine MODÜL ÇIKAR**
(`docs/reports/API_MONOLITH_SPLIT_PLAN.md` §4).

Çıkarılan iki modül (ikisi de `docs/reports/API_MONOLITH_SPLIT_PLAN.md` §4
"düşük bağımlılık" sırasında adı geçen alanlar):

| Modül | İçerik | api.py kazancı |
|---|---|---|
| `backend/routes/telemetry.py` | `/api/telemetry` ucu (bağımlılıklar ENJEKTE) | ~57 satır |
| `backend/services/web_dossier.py` | Web dosyası profil kuralları + kanal satırları | ~63 satır |

Ölçüm: `backend/api.py` **5.908 satır**; tavan **5.916 → 5.907** DÜŞÜRÜLDÜ
(`tests/unit/test_api_monolith_ratchet.py`). Dış sözleşme korundu:
`api.api_telemetry` yeniden ihraç edildi, yol ve gövde değişmedi.

> `tests/unit/test_rust_runtime_status.py` içindeki `allowed_status_surfaces`
> listesine `backend/routes/telemetry.py` eklendi: bu modül rust çekirdeğini
> **çağırmaz**, yalnız `backend/api.py`'den enjekte edilen durumu **aktarır**.
> AST kapıları (import/invoke yasağı) bu dosya için değişmeden çalışır.

---

## 8. Testler

Yeni dosya: **`tests/unit/test_p0_honest_status.py`** (638 satır, 30 test).

```
$ .venv/bin/python -m pytest tests/unit/test_p0_honest_status.py -q -p no:cacheprovider
..............................                                           [100%]
30 passed in 1.96s
```

Revert-doğrulama betiği: **`scripts/revert_verification_p0.py`** (YENİ).
Her düzeltme geri alınır → hedef test koşulur → **KIRMIZI olduğu doğrulanır**
→ dosya geri yüklenir.

```
$ .venv/bin/python scripts/revert_verification_p0.py
PASS · P0-1 kanıt tipi: snippet 'gönderi' olarak yazılmaz
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P0-2 X sensörü: boş havuz → no_session_pool
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P0-3 UI: 'bağlandı' yalanı geri geliyor
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P0-4 telemetri: capabilities[].reason kaynağı
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P0-5 accounts.db: DB yolu yeniden yapılandırılamaz
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P0-6 hüküm belgesi: koşmayan kanallar listelenmiyor
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P0-7 rapor: koşmayan kanallar listelenmiyor
      revert sonrası pytest exit: 1 (beklenen: !=0)

REVERT-DOĞRULAMA: 7/7 düzeltme geri alınınca KIRMIZIya döndü
```

---

## 9. Tam koşu

```
$ .venv/bin/python -m pytest tests -q -p no:cacheprovider
2658 passed, 4 skipped, 318 warnings in 143.65s (0:02:23)

$ .venv/bin/python -m ruff check .
All checks passed!
```

Yeni/üretilen artefaktlar (tazelik kapıları):

```
$ .venv/bin/python scripts/audit_regression.py
✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.
rapor: reports/audit_regression.json

$ .venv/bin/python scripts/generate_inventory_page.py
yazıldı: /home/user/pineal-epifiz/docs/envanter.html (727 KB) · 719 dosya
sha256: 421aca0ed94c9a4f · ortam: posix
```

---

## 10. Kalan DOĞRULANMADI listesi (P0)

| # | Konu | Neden doğrulanamadı | Etki |
|---|---|---|---|
| 1 | **Canlı X kazıma** (gerçek `no_session_pool` → `user_not_found` ayrımı canlıda) | Sandbox egress'i yalnız github/npm/pypi; `x.com` erişilemez. `twscrape` gerçek hesap havuzu da yok. Testler sahte çiftlerle ölçüyor. | Kapı kodu ve sebep zinciri doğrulandı; UÇTAN UCA canlı akış doğrulanmadı. |
| 2 | **Canlı arama sonucu → snippet → UI** akışı | Arama motoru (Tavily/SerpAPI/Exa/SearXNG) anahtarları yok; `search.web` kanalı `not_run` ölçüldü. | Dossier kuralları testlerle doğrulandı; canlı sağlayıcı çıktısı doğrulanmadı. |
| 3 | **WebSocket canlı yayınında `channel_status`** | WS sunucusu canlı hedefe bağlanmadı; `broadcast_result` gövdesi statik olarak ve `test_ws_ordering` ile doğrulandı. | Alan doğru taşınır; canlı tarayıcıda görüntü doğrulanmadı. |
| 4 | **9Router LLM zinciri** | `http://127.0.0.1:20128/v1` sandbox'tan erişilemiyor (Faz 1 §4.4). | Prompt etiketleme kuralı TESTTE doğrulandı; gerçek model yanıtı doğrulanmadı. |
| 5 | **`ENABLE_*` bayraklarının açık hâli** | Görev kuralı gereği körlemesine bayrak açılmadı; egress/kasa/çocuk kilidi kapılarına dokunulmadı. | Kapı davranışı `policy:gate_disabled` ile ölçüldü; açık hâli ölçülmedi. |
| 6 | **PDF/diyagram/video rapor çıktılarında kanal listesi** | Markdown bölümü eklendi ve test edildi; PDF/diagram/video üreticileri kanal listesini almıyor. | Markdown doğrulandı; diğer formatlar doğrulanmadı. |

---

## 11. P1'e devir notları (sonraki faz)

1. `detected_urls` → `platform_registry` sınıflandırması → **ilgili sensör/
   yeteneğe `CapabilityRunner` üzerinden** bağlanmalı; sensör kapalıysa P0
   `not_run` düşülmeli, snippet'a sessiz düşüş olmamalı.
2. `extractor.identity.socid` capability'si hâlâ **hiçbir yerden çağrılmıyor**
   (Faz 1 §3.3) — P1'de bu hatta bağlanmalı.
3. `sensor.x.twscrape` hâlâ `ENABLE_X_SENSOR` bayrağına bağlı ve varsayılan
   kapalı; `PINEAL_X_ACCOUNTS_DB` yolu hazır ama **hesap kaydı yok** (havuz
   boş → `no_session_pool`).
4. Ölçüm motorları (`frequency`/`gravity`/`void`) snippet'ı kullanmıyor; bu
   BİLİNÇLİ bir karar (ölçüm "gönderi" üzerinden olmalı) — P1'de değiştirilirse
   gerekçe yazılmalı.

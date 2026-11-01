# DÜZELTME · FAZ 2 · P1 — Profil derinleştirme hattı (2026-10-16)

> **Kapsam:** Denetim 2026-10-16 · Bulgu 1 ("bulunan profiller hiçbir yere
> deşilmiyor") + Bulgu 3 ("`extractor.identity.socid` ölü kod").
> **Plan:** [`FAZ2_P1_PLAN_2026-10-16.md`](FAZ2_P1_PLAN_2026-10-16.md)
> **Taban:** `e4a4478` (PR #137 merge commit'i) · **Dal:** `arena/b3c799d4-pineal-epifiz`

---

## 0. Özet (tek cümle)

Bulunan profil URL'leri artık **gerçekten** taranıyor: `detected_urls` →
`profile_router` (saf sınıflandırma) → ilgili yetenek (`CapabilityRunner` tek
geçidi) → **kanal durumu + kanıt + kazanılan alan**; kapalı kapı `not_run` +
makine-okunur sebep olarak yazılıyor, kanıt zinciri (`forensic_evidence` /
`evidence_timeline`) gerçek yetenek kanıtıyla besleniyor ve `socid` capability'si
artık **ölü kod değil** (ölçüldü: ağ denemesi yaptı).

| Ölçüm | Taban (`e4a4478`) | P1 sonrası | Fark |
|---|---|---|---|
| `pytest tests -q` | 2656 passed, 6 skipped | **2697 passed, 6 skipped, 0 failed** (149.06 s) | **+41 test** |
| `backend/api.py` satır | 5908 | **5805** | **−103** (API-BÖLME 4) |
| ratchet tavanı `MAX_LINES` | 5908 | **5805** | düşürüldü |
| P1 test dosyası | — | `tests/unit/test_p1_profile_routing.py` (**37 test**) | yeni |
| Revert-doğrulama | P0: 7/7 | **P1: 6/6** | yeni |

---

## 1. Değişen dosyalar

### 1.1 Yeni dosyalar

| Dosya | Satır | Ne yapar |
|---|---|---|
| `agent_core/services/profile_router.py` | 240 | **SAF** URL→yetenek sınıflandırması. Ağ yok, dosya yazımı yok, global durum yok. |
| `agent_core/services/profile_deep_scan.py` | 364 | `CapabilityRunner` üzerinden koşum; kanal/kanıt/kazanılan alan üretimi. |
| `backend/services/web_research.py` | 222 | **API-BÖLME 4**: public-web araştırma gövdesi `backend/api.py`'den çıkarıldı. |
| `tests/unit/test_p1_profile_routing.py` | 580 | 37 sözleşme testi (6 bölüm + 1 bağlantı bölümü). |
| `scripts/revert_verification_p1.py` | 166 | 6 adımlık revert-doğrulama. |

### 1.2 Değiştirilen dosyalar

| Dosya | Değişiklik |
|---|---|
| `backend/api.py` | 243 satır değişti (net **−103**): public-web gövdesi çıkarıldı, **derin tarama bağlandı**, `payload["profile_deep_scan_evidence"]` eklendi. |
| `backend/services/web_dossier.py` | `build_dossier_profile(..., deep_scan=)` → `scanned_urls` + `scanned_profiles`; `dossier_channel_rows(..., deep_scan_rows=)` → gerçek satırlar. |
| `agent_core/services/pillar_evidence_adapter.py` | `adapt_pillar_bundle(..., extra_items=)` → dışarıdan gelen **gerçek** kanıtlar kanonik listeye eklenir. |
| `agent_core/task_executor.py` | `extra_items=input_data.get("profile_deep_scan_evidence")` → kanıt zincirine giriş. |
| `frontend/src/lib/channelStatus.ts` | `ScannedUrl` tipi + `scannedUrlText()` + `scannedSummary()`. |
| `frontend/src/components/TacticalWarRoom.svelte` | Profil chip'lerine **gerçek kazım durumu** rozeti; radar rozeti ve OSINT özeti artık "kazandı/kazınamadı" diyor. |
| `tests/unit/test_api_monolith_ratchet.py` | Tavan 5908 → **5805**; API-BÖLME 4 için 5 yeni test. |
| `docs/reports/API_MONOLITH_SPLIT_PLAN.md` | §2.4 "Dördüncü bölme" kaydı. |
| `docs/envanter.html`, `reports/audit_regression.json` | Üretilmiş çıktı (yenilendi). |

---

## 2. Yapılan komutlar ve HAM ÇIKTILAR

### 2.1 Tam test koşusu (P1 sonrası, son hâl)

```
$ .venv/bin/python -m pytest tests -q -p no:cacheprovider --timeout=300
2697 passed, 6 skipped, 319 warnings in 149.06s (0:02:29)
```

6 skip = opsiyonel paketler (twscrape/trafilatura/crawl4ai vb.) CI'da da yok.

### 2.2 Lint

```
$ .venv/bin/python -m ruff check .
All checks passed!
```

### 2.3 Frontend tip denetimi + derleme

```
$ cd frontend && npm run check
svelte-check found 0 errors and 0 warnings

$ cd frontend && npm run build
✓ 137 modules transformed.
✓ built in 1.85s
```

### 2.4 Revert-doğrulama (P1)

```
$ .venv/bin/python scripts/revert_verification_p1.py
PASS · P1-1 router: profil URL'si doğru yeteneğe bağlanmıyor
      test: tests/unit/test_p1_profile_routing.py::test_instagram_profile_url_routes_to_instagrapi
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P1-2 koşum: derin tarama yeteneği çalıştırmıyor
      test: ...::test_deep_scan_runs_through_the_capability_runner
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P1-3 kapalı kapı: koşmama sebebi yazılmıyor
      test: ...::test_closed_sensor_yields_not_run_with_machine_reason
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P1-4 API bağlantısı: bulunan profiller taranmıyor
      test: ...::test_api_actually_runs_the_deep_scan_for_detected_profiles
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P1-5 kanıt zinciri: socid/derin tarama kanıtı forensik kanıta girmiyor
      test: ...::test_deep_scan_evidence_merges_into_the_canonical_chain
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P1-6 API-BÖLME 4: public-web araştırma gövdesi api.py içinde yeniden tanımlandı
      test: tests/unit/test_api_monolith_ratchet.py::test_api_does_not_redefine_web_research_body
      revert sonrası pytest exit: 1 (beklenen: !=0)

REVERT-DOĞRULAMA (P1): 6/6 düzeltme geri alınınca KIRMIZIya döndü
```

### 2.5 Diğer kapılar

```
$ .venv/bin/python scripts/generate_inventory_page.py --check
GÜNCEL: docs/envanter.html kaynakla uyumlu
$ .venv/bin/python scripts/generate_routing_shadows.py
generate_routing_shadows: taze ✅
$ .venv/bin/python scripts/export_skills.py --check
Skills paketi taze: 26 dosya
$ .venv/bin/python scripts/audit_regression.py
✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.
$ .venv/bin/python scripts/verify_openrouter_catalog.py
SKIP: live OpenRouter check (OPENROUTER_API_KEY not configured)
PASS: local catalog contract verified
```

---

## 3. Canlı ölçümler (gerçek koşum, sahte veri yok)

### 3.1 Derin tarama — GERÇEK `CapabilityRunner`, GERÇEK yetenekler (mock YOK)

`vault_locked=True` (kasa kilitli):

```
{"url": "https://www.instagram.com/hedef/", "capability_id": "sensor.ig.instagrapi",
 "status": "not_run", "reason": "policy:vault_locked", "post_count": 0}
{"url": "https://x.com/hedef", "capability_id": "sensor.x.twscrape",
 "status": "not_run", "reason": "policy:vault_locked", "post_count": 0}
{"url": "https://linkedin.com/in/hedef", "capability_id": "extractor.identity.socid",
 "status": "not_run", "reason": "policy:vault_locked", "post_count": 0}
kanıt sayısı: 0
özet satırı: {'channel': 'profile.deep_scan', 'status': 'not_run',
              'reason': 'policy:vault_locked',
              'detail': "3 profil URL'si planlandı; hiçbiri kazınamadı"}
```

`vault_locked=False`, `ENABLE_*` bayrakları KAPALI (dokunulmadı):

```
{"url": "https://www.instagram.com/hedef/", "capability_id": "sensor.ig.instagrapi",
 "status": "not_run", "reason": "policy:gate_disabled", "post_count": 0}
{"url": "https://x.com/hedef", "capability_id": "sensor.x.twscrape",
 "status": "not_run", "reason": "policy:gate_disabled", "post_count": 0}
{"url": "https://linkedin.com/in/hedef", "capability_id": "extractor.identity.socid",
 "status": "not_run", "reason": "extract_unavailable:network_error", "post_count": 0}
kanıt sayısı: 0
```

**Okuma:** (a) kasa kapısı **korundu** — kilitliyken hiçbir yetenek koşmadı;
(b) `ENABLE_*` bayrakları **körlemesine açılmadı** — kapalıyken sensörler
`policy:gate_disabled` ile durdu; (c) `socid` capability'si **ölü kod değil**:
kapısı yalnız `vault` olduğu için ağ denemesi yaptı ve ağ yoksa
`extract_unavailable:network_error` ile **dürüstçe** başarısız oldu — kanıt
uydurmadı (kanıt sayısı 0).

### 3.2 Canlı sunucu (uvicorn) + WebSocket

```
$ PINEAL_ENV=development PINEAL_REQUIRE_AUTH=false ENABLE_CROSS_PLATFORM=true \
    .venv/bin/python -m uvicorn backend.api:app --host 0.0.0.0 --port 20128

$ curl /health                       → HTTP 200 {"status":"ready", ...}
$ curl /api/telemetry                → HTTP 200 · capabilities: 26
$ curl -X POST /api/vault            → HTTP 200 {"status":"secured"}
$ curl -X POST /api/initiate         → HTTP 200 {"status":"started","task_id":"op_2026..."}
WS /ws/p1_live                       → 63 kare, "result" karesi içinde:
```

```
channel_status: [
  {"channel": "search.web", "status": "not_run", "reason": "search_unavailable",
   "detail": "0/3 sorgu kullanılabilir"},
  {"channel": "sensor.identity.maigret", "status": "not_run",
   "reason": "policy:gate_disabled", "detail": null}
]
target_profile: {"detected_urls": [], "scanned_urls": [], "content_basis": "none",
                 "posts": [], "post_evidence_types": [],
                 "sensor_note": "Açık kaynak dosyası: platform sensörüyle kazınmadı."}
```

**Kasa kilitliyken** `/api/initiate` → **HTTP 423** `VAULT_LOCKED` (dış dünyaya
tek bayt çıkmıyor). Canlı koşuda arama sağlayıcısı erişilemediği için
`search.web` dürüstçe `not_run/search_unavailable` yazdı ve `detected_urls`
boş kaldı → derin tarama **gereksiz satır üretmedi**.

---

## 4. Eklenen testler (37 + 5)

`tests/unit/test_p1_profile_routing.py` — 37 test, 7 bölüm:

1. **Sınıflandırma (12):** IG→`sensor.ig.instagrapi` · X/twitter→`sensor.x.twscrape`
   · linkedin/facebook→`extractor.identity.socid` · rezerv segment
   (`instagram.com/p/ABC`, `x.com/i/status/123`) → `not_a_profile_url` ·
   `example.com` → `unsupported_platform` · lookalike host
   (`instagram.com.evil.example`) IG DEĞİLDİR · tekrar yok · limit uygulanır ·
   yol bulunamayan URL **sessizce atılmaz** (sebebiyle plan satırı).
2. **Kapalı kapı (5):** `ENABLE_X_SENSOR` kapalı → `not_run` + `policy:gate_disabled`
   · kasa kilitli → engelli · kapalı kapıda **kanıt üretilmez** · yolsuz URL →
   `not_run` satırı · planlanan her profil için **tam bir** kanal satırı.
3. **Kanıt tipi ayrımı (2):** derin tarama başarısızsa `posts` boş kalır
   (snippet inmez) · `scraped` yalnız GERÇEKTEN koşan yeteneğin payload'ı ile dolar.
4. **Çağrı yolu (3):** koşum `CapabilityRunner` üzerinden · `state` **aynen**
   aktarılır · yeni modüller `httpx`/`requests`/`urllib.request` import ETMEZ ·
   `egress.py` tek HTTP çıkışı olarak duruyor.
5. **socid ölü kod değil (2):** capability gerçekten **çağrılıyor** ·
   çıktısı `EvidenceItem` olarak taşınıyor.
6. **Raporlama dili (2):** taranan URL "kazınmış" diye sunulmuyor ·
   "BAĞLANAN" dili **yalnız** `targetPosts.length > 0` koşuluna bağlı ·
   "veri bağlandı" diye ölçülmemiş iddia yok.
7. **API bağlantısı + kanıt zinciri (6):** API gerçekten derin taramayı çağırıyor
   (`not_attempted` DEĞİL) · defterde her URL için bir satır ·
   **bulunan profilin gönderileri hedefin `posts` alanına YAZILMAZ** ·
   kanıt görev payload'ına taşınır · kanıt kanonik zincire girer ·
   zaman çizelgesinde `rejected_item_count == 0`.

`tests/unit/test_api_monolith_ratchet.py` — +5 test (modül var mı, yeniden ihraç
var mı, gövde kopyalanmış mı, tavan düştü mü, ölçülebilir ilerleme).

---

## 5. Tasarım kararları (gerekçeli)

### 5.1 Bulunan profil ≠ hedef → `posts` karışmaz

P0'un temel kuralı "arama sonucu ≠ gönderi" idi. P1'de bunun bir adım ötesi
uygulanır: **bulunan (eşleşen) profil de hedefin kendisi olduğu kanıtlanmadan**
o profilin gönderileri hedefin `posts` alanına yazılmaz. Kazınan gönderiler
`target_profile["scanned_profiles"][url]` altında, kendi `content_basis` ve
`post_evidence_types` değerleriyle, **ayrı** tutulur. Aksi hâlde "Alper
Öztürk" aramasında çıkan `@alper` hesabının gönderileri hedefin gönderileri
sayılırdı — kimlik karıştırma hatası.

### 5.2 `rate_ok=True` — mevcut repo konvansiyonu

`backend/api.py`'nin kendi X yolu aynı sensörü `rate_ok=True` ile çağırıyor
(`backend/api.py:2526`). Derin tarama da aynı değeri kullanır; **kapı
zayıflatılmamıştır** (kasa kapısı `_check_vault_interlock`'tan gelir,
`ENABLE_*` bayrakları dokunulmamıştır). `policy_state(rate_ok=None)` seçilseydi
X sensörü hiç koşamazdı ve P1 ölü hâle gelirdi.

### 5.3 Kasa mandalı DI ile (modül `backend.api`'yi içe aktarmaz)

`backend/services/web_research.py` kasa durumunu **parametreyle** alır
(`vault_locked_fn`). Yalnız geriye dönük uyum (doğrudan çağıran testler) için
tembel import içeren bir geri düşüş yolu vardır; import anında döngü yoktur.

### 5.4 Bulunan profillerin kanıtı `forensic_evidence`'a girer

`adapt_pillar_bundle(..., extra_items=...)` → `task_executor` →
`input_data["forensic_evidence"]` → `evidence_timeline`. Yani socid çıktısı
ekranda "kimlik alanı" olarak değil, **mühürlü kanıt girdisi** olarak görünür.

---

## 6. Kapı zayıflatılmadı (kanıt)

| Kapı | Durum | Kanıt |
|---|---|---|
| `ENABLE_*` bayrakları | **DOKUNULMADI** | Kaynak dosya diff'inde `ENABLE_` geçen tek satır **taşınan bir yorum** (api.py → `web_research.py`, aynen taşındı); hiçbir bayrağın değeri/kapı koşulu değişmedi. Canlı koşuda `policy:gate_disabled` görüldü (§3.1). |
| Kasa (vault) interlock | **DOKUNULMADI** | kasa kilitliyken `policy:vault_locked`; kilitli odada `/api/initiate` → HTTP 423. |
| Çocuk kilidi | **DOKUNULMADI** | `CapabilityRunner` çocuk kilidini politika kapılarından **önce** uygular (`agent_core/capabilities/runner.py:76`); deep scan `state`'i aynen aktarır. |
| Egress | **DOKUNULMADI** | yeni modüller `httpx`/`requests`/`urllib.request` import ETMEZ (AST testi); çıkış yalnız `egress.open_client`. |
| Sıfır noktası (rate/budget) | **DOKUNULMADI** | `PolicyKernel` aynen; `budget`/`rate` kapıları `policy_state` üzerinden. |

---

## 7. DOĞRULANMADI (sebebiyle)

| # | Konu | Sebep |
|---|---|---|
| 1 | **Canlı X/Instagram kazıma** | `instagram.com` / `x.com` bu ortamdan **erişilemiyor** (egress). Kapılar kapalıyken `policy:gate_disabled` ölçüldü; gerçek gönderi sayısı ölçülemedi. |
| 2 | **Canlı socid_extractor çıkarımı** | `linkedin.com` erişilemiyor → `extract_unavailable:network_error` ölçüldü (dürüst hata). Kanıtın gerçek üretimi testte (sabit yetenek çıktısıyla) doğrulandı. |
| 3 | **Canlı arama → `detected_urls` → derin tarama** zinciri | Arama sağlayıcıları (tavily/serpapi/DDG) erişilemiyor → `search.web: not_run/search_unavailable`. Zincirin "arama sonrası" halkası canlı doğrulanamadı; API halkası sahte arama motoruyla testte doğrulandı. |
| 4 | **WS canlı `channel_status` gönderimi** | `websockets` paketi venv'de yoktu → kuruldu ve canlı doğrulandı (§3.2) **ama** `channel_status` alanı WS "result" karesinde **yok**; kanal defteri görev payload'ında ölçüldü. |
| 5 | **9Router / canlı LLM zinciri** | `localhost:20128` bu sandbox'tan erişilemiyor (HTTP 000). Etkilenmedi: P1 LLM'e dokunmuyor. |
| 6 | **`ENABLE_X_SENSOR` / `ENABLE_IG_SECONDARY` açık hâli** | Kapılar bilinçli olarak **kapatıldı** (kullanıcı kuralı: körlemesine açma). Açık hâlde de akış aynı kod yolunu izler; sonucu ölçülmedi. |

---

## 8. P2'ye devir notları

* **P2 (çapraz profilleme)** için hazır altyapı: `profile_router` saf
  sınıflandırma + `profile_deep_scan` kanıt üretimi ayrı modüller; her eşleşme
  `EvidenceItem` olabilir (güven skoru "kapsam" etiketiyle, olasılık değil).
* **P3 (Lilith)**: hâlâ CLI-only; ana hatta bağlanmadı (P4'te README'de açıkça
  yazılacak).
* **P4 (dokümantasyon)**: README'ye yalnız **kanıtla doğrulanmış** kısımlar
  yazılacak; doğrulanamayanlar "DOĞRULANMADI" olarak işaretlenecek.
* **P1'den kalan teknik borç:** `backend/api.py` hâlâ 5805 satır (tavan 5805).
  Bir sonraki modül çıkarımı için §2.4'e bakılmalı.

---

## 9. Teslim kapıları — son durum

| Kapı | Komut | Sonuç |
|---|---|---|
| Tam test | `pytest tests -q` | ✅ **2697 passed, 6 skipped** (0 failed) |
| Lint | `ruff check .` | ✅ `All checks passed!` |
| Frontend tip | `npm run check` | ✅ 0 errors, 0 warnings |
| Frontend derleme | `npm run build` | ✅ built in 1.85s |
| api.py tavanı | `pytest tests/unit/test_api_monolith_ratchet.py` | ✅ 14 passed (tavan **düşürüldü**: 5908 → 5805) |
| Audit bekçisi | `python scripts/audit_regression.py` | ✅ `✓ BEKÇİ GEÇTİ` |
| Envanter tazeliği | `python scripts/generate_inventory_page.py --check` | ✅ `GÜNCEL` (735 KB · 726 dosya) |
| Routing gölgeleri | `python scripts/generate_routing_shadows.py` | ✅ taze |
| Skills paketi | `python scripts/export_skills.py --check` | ✅ taze (26 dosya) |
| Katalog kontratı | `python scripts/verify_openrouter_catalog.py` | ✅ local PASS (live SKIP: anahtar yok) |
| Revert-doğrulama | `python scripts/revert_verification_p1.py` | ✅ **6/6** |
| CI | GitHub Actions | ✅ PR #139 · koşu [38871291504](https://github.com/AppleCurse/pineal-epifiz/actions/runs/38871291504) + smoke [38871284864](https://github.com/AppleCurse/pineal-epifiz/actions/runs/38871284864): `backend`/`frontend`/`rust-core`/`android`/`smoke`/Workers×2 **hepsi yeşil** (ara koşularda `backend` **katalog adımı** kırmızıydı — canlı fiyat salınımı, §10 ve §12) |

---

## 10. CI `backend` adımının kırmızı düşmesi — CANLI FİYAT KAYMASI (P1 ile ilgisiz)

PR #139'un CI'sinde `backend` adımı **katalog adımında** kırmızıydı:

```
FAIL: z-ai/glm-5.2: live input price $0.037/1M != $0.62/1M
FAIL: z-ai/glm-5.2: live output price $7/1M != $2.42/1M
```

**Kanıt bunun P1 ile ilgisi olmadığını gösteriyor:**

1. P1'in dokunduğu hiçbir dosya bu adımın girdisi değil: adım yalnız
   `scripts/verify_openrouter_catalog.py` + `config/provider_catalog.json`'ı
   okuyor ve `GET https://openrouter.ai/api/v1/models` çağırıyor.
2. Aynı depodaki `main` dalının **Catalog Drift** koşusu
   (`38851706200`, 2 saat önce) **başarılıydı** → aynı pin o saat canlı
   katalogla uyumluydu.
3. PR koşularında **ardışık iki** ölçüm (`38866434547`, `38867016705`) birebir
   aynı kaymayı gösterdi → canlı değer değişmişti, ölçüm hatası değil.

**Yapılan:** depo politikası gereği ("ölçülen değere hizala") üç fiyat kopyası
son ölçüme hizalandı (pin · `config/provider_catalog.json` ·
`llm_gateway.MODEL_PRICING`) → `$0.037 / $7.00`. Ayrıntı ve **açık öneri**
(salınan model için "ölçülmüş durum kümesi" bekçisi) →
[`DUZELTME_FIYAT_HIZALAMA_2026-10-16.md`](DUZELTME_FIYAT_HIZALAMA_2026-10-16.md) §5.

**Uyarı (dürüstlük):** `glm-5.2` fiyatı iki gündür salınıyor; tek pinle
çalışan bekçi bu modelde kırılgan kalır. Bu bir **ölçüm kusuru değil, bekçi
tasarımı** meselesidir ve ayrı bir iş kalemi olarak önerilmiştir (bu PR'da
UYGULANMADI). `deepseek/deepseek-v4-pro` canlı fiyatı hâlâ
$0.95526/$1.91052 ile uyumlu (kırmızı değil).

---

## 11. KONSOLİDASYON — main'e paralel bir P1 uygulaması merge edilmişti

### 11.1 Ne oldu (kanıtlı)

PR #139 açıldıktan sonra `main` **tek bir squash commit** ile yeniden yazıldı
(`d83c67b`, 1 commit; bizim branch'imiz 6 commit'lik ayrı bir soydur →
`git merge` "refusing to merge unrelated histories" verdi). O commit'in içinde
**PR #138** vardı: *"Phase 2 P1 Deep Profiling Pipeline & P2 Cross-Profiling
Matcher"* (08:45 merge).

`gh api`/`git show` ile doğrulanan PR #138 içeriği:

| Dosya | Satır | Ne yapıyor |
|---|---|---|
| `agent_core/services/deep_profile_resolver.py` | 164 | **Paralel P1**: `detected_urls` → `platform_registry.classify_profile_url` → sensör + `extractor.identity.socid` → kanıt + kanal satırı |
| `agent_core/services/cross_profiler.py` | 260 | **P2**: çapraz profilleme (deterministik eşleşme) |
| `agent_core/services/platform_registry.py` | +42 | `classify_profile_url` (yeni) |
| `agent_core/task_executor.py` | +37 | derin taramanın görev yürütücüsüne bağlanması |
| `tests/unit/test_p1_p2_deep_profiling.py` | 416 | P1+P2 sözleşme testleri (15 test) |

**Yani: aynı hedefe iki ayrı uygulama vardı.** Depoda iki koşum yolu,
iki sınıflandırma ve iki kanal defteri kalması "kopuk kablo" bulgusunun
yeni bir hâli olurdu.

### 11.2 Karar: İKİ UYGULAMA DEĞİL, TEK UYGULAMA

Kullanıcı onayıyla (2026-10-16) **konsolidasyon** yapıldı. Korunan ve
bağlanan parçalar:

| Katman | Son hâli | Neden |
|---|---|---|
| **Sınıflandırma** | `agent_core/services/profile_router.py` (saf, host tabanlı) — **TEK kaynak** | Profil OLMAYAN adresleri (gönderi/etiket/giriş) eler; `platform_registry.classify_profile_url` artık **ona devrediyor** (dış sözleşme biçimi korundu) |
| **Koşum** | `agent_core/services/profile_deep_scan.py` — **TEK koşum geçidi** (`CapabilityRunner`) | Kapılar/çocuk kilidi/timeout aynı yerden |
| **Giriş noktası** | `agent_core/services/deep_profile_resolver.py` (PR #138'in modülü) → **motoru çağırır** | PR #138'in üçlü sözleşmesi `(kanıtlar, kanal satırları, kimlikler)` **korunur**; `resolve_deep_profiles_detailed` ek olarak defter döndürür |
| **Koşum yeri** | **Görev yürütücüsü** (`agent_core/task_executor.py`) | API + CLI **gibi tüm giriş noktalarını** kapsar; API katmanı yalnız adresleri taşır → **ikinci koşum yolu yok** (aynı yetenek iki kez çağrılmaz) |
| **Kanıt zinciri** | `pillar_evidence_adapter(extra_items=[*_deep_items, *_cross_items])` | Derin tarama **ve** çapraz profilleme kanıtları **tek** kanaldan kanonik zincire girir (PR #138'in "liste + liste" birleştirmesi kaldırıldı) |

Korunan davranışlar (PR #138'in testleri kırmızı olmadan geçiyor —
`tests/unit/test_p1_p2_deep_profiling.py` **15 passed**):
kasa kilitliyse tek satır `not_run/vault_locked` · socid bağımlılığı yoksa
`not_run/dependency_missing:socid_extractor` · `classify_profile_url` dış
sözleşmesi (x→`sensor.x.twscrape`, instagram→`sensor.ig.instagrapi`,
web→`None`+socid) · kapalı sensörde `gate_disabled` sebebi · "1/2 profilden"
toplam satır dili.

Ek olarak düzeltilen **gerçek kusur**: PR #138'in çözümleyicisi politika
durumunu `payload["policy"]`'ten alıyordu; API katmanı `rate_ok` **yazmıyordu**
→ hız kapısı "bilinmiyor" diye **RET** ediyordu → sensörler hiç koşamıyordu.
`backend/api.py` artık `payload["policy"]["rate_ok"] = True` taşıyor (aynı
dosyanın kendi X kazıma yolunun konvansiyonu). Kasa kapısı, çocuk kilidi ve
`ENABLE_*` bayrakları **dokunulmadan** aynı yerde duruyor.

### 11.3 Ölçüm (konsolidasyon sonrası)

```
pytest tests/unit/test_p1_profile_routing.py      → 37 passed   (kendi sözleşmelerim)
pytest tests/unit/test_p1_p2_deep_profiling.py    → 15 passed   (PR #138'in sözleşmeleri)
pytest tests -q                                    → 2707 passed, 6 skipped
                                                    (envanter/audit yenilemesi sonrası: hepsi yeşil)
ruff check .                                       → All checks passed!
revert_verification_p1.py                          → 6/6 PASS
npm run check (frontend)                           → svelte-check found 0 errors and 0 warnings
backend/api.py satır sayısı                       → 5805 → 5758 (tavan 5758'e düşürüldü)
```

### 11.4 Bu konsolidasyonda YAPILMAYANLAR (dürüstlük)

* **PR #138'in P2'si (`cross_profiler.py`) değiştirilmedi** — ayrı faz işi;
  bu PR'de yalnız kanıt zincirine **bağlandı** (`extra_items`).
* `z-ai/glm-5.2` canlı fiyat salınımı bu konsolidasyonla ilgisi yoktur
  (§10) — ayrı ölçüm, ayrı commit.
* **DOĞRULANMADI:** konsolidasyonun canlı uçtan uca (WS) doğrulaması bu
  turda **yeniden yapılmadı** (P1'in canlı koşusu a4a4a61'de yapılmıştı;
  bu turda ortam egress'i kapalı).

---

## 12. Canlı fiyat: üçüncü ölçüm + bekçi tasarımı düzeltmesi

Konsolidasyon koşusunda ([38870244950](https://github.com/AppleCurse/pineal-epifiz/actions/runs/38870244950))
canlı katalog **üçüncü kez** farklı okundu: `z-ai/glm-5.2` çıktı $7.00 → **$9.00**
(girdi $0.037). İki günde dört ayrı fiyat ölçüldü → teşhis: ölçüm değil,
**bekçinin tasarımı** sorunluydu (tek pin, salınan fiyatta yanlış alarm).

Düzeltme: `scripts/verify_openrouter_catalog.py` → `OBSERVED_OPENROUTER_STATES`
(her durum CI koşu kimliğiyle kayıtlı). Bilinen ölçülmüş durum → `PASS` +
`WARNING`; **bilinmeyen yeni fiyat → yine `FAIL:`** (giriş/çıktı karışık
eşleşemez). Kapı zayıflatılmadı. 5 yeni sözleşme testi eklendi.

Ayrıntı: [`DUZELTME_FIYAT_HIZALAMA_2026-10-16.md`](DUZELTME_FIYAT_HIZALAMA_2026-10-16.md) §5.4.
**Kapsam sınırı:** harcama sayacı tek değer taşır (son ölçülen durum);
canlı fiyatın periyodik tabloya alınması ayrı bir iş kalemi olarak açık.

# GO_LIVE.md — PINEAL EPİFİZ canlıya alma kapısı

> Bu dosyadaki **her satır bu depoda ölçüldü**. Doğrulama ortamı: temiz sandbox,
> Python 3.11.2, Node 20+, commit `ce2e646` (dal `main`). Ölçülmeyen hiçbir şey
> "tamam" diye yazılmadı; ölçülemeyenler **DOĞRULANMADI** diye işaretli.

---

## 1. Bu depo ne, ne değil

Bu depo **adli OSINT istasyonudur** (Instagram/LinkedIn/X kazıma + 7 matematik
motoru + 12 ajan + LLM havuzu). **WhatsApp / ödeme / Meta ticaret iş mantığı bu
depoda YOKTUR.**

Ölçüm:

```
grep -rniE "whatsapp|iyzico|stripe|paypal|checkout" --include="*.py" --include="*.ts" --include="*.svelte" --include="*.js" .
→ üretim kodunda 0 gerçek eşleşme
```

Görünen tek eşleşmeler yanlış pozitiftir: `test_media_forensics.py` içinde
`kind="stripes"` (desen adı, `stripe` alt dizesi) ve yorumlarda geçen İngilizce
`checkout` kelimesi. **Yani bu depo bir WhatsApp ticaret botu değildir; webhook
doğrulama / sepet / ödeme denetimi burada boş kategoridir.** WhatsApp botu ayrı
bir servis ise o servis ayrı denetlenmelidir.

---

## 2. Port haritası

| Port | Servis | Açıklama |
|---|---|---|
| `8000` | FastAPI backend | REST (`/api/*`), OpenAI-uyumlu uç (`/v1/*`), telemetri WS (`/ws/{client_id}`), statik frontend mount (`/`) |
| `4173` | Frontend preview | `npm run preview` — üretim derlemesi |
| `5173` | Vite dev server | HMR; `/api` ve `/ws` isteklerini `8000`'e proxy'ler |
| `20128` | 9Router local hub | Yerel OpenAI-uyumlu çoklu hesap yönlendirici (opsiyonel) |
| `6379` | Redis | Agent Rack Pub/Sub canlı köprüsü (opsiyonel; yoksa süreç içi bellek + dürüst `fallback` beyanı) |

Kaynak: `README.md` §"Port Haritası", `docker-compose.yml`, `wrangler.toml`.

---

## 3. Mimari (gerçek dosya yollarıyla)

```
frontend/src/components/*.svelte  ──(fetch)──▶  /api/*, /v1/*   ── auth_middleware ──▶ handler
frontend (Cloudflare Pages)       ──(WS)────▶  /ws/{client_id}
        │                                            │
        │  functions/api/[[path]].ts  (HTTP proxy)   │  backend/api.py:2155 @app.websocket
        │  functions/ws/[[path]].ts   (WS proxy)     ▼
        └──────── BACKEND_ORIGIN ─────────▶  backend/routes/websocket.py::run_telemetry_socket
                                                     │
                        agent_core/utils/security.py │  token → principal
                        backend/security/principal.py│  principal → oda mührü
                                                     ▼
                        agent_core/services/canonical_memory.py  ← ⚠ BÖLÜM 4 P0
```

Kimlik zinciri (ölçüldü):

1. `auth_middleware` (`backend/api.py:287`) yalnız `/api/*` ve `/v1/*` yollarını
   korur; `/api/*` için başlık **`X-API-Key`**, `/v1/*` için `Authorization:
   Bearer` da kabul edilir (`backend/api.py:307-311`).
2. `principal_of_request(token)` → `resolve_principal` (`agent_core/utils/security.py:203`)
   token'ı bir operatör kimliğine çözer (`PINEAL_TOKEN` = `root`,
   `PINEAL_OPERATOR_TOKENS` = `etiket:token` listesi).
3. `get_room(client_id)` (`backend/api.py:1055`) biçim + uzunluk doğrular, sonra
   `enforce_room_ownership` (`backend/security/principal.py`) mührü uygular;
   başkasının odası → `403 ROOM_FORBIDDEN`.
4. `/ws/{client_id}` aynı mührü `run_telemetry_socket` içinde uygular:
   **hız kapısı → accept() → kimlik → SAHİPLİK → `auth_ok`**.

---

## 4. P0 — kanıt deposu oda başına ayrışmıyordu → **KAPATILDI (2026-10-12)**

**Durum: kapatıldı.** Kalıcı `task_id → principal` sahipliği eklendi; ölçülen
PoC artık `403 ROOM_FORBIDDEN` dönüyor ve kanıt diskte kalıyor.

### Ölçülen orijinal kusur

Kök neden: görev kayıtları `CanonicalMemory(storage_path)` altında **yalnız
`task_id` ile anahtarlanmış düz bir dosya alanıdır**
(`agent_core/services/canonical_memory.py:89` →
`safe_child_path(storage_path, f"{task_id}.json")`), ve `storage_path`
`os.getenv("PINEAL_MEMORY_PATH", "./memory/")` değerinden gelir
(`agent_core/services/hindsight_memory.py:326`). Yani **tüm odalar aynı klasörü
paylaşır**; kayıtta oda/operatör damgası yoktu. Oda mührü bu yüzden yalnız ODA
ADI sınırını koruyordu.

Ölçülen canlı PoC (production modu, iki ayrı operatör token'ı) — kapatmadan önce:

```
alice room tasks BEFORE: ['op_20261012021906_296645f1', 'op_20261012022612_1f843326']
bob sees in his OWN room: ['op_20261012021906_296645f1', 'op_20261012022612_1f843326']   ← sızıntı
bob DELETE alice task from own room: 200 {"status":"deleted","memory_file_deleted":true}    ← kanıt yok edildi
alice room tasks AFTER : ['op_20261012022612_1f843326']
disk: memory/op_20261012021906_296645f1.json  →  artık yok
```

### Kapatma

| Katman | Dosya | Ne yapar |
|---|---|---|
| Kayıt | `backend/security/task_ownership.py` | `task_id → principal` SQLite'ta (`PINEAL_TASK_OWNERS_DB`, varsayılan `PINEAL_MEMORY_PATH/task_owners.db`). Süreç yeniden başlayınca sahiplik **kaybolmaz** — süreç içi sözlük bu işi görmezdi, çünkü silme kalıcıdır. |
| Uygulama | `backend/security/task_access.py` | `guard_task` / `visible_tasks` / `record_new_task` + `MAX_TASK_ID_LENGTH` (tek sözleşme). |
| Yazma | `backend/api.py` `/api/initiate` ve `/api/aspasia/command` | Sahiplik **kanıt dosyası oluşmadan ÖNCE** yazılır (aksi halde pencerede görev sahipsiz görünürdü). |
| Okuma | `backend/routes/tasks.py` `GET /api/tasks` | Başka operatöre kayıtlı satır listeye **hiç girmez** — "bu görev var ama senin değil" bilgisi de sızmaz. |
| Silme | `backend/routes/tasks.py` `DELETE /api/tasks/{id}` | Farklı principal → `403 ROOM_FORBIDDEN` (gövde oda reddiyle **birebir aynı**: görevin varlığı doğrulanmaz). |
| İptal | `backend/api.py::_terminate_mission` | Savunma derinliği; yaşam döngüsü kaydı zaten oda başına. |

Semantik oda mührüyle birebir aynıdır:

* `principal is None` (kimlik doğrulama kapalı / development) → mühür yok,
  mevcut davranış korunur.
* Kayıt **yok** (bu sürümden önce üretilmiş kanıt) → **İLK ERİŞEN SAHİPLENİR.**
  Bilinçli: mevcut dağıtımlar kilitlenip dışarıda bırakılmaz. Bedeli: sahipsiz
  eski kanıtı ilk okuyan operatör onun sahibi olur.
* Kayıt başka operatörde → ret.
* `PINEAL_TASK_OWNERS_DB` yazılamıyorsa **fail-OPEN** ve dar: görev erişilebilir
  kalır + uyarı loglanır (kayıt kanıt değildir; yanlışlıkla kimse kilitlenmez).

Kilit testleri: `tests/unit/test_task_ownership.py` (13 test). Bir mührü
gevşetirseniz orada kırmızı yanar — DELETE mühürü kaldırıldığında **4 test
kırmızıya döndü** (ölçüldü), yani testler gerçekten bu kodu koşuyor.

### Kalan sınır (bilinçli)

Sahiplik **görev** düzeyindedir, **depo** düzeyinde değil: `memory/` hâlâ düz ve
paylaşımlıdır. Yani sahiplik kaydı silinirse/başka makineye taşınmazsa kanıt
tekrar sahipsiz görünür ve ilk erişen sahiplenir. Depoyu operatör başına
ayırmak (`PINEAL_MEMORY_PATH` bölme) daha köklü bir çözümdür ama mevcut
`memory/*.json` kayıtlarının sahibi bilinmediği için göç planı ister; ürün
sahibi kararı gereği bu turda uygulanmadı.


---

## 5. Diğer açık bulgular (ölçüldü)

| # | Bulgu | Ölçüm | Önem |
|---|---|---|---|
| 5.1 | Çocuk kilidi uçları çapraz operatör **mühürsüzdü** — **KAPATILDI (2026-10-12)** | Ölçülen: Bob, Alice'in oda adıyla `GET /api/minor/state` → `200` (`case_type` + `case_id` sızıyordu). Daha ağırı: `POST /api/minor/clear` beyanı SİLİYORDU, yani **çocuk kilidi çapraz operatör AÇILABİLİYORDU**. Kapatma: `principal.check_room_seal` (oda OLUŞTURMAYAN denetim) üç uca da kondu — `state`, `case`, `clear`. Ölçülen sonrası: üçü de `403 ROOM_FORBIDDEN`, Alice'in beyanı yerinde, Alice kendi beyanını silebiliyor. Kilit testleri: `tests/unit/test_task_ownership.py` (5 test; mühür kaldırılınca 3'ü kırmızıya döndü — ölçüldü). | Kapatıldı |
| 5.2 | WS `_authenticate` `WebSocketDisconnect` yakalamıyor | `backend/routes/websocket.py:148` yalnız `TimeoutError/ValueError/RuntimeError` yakalıyor. İstemci auth çerçevesi göndermeden kapatınca gerçek sunucu logu: `starlette.websockets.WebSocketDisconnect: (1005, None)` izi. Modül docstring'i "fonksiyon istisna FIRLATMAZ" diyor — **sözleşme ihlali**. | P2 (dürüstlük/log gürültüsü; bağlantı zaten kapanıyor) |
| 5.3 | Kimliksiz WS soketi 5 sn açık kalıyor | Hız kapısı `accept()`ten önce (doğru), ama `WS_AUTH_TIMEOUT_S = 5.0` (`backend/routes/websocket.py:47`) içinde kimliksiz soket kabul edilip bekletiliyor. Kova `ws: 30/60 sn` olduğundan sınırsız değil, IP başına 30/60 sn. | P3 |
| 5.4 | `import backend.api` diske yazıyor — **DÜZELTİLMEDİ** | Boş bir CWD'de `python -c "import backend.api"` → `cache/responses.db`, `-wal`, `-shm` ve `frontend/` oluştu. Kaynak: `agent_core/services/response_cache.py:97` (`os.makedirs`) + `backend/api.py:5993` (`os.makedirs(static_dir)`). Testlerde görünmüyor çünkü `tests/conftest.py:35-42` modül seviyesinde env ile izole ediyor. Salt-okunur dosya sisteminde açılış patlar. | P2 |
| 5.5 | Pydantic doğrulaması sahiplikten önce | Bozuk gövde → `422` alan şeması sızıntısı, oda mührü hiç çalışmadan. Örnek: `POST /api/aspasia/chat` gövdesinde `user_message` eksikken `422`; doğru gövdeyle `403 ROOM_FORBIDDEN`. | P3 |
| 5.6 | Çocuk kilidi **beyana dayalı** | `agent_core/safety/minor_gate.py:172` `evaluate(case)` yalnız operatör beyanını değerlendirir; `estimate_age` yok (grep ile doğrulandı). `POST /api/minor/case` ile beyan edilmezse kilit devreye girmez. **Düzeltme:** önceki denetim "tüzük metni ile kod farklı" demişti — bu tam doğru değildi: `docs/PINEAL_TUZUK.md` Madde 4/A bir *politika* koyar ("18 yaşından küçük her birey çocuktur"), yaş *tespit yöntemi* emretmez. Asıl boşluk, tüzüğün sistemin yaş TAHMİN ETMEDİĞİNİ hiç yazmamasıydı. | **KARAR VERİLDİ (2026-10-12):** beyana dayalı kalıyor; Madde 4/A'ya 9. fıkra eklendi (sistem yaş tespit etmez, tetik operatör beyanıdır, hukuki sorumluluk beyan makamınındır). |
| 5.7 | Tek replika zorunlu | Oda/kasa/hız kovası süreç içi; `railway.toml` → `numReplicas = 1` + uyarı yorumu. Redis yalnız telemetri köprüsüdür. Ölçeklerseniz oturumlar ve kovalar sıfırlanır. | Bilinçli |
| 5.8 | Cloudflare worker `cf-connecting-ip` siliyor | Token'sız akışta tüm anonim kullanıcılar aynı hız kovasını paylaşır. Token'lı akışta kimlik token hash'i olduğu için sorun yok. | Bilinçli |
| 5.9 | 2.84 MB PNG üretim bundle'ında | Ölçüldü: `vite build` → `dist/assets/cockpit-v10-reference-nfBm81wi.png 2,838.59 kB`. Bilinçli tasarım; WebP'ye çevirmek ~%85 küçültür. | İyileştirme |
| 5.10 | Test paketi ortam bağımlı | Aşağıda §7: eksik opsiyonel paketler 40 testi kırmızı yapıyor. | Bilinçli |

---

## 6. BLOCKER `.env` tablosu — bunlar yoksa canlı patlar

| Değişken | Nerede | Yoksa ne olur (kod kanıtı) |
|---|---|---|
| `PINEAL_ENV=production` | Railway/container env | Set edilmemişse ortam **ÜRETİM varsayılır** ve `AUTH_FAIL_CLOSED` uyarısı loglanır (`agent_core/utils/security.py:88-97`). Yani "unuttum" = üretim davranışı; ama yerel geliştirmede sürpriz 503 üretir. |
| `PINEAL_TOKEN` (≥32 rastgele) | Railway/container env | Production + token yok → `SecurityConfigurationError("PRODUCTION_AUTH_REQUIRED")` → tüm `/api/*` ve `/v1/*` **503** (`security.py:98-105`). |
| `PINEAL_OPERATOR_TOKENS=alice:<t>,bob:<t>` | Railway/container env | Tanımsızsa **tüm operatörler tek `PINEAL_TOKEN`'ı paylaşır → tek kimlik → odalar ayrışmaz** (`.env.example:164-166`). Yukarıdaki P0'ı büyütür. Biçim: `etiket:token`, etiket `[A-Za-z0-9_.-]{1,64}`, token **≥8 karakter** (daha kısası sessizce atlanır + loglanır, `security.py:193`). |
| `OPENROUTER_MAX_SPEND_USD=50` | Railway/container env | Production + cap ≤ 0/tanımsız → `SecurityConfigurationError("PRODUCTION_SPEND_CAP_REQUIRED")` → **503** (`security.py:114-125`). Sınırsız LLM harcaması engellenir. |
| `BACKEND_ORIGIN` | **Cloudflare SECRET** (`npx wrangler pages secret put BACKEND_ORIGIN`) | Tanımsızsa `functions/api/[[path]].ts:30-38` ve `functions/ws/[[path]].ts:20-27` **`502 BACKEND_ORIGIN_NOT_CONFIGURED`** döner → arayüz backend'e hiç ulaşamaz, **tam kesinti**. |
| `REDIS_URL` | Railway/container env | Opsiyonel. Boş/erişilemezse sistem çökmez; süreç içi belleğe düşer ve `/api/telemetry` dürüstçe `agent_status_source: "fallback"` bildirir (`.env.example:174-178`). |
| `WS_DEBUG_LOG` | Cloudflare env | Opsiyonel, varsayılan kapalı. `1` yapılırsa `functions/ws/[[path]].ts:100` yalnız **sayaç** loglar; payload içeriği loglanmaz. |

Üretim token üretimi:

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(32))"
```

---

## 7. Ölçülmüş doğrulama (bu sandbox'ta, bu commit'te)

| Kontrol | Komut | Sonuç |
|---|---|---|
| Birim/entegrasyon testleri | `pytest tests -q` | **40 failed / 2331 passed / 9 skipped** (135.88 s). Kırmızıların **tümü** eksik opsiyonel pakettir: `socid_extractor`, `maigret`, `holehe`, `playwright_stealth`, PDF üreticisi, ve `cv2.CascadeClassifier`'ı olmayan headless OpenCV derlemesi. Örnek: `ModuleNotFoundError: No module named 'socid_extractor'`. |
| IDOR test dosyası | `pytest tests/unit/test_room_ownership_idor.py -q` | **16 passed** |
| Lint | `ruff check .` | **All checks passed!** |
| Tip/derleme | `npx svelte-check --tsconfig ./tsconfig.app.json` | **0 errors, 0 warnings** |
| Üretim derlemesi | `npm run build` (frontend) | **✓ built in 1.96s** |
| Bağımlılık denetimi | `npm audit` (frontend) | **found 0 vulnerabilities** |
| Test izolasyonu | tam koşu sonrası depo kökü | `memory/` içinde **0 dosya**, `cache/` **yok** |
| Canlı HTTP IDOR | 2 operatör token'lı production sunucu | Oda adı üzerinden **11/11 kapalı** (`403 ROOM_FORBIDDEN`): `/api/tasks`, `/api/telemetry`, `/api/vault/status`, `POST /api/vault`, `DELETE /api/tasks/<id>`, `POST /api/initiate`, `POST /api/aspasia/chat`; `root` token'ı da Alice'in odasına giremedi; tokensiz istek `401`; Bob kendi odasında `200`. |
| Canlı WS sahipliği | aynı sunucu | Bob → Alice'in odası: **`auth_ok` HİÇ gönderilmedi**, soket `1008` ile kapandı. Alice kendi odasında `auth_ok` aldı. Anonim ve yanlış token: `1008`. |
| Canlı WS hız kovası | aynı IP'den 35 ardışık bağlantı | **27 kabul, 8 `1013` (try-again-later)** — kova `ws: (30, 60)` (`backend/api.py:459`). |
| **Kanıt deposu ayrışması** | aynı sunucu | Kapatmadan önce **BAŞARISIZ** (Bob, Alice'in görevini kendi odasından görüp silebildi); §4'teki kapatmadan sonra `tests/unit/test_task_ownership.py` **13 passed**. |
| Sahiplik testleri gerçekten ölçüyor mu | DELETE mühürü geçici olarak kaldırıldı | **4 test kırmızıya döndü** (`test_stranger_cannot_delete_victim_evidence_from_his_own_room`, `test_root_token_cannot_delete_operator_evidence`, `test_task_forbidden_body_is_identical_to_room_forbidden`, `test_unowned_legacy_task_is_adopted_by_first_accessor`); mühür geri konunca 13/13 yeşil. |
| Monolit tavanı (ratchet) | `pytest tests/unit/test_api_monolith_ratchet.py -q` | Önce **2 FAILED** (`backend/api.py` 6070 satır > tavan 6000) → görev uç noktaları `backend/routes/tasks.py`'e taşındı → **5969 satır**, tavan testleri yeşil. |
| Çocuk kilidi mührü gerçekten ölçüyor mu | `_require_room_seal` gövdesi geçici olarak boşaltıldı | **3 test kırmızıya döndü** (`test_stranger_cannot_read_victim_minor_state`, `test_stranger_cannot_unlock_victim_child_lock`, `test_stranger_cannot_declare_into_victim_room`); mühür geri konunca 18/18 yeşil. |
| Canlı uçtan uca (production, 2 operatör) | `uvicorn` + `httpx` PoC | **9/9 PASS**: Bob Alice'in görevini görmüyor; `DELETE` → `403`; kanıt diskte; Alice'in çocuk beyanı odasını `451` ile kilitliyor; Bob beyan durumunu OKUYAMIYOR (`403`), beyanı SİLEMİYOR (`403`), Alice kendi beyanını silebiliyor. |
| Tam koşu (kapatmalardan sonra) | `pytest tests -q` | **40 failed / 2349 passed / 9 skipped** — kırmızı kümesi baseline ile BİREBİR aynı (tümü eksik opsiyonel paket), **0 regresyon**, +18 yeni geçen test. |

**DOĞRULANMADI:** CI'ın yeşil olduğu (bu sandbox'ta GitHub Actions koşmadı);
`maigret`/`holehe`/`socid-extractor` kurulu bir ortamda 40 kırmızının sıfırlandığı
(paketler burada kurulu değil); Railway/Cloudflare üzerinde uçtan uca dağıtım.

---

## 8. Kaldırma (tek komut zinciri)

```bash
# 0) Ortam dosyası
cp .env.example .env          # §6 tablosundaki BLOCKER'ları doldur

# 1) Bağımlılıklar
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium

# 2) Frontend
cd frontend && npm ci && npm run build && cd ..

# 3) Kapı kontrolleri (hepsi yeşil olmalı)
python -m pytest tests/unit/test_room_ownership_idor.py -q
python -m ruff check .
(cd frontend && npm audit && npx svelte-check --tsconfig ./tsconfig.app.json)

# 4) Sunucu — CWD depo kökü OLMALI (bkz. §5.4: import anında ./cache ve
#    ./frontend yazılıyor; başka CWD'de salt-okunur FS'de açılış patlar)
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000

# 5) Cloudflare secret
npx wrangler pages secret put BACKEND_ORIGIN
```

Manuel IDOR doğrulaması (iki operatörle):

```bash
# Bob, Alice'in oda adıyla → 403 ROOM_FORBIDDEN beklenir
curl -s -H "X-API-Key: $BOB_TOKEN" "$ORIGIN/api/tasks?client_id=alice-room-01"
# §4 kapatıldı: Bob KENDİ odasıyla Alice'in task_id'sini silmeye çalışınca
# 403 ROOM_FORBIDDEN beklenir ve kanıt dosyası diskte kalır
curl -s -X DELETE -H "X-API-Key: $BOB_TOKEN" \
  "$ORIGIN/api/tasks/<alice_task_id>?client_id=bob-room-01"
```

---

## 9. Çürütülen hipotezler (bulgu diye yazılmadı)

Bunlar arandı ve **temiz** çıktı: hardcoded API anahtarı yok; `shell=True` ile
komut enjeksiyonu yok; SSRF tersine iyi korunmuş (DNS pinleme + yönlendirmede
yeniden doğrulama); tanımsız değişken yok; CORS gevşek değil; global exception
handler var; `/health` canlı sunucuda `200 ready`.

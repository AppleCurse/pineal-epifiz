# `backend/api.py` Tek-Modül Şişkinliği — Ölçüm ve Bölme Planı

**Tarih:** 2026-10-07 · **Kaynak:** Üretim denetimi, P2 maddesi
**Ölçüm noktası (commit öncesi):** `backend/api.py` = **6.034 satır**, **72 uç nokta**

---

## 1. Sorun

`backend/api.py`, FastAPI uygulamasının TAMAMINI tek bir modülde taşıyor:
yaşam döngüsü (lifespan), middleware'ler, kimlik doğrulama, hız sınırlama,
kasa (vault) yönetimi, tarayıcı oturumları, görev yürütme, OSINT, konuşma
sentetikleme, MCP köprüsü ve OpenAI uyumlu ağ geçidi.

Somut maliyetleri:

| Maliyet | Açıklama |
|---|---|
| **Değişiklik çakışması** | Her dokunuş aynı dosyada: eş zamanlı çalışma ve gözden geçirme zorlaşır |
| **İçe aktarım yan etkisi** | Modül içe aktarıldığında CORS/bağlam/kasa gibi kurulum kodları koşar; tek bir sembol için bile tüm dosya yüklenir |
| **Test izolasyonu** | Uç noktalar tek bir `app` nesnesine bağlı: bir alt sistemi yalıtmak zor |
| **İnceleme yükü** | 6.000 satırlık bir dosyada "gözden kaçan" kusur olasılığı yüksek (bu denetimde de böyle bir kusur bulundu: gövde tavanı middleware'i istisna yutuyordu) |

---

## 2. Atılan adımlar

### 2.1 İlk bölme — gövde tavanı middleware'i (2026-10-07)

Bölme, **en iyi test edilmiş ve en az bağımlılığı olan** katmanla başlar:

| Modül | Satır | Test |
|---|---|---|
| `backend/middleware/body_size_limit.py` | 127 | `tests/unit/test_body_size_limit.py` (14 test) |

* `backend/api.py`: **6.034 → 5.937 satır** (−97)
* Geriye dönük uyumluluk korunur: `backend/api.py` isimleri yeniden ihraç
  eder (`from backend.middleware.body_size_limit import ... as ...`),
  yani `from backend.api import BodySizeLimitMiddleware` DEĞİŞMEDEN çalışır.
* Kilit: `tests/unit/test_api_monolith_ratchet.py`

### 2.2 İkinci bölme — `/api/language/*` (2026-10-14, API-BÖLME 2)

| Modül | Satır | Test |
|---|---|---|
| `backend/routes/language.py` | 152 | `tests/integration/test_language_api_faz_d.py` (9), `tests/unit/test_language_detect.py` |

* Tetikleyici: dosyaya modül docstring'i (envanter açıklaması) yazılacaktı; ölçüm
  `backend/api.py = 6.000 satır` gösterdi — yani tavanın TAM ÜSTÜNDE. Kural
  işletildi: **satır eklemek yerine modül çıkarıldı.**
* `backend/api.py`: **6.000 → 5.916 satır** (docstring dâhil).
* Tavan (`MAX_LINES`) 6.000 → **5.916** olarak DÜŞÜRÜLDÜ (ratchet: geri çıkış yok).
* Uç gövdeleri DEĞİŞMEDİ; yalnız enjekte edilen adlar bağlandı
  (`_check_vault_interlock` → `check_vault_interlock`, `_flag_env` → `flag_env`).
* Dış sözleşme korunur: `backend/api.py` payload modellerini ve
  `register_language_routes`'u yeniden ihraç eder.
* Yeni kilitler: `test_language_split_module_exists_and_is_importable`,
  `test_api_reexports_language_split_symbols`,
  `test_language_routes_are_registered_on_the_app`,
  `test_api_does_not_redefine_language_models`.

### 2.3 Üçüncü bölme — `/api/telemetry` + web dosyası (2026-10-16, API-BÖLME 3)

| Modül | Satır | Test |
|---|---|---|
| `backend/routes/telemetry.py` | 135 | `tests/unit/test_p0_honest_status.py`, `tests/unit/test_task_lifecycle.py`, `tests/e2e/test_smoke.py` |
| `backend/services/web_dossier.py` | 184 | `tests/unit/test_p0_honest_status.py` |

* Tetikleyici: Faz 2 · P0 dürüstlük düzeltmeleri (kanıt tipi ayrımı, kanal
  durumu, telemetri sebep tablosu) `backend/api.py`'yi 6.021 satıra çıkardı;
  tavan 5.916 idi. Kural işletildi: **satır eklemek yerine modül çıkarıldı.**
* `backend/api.py`: **6.021 → 5.908 satır**.
* Tavan (`MAX_LINES`) 5.916 → **5.908** olarak DÜŞÜRÜLDÜ (ratchet: geri çıkış yok).
* Uç gövdeleri DEĞİŞMEDİ; `/api/telemetry` yolu ve yanıt anahtarları aynen
  korundu (`capabilities` / `x_scraper_reason` YENİ alanlar eklendi).
* Dış sözleşme korunur: `backend/api.py` `api_telemetry` ve
  `capability_status_table` adlarını yeniden ihraç eder.
* `tests/unit/test_rust_runtime_status.py` içindeki `allowed_status_surfaces`
  listesine `backend/routes/telemetry.py` eklendi: bu modül rust çekirdeğini
  **çağırmaz**, yalnız `backend/api.py`'den enjekte edilen durumu aktarır.

### 2.4 Dördüncü bölme — public-web araştırma (2026-10-16, API-BÖLME 4)

| Modül | Satır | Test |
|---|---|---|
| `backend/services/web_research.py` | 214 | `tests/unit/test_alternative_web_research.py`, `tests/unit/test_crawl_enricher.py` |

* Tetikleyici: Faz 2 · P1 (profil derinleştirme) `backend/api.py`'ye bağlantı
  satırları eklemek zorundaydı; tavan 5.908 idi ve **artırılamazdı**.
  Kural işletildi: **satır eklemek yerine modül çıkarıldı.**
* Taşınan gövde: `_run_public_web_research` (159 satır) + `_extract_handle_from_url`
  (9 satır) → `backend/services/web_research.py`.
* `backend/api.py`: **5.908 → 5.805 satır**.
* Tavan (`MAX_LINES`) 5.908 → **5.805** olarak DÜŞÜRÜLDÜ (ratchet: geri çıkış yok).
* Dış sözleşme korunur: `backend/api.py` `_run_public_web_research` ve
  `_extract_handle_from_url` adlarını yeniden ihraç eder.
* Bağımlılıklar **ENJEKTE** edilir: kasa mandalı (`vault_locked_fn`) ve arama
  sağlayıcısı çağırandan gelir; modül `backend.api`'yi içe aktarmaz
  (dairesel bağımlılık yok — yalnız geriye dönük uyum için TEBEL İÇE AKTARIM var).
* `tests/unit/test_api_monolith_ratchet.py` yeni bölme için de kapatıldı
  (modül var mı, yeniden ihraç var mı, gövde kopyalanmış mı, tavan düştü mü).

---

## 3. Uç nokta envanteri (ölçülen dağılım)

Aşağıdaki tablo, gerçek `@app.*` dekoratörlerinden sayılmıştır. Bölme
sırası, **bağımlılığı en az olandan çoğa** doğru önerilir.

| Alan | Uç nokta | Önerilen hedef modül | Bağımlılık |
|---|---|---|---|
| `/api/experimental` | 9 | `backend/routes/experimental.py` | Orta |
| `/api/browser` | 9 | `backend/routes/browser.py` | Orta (BrowserSession) |
| `/api/tasks` | 7 | `backend/routes/tasks.py` | Yüksek (executor + lifecycle) |
| `/api/speech` | 6 | `backend/routes/speech.py` | Düşük |
| `/api/vault` | 5 | `backend/routes/vault.py` | Orta (disk + şifreleme) |
| `/api/minor` | 3 | `backend/routes/minor.py` | Orta |
| `/api/language` | 3 | `backend/routes/language.py` ✅ **taşındı (2.2)** | Düşük |
| `/api/calibration` | 3 | `backend/routes/calibration.py` | Orta |
| `/api/aspasia` | 3 | `backend/routes/aspasia.py` | Orta |
| `/v1` (OpenAI uyumlu) | 2 | `backend/routes/openai_compat.py` | Yüksek (gateway) |
| `/api/telemetry` | 2 | `backend/routes/telemetry.py` | Düşük |
| `/api/report` | 2 | `backend/routes/report.py` | Orta |
| `/api/memory` | 2 | `backend/routes/memory.py` | Orta |
| `/api/media` | 2 | `backend/routes/media.py` | Orta |
| `/api/jury` | 2 | `backend/routes/jury.py` | Orta |
| `/api/company` | 2 | `backend/routes/company.py` | Orta |
| `/api/agents` | 2 | `backend/routes/agents.py` | Düşük |
| `/ws` | 1 | `backend/routes/websocket.py` | Yüksek (odalar) |
| `/health` | 1 | `backend/routes/health.py` | Düşük |
| `/api/scraper`, `/api/override`, `/api/mcp`, `/api/initiate`, `/api/executor`, `/api/dialogue` | 1'er | `backend/routes/*.py` | Değişken |

**Toplam:** 72 uç nokta.

---

## 4. Uygulama sırası (öneri)

Her adım TEK bir modül taşır, testler YEŞİL kalır ve `backend/api.py`
yeniden ihraç etmeye devam eder. Bu sayede her adım bağımsız ve geri
alınabilir (revertible) olur.

1. **Düşük bağımlılık:** ~~`language`~~ ✅ (bkz. 2.2), `speech`, `telemetry`,
   `health`, `agents`
2. **Orta:** `vault`, `report`, `memory`, `media`, `jury`, `company`,
   `calibration`, `aspasia`, `experimental`, `browser`
3. **Yüksek bağımlılık (en sona bırakılır):** `tasks`, `/v1` OpenAI uyumlu
   ağ geçidi, `/ws` websocket odaları — bunlar `app.state.rooms` ve
   yaşam döngüsü ile sıkı bağlıdır.

### Taşıma kontrol listesi

- [ ] Yeni modül `APIRouter(prefix="/api/...", tags=[...])` kullanır
- [ ] Uç nokta GÖVDELERİ değişmez (yalnızca taşınır)
- [ ] `backend/api.py` içinde `app.include_router(...)` çağrılır
- [ ] Mevcut isimler yeniden ihraç edilir (dış sözleşme bozulmaz)
- [ ] `tests/unit/test_api_monolith_ratchet.py` tavanı DÜŞÜRÜLÜR
- [ ] Tam koşu yeşil: `pytest -q` + `ruff check .`

---

## 5. Tavan (ratchet) politikası

`backend/api.py` için satır tavanı `tests/unit/test_api_monolith_ratchet.py`
içinde tanımlıdır. Dosya KÜÇÜLEBİLİR; tavana yaklaşınca yeni uç nokta
eklemek yerine **yukarıdaki sıradan bir modül çıkarılır**.

Tavanı yükseltmek, bu belgeye gerekçe yazmayı gerektirir — yani şişkinlik
 ancak BİLİNÇLİ bir kararla büyüyebilir.

**Güncel ölçüm (2026-10-14):** `backend/api.py` = **5.916 satır** ve içinde
**67 uç dekoratörü**; `/api/language/*` (3 uç) artık `backend/routes/language.py`
içinde. `app.routes` toplamı **80 rota nesnesi** (dekoratörlü uçlar + statik mount
+ FastAPI varsayılanları). Tavan **5.916**.

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

## 2. Bu denetimde atılan adım (ilk bölme)

Bölme, **en iyi test edilmiş ve en az bağımlılığı olan** katmanla başlar:

| Modül | Satır | Test |
|---|---|---|
| `backend/middleware/body_size_limit.py` | 127 | `tests/unit/test_body_size_limit.py` (14 test) |

* `backend/api.py`: **6.034 → 5.937 satır** (−97)
* Geriye dönük uyumluluk korunur: `backend/api.py` isimleri yeniden ihraç
  eder (`from backend.middleware.body_size_limit import ... as ...`),
  yani `from backend.api import BodySizeLimitMiddleware` DEĞİŞMEDEN çalışır.
* Kilit: `tests/unit/test_api_monolith_ratchet.py`

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
| `/api/language` | 3 | `backend/routes/language.py` | Düşük |
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

1. **Düşük bağımlılık:** `speech`, `language`, `telemetry`, `health`, `agents`
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

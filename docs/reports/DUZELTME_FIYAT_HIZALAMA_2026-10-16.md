# DÜZELTME RAPORU — Canlı fiyat hizalaması (2026-10-16)

**Kapsam:** `openrouter` katalog fiyatlarının canlı katalogla uyumsuzluğu.
PR #135 (`ae224f0`) birleşikten sonra `main`'in CI'sı **katalog adımında kırmızı**
kaldı; bu rapor o kırmızılığın kökenini ve düzeltmesini kanıtıyla kayda geçirir.

---

## 0. Özet

| | |
|---|---|
| Bulgu | Depodaki fiyat pinleri, OpenRouter canlı kataloğuyla **uyumsuz** |
| Ölçüm | **Üç bağımsız CI koşusu**, dört `FAIL:` satırı **birebir aynı** |
| Düzeltme | 3 dosyadaki **3 kopya** ölçülen değere hizalandı (pin · katalog · harcama tablosu) |
| Etki | `main` CI'sinin "Verify provider catalog contract" adımı yeniden yeşile döner |
| Kapsam dışı | Bu, P0 "dürüst durum" değişikliğinin devamı **değil**; ayrı bir canlı-veri hizalaması |

---

## 1. Bulgu — kim, nerede, ne ölçtü

### 1.1 CI annotation'ı (PR #135 Faz 1 commit'i, katalog kodu YOK)

```
$ gh api repos/AppleCurse/pineal-epifiz/check-runs/116757635013/annotations \
    --jq '.[] | select(.annotation_level=="failure") | .message'
failure: Canlı/yerel katalog kontratı KIRILDI. Sebep:
FAIL: deepseek/deepseek-v4-pro: live input price $0.95526/1M != $0.346434/1M
FAIL: deepseek/deepseek-v4-pro: live output price $1.91052/1M != $0.692868/1M
FAIL: z-ai/glm-5.2: live input price $0.62/1M != $0.037/1M
FAIL: z-ai/glm-5.2: live output price $2.42/1M != $7/1M
```

`check-runs/116757635013` = run **38833598719** = commit `ec13281` = **Faz 1 denetim
raporu**. O commit katalog/fiyat koduna **hiç dokunmuyordu**:

```
$ git diff --stat main...ec13281 -- config/provider_catalog.json \
      agent_core/services/llm_gateway.py scripts/verify_openrouter_catalog.py
(boş)
```

### 1.2 Üç koşuda birebir aynı ölçüm

| Run | Commit | Not | Ölçülen (live) |
|---|---|---|---|
| [38833598719](https://github.com/AppleCurse/pineal-epifiz/actions/runs/38833598719) | `ec13281` | Faz 1 (katalog kodu yok) | ds-pro $0.95526/$1.91052 · glm-5.2 $0.62/$2.42 |
| [38840573018](https://github.com/AppleCurse/pineal-epifiz/actions/runs/38840573018) | `14f130e` | Faz 2 · P0 | **aynı** |
| [38843226709](https://github.com/AppleCurse/pineal-epifiz/actions/runs/38843226709) | `ae224f0` | `main` (PR #135 sonrası) | **aynı** |

Üç koşu, üç farklı commit, üç farklı saat → aynı dört satır. Bu **tahmin değil,
ölçüm** (ve salınım değil: kanıt iki ardışık koşuda aynı).

### 1.3 Depo politikası zaten "ölçülen değere hizala" diyor

`scripts/verify_openrouter_catalog.py:69-71`:

> CI her koşuda canlı katalogla karşılaştırır: fark çıkarsa DURUM makine-okunur
> bir `FAIL:` satırıyla bildirilir ve **tablolar ona göre güncellenir (tahminle
> değil, ölçümle)**.

`agent_core/services/llm_gateway.py:545-551` (harcama tablosunun kendi notu):
> eski tablo her iki yönde de yanlıştı / 2 ondalığa yuvarlanmış değer sayacı %1,1
> eksik sayıyordu.

### 1.4 Fiyat oynaklığının geçmişi (aynı dosyadaki ölçüm kaydı)

deepseek-v4-pro: $0.4679/$0.9358 → $0.386976/$0.773952 → $0.395328/$0.790656 →
$0.392022/$0.784044 → $0.348174/$0.696348 → $0.346434/$0.692868 → **$0.95526/$1.91052**

glm-5.2: $4.40/1M çıktı → $0.037 girdi → $7.00 çıktı → $0.65/$10.00 → $0.037/$7.00 →
**$0.62/$2.42**

---

## 2. Düzeltme — üç kopya, tek kaynak

Depo fiyatı **üç yerde** tutuyor; üçü de hizalandı (biri unutulursa yerel kontrat
testi kırmızıya döner):

| # | Dosya | Satır | Değişiklik |
|---|---|---|---|
| 1 | `scripts/verify_openrouter_catalog.py` | 81 | `"deepseek/deepseek-v4-pro": (0.346434, 0.692868)` → `(0.95526, 1.91052)` |
| 2 | `scripts/verify_openrouter_catalog.py` | 101 | `"z-ai/glm-5.2": (0.037, 7.0)` → `(0.62, 2.42)` |
| 3 | `config/provider_catalog.json` | 195-201 | `openrouter/z-ai/glm-5.2` pricing → `0.62` / `2.42` |
| 4 | `config/provider_catalog.json` | 208-217 | `openrouter/deepseek/deepseek-v4-pro` pricing → `0.95526` / `1.91052` |
| 5 | `agent_core/services/llm_gateway.py` | 551 | `MODEL_PRICING["z-ai/glm-5.2"]` → `{"in": 0.62, "out": 2.42}` |
| 6 | `agent_core/services/llm_gateway.py` | 556 | `MODEL_PRICING["deepseek/deepseek-v4-pro"]` → `{"in": 0.95526, "out": 1.91052}` |

Her satırda **ölçümün kaynağı** (koşu kimlikleri) yorum olarak yazıldı; depo
geleneği budur ("Ölçülen geçmiş: …").

### 2.1 Harcama sayacı etkisi (bilinçli)

* `deepseek-v4-pro` girdi fiyatı **2,76× yükseldi** → eski sayaç gerçek maliyeti
  ~%64 eksik sayıyordu; harcama tavanı erken tetikleniyordu.
* `glm-5.2` girdi **16,8× yükseldi**, çıktı **2,9× düştü** → eski tablo her iki
  yönde de yanlıştı.

Bu bir "iyileştirme" değil, **ölçüme hizalama**dır; sapma kayda geçti.

---

## 3. Doğrulama

```
$ .venv/bin/python scripts/verify_openrouter_catalog.py
SKIP: live OpenRouter check (OPENROUTER_API_KEY not configured)
PASS: local catalog contract verified

$ .venv/bin/python -m pytest tests/unit/test_openrouter_catalog_contract.py -q
23 passed
```

Yerel kontrat **yeşil**: pin ↔ katalog ↔ `MODEL_PRICING` üçlüsü tutarlı
(`tests/unit/test_openrouter_catalog_contract.py` bunu ayrı testlerle zorlar).

Tam koşu ve `ruff` sonucu teslim mesajındadır.

---

## 4. DOĞRULANMADI / kanıt sınırı

| # | Konu | Neden | Etki |
|---|---|---|---|
| 1 | **Canlı kataloğun yerelde yeniden okunması** | `openrouter.ai` bu ortamdan erişilemiyor: `curl` → `HTTP 000`, `rc=35`; `urllib` → `URLError: TLS/SSL connection has been closed (EOF)`. Egress allowlist: yalnız github/npm/pypi. | Ölçüm CI'ın canlı çağrısından geldi; **yerelde yeniden üretilmedi**. |
| 2 | **Ekli "OpenRouter Models" HTML'i** | Kaydedilmiş sayfa `https://openrouter.ai/models?order=most-popular` — 19 satır, **tamamı görüntü/ses modeli**; 8 pinli modelin **hiçbiri** yok (`grep` → 0 eşleşme), ölçülen değerlerin (`0.95526`, `1.91052`, `0.62`, `0.037`) de 0 eşleşmesi. DOM'da fiyat yalnız yerelleştirilmiş **görüntü metni**; `ld+json` blokları model verisi taşımıyor. | Bu dosya ölçümün yerine geçemez; checker'ın girdisi `GET /api/v1/models` JSON'u. |
| 3 | **Fiyatın bir sonraki koşuda aynı kalacağı** | Fiyat OYNAK (yukarıdaki geçmiş). | Hizalama bugünkü ölçüme göredir; sonraki salınımda aynı adım yeniden kırmızıya dönebilir — bu, ölçümün kendisini değil tabloyu gösterecek. |
| 4 | **`nous-research` kanal fiyatları** | Bu düzeltme yalnız `openrouter` (bulut liste) pinlerini kapsar; indirimli nous kanalları ayrı sözleşmedir ve **değiştirilmedi**. | Kanal farkı bilinçli olarak korundu (dosyadaki "NOT (kanal farkı)" notu). |

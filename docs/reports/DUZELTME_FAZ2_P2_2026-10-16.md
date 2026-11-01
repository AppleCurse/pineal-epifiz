# DÜZELTME RAPORU — Faz 2 · P2 · Çapraz profilleme (2026-10-16)

**Kapsam:** Denetim maddesi 11 — *"Denetimde yok → deterministik ve kanıtlı
eşleştirme yaz: (a) aynı kullanıcı adı varyantı, (b) bio'daki ortak harici
link, (c) socid ortak ID. Her eşleşme `EvidenceItem`; güven skoru **'kapsam'**
(coverage) etiketiyle, olasılık olarak sunulmadan."*

---

## 0. Özet

| | |
|---|---|
| Bulgu | Denetimde çapraz profilleme kodu **yoktu**; PR #138 ile `main`'e bir uygulama geldi, ancak **üç gerçek kusur** taşıyordu (aşağıda kanıtıyla) |
| Düzeltme | `agent_core/services/cross_profiler.py` yeniden yazıldı: alt dize eşleşmesi yok, socid id kullanıcı adı sayılmıyor, skor **"kapsam"** etiketli ve `confidence` alanına girmiyor |
| Kanıt | 13 yeni P2 sözleşme testi · revert-doğrulama **3/3** · tam koşu yeşil · UI rozeti eklendi |
| Kapsam dışı | P3 (Lilith) ve P4 (dokümantasyon) ayrı fazlar |

---

## 1. Bulgu — PR #138'in uygulamasındaki üç gerçek kusur

PR #138, `main`'e (squash commit `d83c67b`) `agent_core/services/cross_profiler.py`
(260 satır) ekledi. Denetim maddesi 11'in sözleşmesine bakıldığında **üç ayrı
ihlal** var. Her biri için "düzeltilmiş hâl → eski hâl" geri alıması ve
kırmızıya dönmesi ayrı ayrı doğrulandı (bkz. §4).

### 1.1 Alt dize eşleşmesi → yanlış pozitif

Eski kod (PR #138, `cross_profiler.py`):

```python
if a1["url"].lower() in bio_text:      # hesabın adresi biyografinin ALT DİZESİ mi?
    method = "cross_link"; conf = 0.95
```

Hedefin biyografisinde `https://x.com/alicexyz` yazıyorsa, `x.com/alice`
adresindeki **başka** bir hesap "bağlantı" sanılıp **0.95** ile eşleştirilir —
yani en güçlü sinyalle, %95'lik (olasılık gibi okunan) bir güvenle. Ölçülen
hata: **eşleşme yok olması gereken yerde üretiliyor.**

### 1.2 socid kimlik alanı kullanıcı adı gibi eşleşiyor → yanlış pozitif

Eski kod:

```python
for k in ("username", "user_id", "login", "screen_name", "account"):
    val = fields.get(k)
    if isinstance(val, str) and val.strip():
        _register(p, val.strip(), source_url, "socid_identity")
```

socid'in okuduğu `user_id` bir **platform içi kimliktir**, kullanıcı adı
değildir. Bu yüzden `user_id=4242` ile başka bir platformdaki `@4242` hesabı
"birebir aynı kullanıcı adı" sanılıp eşleştirilir — **rastgele sayı
çakışması** kimlik eşleşmesi sanılır.

### 1.3 Skor olasılık gibi sunuluyor + alan sözleşmesi ihlali

Eski kod:

```python
conf = 0.95 / 0.85 / 0.70
...
ev = make_evidence(..., confidence=m.confidence, ...)
```

İki ayrı ihlal:

1. Denetim maddesi 11 "güven skoru **'kapsam'** etiketiyle, olasılık olarak
   sunulmadan" diyor; eski kod skoru "korelasyon güveni" diye sunuyor.
2. `agent_core/domain/evidence_models.py:48-53` alan sözleşmesi:
   *"Calibrated confidence only; source scores must remain in source_metrics."*
   → kalibre edilmemiş bir heuristik skoru `confidence` alanına yazılamaz.

---

## 2. Düzeltme

`agent_core/services/cross_profiler.py` yeniden yazıldı.

### 2.1 Sinyaller (yalnız deterministik)

| Sinyal | Koşul | Ağırlık (kapsam) |
|---|---|---|
| `self_declared_link` | hedefin biyografisindeki bağlantı, hesabın adresiyle **birebir** aynı (normalize edilmiş: şema/`www.`/sondaki `/` düşer) | 0.45 |
| `exact_handle` | kullanıcı adları birebir aynı | 0.30 |
| `normalized_handle` | nokta/altçizgi/tire varyantı (normalize uzunluk ≥ 5) | 0.15 |
| `shared_platform_id` | socid'in **iki URL'de** okuduğu ortak kimlik alanı | 0.10 |

Toplam 1.00. Ek kurallar: aynı platformdaki iki hesap "çapraz profil" değildir ·
jenerik kullanıcı adları (`admin`, `login`, …) ve 3 karakterden kısa adlar
eşleşme üretmez · sinyal yoksa eşleşme **yoktur** (olasılıksal eşleştirme yok).

### 2.2 Skor artık "kapsam"dır

```
coverage = Σ (yanan sinyallerin ağırlıkları)      # [0,1], normalize_confidence ile doğrulanır
```

Kanıtta:

* `EvidenceItem.confidence = None` — alan sözleşmesi gereği (kalibre edilmemiş
  skor `confidence` alanına girmez);
* `source_metrics = {"coverage": …, "coverage_label": "kapsam",
  "coverage_is_probability": False, "signals": [...]}`;
* `scope["confidence_label"] = "kapsam"`;
* metin: *"… eşleşti (sinyal: exact_handle; kanıt kapsamı: 0.30 — olasılık
  DEĞİLDİR)"* — yüzde dili yok.

### 2.3 Bağlantı

Görev yürütücüsü eşleşmeleri hem payload'a (`cross_profile_matches`) hem de
hedef profilin içine (`target_profile.cross_profile_matches`) yazar; kanıt
zinciri `extra_items` kanalıyla girer (P1 ile **aynı** mekanizma). UI'da profil
kartının altında **"ÇAPRAZ PROFİL (çıkarım · kapsam)"** başlığıyla listelenir.

---

## 3. Ölçüm

```
pytest tests/unit/test_p2_cross_profiling.py      → 13 passed  (YENİ)
pytest tests/unit/test_p1_p2_deep_profiling.py    → 15 passed  (PR #138 sözleşmeleri, güncellendi)
pytest tests -q                                   → tam koşu (aşağıdaki teslim notunda)
ruff check .                                      → All checks passed!
npm run check                                     → svelte-check found 0 errors and 0 warnings
npm run build                                     → ✓ built in 1.83s
scripts/revert_verification_p2.py                 → 3/3 PASS
```

PR #138'in üç P2 testi **bilinçli olarak güncellendi**: `confidence == 0.85 /
0.95 / 0.70` gibi "olasılık" değerleri artık `coverage == SIGNAL_WEIGHTS[...]`
ve `confidence_label == "kapsam"` olarak sözleşmeleniyor. Aynı testlerin
reddedildiği davranış (eşleşmenin üretilmesi) korunmuştur.

---

## 4. Revert-doğrulama (3/3)

`scripts/revert_verification_p2.py` her düzeltmeyi geri alıp hedef testin
**kırmızıya döndüğünü** doğrular:

| # | Düzeltme | Test |
|---|---|---|
| P2-1 | alt dize eşleşmesi → `test_substring_url_in_bio_is_not_a_match` |
| P2-2 | socid id → `test_socid_id_does_not_match_an_unrelated_handle` |
| P2-3 | `confidence` alanına geri dönüş → `test_coverage_is_a_scope_score_not_a_probability` |

---

## 5. DOĞRULANMADI / kanıt sınırı

| # | Konu | Neden | Etki |
|---|---|---|---|
| 1 | **Canlı çapraz eşleşme (gerçek hesaplar)** | Bu ortamda dış ağ erişimi yok (instagram/x/linkedin → egress kapalı) | Eşleşmeler yalnız **sentezlenmiş girdilerle** sınandı; gerçek hesap çiftlerinde ölçülmedi |
| 2 | **Ağırlıkların kalibrasyonu** | `SIGNAL_WEIGHTS` **belgelenmiş uzman seçimi**, ölçülmüş kalibrasyon DEĞİL | "Kapsam" skoru bir olasılık DEĞİR; hangi boyutun ne kadar sayıldığı açıkça belgelidir, ama sayılar ampirik olarak doğrulanmamıştır |
| 3 | **Aynı kişilik kanıtı** | Eşleşme bir **çıkarımdır** (`epistemic_type="inference"`); gerçek kişilik doğrulaması yok | Eşleşmeler kanıt zincirine "gözlem" olarak değil "çıkarım" olarak girer |
| 4 | **Kapalı platformlar** | `PLATFORM_DOMAINS` listesi sabit | Yeni bir platform eklendiğinde liste güncellenmez; eşleşme **kaçırılır** (uydurma üretilmez) |

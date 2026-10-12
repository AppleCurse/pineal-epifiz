# YEREL JÜRİ — karar tek modele bırakılmaz, veri makineden çıkmaz

> FAZ D · D2 · 2026-10-07
> Aynı iddia ve kanıt, birden çok **yerel** modelde bağımsız oylanır; karar
> oybirliği ya da yeter sayılı çoğunlukla verilir.

## 1 · Neden

Panel kararı eskiden tek zincire (ya da uzak modellere) bağlıydı. Uzak jüri iki
şeyi bedava vermez: maliyet sıfır değildir ve hedef verisi makineden çıkar.
Yerel jüri aynı çapraz denetimi **yerel modellerde** koşar.

## 2 · Kurulum (Ollama örneği)

```bash
ollama pull llama3.1:8b && ollama pull qwen2.5:7b && ollama pull mistral:7b
export ENABLE_LOCAL_JURY=1
export PINEAL_JURY_LOCAL_MODELS="llama3.1:8b,qwen2.5:7b,mistral:7b"
# uç: varsayılan http://127.0.0.1:11434/v1 (Ollama OpenAI-uyumlu)
python -m uvicorn backend.api:app --port 8000
```

Uç adresi ``LOCAL_LLM_URL`` (LLM ağ geçidinin kullandığı aynı değişken) ya da
``PINEAL_JURY_LOCAL_URL`` ile verilir. **Uzak adres reddedilir.**

## 3 · Koltuk kuralı

- **Koltuk = ayrı model.** Aynı model adı iki kez yazılırsa ikinci koltuk
  SAYILMAZ (aynı ağırlıklar bağımsız oy vermez); tekrar ``duplicates_removed``
  olarak raporlanır.
- Tavan ``PINEAL_JURY_SEATS`` (varsayılan 3, en çok 5).
- Tek model tanımlıysa jüri koşar ama kural ``tek_koltuk`` olur ve
  ``consensus: false`` döner: **tek koltukla konsensüs ilan edilmez.**

## 4 · Karar kuralları (makine-okunur)

| Kural | Anlamı | ``consensus`` |
|---|---|---|
| ``oy_birligi`` | Bütün koltuklar aynı oyu verdi | ✅ |
| ``cokluk`` | Çoğunluk var ve yeter sayı karşılandı | ✅ |
| ``berabere`` | Eşit oy → hüküm ``BİLİNMİYOR`` | ❌ (kırılma uydurulmaz) |
| ``tek_koltuk`` | Tek geçerli oy | ❌ |
| ``gecerli_oy_yok`` | Hiçbir koltuk sözlük içi oy veremedi | ❌ |

Yeter sayı ``PINEAL_JURY_QUORUM`` (B1 denetçisiyle **aynı** ayar) ile belirlenir;
çoğunluk bu sayıyı karşılamıyorsa ``consensus`` false olur ve gerekçe not edilir.

**Konsensüs yoksa kanıt üretilmez.** Koltuk koltuk döküm (model, ham kelime,
kanonik oy, güven, gecikme, hata) yanıtta görünür — sessizce yutulan tek bir
koltuk yoktur.

## 5 · Oy sözlüğü

Kapalı küme **tek kaynaktan** gelir (``services/jury_consensus``):
``DOĞRULANDI`` · ``ÇELİŞKİLİ`` · ``YALAN`` · ``BİLİNMİYOR``. İngilizce yanıt
veren yerel modeller için yalnız şu karşılıklar geçerlidir: ``verified``,
``supported`` → DOĞRULANDI · ``contradicted`` → ÇELİŞKİLİ · ``false`` → YALAN ·
``unknown`` → BİLİNMİYOR. Bunların dışındaki her kelime **oy sayılmaz**
(``sozluk_disi``).

Model yanıtı JSON değilse ``seat_unparseable`` — model "sanırım doğru"
diyorsa bu oy değildir; uydurmaya çevrilmez.

## 6 · Kanıt türü

Jüri kararı kanıt zincirine **``inference``** olarak yazılır: bir model
yargısıdır, gözlem değildir. Kanıt içeriği karar + kural + kaç koltuğun oy
verdiğini taşır; ``confidence`` yalnız koltukların kendi beyanlarının
ortalamasıdır (yoksa ``None`` — uydurma güven yok).

## 7 · Yüzeyler

| Yüzey | Ne verir |
|---|---|
| ``GET /api/jury/status`` | Uç yerel mi, koltuklar, bağımsızlık, yeter sayı |
| ``POST /api/jury/vote`` | ``{claim, evidence}`` → karar + kural + koltuk dökümü |
| Kokpit **JÜRİ** pili | ``JÜRİ: 3 YEREL KOLTUK`` · ``1 KOLTUK · BAĞIMSIZ DEĞİL`` · ``KAPALI`` |
| MCP aracı ``verifier_jury_local`` | Dış istemciler de aynı mandalı kullanır (D1) |

Kapılar: ``vault`` (istisnasız) + ``ENABLE_LOCAL_JURY`` (varsayılan **kapalı**).

## 8 · Sınama

```bash
pytest tests/unit/test_local_jury.py tests/unit/test_local_jury_capability.py \
       tests/integration/test_jury_api_faz_d.py -q
```

Testler gerçek bir yerel OpenAI-uyumlu uç taklidi kullanır; hiçbir test ağa
çıkmaz ve hiçbir test uzak sağlayıcı çağırmaz.

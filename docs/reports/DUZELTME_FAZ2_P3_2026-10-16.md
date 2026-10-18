# DUZELTME FAZ 2 — P3 (LILITH: KARAR + ANA HAT KAPILARI)

**Tarih:** 2026-10-16
**Kapsam:** Denetim maddesi 12 (Lilith) + M-2 (LLM maliyet/sayac bypass'ı)
**Önceki faz:** P0 MERGED (`ae224f0`) · fiyat MERGED (`e4a4478`) · P1+P2 MERGED (`0550d41`, PR #139)

---

## 1. DENETİMDE DOĞRULANAN BULGULAR (kanıtlı)

### 1.1 M-2 — Lilith CLI, ana hattın bütçe/kapı düzenini BYPASS ediyordu

**Kanıt (dosya:satır):**

| Konum | Gerçek |
|---|---|
| `agent_core/agents/lilith_growth.py:254` | `class OpenAICompatibleGateway` — kendi `httpx` istemcisi (`open_client(purpose="llm")`, satır 285) |
| `agent_core/agents/lilith_growth.py:313-331` (ESKİ) | `from_cli_credentials()` → `OpenAICompatibleGateway` (bypass) veya `FreeTextGateway` |
| `run_lilith.py:26-64` (ESKİ) | `resolve_credentials()` yalnız `OPENROUTER_BASE_URL` / `OPENAI_BASE_URL` / `NOUS_API_KEY` / `OPENAI_API_KEY` / kasa dosyası okuyor — **`NINEROUTER_*` yok** |
| `agent_core/services/llm_gateway.py:144-163` | Ana hattın taşıma sırası: `NINEROUTER_* > PINEAL_LLM_* > OPENROUTER_*` |
| `agent_core/services/llm_gateway.py:954` | `self.spend_cap_usd = ... "OPENROUTER_MAX_SPEND_USD"` — Lilith bu sayaca **girmiyordu** |
| `agent_core/services/llm_gateway.py:2303-2312` | Canlı çağrı kapısı: `LIVE_LLM_E2E=1` / `PINEAL_ROUTER_LIVE=1` yoksa `REAL_LLM_CALL_NOT_EXECUTED` — Lilith bu kapıdan **geçmiyordu** |

**Sonuç:** Lilith'in ölçülen maliyeti ana hattın sayacına yazılmıyordu; ana hatta uygulanan canlı çağrı kapısı Lilith için işlemiyordu.

### 1.2 README_TECHNICAL.md, kodla ÇELİŞİYORDU

- **Eski metin (README_TECHNICAL.md:161):** "ham profil metni prompt bağlamına doğrudan eklenmez."
- **Gerçek kod (`agent_core/agents/lilith_growth.py:586-593`):** hedef `bio` → `profile_lines.append(f"Biyografi: {target_bio}")`, ilk 10 `post` → `profile_lines.append("Paylaşımlar: " + " | ".join(target_posts))` → `target_profile_text` → `context_block` → **prompt'a düz metin olarak giriyor.**
- Yani iddia yanlıştı; kod "ekliyor".

### 1.3 README'de yanlış dosya yolu

- **Eski metin (README.md:183):** `scripts/run_lilith.py` — **bu dosya YOK**; `run_lilith.py` **depo kökünde** (`ls scripts/run_lilith.py` → "No such file"; `docs/inventory_notes.json` kökü doğru gösteriyor).

### 1.4 Lilith'in "kopuk ada" olup olmadığı — ÇÜRÜTÜLDÜ

- `agent_core/agents/lilith_growth.py` gerçek bir ajan (303+ satır), `tests/unit/test_lilith_growth.py` 21 test içeriyor, `config/agent_tiers.json:76-79` tier tanımı var → **kopuk ada değil**, kasıtlı ayrı bir CLI ürünü.

---

## 2. KARAR (P3 teslim şartı: "ana hatta bağla ya da CLI-only belgele")

**KARAR: Lilith **CLI-only** kalır; ayrıca CLI, çağrılarını **ana hattın `LLMGateway`'i** üzerinden yapar.**

**Gerekçe (koddan türetilmiş):**

1. **Kanıt–üretim ayrımı:** Lilith'in çıktısı `LilithContentPackage`'tır — kanıt değil, **üretimdir**. Ana hatta bağlansaydı "gönderi" alanı snippet tabanlı olur, "hedef" ile "bulunan profil" ayrımı bulanıklaşırdı (P1'in `content_basis` disiplininin ihlali).
2. **Kanıt zinciri:** Lilith'in girdisi *profil metnidir*; bu metin bir **kanıt kaynağı değildir**. Kanıt zincirine karışmamalıdır.
3. **Bütçe disiplini:** Kullanıcı "ana hatta bağla" dediğinde amaç kanıt zinciri değil, **maliyet/kapı disiplininin Lilith'e de uygulanmasıydı** (M-2). Bu, "CLI-only" ile çelişmez: ajanın konumu aynı kalır, **çağrı yolu** ana hatta bağlanır.

**Uygulanan sonuç:**

- Konum: **CLI-only** (ana görev hattından çağrılmaz — `tests/unit/test_p3_lilith_cli.py::test_lilith_cli_is_not_called_from_the_main_line` AST taramasıyla kilitli).
- Çağrı yolu: **ana hattın `LLMGateway`'i** → taşıma sırası, canlı kapı, bütçe sayacı, çağrı kaydı Lilith için de geçerli.
- Doküman: README + README_TECHNICAL açıkça yazıyor (karar + gerekçe + kapı kuralları).

---

## 3. YAPILAN DÜZELTMELER

### 3.1 `agent_core/agents/lilith_growth.py` — ana hat gateway'i (M-2)

`from_cli_credentials()` artık anahtar varsa **ana hattın `LLMGateway`'ini** kurar:

```python
if use_main_line_gateway and api_key:
    from agent_core.services.llm_gateway import LLMGateway
    return cls(llm_gateway=LLMGateway())
```

- Anahtar yoksa → `FreeTextGateway` (sıfır-maliyet, anahtar gerektirmeyen) — değişmedi.
- Eski `OpenAICompatibleGateway` yalnızca **açıkça** `use_main_line_gateway=False` ile seçilir (ölçülen maliyet ana hattın sayacına yazılmadığı için varsayılan DEĞİLDİR).
- Ajanın `_request_generation()` (satır 427-470) zaten `query_json`/`query_json_chain` sözleşmesini destekliyordu → ana hat gateway'i **değişiklik gerektirmeden** uyumlu ✓.

### 3.2 `run_lilith.py` — kasa anahtarı yedeği + dürüst hüküm

- **Yeni** `inject_vault_key_fallback()` (satır 33): kasa (`.pineal_vault.json`) anahtarı **yalnızca** `NINEROUTER_API_KEY`/`PINEAL_LLM_API_KEY`/`OPENROUTER_API_KEY` hiçbiri tanımlı değilse `OPENROUTER_API_KEY` olarak ortama eklenir → ana hattın taşıma sırası **korunur** (operatörün seçimi ezilmez).
- `main()` artık ana hattın kapısı reddederse **sessizce "başarılı" saymaz**: `stderr`'e `[LILITH] ÇALIŞMADI: <hüküm>` yazar ve **çıkış kodu 2** ile çıkar (satır 148-154).
- Modül docstring'ine karar ve kapı kuralları yazıldı.

### 3.3 `README_TECHNICAL.md:161` — iddia koda hizalandı

- "ham profil metni prompt bağlamına doğrudan eklenmez" → **"Verilen profildeki biyografi ve gönderi metni prompt bağlamına 'sağlanan metin' olarak eklenir (bkz. `agent_core/agents/lilith_growth.py:586-593`): bu metin bir üretim girdisidir, kanıt değildir"**.
- Lilith bölümüne **7. madde** eklendi: hangi kapılara tabi (taşıma sırası / canlı kapı / bütçe sayacı / anahtarsız fallback).
- 5. maddenin yolu düzeltildi: "Depo kökündeki `run_lilith.py`".

### 3.4 `README.md:183` — karar + doğru yol

- `scripts/run_lilith.py` → **depo kökündeki `run_lilith.py`** (ör. `python run_lilith.py --topic "..." --platform instagram`).
- Karar açıkça yazıldı: **"[P3 · 2026-10-16] kararı: CLI-only"** + gerekçe + kapı kuralları.

### 3.5 `tests/unit/test_lilith_growth.py` — eski sözleşme güncellendi

`test_from_cli_credentials_selects_correct_gateway` artık ana hat gateway'ini bekler; eski adaptör **yalnız açıkça seçildiğinde** beklenir.

---

## 4. ÖLÇÜM (ham çıktılar)

### 4.1 Yeni testler

```
$ .venv/bin/python -m pytest tests/unit/test_p3_lilith_cli.py -q -p no:cacheprovider
..........                                                               [100%]
10 passed in 2.65s
```

`tests/unit/test_lilith_growth.py` → **21 passed** (güncellenen sözleşme dahil).

### 4.2 Revert-doğrulama (her düzeltme geri alınınca KIRMIZI)

```
$ .venv/bin/python scripts/revert_verification_p3.py
PASS · P3-1 M-2: Lilith CLI ana hattın bütçe/kapı düzenini bypass ediyor
      test: tests/unit/test_p3_lilith_cli.py::test_cli_uses_the_main_line_gateway_when_a_key_exists
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P3-2 doküman: README_TECHNICAL 'ham profil metni eklenmez' diyor, kod ekliyor
      test: tests/unit/test_p3_lilith_cli.py::test_readme_technical_claim_matches_the_code
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P3-3 doküman: README Lilith kararını ve dosya yolunu yazmıyor
      test: tests/unit/test_p3_lilith_cli.py::test_readme_states_the_cli_only_decision
      revert sonrası pytest exit: 1 (beklenen: !=0)
PASS · P3-4 kapı: CLI canlı çağrı reddini yutuyor (sessiz başarı)
      test: tests/unit/test_p3_lilith_cli.py::test_the_live_gate_blocks_the_cli_instead_of_failing_silently
      revert sonrası pytest exit: 1 (beklenen: !=0)

REVERT-DOĞRULAMA (P3): 4/4 düzeltme geri alınınca KIRMIZIya döndü
```

Adım-4'ün kırmızıya dönme nedeni ayrıca doğrulandı: revert sonrası `SystemExit(2)` yerine `RuntimeError: REAL_LLM_CALL_NOT_EXECUTED` yükseliyor (test çıktısı: `E RuntimeError: REAL_LLM_CALL_NOT_EXECUTED: Canlı LLM çağrıları kapalı.`).

### 4.3 CLI'nin GERÇEKTEN koşumu (bu sandbox'ta)

```
$ .venv/bin/python run_lilith.py --topic "Test konusu" --platform instagram
Lilith içerik üretilemedi (ConnectError)
[LILITH] İçerik üretiliyor... (Konu: Test konusu | Platform: instagram)
=================================================================
🔥 LILITH NÖROBİLİŞSEL VİRAL İÇERİK MOTORU — MODEL ÇAĞRISI BAŞARISIZ — FALLBACK
=================================================================
...
```

- Sandbox'ta `NINEROUTER_*`/`OPENROUTER_API_KEY`/kasa dosyası **yok** → anahtar gerektirmeyen `FreeTextGateway` (Pollinations) denendi → egress kapalı olduğu için `ConnectError` → ajan **dürüstçe** "MODEL ÇAĞRISI BAŞARISIZ — FALLBACK" dedi, sahte içerik uydurmadı ✓.

### 4.4 Tam koşu + ruff + regresyon beçisi

```
$ .venv/bin/python -m pytest tests -q -p no:cacheprovider
2740 passed, 6 skipped, 319 warnings in 150.66s (0:02:30)

$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python scripts/audit_regression.py
✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.
```

(İlk tam koşuda 4 envanter testi kırmızıydı — 2 yeni dosya eklendiği için `docs/envanter.html` bayatlamıştı; `scripts/generate_inventory_page.py` ile yenilendi → 16 passed.)

---

## 5. DEĞİŞEN DOSYALAR

| Dosya | Değişiklik |
|---|---|
| `agent_core/agents/lilith_growth.py` | `from_cli_credentials` → ana hat `LLMGateway` (M-2); docstring'te karar |
| `run_lilith.py` | `inject_vault_key_fallback()`; kapı reddinde dürüst hüküm + çıkış kodu 2; docstring |
| `README.md:183` | CLI-only kararı + doğru dosya yolu |
| `README_TECHNICAL.md:161` | "sağlanan metin" gerçeği + 7. madde (kapı kuralları) + yol düzeltmesi |
| `tests/unit/test_lilith_growth.py` | Yeni gateway sözleşmesine güncellendi (eski sözleşme bilinçli değişti) |
| `tests/unit/test_p3_lilith_cli.py` | **YENİ** — 10 test |
| `scripts/revert_verification_p3.py` | **YENİ** — 4 adım |
| `docs/envanter.html` | Yenilendi (735 dosya) |

---

## 6. DOĞRULANMADI (sebebiyle)

1. **Canlı LLM çağrısının ana hattın sayacına yazılması** — DOĞRULANMADI: sandbox egress'i kapalı (Canlı LLM çağrısı `ConnectError` verdi); `LLMGateway` içindeki sayac yazımı **canlı doğrulanmadı**, yalnız kod yolu üzerinden doğrulandı.
2. **9Router (NINEROUTER_*) üzerinden Lilith** — DOĞRULANMADI: `http://127.0.0.1:20128/v1` sandbox'tan erişilemiyor (HTTP 000); taşıma sırasının Lilith'e uygulanması **koddan** doğrulandı, canlı taşıma doğrulanmadı.
3. **Ana hattın canlı kapısının Lilith üzerinden gerçekten reddi** — DOĞRULANMADI: gerçek anahtar/taşıma yok; red davranışı **testte sahte gateway ile** doğrulandı (kapı hükümünün metni `llm_gateway.py:2308`'den gelir).
4. **Anahtar gerektirmeyen `FreeTextGateway` yolunun canlı Pollinations çağrısı** — DOĞRULANMADI: egress kapalı → `ConnectError`; deterministik fallback'in kendisi canlı olarak gözlemlendi ✓.
5. **P3'ün "kanıt zincirine girmemesi" iddiasının uçtan uca denetimi** — DOĞRULANMADI: denetim **statik** (AST taraması + yürütücüde `lilith_growth` geçmiyor); çalışma zamanında "Lilith kanıt üretmedi" testi yazılmadı.

---

## 7. TESLİM ÖZETİ

- **Karar:** Lilith **CLI-only** kalır; çağrı yolu ana hattın `LLMGateway`'ine bağlandı (M-2 kapandı).
- **Doküman:** README + README_TECHNICAL kararı, gerekçeyi ve kapı kurallarını yazıyor; yanlış dosya yolu ve kodla çelişen iddia düzeltildi.
- **Test:** 10 yeni test (P3) + 21 Lilith testi; **4/4 revert-doğrulama PASS**.
- **Ölçüm:** `pytest tests -q` → **2740 passed, 6 skipped** · `ruff check .` → **All checks passed!** · `audit_regression.py` → **✓ BEKÇİ GEÇTİ**.

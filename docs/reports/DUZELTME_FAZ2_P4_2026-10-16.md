# DUZELTME FAZ 2 — P4 (DOKÜMANTASYON = KOD)

**Tarih:** 2026-10-16
**Kapsam:** Denetim maddeleri 13 · 14 · 15 ("yalnızca ölçülmüş yetenekler 'çalışıyor' yazılmalı", "Lilith: CLI-only + holehe notu", "RUNBOOK: M-1 + M-3")
**Önceki faz:** P0 MERGED (`ae224f0`) · fiyat MERGED (`e4a4478`) · P1+P2 MERGED (`0550d41`, PR #139) · P3 PR #140

---

## 1. YÖNTEM

P4 bir "metin düzeltme" değil, **iddia denetimi**dir: README/RUNBOOK'daki her sayısal ve yönlendirme iddiası **kodla karşılaştırıldı**; tutmayanlar düzeltildi, tutanlar teste bağlandı.

Araçlar:
- Yol referansı taraması: README/README_TECHNICAL içindeki backtick'li yolların varlığı (p1 sonrası).
- AST taraması: ajan sayısı, kanonik zincir sayısı, `run_lilith` importu yokluğu.
- Canlı prob: `osint_investigator` → holehe omurga çağrısı (mock'suz, gerçek `CapabilityRunner`).

---

## 2. DENETİMDE DOĞRULANAN BULGULAR

### 2.1 Denetimin "holehe ana hattan erişilemez" tespiti **P1'LE GEÇERSİZLEŞTİ** (bilgi güncellemesi)

**Denetim (2026-10-16, Faz 1):** "`sensor.identity.holehe` ana görev hattında HİÇBİR konfigürasyonda erişilemez" (`DENETIM_2026-10-16.md`, Bulgu 4).

**Bugünkü kod (P1 konsolidasyonu sonrası):**

| Konum | Gerçek |
|---|---|
| `agent_core/agents/osint_investigator.py:307` | `candidate_emails = self._extract_candidate_emails(target, payload)` — hedef `email`/biyografi/snippet'tan e-posta çıkarılıyor |
| `agent_core/agents/osint_investigator.py:316` | `connected_emails=candidate_emails` → artık **boş olmayabilir** |
| `agent_core/agents/osint_investigator.py:333-335` | `if profile.connected_emails:` → `_apply_email_scan(...)` **çağrılır** → `sensor.identity.holehe` omurgadan koşar |

**Canlı prob (mock'suz, gerçek `CapabilityRunner`):**

```
$ PYTHONPATH=. .venv/bin/python /tmp/probe_p4_holehe.py
=== profile.email_scan ===
{
  "requested_email": "ornek.kullanici@example.com",
  "available": false,
  "provider": "holehe",
  "reason": "policy:vault_locked",
  "found_sites": [], "scanned_count": 0, "error_count": 0
}
=== connected_emails ===
['ornek.kullanici@example.com']
```

→ **Holehe artık ana hattan BAĞLI**; kasa kilitliyken dürüstçe `policy:vault_locked` ile duruyor. Denetimin tespiti **bugün için geçersiz** → dokümana eski tespit yazılmayacak.

### 2.2 Bulgu: reddedilen holehe taraması **mühürlü kayda bağlanmıyordu** (maigret asimetrisi) 🔴

- `osint_investigator.py` **maigret** yolu: `return profile.model_copy(update={"username_scan": scan.model_dump(), **sealed})` → reddedilen tarama da profilde görünür.
- **holehe** yolu: `return profile.model_copy(update={"email_scan": scan.model_dump()})` → **mühür atılıyor**; profil yalnız `email_scan.reason` taşıyor.

Prob çıktısı (düzeltme öncesi): `email_scan_evidence: YOK` → "reddedildi" olayı profilde iz bırakmıyordu. **Düzeltildi** (1 satır) → maigret ile simetri.

### 2.3 Denetim maddeleri 13/14/15 için eksikler

| Madde | Eksik | Kanıt |
|---|---|---|
| 13 | README'de "ölçülen ↔ DOĞRULANMADI" ayrımı **yoktu**; canlı doğrulanmamış yetenekler için "çalışıyor" izlenimi doğuruyordu | README'de ölçüm/DOĞRULANMADI bölümü yoktu |
| 14 | README_TECHNICAL'de Lilith başlığı "AYRI CLI" idi (CLI-only kararı P3'te yazıldı, başlıkta yok); holehe'nin gerçek durumu **hiç** yazılmamıştı | `README_TECHNICAL.md:93-99` |
| 15 | RUNBOOK'da M-1 (`dialogue_manager` 9Router boşluğu) ve M-3 (`sk-pineal` önek şartı) **yoktu** | `RUNBOOK.md` 9Router bölümü |

### 2.4 Doğrulanan (düzeltme gerektirmeyen) README iddiaları

| İddia | Doğrulama |
|---|---|
| "12 `beacon-*` servisi" | `docker-compose.yml` → **12** `beacon-*` servisi ✓ |
| "13 görev ajanı" | `agent_core/task_executor.py` `self.agents = {...}` → **13** kayıt (+ opt-in `interpreter`) ✓ |
| "http://localhost:8000" | `docker-compose.yml` `8000:8000` · `baslat.bat` `--port 8000` · `backend/api.py:284` CORS izni ✓ |
| "13 ajan" listesi | `agent_core/agents/` → 14 modül; `target_psyche_profiler.py` bir **taban sınıf** (3 ajanın omurgası), ayrı görev ajanı **değil** ✓ |
| Dosya yolları | README + README_TECHNICAL'daki backtick'li yol referanslarının tamamı mevcut ✓ (P3'teki `scripts/run_lilith.py` hatası giderildi) |

---

## 3. YAPILAN DÜZELTMELER (5)

### 3.1 `agent_core/agents/osint_investigator.py` — reddedilen tarama da mühürlenir (2.2)

```python
# [P4 · 2026-10-16] Kapı/kasa reddi de MÜHÜRLÜ kanıt olarak korunur
# (maigret ile simetri): reddedilen tarama da zincirde görünür.
return profile.model_copy(update={"email_scan": scan.model_dump(), **sealed})
```

**Ölçüm sonrası:** prob → `email_scan_evidence` artık **var**, giriş sayısı **0** (reddedilen tarama kanıt **uydurmaz**).

### 3.2 `README.md` — "ölçülen ↔ DOĞRULANMADI" durum tablosu (md.13)

İki tablo eklendi: **ÖLÇÜLEBİLDİ** (11 satır: API 200/423, 63 kare WS, mock'suz yetenek omurgası, P1/P2 zinciri, holehe omurgası, test tabanı, frontend, fiyat) ve **DOĞRULANMADI** (9 satır, her biri **sebebiyle**).

### 3.3 `README_TECHNICAL.md` — OSINT bölümüne holehe'nin ölçülmüş durumu (md.14)

7. madde eklendi: kapı listesi, reddedilen taramaların mühürlenmesi, **denetim tespitinin P1'le geçersizleştiğinin** yazılması ve canlı taramanın **DOĞRULANMADI** olduğu. Lilith başlığı `[...; **CLI-ONLY**]` olarak işaretlendi.

### 3.4 `RUNBOOK.md` — M-1: 9Router kipinde `dialogue_manager` zinciri yok

`llm_gateway.py:765` yalnız `NINEROUTER_AGENT_CHAINS`teki 20 ajana kanonik yerel zincir verir; `dialogue_manager` orada **yok** → 9Router kipinde `config/task_routing.json`'daki **bulut** model-id'lerine (`openai/gpt-oss-120b`, `poolside/laguna-s-2.1:free`) düşer. Çözüm yolu (`OPENROUTER_AGENT_CHAIN_DIALOGUE_MANAGER=...`) ve "görev yürütücüsünde çağıran yok, `/api/chat/respond` çağırır" notu yazıldı.

### 3.5 `RUNBOOK.md` — M-3: 9Router kasa anahtarında `sk-pineal` önek şartı

`backend/api.py:1231-1240`: 9Router kipinde `/api/vault` yalnız **ortam değişkenindeki** ve `sk-pineal` ile başlayan anahtarı kullanır; sıradan `sk-...` anahtar kasadan girilirse 9Router yolu **seçilmez** → somut tuzak + çözüm yazıldı.

---

## 4. ÖLÇÜM (ham çıktılar)

### 4.1 Yeni testler

```
$ .venv/bin/python -m pytest tests/unit/test_p4_documentation.py -q -p no:cacheprovider
............                                                             [100%]
12 passed in 1.95s
```

`tests/unit/test_holehe_scanner.py` → **27 passed** (yeni `test_refused_scan_is_sealed_as_evidence` dahil).

### 4.2 Revert-doğrulama (5/5)

```
$ .venv/bin/python scripts/revert_verification_p4.py
PASS · P4-1 kanıt: reddedilen holehe taraması zincirde görünmüyor
PASS · P4-2 doküman: README'de ölçülen ↔ DOĞRULANMADI tablosu yok
PASS · P4-3 doküman: README_TECHNICAL holehe'nin ölçülmüş durumunu yazmıyor
PASS · P4-4 doküman: RUNBOOK 9Router dialogue_manager boşluğunu yazmıyor
PASS · P4-5 doküman: RUNBOOK 9Router 'sk-pineal' önek şartını yazmıyor

REVERT-DOĞRULAMA (P4): 5/5 düzeltme geri alınınca KIRMIZIya döndü
```

(İlk koşu **3/5** idi: 2 adım yalnız **başlığı** geri aldığı için gövde işaretleri (ÖLÇÜLEBİLDİ / DOĞRULANMADI) duruyordu → betiğe blok-silme modu eklendi.)

### 4.3 Tam koşu + ruff + regresyon beçisi

```
$ .venv/bin/python -m pytest tests -q -p no:cacheprovider
2753 passed, 6 skipped, 319 warnings in 149.47s (0:02:29)

$ .venv/bin/python -m ruff check .
All checks passed!

$ .venv/bin/python scripts/audit_regression.py
✓ BEKÇİ GEÇTİ — regresyon yok, taban çizgisi gerçekle birebir.
```

---

## 5. DEĞİŞEN DOSYALAR

| Dosya | Değişiklik |
|---|---|
| `agent_core/agents/osint_investigator.py` | Reddedilen holehe taraması da mühürlü kayda bağlanıyor (1 satır) |
| `README.md` | "Durum tablosu: ölçülen çalışma ↔ DOĞRULANMADI" bölümü (2 tablo) |
| `README_TECHNICAL.md` | OSINT bölümüne 7. madde (holehe'nin ölçülmüş durumu) · Lilith başlığı "CLI-ONLY" |
| `RUNBOOK.md` | M-3 (`sk-pineal`) ve M-1 (`dialogue_manager`) notları |
| `tests/unit/test_holehe_scanner.py` | +1 test (reddedilen tarama mühürlü) |
| `tests/unit/test_p4_documentation.py` | **YENİ** — 12 test |
| `scripts/revert_verification_p4.py` | **YENİ** — 5 adım |
| `docs/envanter.html` | Yenilendi (738 dosya) |

---

## 6. DOĞRULANMADI (sebebiyle)

1. **Canlı holehe taraması** — DOĞRULANMADI: sandbox egress'i kapalı; ölçülen yalnız **kablo** (biyografi → e-posta → yetenek çağrısı) ve kapının dürüst reddi (`policy:vault_locked`).
2. **9Router kipinde `dialogue_manager` zincirinin canlı davranışı** — DOĞRULANMADI: `127.0.0.1:20128` erişilemiyor (HTTP 000); yalnız **kod yolu** ölçüldü (kanonik listede yok → `task_routing`).
3. **`sk-pineal` tuzağının canlı etkisi** — DOĞRULANMADI: 9Router erişilemiyor; koşul `backend/api.py:1231-1240` üzerinden **statik** doğrulandı.
4. **README'deki "26 capability" sayısının bugünkü değeri** — DOĞRULANMADI: bu turda `/api/telemetry` yeniden çağrılmadı; sayı 2026-10-16 ölçümünden gelir (P1 raporu §9).
5. **Tüm doküman iddialarının kapsamlı doğrulaması** — DOĞRULANMADI: sayısal/yönlendirme iddiaları tarandı; **anlatısal** (prose) iddiaların tamamı otomatik doğrulanamaz — bu dosya kilitli olanları kapsar.

---

## 7. TESLİM ÖZETİ

- **Kod:** 1 satırlık kanıt zinciri düzeltmesi (reddedilen holehe taraması mühürleniyor).
- **Doküman:** README durum tablosu (md.13) · README_TECHNICAL holehe + Lilith notları (md.14) · RUNBOOK M-1 + M-3 (md.15).
- **Test:** 13 yeni test (12 doküman + 1 kanıt) · **5/5 revert-doğrulama PASS**.
- **Ölçüm:** `pytest tests -q` → **2753 passed, 6 skipped** · `ruff check .` → **All checks passed!** · `audit_regression.py` → **✓ BEKÇİ GEÇTİ**.

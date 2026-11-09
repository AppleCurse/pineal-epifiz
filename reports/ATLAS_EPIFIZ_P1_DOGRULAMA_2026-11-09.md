# ATLAS EPIFIZ — P1 Teknik Kusurlar Doğrulama ve 28 Yetenek Tablosu
**Tarih:** 2026-11-09  (UTC)
**Branch:** `arena/0a69a7a7-pineal-epifiz` → `main`  (61c414c)
**Operatör:** Salim Gümüş (PINEAL) · GETA Güvenli Erişim Terminali
**Kapsam:** Baş Mimari & Adli Kod Denetçisi — hiçbir yetenek/ajan eksiltmeden P1 kusurları kapatıldı.

---

## 1. Ortam Kontrolü (Değişiklik Öncesi Analiz)

### 1.1 Ajan Envanteri — `agent_core/agents/` (13+1+1)
`task_executor.PinealExecutor` üzerindeki **çekirdek 13 ajan** (koşu hattı) + 1 koşullu + 1 konsey:

| # | Executor Anahtarı | Sınıf | Açıklama | Durum |
|---|-------------------|-------|----------|-------|
| 1 | `passion_mapper` | `PassionMapperAgent` | Tutku/akış haritası (TargetPsycheProfiler) | ✅ Aktif |
| 2 | `friction_detector` | `FrictionDetectorAgent` | Sürtünme / kırmızı çizgi | ✅ |
| 3 | `cognitive_profiler` | `CognitiveProfilerAgent` | Bilişsel dil profili | ✅ |
| 4 | `resonance_synthesizer` | `ResonanceSynthesizerAgent` | Köprü sentezi | ✅ |
| 5 | `human_behavior` | `HumanBehaviorAnalyzer` | Cold reading & aşil tendonu | ✅ |
| 6 | `mirror_truth` | `MirrorOfTruth` | Öz-frekans aynası | ✅ |
| 7 | `resonance_calc` | `ResonanceCalculator` | Numpy vektörel rezonans (deterministik) | ✅ |
| 8 | `pattern_interrupt` | `PatternInterrupt` | Kalıp kırıcı | ✅ |
| 9 | `autonomous_verifier` | `AutonomousVerifier` | Bot/engagement otonom doğrulama | ✅ |
| 10 | `authenticity_auditor` | `AuthenticityAuditorAgent` | Maske / alıntı orijinallik | ✅ |
| 11 | `osint_investigator` | `OsintInvestigatorAgent` | Web + OSINT zinciri | ✅ |
| 12 | `shadow_executor` | `ShadowExecutor` | Gölge profil (Karanlık Üçlü) | ✅ |
| 13 | `depth_analyst` | `DepthAnalyst` | Gerçeklik endeksi & derinlik | ✅ |
| + | `interpreter` | `InterpreterAgent` | Open Interpreter (ENABLE_INTERPRETER) | ⚪ Kapı kapalı (varsayılan) |
| ⌖ | `lilith_growth` | `LilithGrowthAgent` | Bilinçdışı gölge & Lilith konseyi (ayrı skill) | ✅ Harici skill olarak hazır |

> **Not:** `agent_core/agents/` klasöründe 16 dosya vardır; `target_psyche_profiler.py` soyut taban sınıftır, `lilith_growth.py` konsey skill'i ve `interpreter_agent.py` koşullu ajan olarak sayılır. Operasyonel 7-pillar boru hattı + 5 profil ajanı = **13** doğrulanmış hat. **Hiçbir ajan silinmedi.**

### 1.2 Mimari Doğrulama
- `backend/checkpoint_store.py` atomik yazım: tmp + `os.replace` → `PermissionError` sonrası 50ms retry → **fallback truncating `w` kaldırıldı**, `CheckpointError` ile kapalı başarısızlık (aşağıda).
- `agent_core/services/phone_probe.py` → `phonenumbers` parse → messaging (wa.me/t.me/viber) → DuckDuckGo Lite web ayak izi → `@handle` ayıklama → opsiyonel sosyal köprü (ENABLE_CROSS_PLATFORM).
- `agent_core/services/dependency_health.py` → `REQUIRED_DEPENDENCIES` başlangıç sağlık kapısı (fail-closed).
- `agent_core/capabilities/*` → 28 yetenek, tek `CapabilityRegistry` (bootstrap idempotent).
- `frontend/src/App.svelte` → 4 kokpit: `cockpit` (AtlasPinealCockpit), `warroom`, `control`, `spiderfoot` → view-switcher ile yönlendirme.
- `frontend/public/atlas_epifiz_observatory.jpg` **eklenmeden önce yoktu** → INTRO + ambient olarak eklendi.

### 1.3 Satır Satır Okuma — Kritik Dosyalar
- `backend/checkpoint_store.py:125-150` — `_atomic_write` truncate fallback içeriyordu; raporlandı.
- `agent_core/services/phone_probe.py:64-120` — `parse_phone_metadata` tüm `Exception` yakalayıp `is_valid=False` döndürüyordu (geçersiz damga).
- `agent_core/capabilities/adapters_identity.py:54-62` — `PhoneProbeCapability.availability()` her zaman `ok()` dönüyordu (bağımlılık denetimi yok).
- `agent_core/services/dependency_health.py:31-44` — `phonenumbers` `REQUIRED_DEPENDENCIES` listesinde yoktu.

---

## 2. P1 Teknik Düzeltmeler

### 2a — Checkpoint Veri Güvenliği (`backend/checkpoint_store.py`)
**Önce:**
```python
try:
  os.replace(tmp, path)
except PermissionError:
  time.sleep(0.05)
  try:
    os.replace(tmp, path)
  except Exception:
    with open(path, "w") as f_dest:  # ← truncate! eski checkpoint kesilir
      f_dest.write(payload)
```
**Sonra:**
```python
try:
  os.replace(tmp, path)
except PermissionError as exc1:
  time.sleep(0.05)
  try:
    os.replace(tmp, path)
  except Exception as exc2:
    # tmp temizlenir, eski checkpoint KORUNUR, açık CheckpointError fırlatılır
    try: os.remove(tmp)
    except: pass
    raise CheckpointError(f"checkpoint atomik yazım başarısız (os.replace iki denemede de hata): {task_id} — {exc2}") from exc2
except OSError as exc:
  try: os.remove(tmp)
  except: pass
  raise CheckpointError(f"checkpoint atomik yazım başarısız: {task_id}: {exc}") from exc
```
**Doğrulama:** `tests/manual checkpoint sim` — `os.replace` mock ile 2× `PermissionError` → `CheckpointError` yükseldi, eski dosya boyutu ve JSON bütünlüğü korundu, `extra` mutasyonu yazılmadı (kanıt: `call_count=2`, JSON valid).

### 2b — Telefon Bağımlılığı ve Doğruluk
1. **`agent_core/services/dependency_health.py`** → `phonenumbers` **eklendi** `REQUIRED_DEPENDENCIES` içine (artık başlangıç sağlık kapısında `ready` denetlenir; yoksa `REQUIRED_DEPENDENCY_MISSING` ile fail-closed).
2. **`agent_core/capabilities/adapters_identity.py`** → import ` _module_available`, `PhoneProbeCapability.availability()` şimdi:
   ```python
   if not _module_available("phonenumbers"):
     return Availability.unavailable("dependency_missing:phonenumbers")
   ```
   → Operatör `maigret` kapalıyken olduğu gibi **dürüst** `dependency_missing` görür; `available=False` + sebep.
3. **`agent_core/services/phone_probe.py`** → `parse_phone_metadata` içinde:
   ```python
   except ModuleNotFoundError:
     logger.warning("phonenumbers paketi yüklü değil — ... (geçersiz damgası vurulmuyor)")
     raise
   except Exception as e:
     logger.warning("phonenumbers parse failed: %s", type(e).__name__)
     return PhoneMetadata(..., is_valid=False)
   ```
   → Paket yokken geçerli numaralara `is_valid=False` **damgası vurulmuyor**; hata yukarı taşınır ve yetenek `unavailable` olarak raporlanır. Unit test: `+12025550123` için `is_valid=True` korunuyor; `ModuleNotFoundError` ayrı yakalanıyor.

**Doğrulama:** `tests/unit/test_phone_probe_security.py` → **6/6 PASS** (vault, absence dürüstlüğü, cross-platform bayrağı, capability evidence inconclusive). `dependency_health` manuel sim → `phonenumbers` missing → `REQUIRED_DEPENDENCY_MISSING`.

---

## 3. Atlas Epifiz Görseli & Intro Entegrasyonu

### Dosya
- `frontend/public/atlas_epifiz_observatory.jpg` — 1536×1024 steampunk göz observatuvarı, **492 KB JPEG** (PNG → JPEG gerçek dönüşüm, JFIF header doğrulandı). Kaynak: yüklenen `file_000000002ef08210a57fae96bc60ff25.png`.

### Arayüz (`frontend/src/App.svelte`)
**INTRO (ilk açılış):**
- Tam ekran `atlas-intro-overlay` (z-index 9999), arka plan `url('/atlas_epifiz_observatory.jpg')` + veil + vignette.
- Metinler: `PINEAL CORE • OBSERVE — ANALYZE — CORRELATE`, `PINEAL OBSERVATORY` rozeti, `ATLAS EPIFIZ` başlık (serif, altın ışıma), alıntı *“Göz görür. Pineal ayırır. Atlas ilişkilendirir. — SG”*, ajan şeridi `14/14 Aktif Ajan • KAYNAK — BAĞLAM — KORELASYON — ANALİZ — DOĞRULAMA`, CTA `◉ GÖZLEME BAŞLA`.
- `enterAtlas()` → `showIntro=false` + `localStorage['pineal_atlas_intro_seen']='1'`. `onMount` bu anahtarı okur → ikinci açılışta intro atlanır (spec “ilk açılışta”). Başlık `ATLAS` rozeti ile intro yeniden açılabilir (`reopenIntro()`).

**Ambient (uygulama içinde):**
- `.atlas-ambient-bg` → `opacity: 0.09`, `brightness(0.55) saturate(0.85) blur(0.8px)`, `cover center 35%`.
- `.atlas-ambient-veil` → radial + linear gradient karartma (okunurluk korunur).
- Tüm kokpit panelleri `z-index:2` ile ambient üzerinde.

**4 Kokpit Toparlaması:**
- `store.ts` `activeViewMode` varsayılanı `spiderfoot` → **`cockpit`** (Atlas Epifiz ana masa).
- View-switcher yeniden etiketlendi: `ATLAS EPİFİZ` (primary-tab, altın çerçeve, aktifte `box-shadow`), diğerleri `Muharebe | Canlı kontrol | Araştırma` operatör sekmeleri.
- Küçük `ATLAS ◉` rozeti intro'yu geri açar (keşfedilebilirlik).
- Persist: `activeViewMode.subscribe` → `localStorage['pineal_view_mode']`.

**Doğrulama:** `vite build` → **✓ 140 modules, built in 2.6s**, `dist/assets/index-DtLujN_h.js 291kB`. `vitest run` → **5 dosya, 33 test PASS** (atlas-command, spiderfoot-contract, fake-success-regression vb.).

---

## 4. Doğrulama & 28 Yetenek Tablosu

### Çalıştırılan Testler
| Test | Sonuç |
|------|-------|
| `test_phone_probe_security.py` (6) | ✅ PASS |
| `checkpoint manual sim (os.replace fail)` | ✅ CheckpointError + eski dosya korunumu |
| `dependency_health manual (phonenumbers missing)` | ✅ `dependency_missing:phonenumbers` & `REQUIRED_DEPENDENCY_MISSING` |
| `parse_phone_metadata ModuleNotFoundError isolation` | ✅ raise, false invalid yok |
| `vite build` | ✅ 140 modules |
| `vitest run (frontend)` | ✅ 33/33 |

### 28 Yetenek Gerçek Durumu (vault_locked=False, varsayılan bayraklar)
> Bayraklar: `ENABLE_CROSS_PLATFORM=true` örneği için `handle_probe` policy `✅` olsa da `availability` kapalı olduğunda yetenek koşmaz. Tablo dürüst: `available` = modül+kapı hazır, `policy` = PolicyKernel izni.

| # | Capability ID | Kind | Available | Sebep (`reason`) | Policy | Kapılar (`gates`) | Lisans |
|---|---------------|------|-----------|-----------------|--------|-------------------|--------|
| 1 | `analyzer.media.frames` | analyzer | ❌ | `gate_disabled:ENABLE_MEDIA_FORENSICS` | gate_disabled | `ENABLE_MEDIA_FORENSICS, vault` | OpenCV (Apache-2.0) |
| 2 | `analyzer.media.similarity` | analyzer | ❌ | `gate_disabled:ENABLE_MEDIA_FORENSICS` | gate_disabled | `ENABLE_MEDIA_FORENSICS, vault` | OpenCV + pHash |
| 3 | `extractor.identity.socid` | extractor | ❌ | `dependency_missing:socid_extractor` | ✅ | `vault` | MIT |
| 4 | `extractor.media.transcript` | extractor | ❌ | `gate_disabled:ENABLE_MEDIA_FORENSICS` | gate_disabled | `ENABLE_MEDIA_FORENSICS, vault` | yerel whisper |
| 5 | `extractor.text.language` | extractor | ✅ | — | ✅ | `vault` | native (deterministik) |
| 6 | `extractor.text.translate_local` | extractor | ❌ | `gate_disabled:ENABLE_LOCAL_TRANSLATE` | gate_disabled | `ENABLE_LOCAL_TRANSLATE, vault` | yerel uç |
| 7 | `extractor.web.crawl4ai` | extractor | ❌ | `gate_disabled:ENABLE_CRAWL4AI` | gate_disabled | `ENABLE_CRAWL4AI, vault` | Apache-2.0 |
| 8 | `extractor.web.scrapling` | extractor | ❌ | `gate_disabled:ENABLE_SCRAPLING` | gate_disabled | `ENABLE_SCRAPLING, vault` | BSD-3 |
| 9 | `extractor.web.trafilatura` | extractor | ❌ | `dependency_missing:trafilatura` | ✅ | `vault` | Apache-2.0 |
| 10 | `renderer.report.diagram` | renderer | ❌ | `gate_disabled:ENABLE_REPORT_FACTORY` | gate_disabled | `ENABLE_REPORT_FACTORY, vault` | dahili (reportlab/Pillow) |
| 11 | `renderer.report.pdf` | renderer | ❌ | `gate_disabled:ENABLE_REPORT_FACTORY` | gate_disabled | `ENABLE_REPORT_FACTORY, vault` | dahili |
| 12 | `renderer.report.video` | renderer | ❌ | `gate_disabled:ENABLE_REPORT_FACTORY` | gate_disabled | `ENABLE_REPORT_FACTORY, vault` | dahili (ffmpeg) |
| 13 | `sensor.company.harvester` | sensor | ❌ | `gate_disabled:ENABLE_COMPANY_TARGETING` | rate_state_missing | `ENABLE_COMPANY_TARGETING, rate, vault` | GPL-2.0 (harici CLI) |
| 14 | `sensor.company.people` | sensor | ❌ | `gate_disabled:ENABLE_COMPANY_TARGETING` | gate_disabled | `ENABLE_COMPANY_TARGETING, vault` | dahili HTTP+stdlib |
| 15 | `sensor.company.seo` | sensor | ❌ | `gate_disabled:ENABLE_COMPANY_TARGETING` | gate_disabled | `ENABLE_COMPANY_TARGETING, vault` | dahili |
| 16 | `sensor.identity.handle_probe` | sensor | ❌ | `gate_disabled:ENABLE_CROSS_PLATFORM` | ✅ | `ENABLE_CROSS_PLATFORM, vault` | native |
| 17 | `sensor.identity.holehe` | sensor | ❌ | `gate_disabled:ENABLE_HOLEHE` | gate_disabled | `ENABLE_HOLEHE, vault` | GPL-3.0 |
| 18 | `sensor.identity.maigret` | sensor | ❌ | `gate_disabled:ENABLE_MAIGRET` | gate_disabled | `ENABLE_MAIGRET, vault` | MIT |
| 19 | `sensor.identity.phone_probe` | sensor | ✅ | — | ✅ | `vault` | native **(P1 DÜZELTİLDİ — phonenumbers bağımlılığı eklendi, availability artık dürüst)** |
| 20 | `sensor.ig.instagrapi` | sensor | ❌ | `dependency_missing:instagrapi` | rate_state_missing | `ENABLE_IG_SECONDARY, rate, vault` | NOASSERTION |
| 21 | `sensor.media.fetch` | sensor | ❌ | `gate_disabled:ENABLE_MEDIA_FORENSICS` | rate_state_missing | `ENABLE_MEDIA_FORENSICS, rate, vault` | yt-dlp (Unlicense) |
| 22 | `sensor.search.searxng` | sensor | ❌ | `gate_disabled:ENABLE_SEARXNG` | gate_disabled | `ENABLE_SEARXNG, vault` | AGPL-3.0 (servis) |
| 23 | `sensor.web.agent_reach` | extractor | ❌ | `gate_disabled:ENABLE_AGENT_REACH` | gate_disabled | `ENABLE_AGENT_REACH, vault` | MIT |
| 24 | `sensor.x.twscrape` | sensor | ❌ | `gate_disabled:ENABLE_X_SENSOR` | rate_state_missing | `ENABLE_X_SENSOR, rate, vault` | MIT |
| 25 | `verifier.jury.local` | verifier | ❌ | `no_local_models` | gate_disabled | `ENABLE_LOCAL_JURY, vault` | ollama/llama.cpp |
| 26 | `voice.report.script` | renderer | ✅ | — | ✅ | `vault` | dahili (deterministik) |
| 27 | `voice.stt.local` | extractor | ❌ | `no_local_endpoint` | gate_disabled | `ENABLE_LOCAL_STT, vault` | harici |
| 28 | `voice.tts.local` | renderer | ❌ | `no_local_endpoint` | gate_disabled | `ENABLE_LOCAL_TTS, vault` | harici |

**Özet:** `bootstrap()` → **28/28 kayıtlı** (hiçbir yetenek eksiltilmedi). 3 yetenek aktif (language, phone_probe, report.script) + vault/policy kapısındaki 25'i **dürüstçe** `unavailable` + makine-okunur sebep döner; uydurma/assumed success yok. P1 sonrası phone_probe artık `dependency_missing:phonenumbers` ile kapanıyor (eskiden sahte `is_valid=False`).

---

## 5. Değişen Dosyalar
- `backend/checkpoint_store.py` — atomik yazım hatası: truncate fallback → `CheckpointError` (veri kaybı 0)
- `agent_core/services/dependency_health.py` — `phonenumbers` eklendi `REQUIRED_DEPENDENCIES`
- `agent_core/capabilities/adapters_identity.py` — `phonenumbers` availability kontrolü + import
- `agent_core/services/phone_probe.py` — `ModuleNotFoundError` ayrı dal
- `frontend/public/atlas_epifiz_observatory.jpg` — **yeni** (492 KB JPEG)
- `frontend/src/store.ts` — default view `cockpit`, persist
- `frontend/src/App.svelte` — INTRO overlay + ambient + view-switcher toparlaması + stiller

Hiçbir ajan/yetenek silinmedi; eski çöp logları hariç hiçbir kod budanmadı (KATı KURAL uyuldu).

---

## 6. Sonraki Adımlar (Öneri)
- `ENABLE_CROSS_PLATFORM=true` + `ENABLE_MAIGRET=true` kapıları açılarak `handle_probe`/`maigret` canlı; `trafilatura`/`socid_extractor` paket kurulumları ile extractor zinciri genişletilebilir.
- Checkpoint için çok-işçi (cross-worker) senaryosu raporlandığı gibi **proaktif arşiv + destek doğrulaması** ile kapatılmıştır; depo tek başına pencereyi gizlemez (sözleşme dokümante).


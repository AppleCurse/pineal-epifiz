# Üç Depo — Net Karşılaştırma Raporu

**Tarih:** 2026-11-08
**Kapsam:** `AppleCurse/pineal-android-companion` · `AppleCurse/Atlas-Pineal` · `AppleCurse/pineal-epifiz`
**Yöntem:** Her üç depo klonlandı; dosya envanteri, satır sayımı, commit/CI geçmişi (GitHub Actions API), `git ls-files` ve kod okuması ile ölçüldü. Aşağıdaki hiçbir sayı tahmin değildir; ölçüm komutu yanında yazılıdır.

---

## 0 · Tek cümlelik hüküm

Bu üç depo **üç ayrı katman değil, tek bir ürünün üç farklı olgunluk anıdır**: `pineal-epifiz` **gerçek ürün** (çalışan motor + API + arayüz + testler), `pineal-android-companion` o ürünün **kabuksuz dokümantasyon anlık görüntüsü** (kod sıfır), `Atlas-Pineal` ise **tamamen başka bir ürün** (kamuya dönük statik tanıtım sitesi + prototip Android uygulaması).

---

## 1 · Ölçülen kimlik kartları

| Ölçüm | pineal-epifiz | pineal-android-companion | Atlas-Pineal |
|---|---|---|---|
| GitHub açıklaması | *(boş)* | "OSINT + psikodinamik profilleme… Rust destekli çok platformlu Otonom Bilişsel İstihbarat Sistemi" | "Dijital dünya hafıza değil, kayıt sistemidir… Merkezde EPİFİZ GÖZÜ var" |
| Dil (GitHub) | Python | *(yok)* | Kotlin |
| Repo boyutu | **167 MB** | 0,55 MB | 0,35 MB |
| İzlenen dosya | **778** | **65** | **67** |
| Kod satırı (py/ts/kt/rs/svelte/js/html/css) | **154.295** | **0** | **6.281** |
| Markdown doküman | 60 | **34** | 1 |
| Python dosyası | **531** | 0 | 0 |
| Test modülü | **298** | 0 | 5 (Kotlin) |
| Kotlin dosyası / satır | 32 / 4.177 | 0 (yalnız `strings.xml`) | 29 / 5.296 |
| Commit sayısı | 1 (squash'lenmiş) | 2 | 4 |
| CI iş akışı | 4 (`ci`, `preflight`, `release-gates`, `catalog-drift`) | 2 (`ci`, `release-gates`) | **0** (`.github` yok) |
| CI koşu sayısı | **1.382** (son koşu: **5/5 job success**) | **1** (2026-09-11, **failure**) | 0 |
| Son güncelleme | 2026-11-07 | 2026-09-11 | 2026-10-21 |
| Sürüm | `3.0.0-rc.2` | `3.0.0-rc.2` (aynı) | yok (`versionName 1.0`) |
| Yıldız | 2 | 0 | 1 |
| Lisans dosyası | yok | yok | yok |

> **İlk sert gerçek:** Depo adı "android-companion" olmasına rağmen içinde **tek satır Kotlin yok**. `app/` altında yalnızca `app/src/main/res/values/strings.xml` (`<string name="app_name">Pineal</string>`) var. README'nin "Kotlin + Jetpack Compose Android uygulaması" tarifi bu depoda karşılıksızdır.

---

## 2 · Depo 1 — `pineal-epifiz`: gerçek ürün

### 2.1 Ne var
| Katman | Somut içerik |
|---|---|
| API | `backend/api.py` **5.726 satır** (tavan 5.760 — anayasal ratchet testiyle kilitli) + `backend/routes/` 13 modül |
| HTTP yüzeyi | **76 benzersiz HTTP ucu + 1 WebSocket** (dekoratör taraması; README "74" diyor → gerçek sayı biraz daha yüksek) |
| Motor | `agent_core/` — 531 Python dosyası: 7 dalga motoru (`engines/`), 13 görev ajanı, yetenek omurgası (`capabilities/`, **28 kayıtlı yetenek**), hafıza, güvenlik |
| Yetenekler | `skills/` altında **28 ayrı `SKILL.md`**: Instagram, X, SearXNG, holehe, maigret, telefon OSINT, şirket tarama, Crawl4AI/Scrapling/Trafilatura, PDF/diyagram/video rapor, yerel TTS/STT, yerel jüri |
| Arayüz | Svelte 5 + Vite, **11.057 satır**: `TacticalWarRoom` (1.568), `SpiderFootCockpit` (**3.850**), `AtlasPinealCockpit` (**2.099**), `LiveControlPanel` (921), `AgentRack` (434) |
| Android | `android/` — 32 Kotlin dosyası, 4.177 satır; **sunucu köprüsü var** (`PinealBackendClient` → `/api/mobile/coach`), Gemini yalnız geri düşüş |
| Rust | `rust_core/` 25 `.rs` — **bilinçli olarak "deneysel, ürün yoluna bağlı değil"** (ADR'de yazılı) |
| Altyapı | Dockerfile, docker-compose, Railway, Vercel, Cloudflare Workers/Pages edge vekilleri |
| Denetim | `scripts/golge_denetimi.py`, `audit_regression.py`, `dead_code_audit.py`, `generate_inventory_page.py` + "revert doğrulama" betikleri |

### 2.2 Yalnız burada olan mühendislik disiplini
- **Envanter = kod.** `docs/envanter.html` `git ls-files` + AST'den üretilir; CI `--check` ile bayatlamayı yakalar. Bu checkout'ta koşturdum: **`GÜNCEL: docs/envanter.html kaynakla uyumlu` (rc=0)**.
- **Tüzük kodda kapı.** `docs/PINEAL_TUZUK.md` (v2, 10 madde) maddeleri `agent_core/capabilities/policy.py` içinde gate olarak çalışır.
- **Fail-closed kanıt.** Kanıt yoksa `InsufficientEvidenceError` / `halted_evidence`; "hiç iz yok" iddiası yalnız sıfır hatalı taramada.
- **Yaş kapısı.** `minor_gate.py` — 18 yaş altı istisnasız durur.
- **Env ↔ kod üç yönlü fark denetimi.** `.env.example`'daki 17 `ENABLE_*` bayrağının **hepsi** kodda okunuyor (benim taramamda sızan 10 adet `ENABLE_*` yalnız test/araç sabiti: `ENABLE_A`, `ENABLE_TAMAMEN_UYDURMA`, `ENABLE_YOK_BOYLE_BIR_SEY` gibi kasıtlı negatif-test isimleri).
- **CI 5 bacağı da yeşil** — son commit `c49fac3` üzerinde `android`, `backend`, `frontend`, `rust-core`, `smoke` hepsi `success`.

### 2.3 Dürüst zayıflıkları
- Tek commit (squash) → **geliştirme geçmişi kayıp**; `CHANGELOG.md` 56 kayıt ve 166 KB ile geçmişi telafi etmeye çalışıyor.
- README'deki bazı sayılar hafif kaymış: "74 HTTP ucu" → ölçülen 76; "13 ajan" doğru (12 sürekli + 1 kapılı interpreter) ama `agents/` altında 16 dosya var (2'si ajan değil).
- Kasa (vault) **şifreli değil**, düz JSON — README bunu kendisi yazıyor ("yetki mandalı, sır kasası değil").
- Lisans yok.

---

## 3 · Depo 2 — `pineal-android-companion`: kod değil, kabuk

### 3.1 İçinde gerçekten ne var
```
65 izlenen dosya:
  ├── 34 × .md   (README, CHANGELOG, ARCHITECTURE, RUNBOOK, PRODUCTION_AUDIT, ZF_ADLI_DENETIM…)
  ├── 6 × config/*.json|yaml, 3 × release/*.json|yml, 2 × .github/workflows/*.yml
  ├── 13 × .gradle/9.3.1/**  ← DERLEME ÖNBELLEĞİ BİNARYLERİ (yanlışlıkla commit'lenmiş)
  └── 1 × app/src/main/res/values/strings.xml
```
Yani: **0 Python, 0 Kotlin, 0 TypeScript, 0 Rust, 0 test dosyası.**

### 3.2 Bunun somut sonucu: CI'ı çalışamaz durumda
`.github/workflows/ci.yml` bu depoda **var olmayan** yolları koşuyor:

| Adımın istediği | Depoda |
|---|---|
| `requirements.txt` | **YOK** |
| `agent_core/`, `backend/`, `tests/` | **YOK** |
| `scripts/generate_routing_shadows.py`, `scripts/verify_openrouter_catalog.py` | **YOK** |
| `frontend/package-lock.json`, `android/`, `rust_core/`, `docker-compose.yml` | **YOK** |

**Tek CI koşusu (2026-09-11) `failure` ile bitmiş.** Yani "Android companion", Android derlemesi yapamaz; hatta hiçbir şey derleyemez.

### 3.3 `pineal-epifiz` ile ilişkisi: **aynısının eski anlık görüntüsü**
| Kanıt | Sonuç |
|---|---|
| `VERSION` → `3.0.0-rc.2` (ikisinde birebir aynı) | aynı sürüm hattı |
| `CHANGELOG.md` başlıkları: buradaki **9 kaydın 9'u** `epifiz`'in 56 kaydının içinde (**eksik: 0**) | epifiz, bunun kesin üst kümesi |
| `release/3.0.0-rc.1.json` ve `rc.2.json` → **bayt bayt aynı** | aynı release hattı |
| `ARCHITECTURE.md` → yalnız **3 satır** fark (çocuk kilidi, tüzük, yetenek omurgası satırları sonradan eklenmiş) | aynı belge, sonradan büyümüş |
| `config/agent_tiers.json`, `config/provider_catalog.json` → **farklı** | epifiz'te evrilmiş |
| `README.md` 31 satır ↔ 450 satır | epifiz'te 14,5 kat büyümüş |
| `ci.yml` 147 satır ↔ 271 satır (epifiz'te audit/dead-code/envanter kapıları eklenmiş) | aynı hattın olgunlaşmış hâli |

**Bu depo bir "companion" (yardımcı istemci) değil; `epifiz`'in 2026-09-11'de alınmış, kodu commit edilmemiş doküman fotoğrafıdır.** İçindeki raporlar da bunu doğruluyor: `DURUM_TESPITI_2026-09-08.md` "6 ardışık commit kırmızı CI ile main'e girdi", `GO_NO_GO_AUDIT_2026-09-11.md` §HÜKÜM: **🔴 NO-GO**, `INDEPENDENT_FORENSIC_AUDIT.md` "Android uygulaması Python backend'ine hiç bağlanmıyor". Bunlar epifiz'in *eski* hâlinin denetimleridir; epifiz bunları çözmüş (bugün CI 5/5 yeşil, Android artık backend köprüsü kullanıyor).

---

## 4 · Depo 3 — `Atlas-Pineal`: başka ürün

### 4.1 İki parça
1. **`public/` — statik tanıtım sitesi** (985 satır: `index.html` 300 + `styles.css` 374 + `app.js` 135 + `server.mjs`). 11 bölüm, "Digital Exposure Intelligence" konumlandırması, "Bu hizmet bana uygun mu?" kapsam seçici. Sunucu **yalnız GET/HEAD** dosya sunar; CSP'de `connect-src 'none'` — **hiçbir ağ çağrısı yapmaz, tarama başlatmaz, form verisi toplamaz.**
2. **`app/` — Android prototipi** (29 Kotlin dosyası, 5.296 satır): 6 ekranlı oyunlaştırılmış "teşkilat" arayüzü — `KONSOL`, `MANIFESTO`, `KÜL`, `SEDEF`, `İZ`, `KAHİN`. Bileşenler steampunk: `BrassKnob`, `NixieDisplay`, `VacuumTube`, `SteampunkGauge`, `PinealEyeView`.

### 4.2 Ürün mantığı epifiz ile **taban tabana zıt**
| | `pineal-epifiz` | `Atlas-Pineal` (app) |
|---|---|---|
| KÜL | *(yok)* | "Kara Delik Protokolü — **Data Poisoning (Zehirleme)**", buton metni: **"KARA DELİĞE GÖNDER VE ZEHİRLE"**, "Artık hiç doğmadın" |
| SEDEF | *(yok)* | "Dönüşüm — SEO arama motoru ilk sayfa işgali" |
| İZ | *(yok)* | "Bize bir isim ver, sana dosyasını verelim. Yargılamaz, fısıldar." |
| Tüzük | 10 maddelik `PINEAL_TUZUK.md`, kanıt mührü, yaş kapısı | yok |
| Ölçüm dürüstlüğü | kanıt yoksa `halted_evidence` | **sabit demo sayılar**: `awarenessLevel = 78f`, `coreIntegrity = 96f`, `latencyMs = 12`, `zeroLogProtection = true`, `totalFrictionBurnt = 184` |

### 4.3 Kendi README'si kendi uygulamasını reddediyor
`Atlas-Pineal/README.md` birebir şunu yazıyor:

> *"Mevcut Android kaynaklarında **eski veri-zehirleme/üçüncü-kişi araştırması metinleri**, **doğrulanmamış AES/sıfır-log ifadeleri** ve **istemciden doğrudan Gemini çağrısı** gibi yayımlama öncesi yeniden ele alınması gereken izler bulunur. Bu Android denemesi güvenlik/gizlilik incelemesinden geçirilmeden yayımlanmamalıdır; **üretim API anahtarı APK içine konmamalıdır**."*
> *"İşleyen **Pineal Epifiz operasyon motoru ayrı bir repo/çalışma katmanındadır**; bu checkout'a gömülü değildir."*

Yani Atlas-Pineal, `epifiz`'i **motor** olarak işaret ediyor ve kendini onun *kamuya dönük yüzü* olarak konumluyor — ama o yüz, motorun bugünkü ilkeleriyle (Madde 1: "gözlem, hüküm değildir"; zehirleme yok) çelişen bir prototipi hâlâ taşıyor.

### 4.4 Somut teknik açıklar
- `metadata.json` bugün doğru (`majorCapabilities: []`), ama **anahtar yönetimi yanlış**: `secrets` Gradle eklentisi anahtarı `BuildConfig.GEMINI_API_KEY` üzerinden **istemciye** gömüyor (`GeminiThinkingService.kt:41`). README bunu itiraf ediyor.
- API anahtarı yoksa uygulama sessizce `generateTacticalIntuition()` ile **yerel uydurma metin** üretiyor ("Dünkü davranış paternleri… simüle edildi") — "zero mock data" iddiasının tam tersi.
- `applicationId = "com.aistudio.kendinleyaris.vzkq"` — bir "kendinle yarış" disiplin uygulaması şablonundan türetilmiş (model adları da bunu ele veriyor: `RaceSession`, `PurgedHabit`, `PearlDiscipline`).
- **CI yok, `.github` yok, 0 koşu** → iddiaların hiçbiri makine tarafından doğrulanmıyor.
- 208 KB'lık tanıtım videosu depoya gömülü.

---

## 5 · Yan yana özet tablo

| Boyut | pineal-epifiz | pineal-android-companion | Atlas-Pineal |
|---|---|---|---|
| **Tür** | Çalışan platform (motor+API+UI) | Doküman snapshot'ı | Statik tanıtım sitesi + prototip app |
| **Kod var mı** | ✅ 154 bin satır | ❌ 0 satır | ⚠️ 6,3 bin satır (çoğu UI) |
| **Gerçek agent motoru** | ✅ 13 ajan, 28 yetenek, 7 dalga motoru | ❌ | ❌ |
| **Test** | ✅ 298 modül | ❌ | ⚠️ 5 dosya, sabit sayı doğrulayan testler |
| **CI** | ✅ 1.382 koşu, son 5/5 yeşil | ❌ 1 koşu, kırmızı, yollar eksik | ❌ hiç yok |
| **Backend bağlantısı** | ✅ `/api/mobile/coach` köprüsü | — | ❌ (CSP `connect-src 'none'`) |
| **API anahtarı nerede** | Sunucu kasası (gateway belleği) | — | ❌ **APK içinde** |
| **Veri yoksa davranış** | `halted_evidence` / "bilmiyorum" | — | ⚠️ sabit sayı veya uydurma metin |
| **Etik kapılar** | ✅ tüzük + yaş kapısı + kanıt mührü | ⚠️ belgede var, kod yok | ❌ "data poisoning" metinleri |
| **Kime hitap eder** | Operatör / geliştirici | Tarihsel kayıt | Son kullanıcı / yatırımcı |
| **Bugün canlı mı** | ✅ | ❌ | ⚠️ site evet, motor hayır |

---

## 6 · Aralarındaki gerçek ilişki (zaman çizelgesi)

```
2026-08-29 ──► epifiz kod tabanının ilk denetimleri (INDEPENDENT_FORENSIC_AUDIT)
2026-09-08 ──► "CI kırmızı, 6 commit kırmızıyla girmiş"  (DURUM_TESPITI)
2026-09-11 ──► android-companion donduruldu  ← README'de "Android uygulaması" tarifi,
2026-09-11 ──► companion CI: FAILURE           ama kod commit edilmemiş (0 satır)
2026-09-20 ──► Atlas-Pineal başladı (yeni ürün ekseni: "digital exposure")
2026-10-06 ──► Atlas-Pineal: kamuya dönük web yüzeyi (PR #1)
2026-10-18/24 ► epifiz: P6–P10 (ölü kod denetimi, canlı panel, gölge denetimi)
2026-11-07 ──► epifiz: cockpit'e gerçek kanıt grafiği; CI 5/5 YEŞİL
```

Okunuşu: **companion = epifiz'in 11 Eylül'deki fotoğrafı**, **Atlas = epifiz'in motorunu kullanmayı vaat eden ayrı bir yüzey**, **epifiz = tek gerçek motor ve tek yeşil CI**.

---

## 7 · Tavsiye (öncelik sırasıyla)

**P0 — `pineal-android-companion` arşivlenmeli.** Kod içermiyor, CI'ı geçemez, epifiz'in eski bir alt kümesi. Silinmesin ama `ARCHIVED` + README'nin ilk satırına *"Bu depo `pineal-epifiz`'in 2026-09-11 tarihli doküman snapshot'ıdır; kod içermez, CI'ı çalışmaz"* notu düşülmeli. Yanlışlıkla commit'lenmiş 13 `.gradle/` binary'si temizlenmeli.

**P1 — `Atlas-Pineal` ikiye ayrılmalı.** `public/` (temiz, dürüst, CSP'li) kalsın; `app/` altındaki prototip **kaldırılmalı** veya ayrı bir `atlas-prototype` dalına taşınmalı. Nedenleri kendi README'sinde yazılı: data poisoning metinleri, doğrulanmamış sıfır-log iddiası, `BuildConfig` üzerinden APK'ya gömülen Gemini anahtarı ve sabit demo sayılar (`awarenessLevel = 78f`).

**P2 — tek doğruluk kaynağı `pineal-epifiz` olmalı.** Atlas'ın "operasyon motoru ayrı katmanda" ifadesi doğruysa, o katmanın **adı ve bağlantısı** yazılmalı (bugün ada gönderme yok). Aksi hâlde iki repo ayrı iddia evrenlerinde yaşamaya devam eder.

**P3 — epifiz'te küçük hijyen.** Lisans ekle; README'deki "74 HTTP ucu" → ölçülen 76 olarak düzelt; tek commit'lik geçmişi bundan sonra parçalı tut (revert-doğrulama betiklerinin kanıt değeri commit geçmişine bağlı).

---

## 8 · Bu raporun sınırları

- `pineal-epifiz` test paketi **bu ortamda koşturulmadı** (sandbox'ta `pytest` yok). Test iddiaları iki kanıttan gelir: (a) GitHub Actions son koşusu `c49fac3` üzerinde **backend success**, (b) deponun kendi revert-doğrulama betikleri. Canlı Instagram/X kazıma ve canlı LLM çağrısı hiçbir depoda doğrulanmadı (anahtar/egress yok).
- `Atlas-Pineal` ve `companion` **derlenmedi** (ikisinde de derlenecek ortam/dosya eksik: companion'da kod, Atlas'ta `gradle/libs.versions.toml` var ama CI yok).
- Sayılar 2026-11-08'deki `main` başlarına aittir; `git ls-files` ve API yanıtlarıyla ölçülmüştür.

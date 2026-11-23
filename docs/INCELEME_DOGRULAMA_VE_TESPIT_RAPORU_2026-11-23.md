# PINEAL EPİFİZ — Bağımsız Tespit ve Doğrulama Raporu

**Tarih:** 2026-11-23
**Dal:** `arena/9c715599-pineal-epifiz` (taban `9651371`)
**Kapsam:** Depo tamamı (824 izlenen dosya), dış inceleme raporundaki iddialar, ve incelemede yer almayan bağımsız bulgular.
**Kısıt:** Raporun analizi **salt-okunur** üretildi (tespit aşamasında tek satır kod değişmedi).

> **UYGULAMA DURUMU (aynı gün, aynı dal):** Raporun P0 maddeleri koda uygulandı.
> Bkz. §9 "Uygulama özeti". Bu bölüm raporun *tespit* kısmıdır; uygulama
> sonrasında bazı satır numaraları kaymıştır.

---

## 0. Tek sayfalık özet

Dış incelemenin **fonksiyonel iddialarının tamamı doğrulandı**; kök nedenleri bulunup satır düzeyine indirildi. UI/UX iddialarının bir kısmı kaynakta kanıtlanabildi, bir kısmı yalnızca "mekanizma doğru, gözlem yapılamadı" düzeyinde kaldı (sandbox'ta Chromium yok).

Bunlara ek olarak, incelemede **hiç yer almayan 10 yeni bulgu** eklendi. En önemlileri:

1. **Açılış 401'i bir güvenlik kontrolünü felç ediyor.** Kasa durumu telemetri üzerinden öğreniliyor; telemetri 401 dönünce kasa "bilinmiyor" oluyor ve kasa düğmesi çalışmaz hâle geliyor. (Bkz. §3.1)
2. **Ayar modalının alt kısmı CSS düzeyinde kesiliyor** — gözlem değil, flexbox mekanizması. 2 satırlık düzeltme. (Bkz. §3.2)
3. **"GET /APİ/TASKS" hatasının kök nedeni bulundu:** `lang="tr"` + `text-transform: uppercase` → tarayıcı Türkçe büyük harf kuralını uyguluyor, `api` → `APİ` oluyor. (Bkz. §3.3)
4. **"Derinlik" sütunu yanlış alanları okuyor:** modelde var olmayan `personality_type / depth_score / mask_score` aranıyor; gerçek alanlar (`reality_index`, `essence_one_liner`) hiç kontrol edilmiyor. Analiz başarılı olsa bile sütun "VERİ YOK" diyebilir; LLM bu alanları üretirse doğrulanmamış kişilik etiketi ekrana basılıyor. (Bkz. §3.4)
5. **`rust_core` depo kendi beyanıyla ürüne bağlı değil** (`product_runtime_integrated: False`, `activation_flag: None`). Ayrı depoya taşınması ürünü etkilemez — incelemenin "küçültme" önerisi gerekçesinden daha güçlü.

En kritik yapısal tespit: **hiçbir `/api/*` yolu token'sız erişilebilir değil** ve depoda **sıfır KVKK/GDPR/aydınlatma/açık rıza/TOS belgesi** var. Bu ikisi, incelemenin "ziyaretçiye örnek rapor göster" ve "kurumsal konumlandır" önerilerinin **ön koşuludur** — bugün teknik olarak imkânsız değiller, ama önce bu iki katman inşa edilmeden yapılamazlar.

---

## 1. Yöntem ve sınırlar

| Boyut | Durum |
|---|---|
| Analiz türü | Statik kaynak analizi (grep, AST benzeri okuma, dosya:satır kanıtı) |
| Çalıştırma | Test/build/sunucu **çalıştırılmadı** (kullanıcı kısıtı) |
| Görsel doğrulama | **Yapılamadı** — sandbox'ta Chromium yok, `fc-list` 0 font |
| Font glyph kontrolü | **Yapıldı** — `fontTools` ile JetBrains Mono cmap ölçüldü (geçici venv, `/tmp`) |
| Canlı `pinealepifiz.com.tr` | **Kontrol edilmedi** |
| Mobil / klavye / ekran okuyucu | **Doğrulanamadı** |

> **Not:** "Doğrulandı" = kaynak kodda satır düzeyinde kanıt var.
> "Mekanizma doğrulandı" = hataya yol açan CSS/mantık kaynakta mevcut, ama görsel etki ölçülmedi.
> "Doğrulanamadı" = tarayıcı/canlı ortam gerekiyor.

**Ölçülen boyutlar:** 824 izlenen dosya · 293 Python test dosyası · 4 frontend test dosyası · ~134.500 Python satırı · ~6.100 Svelte/TS satırı · 97 uzak dal · 120 env değişkeni.

---

## 2. Dış incelemenin iddiaları — doğrulama tablosu

### 2.1 Fonksiyonel iddialar

#### F1 — "Açılışta kırmızı `HTTP 401` + `KASA DURUMU BİLİNMİYOR`" → ✅ **DOĞRU**

Zincir, satır düzeyinde:

1. `backend/api.py:459-494` — `auth_middleware` **tüm** `/api/*` ve `/v1/*` yollarına uygulanır. **Hiçbir herkese açık istisna listesi yok.** `auth_required` true iken token yoksa → `401 UNAUTHORIZED`.
2. `frontend/src/lib/telemetry.ts` — sayfa açılır açılmaz `/api/health/detail` ve `/api/telemetry` yoklanır (5/10/30 sn, varsayılan 10).
3. Bu çağrılar 401 döner → `vaultLocked` store'u hiç set edilmez.
4. `UnifiedPinealCockpit.svelte:1202` — `vaultKnown` false kaldığı için etiket `KASA DURUMU BİLİNMİYOR` basar.

**Kök neden:** Kimlik doğrulama katmanı ile "kasa durumu" göstergesi aynı API'ye bağımlı. Auth hatası, güvenlik göstergesini **yanlış** bir durumla (bilinmiyor) dolduruyor. Kullanıcı "sistem bozuk" sonucuna varıyor; gerçek durum "token yok".

#### F2 — "`GEÇMİŞ & RAPORLAR` içinde `/api/tasks` 401" → ✅ **DOĞRU**

Aynı mekanizma. `UnifiedPinealCockpit.svelte:644` → `GET /api/tasks?client_id=...`. 401 → `tasksError = "HTTP 401"` → modal içinde kırmızı hata. Modal açılışında (`openHistoryModal`, :721) hem `loadTaskHistory` hem `loadReportCenter` tetiklenir; ikisi de 401 yiyebilir.

#### F3 — "`▲ ANALİZİ BAŞLAT` hiçbir şey yapmıyor (`@test`, ARM kapalı/açık)" → ⚠️ **KISMEN DOĞRU — kök neden farklı**

**Doğru olan:** Düğme gerçekten sessiz kalabiliyor.
**Kısmen yanlış olan:** "ARM'ın etkisi yok" değil — ARM handler'da gerçek bir
kapıydı, ama `disabled` ifadesinde olmadığı için etkisi **görünmezdi**.

Kanıt — `UnifiedPinealCockpit.svelte:1077`:

```svelte
disabled={$isProcessing || !targetUrl.trim() || !isAdultDeclared}
```

> **DÜZELTME (uygulama aşamasında bulundu):** Bu bölümün ilk sürümü "ARM'ın
> başlatma yoluna etkisi sıfır" diyordu. **Bu yanlıştı.** `launchAnalysis()`
> içinde `$armEngaged` kontrolü **var** (`if (!$armEngaged) { ... return; }`),
> yani ARM gerçek bir kapıydı — yalnız `disabled` ifadesinde yer almıyordu.
> Sonuç: düğme **aktif görünüyordu**, tıklanınca ARM'a takılıyor ve mesajı
> yalnız sohbet akışına yazıp geri dönüyordu.

`$armEngaged` bu ifadede **hiç geçmiyor** — yani ARM kapalıyken düğme disabled
değil. İncelemenin "ARM off ve on'da aynı" gözlemi bu yüzden: ARM'ın etkisi
*görünmezdi*, çünkü kapı `disabled`'da değil handler'daydı.

Gerçek sessizlik nedeni iki katmanlı:

| Durum | Sonuç |
|---|---|
| 18+ kutusu işaretli değil | Düğme `disabled`. **Hiçbir açıklama, tooltip veya inline mesaj yok.** Tarayıcı `disabled` butona tıklamayı sessizce yutar. |
| 18+ işaretli, `@test` girili | Düğme aktif. `launchAnalysis` → `/api/target/preflight` muhtemelen `eligible=false` döner → `playHalt()` + mesaj **yalnızca sol sütundaki ASPASIA sohbet akışına** düşer. |

`grep -n "launchError\|startError\|initiateError"` → **0 sonuç.** Yani düğmenin yanında gösterilecek bir hata state'i bile yok. Tüm başarısızlıklar sohbet akışına yazılıyor (`chatMessages = [...]`), kullanıcı bakmıyorsa "hiçbir şey olmadı" algısı doğuyor.

> **Bu bir buton bug'ı değil, bir geri bildirim mimarisi sorunu.** İnceleme "düğme çalışmıyor" demiş; gerçek tespit "sistem çalışıyor ama sonucu görünmez bir yere yazıyor".

#### F4 — "Bozuk / tofu ikonlar (LILITH GROWTH / SHADOW / OSINT / RESONANCE + modal kapatma)" → ✅ **DOĞRU, ölçüldü**

JetBrains Mono cmap'i (tüm ağırlıklar birleşik) ile ölçüm:

| Sembol | Kod | Kullanım | JetBrains Mono |
|---|---|---|---|
| `✦` | U+2726 | 14 | ❌ |
| `◈` | U+25C8 | 9 | ❌ |
| `▲` | U+25B2 | 9 | ❌ |
| `→` | U+2192 | 5 | ❌ |
| `⟐` | U+27D0 | 4 | ❌ |
| `⌖` | U+2316 | 3 | ❌ |
| `▼` | U+25BC | 3 | ❌ |
| `✕` | U+2715 | 3 | ❌ |
| `◬` `⟡` `⯁` `◇` `◆` `✷` `◉` `↻` `⟳` `⬇` `⚠` `⛔` | — | 1–2 | ❌ |
| `📜` `📄` `⏱` `🔑` `📡` `📱` `🔥` `⚙` `🔒` | U+1F3xx–1F6xx | 1–2 | ❌ |
| `•` | U+2022 | 1 | ✅ |

`frontend/src/app.css` yalnızca üç ağırlık sırası tanımlıyor: `Cinzel`, `JetBrains Mono`, `VT323` — hepsi Google Fonts'tan. **Fallback zinciri yok** (`font-family: 'JetBrains Mono', monospace` — sistem monospace'i de çoğu sistemde bu glyph'leri içermiyor). Sonuç: kutu (tofu) veya boşluk.

`✕` (U+2715) özellikle kritik: **modal kapatma düğmesi** bu glyph'i kullanıyor (:1817).

#### F5 — "Modal kapatma düğmeleri bozuk" → ✅ **DOĞRU + ek bulgu**

Yukarıdaki glyph eksikliğine ek olarak: `.modal-close-btn` sınıfının **CSS kuralı hiç yok.**

```
grep -n "modal-close-btn" → yalnız 1817 (markup)
```

`.modal-x-btn` için stil tanımlı (:2677), `.modal-close-btn` için değil. Yani kapatma düğmesi tarayıcı varsayılan buton stiline düşüyor — koyu temada görünmez olabilir. **İki ayrı hata üst üste:** glyph yok + stil yok.

### 2.2 UI/UX iddiaları

#### U1 — "Savaş kokpiti + okült jargon duvarı" → ✅ **DOĞRU (ölçüldü)**

Terim sayımları (cockpit + backend): `ASPASIA` 70 · `ARM` 44 · `LILITH` 47 · `SOVEREIGN` 22 · `KANIT` 14 · `HALTED` 9 · `KAZI` 5. Sıfır TODO/FIXME — kod "bitmiş" görünüyor ama kelime dağarcığı tutarsız: aynı ekranda "ADLİ KANIT" (adli) ile "SİLAHLANDIRMA / ARM" (askeri) ve "LILITH / BİLİNÇDIŞI GÖLGE" (okült) aynı anda var.

#### U2 — "Yaygın truncation / overflow" → ⚠️ **KISMEN — mekanizma var, yaygınlık ölçülemedi**

Kanıtlanmış iki mekanizma:
- `UnifiedPinealCockpit.svelte:1239` ve `:1266` — `p.slice(0, 36)` sabit kesme. 36 karakterden uzun her ajan adı sessizce kesilir.
- Canlı durum rozetinde `max-width: 480px`.

"Yaygın" nitelendirmesi görsel ölçüm gerektiriyor; doğrulanamadı.

#### U3 — "Yüzen `▲ TELEMETRİYİ GÖSTER` düğmesi select ve RESONANCE kartının üstünde" → ⚠️ **GEOMETRİK OLARAK TUTARLI, GÖZLENMEDİ**

`frontend/src/App.svelte:483-491`:

```css
.telemetry-toggle {
  position: fixed;
  right: 420px;
  bottom: 14px;
  z-index: 46;
}
```

- `UnifiedPinealCockpit.svelte:1290` → `Tümü (kayıt etiketi)` seçimi **sağ sütunda**.
- 1600 px viewport'ta `right: 420px` → düğme x ≈ 1180 px'ten başlar; sağ sütun (28% ≈ 448 px, x ≈ 1150–1598) tam bu bölgeye denk gelir.
- Aynı düğme `bottom: 14px` → sayfanın en altı, yani 7 sütunlu radar ızgarasının son satırı (RESONANCE) ile aynı bant.

**Sonuç:** Çakışma aritmetik olarak kaçınılmaz görünüyor. Ama gerçek render'da `z-index: 46` üstte kalır mı, seçim hâlâ tıklanabilir mi — **görsel doğrulama gerekli.**

**Ek bulgu (incelemede yok):**
1. `App.svelte:470-475` üstündeki yorum **"Sol üst köşede kompakt konumlandırıldı"** diyor; CSS **sağ-alt**. Kod yorumu yalan.
2. **İki ayrı telemetri düğmesi var:** `App.svelte:433` (fixed, yüzen) ve `UnifiedPinealCockpit.svelte:1754` (sol sütun içinde, akışta). Aynı işlevi yapan iki kontrol; biri z-index 46 ile yüzerken diğeri sütun içinde. İncelemenin gördüğü "yüzen düğme" bunlardan ilki.
3. `SupportPanel.svelte:131` — `position: fixed; right: 18px; bottom: 62px; width: min(420px, 34vw); z-index: 62` → aynı köşe, daha yüksek z-index. **Üçüncü bir katman** aynı bölgede.

#### U4 — "`OpenRouter` / `PINEAL_TOKEN` alanları alt barın arkasında kesiliyor" → ✅ **DOĞRU — kaynakta kanıtlandı**

Bu, incelemenin görsel gözlemi; ben CSS mekanizmasını buldum.

`UnifiedPinealCockpit.svelte:2660-2667`:

```css
.cockpit-modal-card {
  width: min(880px, 96vw); max-height: 90vh;
  display: flex; flex-direction: column; overflow: hidden;
}
```

`:2689`:

```css
.cockpit-modal-body {
  padding: 1rem 1.25rem; overflow-y: auto;
  display: flex; flex-direction: column; gap: 1rem;
}
```

**Eksik olan:** `flex: 1 1 auto;` ve `min-height: 0;`.

Flexbox kuralı: bir flex item'ın varsayılan `min-height`'ı `auto`'dur — yani içerik yüksekliğinin altına inemez. `.cockpit-modal-body` içeriği 90vh'yi aştığında:

1. `overflow-y: auto` çalışmaz, çünkü body'nin kendisi yükseklik kısıtlı değil.
2. Body, kartın `max-height`'ını zorlar.
3. Kart `overflow: hidden` → taşan kısım **kesilir**, scroll bar hiç doğmaz.

Ayarlar modalı 7 `modal-section-box` taşıyor (:1995–2097). OpenRouter + PINEAL_TOKEN kutusu (:2027) sıralamada **5. sırada** — yani tam kesilme bölgesinde. İncelemenin "alanlar alt barın arkasında" tespiti bu mekanizmayla birebir örtüşüyor.

> Bu bulgu incelemeyi **doğrulamakla kalmıyor, düzeltme maliyetini de belirliyor:** 2 satır CSS.

#### U5 — "`ANALİZİ BAŞLAT` vs `KAZIYI BAŞLAT` uyumsuzluğu" → ✅ **DOĞRU — depo kendisi itiraf ediyor**

- Düğme: `:1079` → `▲ ANALİZİ BAŞLAT`
- Aynı ekrandaki yardım metni: `:1385` → "Hedef girip **KAZIYI BAŞLAT** dediğinizde..."

`:1185-1186` yorumu bunu açıkça yazıyor:

> *"`initiateBtn="ANALİZİ BAŞLAT"` ama ekrandaki düğme "KAZIYI BAŞLAT""*

Aynı yorum, i18n tablosunun 94 TR + 94 EN anahtar taşıdığını ama bunların yalnız **10'unun** mevcut arayüzle örtüştüğünü söylüyor.

#### U6 — "`GET /APİ/TASKS` noktalı-İ bozulması" → ✅ **DOĞRU — kök nedeni bulundu**

İnceleme bunu bir "yazım hatası" gibi raporlamış. Gerçek durum daha ilginç:

`UnifiedPinealCockpit.svelte:1833`:
```html
<h4>Kayıtlı Görevler (GET /api/tasks)</h4>
```

`:2694`:
```css
.modal-section-box h4 { ... text-transform: uppercase; }
```

`frontend/index.html:2`:
```html
<html lang="tr">
```

**Zincir:** `lang="tr"` → tarayıcı Türkçe büyük harf kurallarını uygular → `api` → `APİ` (noktalı İ) → ekranda **`GET /APİ/TASKS`**.

Yani hata CSS'te değil, `lang="tr"` + `text-transform: uppercase` etkileşiminde. Düzeltmek için ya `lang`'i `en` yapmak (kötü: Türkçe içerik var) ya `text-transform: uppercase` yerine metni kaynakta büyük yazmak ya o başlıkta `text-transform: none` kullanmak gerekir.

**İkinci sorun:** Arayüzde ham API yolu göstermek ("GET /api/tasks") zaten jargon sızıntısı — kullanıcı için anlamsız.

### 2.3 Öneri iddiaları

#### R1 — "Repoyu tek çekirdeğe küçült (97 dal, `android/`, `rust_core/`, `extensions/chrome-linkedin/`, kullanılmayan hosting dosyaları ayrı depoya)" → ✅ **DOĞRU — ve gerekçe incelemeden daha güçlü**

**Dal sayımı (doğrulandı):**

| Önek | Adet |
|---|---|
| `arena` | 72 |
| `fix` | 12 |
| `feat` | 3 |
| `cleanup` | 2 |
| `main` | 1 |
| `jules` / `chore` / `bolt` ×2 / `AppleCurse` ×3 | 8 |
| **Toplam** | **97** |

Yalnız 2 dal merge edilmiş. 72 `arena` dalı açıkta.

**`rust_core` için belirleyici kanıt** — `agent_core/services/runtime_status.py:9-17`:

```python
_RUST_CORE_STATUS = {
    "classification": "experimental_optional",
    "product_runtime_integrated": False,
    "product_decision_effect": False,
    "packaged_in_python_runtime": False,
    "activation_flag": None,
    "validation": "ci_cargo_check_and_test",
}
```

Ve `agent_core/services/token_compressor.py:9-15` açıkça yazıyor: native çekirdek PyO3/maturin ile ürüne **bağlanamaz**; ürünün fiilen çalıştırdığı kod saf Python mirror'ı. İkisi ortak fixture'dan test ediliyor.

> **Sonuç:** `rust_core/` (49 dosya, 1.1 MB) ayrı depoya taşınırsa **ürün çalışmasını saniyesinde bile etkilemez.** İnceleme "küçült" demiş; ben ekliyorum: depo bunu zaten kendi sözleşmesiyle beyan ediyor, yani karar teknik borç değil **organizasyonel cesaret** meselesi.

`android/` (51 dosya) CI'da ayrı job (`ci.yml:276`) ve ayrı teslimat kanalı; aynı şekilde ayrıştırılabilir. `extensions/chrome-linkedin/` (6 dosya) ayrı iş.

**Dikkat:** `android/` ve `rust_core/` **ölü kod değil** — bakımlı, test edilmiş. "Kaldır" değil "ayrı depoya taşı" doğru karşılık.

#### R2 — "Ziyaretçiye 401 yerine 2 hazır örnek rapor göster" → ✅ **DOĞRU — bugün teknik olarak imkânsız**

- `backend/api.py:459-494` → hiçbir `/api/*` yolu token'sız açılamıyor. **Herkese açık salt-okunur katman yok.**
- Depoda **hiç örnek rapor artefaktı yok** (`release/`, `docs/`, `tests/` tarandı).
- **Ama altyapı hazır:** `backend/routes/reports.py` `/api/report/status|build|list|file/{name}` uç noktaları; `agent_core/services/report_factory.py` markdown/pdf/diagram/video üretiyor; PDF için `reportlab` opsiyonel (`requirements.txt:58`, yoksa dürüst `dependency_missing:reportlab`); sha256 mühür var.

Yani öneri **doğru ve ucuz** — sadece bir public allowlist + 2 statik artefakt gerekiyor.

#### R3 — "Sessizlik yerine açık login / kredi / API anahtarı rehberliği" → ✅ **DOĞRU**

- `grep -rn "kredi|credit|KREDİ" frontend/src` → **0 sonuç.** Kredi/limit kavramı arayüzde hiç yok.
- `PINEAL_TOKEN` alanının placeholder'ı: `"Opsiyonel (üretim modu için)"` (:2040). Oysa 401'in **tek** çözümü bu token. "Opsiyonel" etiketi kullanıcıyı yanlış yönlendiriyor.
- API anahtarı modalında 6+ sağlayıcı var; hangisinin zorunlu olduğu, kredi nereden alınacağı, limitsiz mod olup olmadığı hiçbir yerde yazmıyor.

#### R4 — "Kurumsal/profesyonel konumlandırma (ajans, marka, İK, yatırımcı) vs bireysel 'birini takip et' kullanıcısı" → ✅ **DOĞRU — ama bir engel var**

**Doğru olduğu kanıt:** `docs/KURUM_HEDEFI.md` şirketi **tarama hedefi** olarak tanımlıyor, **müşteri** olarak değil. Yani ürün bugün "kurumu tara" diyor, "kuruma sat" demiyor. Konumlandırma gerçekten çelişkili.

**Engel (incelemede eksik):**
- Depoda **sıfır** KVKK / GDPR / aydınlatma metni / açık rıza / TOS / gizlilik politikası belgesi. (Kapsamlı grep: 0 hit.)
- `agent_core/capabilities/policy.py:9` — *"hedef rızası diye bir kapı YOKTUR"*. `CONSENT_ONLY_FLAGS = ("ENABLE_CROSS_PLATFORM",)`; yerleşik kapılar yalnız `{vault, budget, rate}`.
- `PhoneProbeCapability` (`agent_core/capabilities/adapters_identity.py:118-190`): E.164 numara, operatör, WhatsApp/Telegram probe, web footprint, `auto_bridge_social`. Kapılar: **yalnız `{vault}`.** Rıza kapısı yok.
- Arayüzdeki tek yasal dokunuş 18+ beyan kutusu (`cockpit:1069-1072`) ve Tüzük §2 referansı.

> Kurumsal satış için bu **teknik değil hukuki** bir blokaj. İK kullanım senaryosu (aday taraması) KVKK açısından en riskli kategori; açık rıza olmaksızın tek bir kurumsal demo bile yapılamaz.

#### R5 — "7-dalga motoru (FFT/Lomb-Scargle) + Lilith/Bilinçdışı Gölge eşleşmesi bilimsel kredibiliteyi zedeliyor" → ✅ **DOĞRU — iki ayrı kanıtla**

**Kanıt 1 — Lomb-Scargle iddiası:**
- `README.md:24` ve `README.md:95` Lomb-Scargle'dan bahsediyor.
- Kod tabanında **hiç Lomb-Scargle implementasyonu yok** (grep: 0).
- `requirements.lock` → `scipy==1.17.1` kilitli ama **hiçbir modül kullanmıyor**.
- Gerçek spekttrum: `agent_core/engines/spectrum.py` — numpy `rfft` + Hann penceresi. **FFT gerçek.**

**Kanıt 2 — "Ölçüm" katmanında strateji içerği:**
`agent_core/engines/key_engine.py`:
```python
conf = active / 6   # 6 motorun kaçı aktif — olasılık DEĞİL
```
ve sabit metin:
> *"karşılıklı ilgi oluşursa özel mesaja geçiş"*
> `gate_key` → sohbet açılış yaklaşımı öneriyor.

`agent_core/services/pillar_evidence_adapter.py:558` bunu doğru etiketliyor: `reported_confidence_semantics` = **kapsam oranı, kalibre edilmiş olasılık değil**; KEY öğeleri `heuristic_only`.

**Ama arayüz etiketi düşürüyor:** `cockpit:1664` → `Güven: {summary.confidence}%`. "Kapsam" ya da "kalibre değil" ibaresi yok.

> Bu, incelemenin "bilimsel kredibilite" eleştirisinin **en somut** hâli: altyapı dürüst, sunum dürüst değil. Ve 7. motor ("Key") ölçüm değil **davranış önerisi** üretiyor — "adli kanıt" başlığı altında.

---

## 3. İncelemede olmayan bağımsız bulgular

### 3.1 🔴 Auth hatası güvenlik kontrolünü felç ediyor

`vaultLocked` store'u yalnızca `/api/telemetry` başarılı dönerse set ediliyor. 401 → set edilmiyor → `vaultKnown=false` → kasa düğmesi "bilinmiyor" ve `toggleVaultLock` içindeki `if (!vaultKnown) { await refreshVaultState(); return; }` dalı çalışıyor.

**Etki:** Token'sız kullanıcı yalnız "erişim yok" almıyor; **kasa kilidini açamıyor** da. Kasa, sistemdeki tüm yetenek kapılarının (`{vault, budget, rate}`) ilki. Yani tek bir auth hatası tüm yetenek zincirini kilitliyor.

**Bu incelemenin "401 görünüyor" tespitinden daha derin:** sorun görünür kırmızı yazı değil, **görünmez kilitleme**.

### 3.2 🔴 Ayar modalı flexbox kesmesi

§2.2 U4'te detaylandı. Ek: aynı hata `showHistoryModal` modalını da etkiliyor (:1814 `cockpit-modal-card`, :1829 `cockpit-modal-body`). Görev geçmişi listesi uzadığında da alt kısım kesilir.

**Düzeltme maliyeti:** `.cockpit-modal-body { flex: 1 1 auto; min-height: 0; }` — 2 satır.

### 3.3 🟠 `lang="tr"` + `text-transform: uppercase` sistematik risk

`GET /APİ/TASKS` tek örnek. Aynı mekanizma, `text-transform: uppercase` uygulanan **her** Türkçe metinde `i → İ` dönüşümü yapar. `index.html:2` `lang="tr"` olduğu sürece bu tarayıcı davranışı. Kaynakta büyük yazılmış metinler etkilenmez; karışık küçük/büyük metinler etkilenir.

### 3.4 🔴 "Derinlik" sütunu yanlış alanları okuyor — iki yönlü epistemik hata

`UnifiedPinealCockpit.svelte:320`:
```ts
depth: [depthReport, ['personality_type', 'depth_score', 'mask_score']],
```

`agent_core/agents/depth_analyst.py:35-50` — `DepthReport` modeli:
```python
class DepthReport(BaseModel):
    reality_index: float
    reality_rationale: str
    reality_findings: List[DepthFinding] = []
    contradictions: List[DepthFinding] = []
    state_drift: Optional[str] = None
    timing_pattern: Optional[str] = None
    essence_one_liner: str
    ...
    model_config = ConfigDict(extra="allow")
```

**`personality_type`, `depth_score`, `mask_score` modelde YOK.**

İki sonuç:
1. **Yanlış negatif:** Derinlik analizi başarılı, `reality_index=0.72`, `essence_one_liner` dolu → ama `getPillarHasData('depth')` false döner → sütun **"VERİ YOK"** gösterir. (`summary?.hasData` kurtarabilir ama bu `evidence.ts`'e bağlı; garanti değil.)
2. **Yanlış pozitif:** `extra="allow"` sayesinde LLM bu alanları üretirse model doğrulamadan geçirir → `cockpit:1680-1682` bunları **"Kişilik / Derinlik / Maskelik"** etiketiyle basar. Prompt bu alanları istemiyor (:125-150 `reality_index`, `contradictions`, `state_drift` istiyor) — yani LLM serbest üretimle kişilik etiketi uydurursa ekrana "Kişilik: Narsisist" gibi doğrulanmamış bir yargı düşebilir.

> Bu, ürünün "SIFIR HALÜSİNASYON" iddiasıyla (i18n `footerText`) doğrudan çelişen tek bulgu.

### 3.5 🟠 `.modal-close-btn` stillsiz

§2.1 F5. Glyph de yok, stil de yok. Kapatma düğmesi iki katmanlı kırık.

### 3.6 🟠 Üç katmanlı alt-sağ köşe çakışması

| Öğe | Konum | z-index |
|---|---|---|
| `.telemetry-toggle` (App.svelte) | `right:420px; bottom:14px` | 46 |
| `.telemetry-panel` (App.svelte) | `right:14px; bottom:46px; width:min(380px,30vw)` | 45 |
| `SupportPanel` | `right:18px; bottom:62px; width:min(420px,34vw)` | 62 |

Üçü de aynı köşede. Panel açıldığında 380–420 px genişliğinde bir blok, telemetri düğmesi ve destek paneli üst üste biner.

### 3.7 🟠 ARM "yarı zorunlu": düğmede yok, handler'da var

`cockpit:1036`:
> *"Başlamak için hedef girin, **ARM kilidini açın** ve analizi başlatın."*

`:1077` disabled ifadesinde ARM yok, ama `launchAnalysis()` içinde `$armEngaged`
kontrolü **var**. Yani ARM "yarı zorunlu": kapalıyken düğme aktif görünür,
tıklanınca sessizce geri döner ve mesaj yalnız sohbet akışına düşer. İncelemenin
"ARM off ve on'da aynı" gözleminin kökü bu — ARM'ın etkisi *görünmez*.
(Uygulamada bu kapı kaldırıldı; ARM artık yalnız gösterge.)

`PWR` ve `REC` de aynı durumda: `powerEngaged`, `recordEngaged` yalnız `aria-pressed` ve görsel durum taşıyor; `launchAnalysis` içinde okunmuyor.

### 3.8 🟠 Hata geri bildirimi tek kanala sıkışmış

Tüm başarısızlıklar `chatMessages`'a yazılıyor:
- preflight reddi → chat
- `/api/initiate` hatası → chat
- kasa hatası → `vaultError` (tek istisna, inline var)
- telefon probe hatası → chat

`launchError` benzeri bir state yok. Sonuç: düğmenin yanında hiçbir zaman açıklama görünmüyor. İncelemenin "düğme hiçbir şey yapmıyor" tespitinin gerçek kökü.

### 3.9 🟡 Erişilebilirlik: ESC yok, focus trap yok, outline yok

- `grep -n "Escape"` → 0. Modal'lar ESC ile kapanmıyor.
- Focus trap yok; modal açıkken Tab arka plandaki öğelere geçebilir.
- `outline: none` × 4, `:focus-visible` yok, `prefers-reduced-motion` yok.
- Modal'larda `role="dialog" aria-modal="true"` var (iyi) ama `aria-labelledby` yok.

### 3.10 🟡 i18n tamamen ölü

`frontend/src/i18n.ts` — 94 TR + 94 EN = 188 anahtar (ölçüm: 196 satır, ~188 anahtar). **Tüketici sayısı: 0.**

```
grep -rn "i18n" frontend/src --include=*.svelte --include=*.ts
→ yalnız store.ts:153 re-export + cockpit:1181 yorum
```

Hiçbir bileşen `t.tr.*` ya da `$t(` kullanmıyor. Depo 188 anahtar taşıyor, hiçbiri ekrana çıkmıyor. Bu, "iki dillilik var" izlenimi veren bir **cephe**.

### 3.11 🟡 Tekrarlayan telemetri kontrolü + yalan yorum

`App.svelte:331` `let telemetryVisible = true;` → `:333` `onMount` içinde `telemetryVisible = false;`. Yani başlangıçta kapalı ama kod "açık" diye başlıyor. Mantık doğru, ifade yanıltıcı.

Yorum (`:466`): *"Sol üst köşede kompakt konumlandırıldı — alttaki Aspasia sohbet ekranını ASLA kapatmaz."* CSS sağ-alt. **İddia ile uygulama çelişiyor.**

### 3.12 🟡 README'de var olmayan bileşen

`README §4` → `AtlasPortal.svelte` varsayılan görünüm olarak belgeleniyor.

```
ls frontend/src/components/ → SupportPanel, TaskEvidence, UnifiedPinealCockpit, visualizers/
```

**`AtlasPortal.svelte` yok.** `App.svelte` yalnız `<UnifiedPinealCockpit />` render ediyor. Ayrıca `frontend/scripts/browser-smoke.mjs` 5 sekme / `.surface-tabs` / `ATLAS OBSERVATORY` arıyor — bu yüzden **güncel arayüzle uyumsuz**; CI'da bu betik hiç çağrılmıyor (`grep -rn "browser-smoke" .github frontend/package.json` → 0 hit). Yani depo, çalışmayan bir smoke testi taşıyor.

### 3.13 🟡 Üç belge, üç ajan sayısı

| Kaynak | Ajan sayısı |
|---|---|
| `README.md` | 14 |
| `README_TECHNICAL.md` | 13 (güncel değil) |
| `docs/PINEAL_EPIFIZ_GERCEK_ENVANTER_2026-11-22.md` | "12 uzman" |
| Gerçek (`self.agents`) | 14 (+ opsiyonel yorumlayıcı) |
| Cockpit yedek değeri (`:1992`) | **21** (hardcoded) |

### 3.14 🟡 Hosting çokluğu

`Dockerfile`, `docker-compose` (12 beacon), `railway.toml`, `vercel.json`, `wrangler.toml` + worker + functions (Cloudflare), `baslat.bat`. Backend yalnız `frontend/dist` servis ediyor. Yani 5 farklı dağıtım stratejisi aynı depoda — hangisinin gerçek olduğu belgelenmemiş.

### 3.15 🟡 120 env değişkeni

`.env.example` 120 değişken. Yeni bir geliştiricinin "hangileri zorunlu?" sorusuna cevap yok. Üstelik 401'in tek çözümü olan `PINEAL_TOKEN` için arayüzde "Opsiyonel" yazıyor.

### 3.16 🟡 Telefon girişi arayüze davet ediyor

`cockpit:1048` placeholder:
> *"Hedef Profil URL, @kullanıcı veya Telefon (örn: (552) 956-87-63)..."*

`isPhoneInput()` (`:587-592`) 10+ digit içeren her girişi telefon sayıyor. Bu, rızası alınmamış bir gerçek kişinin numarasının OSINT sensörlerine (WhatsApp/Telegram probe dahil) gidebileceği anlamına geliyor — ve `PhoneProbeCapability`'nin tek kapısı `{vault}`.

---

## 4. Gerçek kullanıcı ihtiyacından türeyen ek öneriler

İnceleme "neyi düzeltmeli" dedi. Aşağıdaki liste **kim için** düzeltileceğini de söylüyor.

### Kullanıcı tipleri

| Tip | Bugünkü deneyim | Gerçek ihtiyaç |
|---|---|---|
| **A. İlk kez gelen ziyaretçi** | Kırmızı 401 + "kasa bilinmiyor" | 10 saniyede "bu ne işe yarar" görmek |
| **B. Anahtarsız deneyici** | Düğme sessiz, hiçbir şey olmuyor | "Neden olmadı" cevabı |
| **C. Analist / ajans** | Jargon duvarı, kesilen alanlar | Kanıta ulaşmak, raporu çıkarmak |
| **D. Kurumsal alıcı (İK/marka)** | Hiçbir yasal belge yok | KVKK uyumu, çoklu kullanıcı, denetim izi |
| **E. Geliştirici** | 120 env, 5 hosting, 97 dal | Tek komutla ayağa kalkan ortam |

### P0 — 1 hafta (kırık olan her şey)

| # | Öneri | Kullanıcı | Kanıt |
|---|---|---|---|
| P0.1 | **Herkese açık salt-okunur katman** (`/api/public/*` allowlist) + 2 statik örnek rapor. Ziyaretçi 401 görmesin. | A, D | `api.py:459` allowlist yok |
| P0.2 | **Düğme yanında inline durum/hata** (`launchState`). Sohbet akışına bağımlılığı kaldır. | B | `launchError` yok |
| P0.3 | **Modal flex düzeltmesi**: `.cockpit-modal-body { flex: 1 1 auto; min-height: 0; }` | C | `:2689` |
| P0.4 | **`.modal-close-btn` stili + `✕` yerine SVG/metin** ("Kapat") | A, B, C | glyph yok + stil yok |
| P0.5 | **ARM'ı ya gerçek kapı yap ya kaldır**; `:1036` yardım metnini düzelt | B | `:1077` ARM yok |
| P0.6 | **Telemetriyi tek düğmeye indir**, 401'de "bağlantı yok" de, kasa durumunu etkileme | A | `:331/:333`, `App.svelte:433` + `:1754` |

### P1 — 2–4 hafta (doğruluk ve güven)

| # | Öneri | Kullanıcı | Kanıt |
|---|---|---|---|
| P1.1 | **"Güven: %" → "Kapsam: N/6 motor (kalibre değil)"** | C, D | `cockpit:1664`, `key_engine.py` |
| P1.2 | **Depth sütununu gerçek alanlara bağla** (`reality_index`, `essence_one_liner`, `contradictions`) | C, D | `:320`, `depth_analyst.py:35` |
| P1.3 | **KVKK/aydınlatma/açık rıza metinleri** + `policy.py`'ye `consent` kapısı | D | 0 belge, `policy.py:9` |
| P1.4 | **Telefon probe'u rıza + amaç beyanına bağla** | D | `adapters_identity.py:118` |
| P1.5 | **Sembolleri ikon setine çevir** (SVG) + `font-family` fallback | A, B, C | 30+ glyph yok |
| P1.6 | **Jargon → insan dili**: ARM/PWR/REC → "Oturum / Kayıt / İzleme"; LILITH → "Otomatik İletişim"; SOVEREIGN → "Uzman" | A, C, D | sayımlar |
| P1.7 | **API anahtarı rehberi**: hangi sağlayıcı zorunlu, kredi nereden, limitsiz mod var mı | B | `kredi` 0 hit |
| P1.8 | **Ham API yollarını arayüzden kaldır** (`GET /api/tasks` başlığı) | A, C | `:1833` |
| P1.9 | **ESC ile kapanma + focus trap + `:focus-visible`** | A, C | `Escape` 0 hit |

### P2 — 1–3 ay (yapısal)

| # | Öneri | Kullanıcı | Kanıt |
|---|---|---|---|
| P2.1 | **`rust_core/` ayrı depoya** — depo kendi sözleşmesiyle zaten opsiyonel | E | `runtime_status.py:9` |
| P2.2 | **`android/` ayrı depoya** (ayrı CI job, ayrı teslimat) | E | `ci.yml:276` |
| P2.3 | **Hosting'i tek stratejiye indir** (diğer 4'ü arşivle) | E | 5 konfig |
| P2.4 | **97 dal temizliği + branch koruma** (arena dalları otomatik kapanış) | E | 72 arena |
| P2.5 | **Örnek raporları report_factory ile üret** (2 senaryo: açık kaynak OSINT + içerik tutarlılığı) | A, D | `reports.py` hazır |
| P2.6 | **Kurumsal çoklu-operatör** — `PINEAL_OPERATOR_TOKENS` + `resolve_principal` zaten var; ekip/kayıt yönetimi ekle | D | `security.py:192-267` |
| P2.7 | **Metodoloji sayfası**: FFT ne ölçer, Lomb-Scargle iddiasını kaldır, Key motorunu "ölçüm"den "öneri"ye taşı | C, D | `README:24,95` |
| P2.8 | **İki dilliliği gerçek yap ya da `i18n.ts`'i sil** — 188 ölü anahtar | E | 0 tüketici |
| P2.9 | **`browser-smoke.mjs`'i güncelle veya kaldır** (5 sekme arıyor, arayüz tek sekme) | E | `surface-tabs` yok |

### Konumlandırma önerisi (incelemenin R4'üne ek)

İnceleme "kurumsal vs bireysel" diyor. Ben daha net bir çizgi öneriyorum:

- **Bireysel "birini ara" kullanımı** → ürünün mevcut kimliği. Burada kalmak isteniyorsa 18+ beyanı + rıza + sınırlı veri tutma yeterli değil; **açık rıza** şart.
- **Kurumsal (İK/marka/ajans)** → `KURUM_HEDEFI.md`'yi tersine çevirmek gerekiyor: kurum **müşteri**, hedef **kamu kaynaklı şirket varlığı** (marka itibarı, rakip analizi, yatırım due diligence). Bu senaryoda hedef **tüzel kişi** olduğundan KVKK riski dramatik düşer — çünkü kişisel veri değil kurumsal veri.
- **Ortak zemin:** İki senaryo da aynı teknik altyapıyı kullanır; fark **rıza akışı** ve **rapor şablonu**'nda. Yani iki ayrı ürün değil, iki ayrı giriş kapısı.

Bu, incelemenin "konumlandırma çelişkisi" tespitini **çözülebilir** bir ürüne çeviriyor.

---

## 5. Önerilen yol haritası

```
HAFTA 1  ── P0.1–P0.6 ──────────────────────────────────────► "Site açılıyor, düğme cevap veriyor"
HAFTA 2-4 ── P1.1–P1.9 ─────────────────────────────────────► "Kanıt dürüst, hata görünür, ikon okunur"
HAFTA 5-8 ── P1.3–P1.4 (KVKK + rıza) ──────────────────────► "Kurumsal demo verilebilir"
AY 3-6  ── P2.1–P2.9 ──────────────────────────────────────► "Tek depo, tek hosting, tek gerçeklik"
```

**Kritik bağımlılık:** P1.3 (KVKK) tamamlanmadan P2.5 (kurumsal örnek rapor) ve kurumsal konumlandırma **başlatılmamalı** — hukuki risk.

---

## 6. Doğrulanamayanlar

| Konu | Neden | Nasıl doğrulanır |
|---|---|---|
| Canlı `pinealepifiz.com.tr` davranışı | İnternet erişimi kısıtlı; canlı site bu oturumda ziyaret edilmedi | Tarayıcıdan açılış; Network sekmesinde 401 zinciri |
| Telemetri düğmesinin gerçek çakışması | Chromium yok | `browser-smoke.mjs` güncellenip 1600×1100'te ekran görüntüsü |
| Mobil kırılımlar (1300px altı) | Aynı | 390×844 viewport'ta render |
| Klavye navigasyonu | Aynı | Tab/Shift+Tab/ESC el testi |
| `depthReport.personality_type` üreticisi | LLM çıktısına bağlı; `extra="allow"` | Gerçek bir görev çalıştırıp `depth_report` payload'ını incele |
| Ayar modalının görsel kesilmesi | Mekanizma kanıtlandı, render görülmedi | Chromium'da modal açıp ekran görüntüsü |

---

## 7. Kanıt eki — hızlı referans

| Bulgu | Dosya | Satır |
|---|---|---|
| Auth middleware, allowlist yok | `backend/api.py` | 459–494 |
| Launch disabled ifadesi (ARM yok) | `frontend/src/components/UnifiedPinealCockpit.svelte` | 1077 |
| Launch etiketi | aynı | 1079 |
| "ARM kilidini açın" yardım metni | aynı | 1027 |
| Kasa "bilinmiyor" etiketi | aynı | 1202 |
| `p.slice(0,36)` | aynı | 1239, 1266 |
| `Güven: NN%` | aynı | 1664 |
| Pillar disclaimer | aynı | 1647 |
| Depth alan listesi | aynı | 320 |
| Depth render | aynı | 1680–1682 |
| Select "Tümü (kayıt etiketi)" | aynı | 1290 |
| Telemetri düğmesi (kokpit içi) | aynı | 1747 |
| `modal-close-btn` markup | aynı | 1817 |
| `GET /api/tasks` başlığı | aynı | 1833 |
| Modal kart / body CSS | aynı | 2660–2667, 2689 |
| `text-transform: uppercase` | aynı | 2694 |
| Telemetri toggle CSS | `frontend/src/App.svelte` | 483–491 |
| Telemetri panel CSS | aynı | 470–475 |
| `telemetryVisible` çelişkisi | aynı | 331, 333 |
| Yalan yorum ("sol üst") | aynı | 466 |
| Destek paneli CSS | `frontend/src/components/SupportPanel.svelte` | 131+ |
| `lang="tr"` | `frontend/index.html` | 2 |
| Font import | `frontend/src/app.css` | 1 |
| `DepthReport` modeli | `agent_core/agents/depth_analyst.py` | 35–50 |
| Rust sözleşmesi | `agent_core/services/runtime_status.py` | 9–17 |
| Rıza kapısı yok | `agent_core/capabilities/policy.py` | 9 |
| Telefon probe | `agent_core/capabilities/adapters_identity.py` | 118–190 |
| `conf = active/6` | `agent_core/engines/key_engine.py` | — |
| Güven semantiği etiketi | `agent_core/services/pillar_evidence_adapter.py` | 558 |
| Lomb-Scargle iddiası | `README.md` | 24, 95 |
| PDF opsiyonel | `requirements.txt` | 58 |
| Report factory gate | `agent_core/services/report_factory.py` | 50, 88–93 |
| Android CI job | `.github/workflows/ci.yml` | 276 |
| 18+ sözleşme testi | `frontend/src/__tests__/unified-cockpit.contract.test.ts` | 423–446 |
| 404 bileşen belgesi | `README.md` §4 (`AtlasPortal.svelte`) | — |

---

## 8. Sonuç

İnceleme raporu **yanlış bir tespit içermiyor.** Beş fonksiyonel iddia da doğrulandı, UI/UX iddialarının beşi kaynakta kanıtlandı, beş önerinin beşi de yerinde.

İki düzeltme gerekli:

1. **"ARM'ın etkisi yok"** tespiti kısmen doğruydu: ARM handler'da gerçek bir
   kapıydı, ama `disabled` ifadesinde olmadığı için etkisi görünmezdi. Uygulamada
   kapı kaldırıldı, ARM yalnız göstergeye indirildi; yardım metni de düzeltildi.
2. **"GET /APİ/TASKS"** bir yazım hatası değil, `lang="tr"` + `text-transform: uppercase` etkileşimi. Düzeltme CSS'te değil, metin stratejisinde.

Ve incelemenin **en zayıf noktası**, en kritik bulguyu kaçırmış olması: **401 yalnız görünür bir hata değil, kasa kilidini açılmaz kılan bir çıkmaz.** Token'sız kullanıcı yalnız veri göremez; **hiçbir yeteneği açamaz.** Bu, "ziyaretçiye örnek rapor göster" önerisinin neden bir pazarlama fikri değil bir **akış tasarımden** ibaret olduğunu gösteriyor.

En yüksek getirili üç adım — kod değişikliği sıralaması:

1. **2 satır CSS** (modal flex) → incelemenin görsel şikâyetinin büyük kısmı biter.
2. **1 allowlist + 2 statik rapor** → açılış 401'i ve "kasa bilinmiyor" zinciri biter.
3. **1 inline error state** → "düğme hiçbir şey yapmıyor" şikâyeti biter.

Üçü birlikte bir haftadan kısa sürer ve üçü de incelemenin ana gövdesini oluşturan şikâyetleri kapatır.

---

*Rapor salt-okunur analizle üretildi. Hiçbir dosya değiştirilmedi, hiçbir test/build/sunucu çalıştırılmadı.*


---

## 9. Uygulama özeti (P0)

Rapor yazıldıktan sonra aynı dalda P0 maddeleri koda uygulandı. Bu bölüm neyin
değiştiğini ve hangi doğrulamanın geçtiğini kaydeder.

### 9.1 Uygulananlar

| # | Değişiklik | Dosya |
|---|---|---|
| 1 | `auth_middleware`'e **dar public allowlist** (`GET`/`HEAD` yalnız, prefix yerine tam eşleşme + slug regex) | `backend/api.py` |
| 2 | **2 sentetik örnek rapor** + yasal uyarı ucu (`/api/public/demo-reports`, `/api/public/demo-reports/{id}`, `/api/public/notice`) | `backend/routes/public_demo.py` |
| 3 | Kasa göstergesi: 401 artık "kasa bilinmiyor" değil **"ERİŞİM: YETKİ GEREKLİ"**; tıklanınca token penceresi açılır | `frontend/src/lib/telemetry.ts`, `UnifiedPinealCockpit.svelte` |
| 4 | `.cockpit-modal-body { flex: 1 1 auto; min-height: 0; }` — modal alt kısmı artık scroll ediyor, kesilmiyor | `UnifiedPinealCockpit.svelte` |
| 5 | `GET /api/tasks` başlığı `<code class="endpoint-path">` + `text-transform: none` → `APİ` (noktalı İ) hatası giderildi | `UnifiedPinealCockpit.svelte` |
| 6 | **30+ eksik glif** (`✕ ▲ ▼ ✦ ◈ ⌖ ⟐ ◬ ⟡ ⯁ ◇ ◆ ✷ ◉ ↻ ⟳ ⬇ ⚠ ⛔ 🔑 📡 📱 🔥 ⚙ 🔒 📜 📄 ⏱`) satır içi SVG'ye çevrildi | `Icon.svelte` + 5 dosya |
| 7 | **`.modal-close-btn`**'e stil + `aria-label` eklendi (daha önce hiç stili yoktu) | `UnifiedPinealCockpit.svelte` |
| 8 | **Inline başlatma hatası** (`launchNotice`, `role="alert"`) — hatalar artık sohbete değil düğmenin altına düşüyor | `UnifiedPinealCockpit.svelte` |
| 9 | **ARM zorunluluğu kaldırıldı** (handler'daki `$armEngaged` kapısı silindi, düğme göstergeye indirildi, yardım metni düzeltildi) | `UnifiedPinealCockpit.svelte` |
| 10 | **"Derinlik" sütunu** `reality_index` / `essence_one_liner` / `reality_findings` / `contradictions` alanlarına bağlandı (önce modelde olmayan `personality_type`/`mask_score` aranıyordu) | `UnifiedPinealCockpit.svelte` |
| 11 | **`consent` kapısı** eklendi (fail-closed: beyan yoksa ret) + `PolicyState.subject_consent`; telefon yoklaması artık açık rıza beyanı istiyor | `policy.py`, `state.py`, `adapters_identity.py`, `commander.py`, `brain_hub.py` |
| 12 | **Yasal metin modülü** (`DISCLAIMER_TR`, `CONSENT_DECLARATION_TR`, `USAGE_TERMS_TR`) + arayüzde "KULLANIM KOŞULLARI" penceresi ve uyarı satırı | `agent_core/legal/`, `UnifiedPinealCockpit.svelte` |
| 13 | Arayüzde telefon için **"AÇIK RIZA ALINDI"** onay kutusu (işaretlenmeden istek gönderilmiyor) | `UnifiedPinealCockpit.svelte` |
| 14 | **Font fallback zinciri** genişletildi (JetBrains → platform monospace → sembol fontları) | `frontend/src/app.css` |

### 9.2 Doğrulama

| Kontrol | Sonuç |
|---|---|
| `npm run check` | **0 hata, 0 uyarı** |
| `npm test` | **24/24 geçti** |
| `npm run build` | **Başarılı** (135 modül) |
| `pytest` (tam suite) | **3298 passed, 6 skipped, 2 xfailed, 0 failed** |
| Yeni test | `tests/unit/test_public_showcase.py` — **14 test** (public uçlar, 401 korunumu, yalnız-GET, path traversal, slug güvenliği) |
| Güncellenen testler | `test_capability_spine_faz0.py` (eski "rıza kapısı yoktur" doktrini → yeni fail-closed sözleşme), `test_phone_probe_security.py` (423 `CONSENT_REQUIRED`) |

### 9.3 Bilinçli olarak dışarıda bırakılanlar

- **`Güven: NN%` etiketi** (P1.1): kapsam oranı olduğu hâlâ "%" olarak gösteriliyor. Aynı dosyada, tek satırlık bir iş — ama P0 kapsamında değildi; **P1'de yapılmalı**.
- **Repo diyeti** (`rust_core`/`android` ayrıştırma, 97 dal temizliği): P2.
- **Canlı görsel doğrulama**: sandbox'ta Chromium yok; modal kesmesinin giderildiği CSS düzeyinde kanıtlı, tarayıcıda doğrulanmadı.

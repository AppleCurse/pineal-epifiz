# INTEGRATION PLAN — OSINT/Stealth/AI Araç Listesi Uzlaşması

**Tarih:** 2026-08-29 · **Kapsam:** Kullanıcının ilettiği "doğrudan entegre edilecek araçlar" listesinin bağımsız kanıt denetimi + uygulama sırası
**Yöntem:** Her araç için (1) varlık/lisans/bakım durumu doğrulandı, (2) pineal-clean mimarisiyle (Playwright tek browser stack, exact-key cache sözleşmesi, "hiçbir platforma otomatik işlem yapılmaz" ilkesi, dürüst-sonuç modeli) oturma analizi yapıldı.

---

## 1. Liste denetimi — düzeltilen iddialar

| Liste iddiası | Kanıt sonucu | Hüküm |
|---|---|---|
| Blackbird "socid-extractor ile aynı ekosistemde" | Blackbird = p1ngul1n0 (WhatsMyName tabanı); socid-extractor = soxoj. **Farklı ekosistemler** | DÜZELTİLDİ |
| Snoop "5300+ site, aktif geliştirme" | Gerçek; ancak lisans **demo/full ayrımlı özel lisans** (full DB bağış karşılığı — repo issue #37). Ürün koduna gömme için lisans incelemesi şart | KOŞULLU |
| GHunt "Email girdisi alır → ayak izi çıkarır" | Gizlenen ön koşul: **operatörün kendi Google oturum cookie/OAuth'u** (GHunt Companion). Hassas kimlik bilgisinin vault'a girmesi gerekir | KOŞULLU (ön koşul belgelendi) |
| GPTCache "SOTA semantic caching" | Proje bakım modunda (v0.1.42 sonrası düşük aktivite, topluluk fork'u öne çıktı). Ayrıca pineal'ın cache'i **bilinçli exact-key** (model+sıcaklık dahil); anlamsal önbellek "benzer soru → başka yanıt" karışması üretebilir = halüsinasyon sözleşmesiyle gerilim | RED (şimdilik) |
| undetected-chromedriver "Hemen entegre" | **Selenium/CDP tabanlı**; pineal tamamen Playwright mimarisinde. İkinci browser stack = bakım yükü ×2. Stealth ihtiyacı için Playwright-native çözümler var | RED (mimari) |
| Stagehand/browser-use "PatternInterrupt ve ShadowExecutor'a browser kontrolü" | İkisi de **eylem üreten** ajanlar. README §9: *"sistem hiçbir platforma otomatik/gizli mesaj göndermez"*. Browser-otomasyon ajanı web'de TIKLAR/FORM DOLDURUR → çekirdek ürün vaadiyle **doğrudan çelişir** | RED (etik sözleşme) |
| CloakBrowser / invisible_playwright | İkisi de gerçek ve Playwright-native: CloakBrowser MIT Chromium fork; invisible_playwright MIT Firefox (238MB indirme, platform kısıtlı) | KABUL (env kapılı, ileri faz) |

## 2. Uzlaşılmış entegrasyon sırası

| Faz | Araç | Gerekçe |
|---|---|---|
| **FAZ 1 (bu commit — uygulandı)** | `socid-extractor` (MIT, hafif, tarayıcı gerektirmez) | Profil URL'sinden kararlı kimlik kaydı; `is_safe_url` SSRF guard'ı arkasında; kütüphane yoksa **dürüst `available:false`**. Kanıt zinciri sözleşmesine birebir oturur |
| FAZ 2 | `Maigret` (MIT) — username taraması | socid-extractor'ın doğal üst katmanı (aynı yazar); `osint_footprint`'i genişletir; env kapılı + timeout |
| FAZ 3 | `blackbird` çekirdeği (yalnız tarama, `--ai` DIŞI) + `holehe` | Email pivotu; **yalnız `/api/experimental/*`** (hassas veri sınıfı) |
| FAZ 4 | `Crawl4AI` (Apache-2.0) | Public-web araştırma sonuçlarını LLM-dostu metne çevirir; quote_guard kaynak kalitesi artar |
| FAZ 5 | `invisible_playwright` / `CloakBrowser` | `STEALTH_PROVIDER=playwright_stealth\|invisible\|cloak` env seçimi; default mevcut davranış; ağır binary indirmeleri opsiyonelde |
| FAZ 6 (koşullu) | `GHunt` + `GitFive` | Yalnız deneysel uç + operatör-kimliği ön koşulları UI'da açıkça belgelenerek |
| İZLEMEDE | Obscura, Stagehand (yalnız extract-okuma modu) | Genç projeler; etik sözleşme gözden geçirilmeden eylem yeteneği eklenmez |

## 3. FAZ 1 uygulaması (bu commit)

- `agent_core/services/socid_enricher.py` — URL/HTML → yapılandırılmış kimlik kaydı; SSRF guard'lı; ImportError/ağ/parse hatalarında dürüst `available:false`
- `POST /api/experimental/socid/extract` — kullanıcı bir profil URL'si yapıştırır, yapılandırılmış kayıt alır
- `_run_public_web_research` zenginleştirmesi — eşleşen arama sonuçlarına (ilk 3) `socid` alanı eklenir (yalnız kayıt bulunduğunda)
- Testler: `tests/unit/test_socid_enricher.py`


---

## 4. FAZ 2 uygulaması (bu commit) — Maigret

- `agent_core/services/maigret_scanner.py`: kullanıcı-adı varlık taraması.
  Kapı `ENABLE_MAIGRET` (default kapalı); `MAIGRET_SITES_LIMIT` (100,
  max 500), `MAIGRET_TIMEOUT` (15s/site), `MAIGRET_TOTAL_TIMEOUT` (45s).
  DB: paket içi maigret DB (3302 site), `ranked_sites_dict(top=N)`.
- `POST /api/experimental/maigret/scan` — deneysel uç (kullanıcı adı
  `^[A-Za-z0-9._-]{1,64}$` doğrulamalı).
- `OsintInvestigatorAgent._apply_username_scan`: yalnız anahtar-yok fallback
  yolunda; kapalıyken profil alanları DEĞİŞMEZ (yalnız provenance alanı);
  bulunan gerçek siteler `associated_platforms`'a girer, güven = gözlenen
  kapsama (found/scanned); güvenilir yokluk yalnız sıfır-hata koşulunda
  iddia edilir.
- requirements: `maigret>=0.6.5` (MIT).

### ADLİ BULGU (kendi entegrasyonumuzda yakalanan halüsinasyon riski)

Maigret 0.6.5'te ağ hatası durumlarında `SiteResult.status = None` dönebiliyor
(checker future'ı istisna ile ölüyor; ilk ham testte `<Unknown (Connecting
failure)>` görünürken ikinci koşuda None). İlk sınıflandırmamız None'ı "hata
değil" sayıyordu → **hiç kontrol yapılmadan 'iz yok' iddia edilebilirdi.**
Düzeltme: `status in (UNKNOWN, None)` → error_count. Canlı doğrulama:
21 site / 21 hata → `available:false, reason:provider_errors` (uydurma yok).
Regresyon testi: `test_none_status_is_error_not_absence`.

### Doğrulama (kanıt)

- ruff PASS; pytest **375/375 PASS** (360+15 yeni)
- Gerçek kütüphane koşusu (top 10 → 21 site): `provider_errors`, dürüst
- Uç: `invalid_username` / `disabled` / `provider_errors` canlı doğrulandı
- Pipeline değişmedi: WS görevi aynı davranış (halted_evidence, planned=[mirror_truth])


---

## 5. FAZ 3 uygulaması (bu commit) — Holehe; Blackbird RED

### 5.1 Holehe (uygulandı)

- `agent_core/services/holehe_scanner.py`: e-posta kayıt taraması.
  Kapı `ENABLE_HOLEHE` (default kapalı); `HOLEHE_MODULES_LIMIT` (100,
  max 300; deterministik isim-sıralı ilk N), `HOLEHE_TIMEOUT` (10s),
  `HOLEHE_TOTAL_TIMEOUT` (120s), `HOLEHE_CONCURRENCY` (20).
- `POST /api/experimental/holehe/scan` — deneysel uç (e-posta doğrulamalı).
- `OsintInvestigatorAgent._apply_email_scan`: yalnız anahtar-yok fallback
  yolunda, profil `connected_emails` doluysa; kapalıyken profil alanları
  DEĞİŞMEZ (yalnız `email_scan` provenance'ı); güven = gözlenen kapsama ve
  mevcut güvenin altına inmez (başka kaynağın kanıtını ezmez).
- requirements: `holehe>=1.61` — **GPL-3.0**: kod repo'ya gömülMEDİ; pip
  bağımlılığı olarak, varsayılan kapalı deneysel uçla kullanılır.

### ADLİ BULGU (holehe 1.61 kaynak okuması + canlı doğrulama)

`holehe.core.launch_module` modül içi HER istisnayı yakalayıp
`rateLimit=True, exists=False` yazıyor. Kapalı ağda tüm modüller "kayıtlı
değil" gibi görünür (FAZ 2'deki maigret status=None tuzağının eşdeğeri).
Kural: rateLimit=True / hükmü olmayan / tanınmayan kayıt = HATA; temiz
yokluk yalnız sıfır-hata koşulunda iddia edilir. Canlı: 6 gerçek modül /
6 hata → `provider_errors` (uydurma yok). Regresyon: `TestForensicClassification`.

### Doğrulama (kanıt)

- ruff PASS; pytest **400/400 PASS** (375+25 yeni)
- Canlı uç: `provider_errors` (6/6 hata) ve `invalid_email` — dürüst
- Pipeline değişmedi: default kapalı (TestClient + canlı mevcut uçlar 200)

### 5.2 Blackbird — BELGELENMİŞ RED (kanıt listesi)

1. **PyPI isim çakışması:** `pip install blackbird` → 2014 tarihli
   "ZABBIX-SENDER middleware daemon'ı" (yazar: ARASHI, Jumpei,
   github.com/Vagrants/blackbird, WTFPL, Python 2.6/2.7). p1ngul1n0'un
   OSINT aracıyla ilgisiz; yanlış paket entegrasyonu sahte olurdu.
2. **Paketleme yok:** p1ngul1n0/blackbird PyPI'da yayımlanmıyor; repo kökü
   `blackbird.py` + `src/` düzeninde, pyproject/setup yok (CLI uygulaması,
   kütüphane API'si değil).
3. **Lisans:** repo lisansı **CC BY-NC-SA 4.0** (`.github/LICENSE`,
   `docs/LICENSE`) — NonCommercial + ShareAlike. OSINT pipeline'a gömme/
   damıtma için red; holehe (GPL-3, kod gömmeden bağımlılık) ile bile
   kıyaslandığında en kısıtlayıcı.
4. **`--ai` özelliği:** site adlarını dış AI servisine yollar — zaten
   kapsam dışıydı; çekirdek de yukarıdaki nedenlerle entegre edilmedi.

Alternatif (FAZ 6 koşullu): blackbird'ün alt kaynağı WhatsMyName (WHNS)
veri setinin kendi lisansı ayrıca incelenerek çekirdek tarayıcı doğrudan
değerlendirilebilir. Karar: red, kanıtlarıyla belgeli.


---

## 6. FAZ 4 uygulaması (bu commit) — Crawl4AI

- `agent_core/services/crawl_enricher.py`: public-web sayfa → LLM-dostu
  metin. Kapı `ENABLE_CRAWL4AI` (default kapalı); HTML `safe_get` ile DNS
  pinlenerek indirilir, Crawl4AI yalnız yerel Markdown parser olarak çalışır.
  `CRAWL4AI_RENDERER=browser` (Playwright/JS) ağ adresi sabitlenebilir olana
  dek fail-closed kapalıdır. `CRAWL4AI_MAX_CHARS` (8000, max 50000),
  `CRAWL4AI_TIMEOUT` (20s), `CRAWL4AI_RESEARCH_LIMIT` (2, max 5).
- `POST /api/experimental/crawl/fetch` — deneysel uç.
- `_run_public_web_research` zenginleştirmesi: kapı açıkken eşleşen ilk
  N sonuç `fetch_readable` ile çekilir; **yalnız available=True** sonuçlara
  `crawl` alanı eklenir; hata alan EKLEMEZ (socid deseniyle aynı dürüst boş).
- `quote_guard.guard_report` korpus genişlemesi: `input_data.public_web_sources`
  (yalnız dict + boş olmayan `text`) gerçek çekilmiş sayfa metni olarak
  korpusa girer; alan yoksa korpus BİREBİR aynı (anti-halüsinasyon davranışı
  değişmez; gerçek public-web alıntıları artık doğrulanabilir).
- requirements: `crawl4ai>=0.9.2` (Apache-2.0, PyPI metadata doğrulandı).

### PSUTIL ÇATIŞMA ADJUDİKASYONU (kanıtla çözüldü)

pip çatışması: crawl4ai `psutil>=6.1.1` BEYAN eder; open-interpreter
`psutil<6.0.0` ister. Kaynak okuması: crawl4ai yalnız `Process()` +
`process_iter()` kullanıyor (async_dispatcher.py, browser_manager.py,
utils.py); open-interpreter yalnız `virtual_memory()` + `disk_usage()`.
Çalışma zamanı kanıtı (psutil 5.9.8): her iki paketin gerçek çağrıları da
sorunsuz. Karar: `psutil>=5.9.6,<6.0.0` pini (open-interpreter beyanına
saygı; crawl4ai kullanımı 5.9.8'de doğrulandı, import + API testleri PASS).

### Doğrulama (kanıt)

- ruff PASS; pytest **419/419 PASS** (400+19 yeni)
- Canlı (ağ kapalı sandbox): gerçek http çekim → `fetch_error` + gerçek
  hata notu ("Cannot connect to host") — içerik UYDURULMADI; ssrf_blocked
  (169.254.169.254) ve invalid_url canlı doğrulandı
- FAZ1-3 regresyon uçları 200 + dürüst provider_errors (21/21 maigret,
  6/6 holehe); pipeline default kapalı → davranış değişmedi
- Not: `_run_public_web_research` FAZ 1'den beri backend/api.py:814'te
  mevcut (ilk grep yalnız agent_core/ taramıştı — çelişki değil, kapsam hatası)


---

## 7. FAZ 5 uygulaması (bu commit) — STEALTH_PROVIDER seçici

- `agent_core/services/stealth_provider.py`: `STEALTH_PROVIDER=
  playwright_stealth|invisible|cloak|none` çözümleyici.
  **Default (env yok) = playwright_stealth — MEVCUT davranış birebir**
  (scrape_instagram bugün de try-import + apply_stealth_async yapıyordu).
- Geçersiz değer asla sessiz değişmez: default'a döner +
  `reason="invalid_provider:<ham>"`. Kullanılamayan seçim: `available=False`
  + makine-okunur sebep (library_missing / binary_missing); tarama
  stealthsiz sürer ve sebep loglanır (sahte gizlilik iddiası yok).
- **Ağır binary indirmeleri opsiyonel:** runtime request yolunda indirme
  ASLA tetiklenmez. invisible yalnız `INVISIBLE_BROWSER_BINARY` dosyası
  mevcutsa available (launcher `binary_path=` ile indirmeyi atlar — kaynak
  okumasıyla doğrulandı); cloak yalnız `CLOAK_BROWSER_EXECUTABLE` ile.
- invisible LAUNCH-level'dır (patched Firefox + kendi async_playwright'ı);
  registry başlatımı `p.firefox`'a geçer; page-bazlı apply ona dürüstçe
  `launch_level_provider` der. cloak: `executable_path=` drop-in.
- `platform_registry.scrape_instagram`: seçim + INFO/WARNING telemetri;
  apply başarısızlığı artık taramayı düşürmez, dürüst loglanır (önceki
  davranışta apply istisnası tüm kazımayı düşürüyordu — belgeli düzeltme).
- `GET /api/experimental/stealth` — salt-okunur seçim/kullanılabilirlik
  görünümü (başlatma yapmaz, indirme tetiklemez; `?provider=` ile sorgu).
- requirements: `invisible-playwright>=0.7.4` (MIT, pip metadata doğrulandı;
  pip paketi hafif, binary YOK).

### Kanıtlar

- invisible-playwright 0.7.4: "Playwright wrapper for a patched Firefox"
  (MIT AND Apache-2.0, pip metadata); `resolve_executable(binary_path=)`
  indirme yolunu tamamen atlar (kaynak).
- playwright-stealth kurulu ve `Stealth().apply_stealth_async(page)` gerçek
  init-script enjeksiyonu sahte page ile doğrulandı (test).
- ruff PASS; pytest **434/434 PASS** (419+15 yeni)
- Canlı: default→available; invisible/cloak→binary_missing; bogus→
  invalid_provider; FAZ1-4 uçları regresyonsuz (maigret/holehe/crawl
  dürüst hatalar, root 200)
- Sınır (dürüst): chromium/patched-Firefox/cloak binary'leri bu sandbox'ta
  YOK (CDN kısıtı; indirme denendiğinde başarısız — standing). Bu yüzden
  gerçek launch-yolu testleri enjekte edilmiş fake playwright ile doğrulandı;
  binary'li doğrulama deploy ortamına bırakıldı.


---

## 8. FAZ 1-5 sağlamlaştırma (bu commit)

Adli self-review iki gerçek kusur yakaladı; her ikisi düzeltildi + regresyon
testiyle kilitlendi:

1. **holehe client yarışı (FAZ 3 kusuru):** `_run_library_scan` istemciyi
   `_runner` içinde yaratıyordu; concurrency>=2'de iki görev aynı anda
   `client is None` görüp ayrı `httpx.AsyncClient` yaratabiliyor — biri
   asla kapatılmıyordu (sızıntı). Düzeltme: tek istemci gather'dan ÖNCE
   yaratılır. Regresyon: `TestHoleheSingleClient` (CountingClient, 4
   eşzamanlı modül → tam 1 istemci).
2. **maigret DB singleton yarışı (FAZ 2 kusuru):** eşzamanlı
   `scan_username` çağrıları 3302 sitelik DB'yi aynı anda iki kez
   yükleyebiliyordu (determinizm yok). Düzeltme: kilitli singleton
   (`_get_site_dict`, `threading.Lock`). Regresyon:
   `TestMaigretSingletonLock` (3 eşzamanlı tarama → tek yükleme).

Yüzey sözleşmesi (`test_consolidation_faz1_5.py`):
- Default pozür tek testte kilitli: maigret/holehe/crawl uçları `disabled`
  + provider üçlüsü birebir; stealth seçici görünümü.
- Beyan→kurulu zinciri: 6 OSINT bağımlılığı (socid_extractor, maigret,
  holehe, crawl4ai, playwright_stealth, invisible_playwright) import
  edilebilir — "requirements'ta var" ile "env'de kurulu" ayrımı kapanır.
- env adları denetimi: 17/17 değişken kod ve plan belgesinde tutarlı.

### Doğrulama (kanıt)

- ruff PASS; pytest **443/443 PASS** (434+9 sağlamlaştırma)
- HEPSİ-AÇIK pozür (yeni iç yollarla canlı): maigret 21/21 provider_errors,
  holehe 6/6 provider_errors, crawl fetch_error — dürüst, uydurma yok
- DEFAULT pozür (kanonik): üç deneysel uç `disabled`; WS pipeline birebir
  aynı (halted_evidence, planned=[mirror_truth]); root/socid 200


---

## 9. Araç-liste denetimi #2 — "Yeraltı/nadir OSINT araçları" (bu commit)

Kullanıcı listesi kanıt sayılmaz: 5 iddia GitHub API + repo/PyPI kaynak
okumasıyla doğrulandı (ölçüm tarihi: 2026-08-29). Mesajlar README çevirisi
olduğu için önceki denetime kıyasla uydurma oranı düşük; yine de üç kayda
değer bulgu var (aşağıda).

| # | Liste adı | Gerçek repo (çözümlenen) | Ölçülen (GitHub API) | İddia hükmü | Pipeline hükmü |
|---|---|---|---|---|---|
| 1 | OpenOSINT "1,5k, 19 araç, MIT, MCP" | OpenOSINT/OpenOSINT | **1490★, MIT, Python**, push 26 Ağu 2026 (aktif), repo **Mayıs 2026'da yaratılmış** (4 aylık) | 19 araç ✓ — projenin KENDİ commit'i sayı kaymasını (16/18/19) koddan türetilen sayı + docs-consistency testiyle düzeltmiş; MCP ✓; MIT ✓; "halüsinasyon yapısal olarak imkânsız" = vendor pazarlaması (araç çıktıları gerçek binary'lerden; rapor/özet katmanı hâlâ LLM üretimi); **ÇELİŞKİ:** "web UI üçüncü taraftan tamamen arındırılmış" — Bright Data SERP/Web Unlocker (ticari) + IP2Location sponsor entegrasyonları mevcut | FAZ 2/3 ile işlevsel çakışma (holehe/sherlock/maigret wrapper'ı); LLM+API-key gerektiren AGENT wrapper → **gömme YOK; izlemede** |
| 2 | "arayıcı" 861 | **seekr-osint/seekr** | **861★ birebir, GPL-3.0**, Go, push 16 Haz 2026 (created 2022-12) | Listenin her maddesi README'nin birebir çevirisi: no-API-keys ✓, Go+BadgerDB ✓, desktop+web ✓, GitHub-to-email ✓, Guide ✓, hesap kartları ✓, tema/eklenti ✓ | Uygulama (kütüphane değil) + **GPL-3.0** → gömme yok; kişi-hedef DB/kart konsepti ürün ilhamı olabilir. **İzlemede** |
| 3 | "kullanıcı tarayıcı" 3.4k | **kaifcodec/user-scanner** | **3433★, MIT, Python**, push 28 Ağu (dün), created Eki 2025 | 455+ vektör (175+/280+) ✓ birebir; 2-in-1 ✓; ayrıca MCP server + cross-scan pivot + metadata scraping | FAZ 2/3 ile TAM çakışma ama **tek entegrasyon adayı**: MIT+Python, ek değer = metadata+pivot. Şart: yerinde dürüstlük-davranış denetimi (holehe tipi rateLimit maskesi taraması) — karar kullanıcıya ait |
| 4 | xurlfind3r 719 | **hueristiq/xurlfind3r** | **719★ birebir, MIT**, Go, push 23 Şub 2026 | Pasif-only ✓ (repo açıklaması birebir) | Domain-URL keşfi (bug bounty recon) — kişi-odaklı pipeline'da karşılığı yok. **Uygulanamaz/izlemede** |
| 5 | "korku veren-osint-arsenal" 2.6k | **rawfilejson/awesome-osint-arsenal** | **2643★, MIT, Shell**, push 29 Ağu (bugün), created Nis 2026, 34 commit | 100+ araç / tek komut / SOCMINT-GEOINT-ağ-darkweb-adli ✓ birebir (install.sh, osint.sh, forensics.sh, tools.json) | Kali hedefli **installer script koleksiyonu** — pipeline'a gömülemez kategori (seçkili requirements zaten mevcut). Kaynak-liste değeri var |

### Denetim bulguları (kontrast önceki listeyle)

1. Bu listede önceki gibi tamamen uydurma araç YOK — 5/5 gerçek; Türkçe
   adlar ("arayıcı", "kullanıcı tarayıcı", "korku veren") orijinal adların
   (seekr, user-scanner, awesome-osint-arsenal) makine çevirisi.
2. Yıldız sayıları 5/5 doğru ölçüldü (1490→"1,5k", 861, 3433→"3,4k",
   719 birebir, 2643→"2,6k").
3. CONTRADICTION: OpenOSINT "üçüncü taraf isteklerinden tamamen arındırılmış"
   iddiası ticari Bright Data + sponsor API entegrasyonlarıyla çelişiyor;
   "halüsinasyon imkânsız" iddiası güçlendirilmiş pazarlama (araç katmanı
   gerçek; rapor katmanı LLM). İlginç paralellik: sayı kaymasını koddan
   türetilmiş sayı + regresyon testiyle kapatmaları bizim docs-consistency
   yaklaşımımızın aynısı.
4. Yaş riski: #1 (4 aylık), #3 (10 aylık), #5 (5 aylık) hypergrowth tek-ön
   repo'lar; #2 (2022) ve #4 (2021) oturmuş projeler.

**Entegrasyon kararı bilinçli olarak AÇIKTA:** yalnız #3 (user-scanner)
koşullu aday; yerinde doğrulama protokolü (kur → introspeksiyon → dürüstlük
davranış testi → FAZ2/3 kapıları arkasında alternatif sağlayıcı) kullanıcı
onayıyla başlar. #1/#2 gömme-red (çakışma/licence), #4/#5 kategori-dışı.


---

## 10. Rapor denetimi #3 — "Kapsamlı Araç Analiz Raporu"nun çapraz denetimi (bu commit)

Dışarıdan sunulan ~90 araçlık rapor standing kurala tabi tutuldu (önceki ajan
raporu = kanıt değil). Kaynak dosya (`Bugün Verdiğin Depolar.txt`)
workspace'te YOK → raporun kapsamı/yeniden üretilebilirliği DOĞRULANAMAZ;
yalnız yapıştırılan iddialar denetlendi. Örnekleme sonucu: **7 somut hata**
(2'si entegrasyon önerisini geçersiz kılan lisans/adres hatası, 1'i haksız
"uydurma" suçlaması).

### Rapor iddiası → kanıtlı hüküm

| Rapor iddiası | Kanıtlı hüküm (GitHub API/kaynak, 2026-08-29) |
|---|---|
| DaProfiler = `aboul3la/DaProfiler`, ~200★ | **YANLIŞ adres** (aboul3la=Sublist3r yazarı). Gerçek: `daprofiler/DaProfiler` — **1041★, GPL-3.0, ARCHIVED** (GitHub read-only; son push Eyl 2023). "Week 3-4 DaProfiler ekle" önerisi → **VETO** |
| undetected-chromedriver "MIT, Aktif, ✅ FALLBACK eklenmeli" | **Lisans GPL-3.0** (MIT değil); **Selenium tabanlı** (Playwright stack'iyle uyumsuz — rapor aynı gerekçeyle Zendriver'ı reddetmiş, çifte standart); 12.8k★ ama son push Tem 2025. Öneri → **VETO** (gömme = GPL + paralel stack; FAZ 5 seçici zaten mevcut) |
| OSINT-D2 "GitHub'da yok, UYDURMA" | **YANLIŞ — repo VAR:** `Doble-2/osint-d2` (265★, MIT, Python, Oca 2026, push Haz 2026; agentic + 6-boyut profilleme açıklaması raporunkinin aynısı). Ama küçük/genç + harici LLM (DeepSeek default) + ScrapingAnt ticari proxy → **izlemede** |
| OWASP/Social-OSINT-Agent "Aktif" | **Adres YANLIŞ (API 404)**; proje gerçek: `bm-github/owasp-social-osint-agent` + OWASP Incubator sayfası (MIT; X/Reddit/GitHub/Bluesky/HN/Mastodon + OpenAI-uyumlu LLM). → **izlemede** (dış-LLM bağımlı wrapper) |
| browser-use "79k★" | **BAYAT: 111.658★** ölçüldü (MIT, bugün push). Sonuç (şimdilik red) yine de makul |
| ScrapeGraphAI = `ScrapGraphAI/scrapgraphai` ~2k | **Adres formu YANLIŞ** (tire eksik). Gerçek: `ScrapeGraphAI/Scrapegraph-ai` (MIT). Yıldız ölçülmedi — "~2k" güvenilmez |
| CloakBrowser "wrapper... Stealth Provider'a eklendi (Chrome)" | Fork (wrapper değil); "eklendi" aşırı: FAZ 5'te kapı+kural var (`CLOAK_BROWSER_EXECUTABLE`), binary yoksa dürüst `binary_missing` — çalışan entegrasyon DEĞİL |
| "Dolphin-2.9 zaten varsayılan" | **DOĞRULANDI:** `llm_gateway.py:61` default `dolphin-llama3:latest` (nüans: `USE_LOCAL_LLM` default false) |
| World Monitor 59.2k / SL Crime Wall "UYDURMA" | Benim aramam YOK — raporun red hükmü de kanıtsız. Red kararı eylem olarak benimsenir, hüküm kanıtsız kalır |
| "~90 araç, 81 doğrulanmış, 32 uygun" | Kaynak dosya olmadığından **yeniden üretilemez** |
| FAZ 1-5 tablosu, OpenOSINT/seekr/user-scanner/xurlfind3r/arsenal satırları, Blackbird/Snoop/Kaz→Goose/Agent-Reach/GPTCache/Obscura hükümleri | Önceki bağımsız denetimlerimle **tutarlı** (bu kısımlar doğru) |

### Sonuç ve düzeltilmiş strateji

Raporun "kanıta dayalı/eksiksiz" öz-iddiası örneklenen iddiaların ~yarısında
çöktü — kullanım şekli: fikir kaynağı EVET, yetki kaynağı HAYIR.

1. Tek koşullu entegrasyon adayı DEĞİŞMEDİ: **user-scanner** (MIT/Python/
   3433★) — yerinde dürüstlük-davranış denetimi (holehe-tipi rateLimit
   maskesi testi) sonrası FAZ 2/3 alternatif sağlayıcı olabilir.
2. Rapordaki "Hafta 1-2 uc-fallback" ve "Week 3-4 DaProfiler" önerileri
   kanıtla VETO edildi (GPL-3.0 lisans / archived repo).
3. GHunt/GitFive "deneysel eklenebilir" ifadesi eksik: operatör-cookie ön
   koşulu UI'da belgelenmeden eklenmez (FAZ 6 koşulu aynen duruyor).
4. Watchlist'e yeni eklendi: OSINT-D2, OWASP SocialOSINTAgent,
   ScrapeGraphAI (crawl4ai zaten mevcut; LLM-pipeline bağımlılığı).


---

## 11. Sahte-veri/ölü-kod tam temizliği (bu commit)

Talep: "tek satır sahte veri / mock / işe yaramaz harf kalmasın." Yöntem ve
sonuç (tüm dosya ağacı: agent_core, backend, scripts/, rust_core, android
main, frontend src, live_llm_gate.py):

### Sweep sonuçları (kanıt)

- **Mock/fake KULLANIMI production'da: SIFIR.** AST-bazlı tarayıcı
  (yorumlar algılayamaz): mock import'u ya da Mock/AsyncMock/MagicMock
  çağrısı yok. Literal sweep (alper/johndoe/test@/fakeUser/mockData vb.)
  Python+Kotlin+Svelte+Rust+Shell'de boş. 37+8 eşleşmenin TAMAMI
  anti-uydurma yorumları ("sahte ... ÜRETİLMEZ" yasaklarını belgeleyen).
- Hardcoded API-key kalıbı: yok. TODO/FIXME/XXX/HACK (py): 0.
- Assert'siz test dosyası: 0. (zaten ölü) agent_core/p2p + db/reflection.sql
  git geçmişinde yok — koruma testi geri dönüşü kilitler.

### Silinen ölü kod (her biri: vulture işareti + tam-repo sıfır-referans kanıtı)

- `interpreter_agent.CodeExecutionChunk` (kullanılmayan pydantic model)
- `pattern_interrupt._extract_cultural_reference` (çağrılmayan yardımcı)
- `pipeline_status.is_success/is_halted` (çağrılmayan metotlar; is_*
  eşleşmeleri rust_core'a aittir — reqwest/struct, ilgisiz)
- `canonical_memory.ProfileMemory` (kullanılmayan model)
- `hindsight_memory.get_task_history/delete_task_semantic` (çağrılmayan API)
- `seismos_engine.burst_factor/style_z_threshold` parametreleri (hiçbir
  çağırıcı geçmiyor; hiçbir atanma yok)
- `human_behavior` erişilemez ikinci try-blok (ilk try her yoldan dönüyor)
- `backend/api` kullanılmayan `scrape_readonly` import'u
- Korunanlar (vulture yanlış-pozitifleri): pydantic field_validator'lar
  (url_must_be_real/posts_must_be_real dekoratörle bağlı), FastAPI
  dekoratörlü uç fonksiyonları, test-kapsamlı metotlar (get_stats vb.)

### Ders (dürüst kayıt): kapsam kusuru ve geri alma

`build_user_context` ilk referans taramamda 0 çıktı çünkü grep kapsamım
scripts/'i KAPSAMIYORDU; silince CLI entegrasyon testleri ImportError verdi
(kanıt: test_run_task_cli). GERİ YÜKLENDİ. Ders: sıfır-referans hükmü tüm
ağaç (scripts/, rust_core/, android/, frontend/) ile verilir.

### requirements: psutil adjudikasyonu düzeltildi (kendi FAZ 4 kusurum)

`psutil>=5.9.6,<6.0.0` pini + crawl4ai `>=6.1.1` beyanı TAZE kurulumda
ResolutionImpossible üretiyordu (tek işlem sözleşmesi bozuktu). Çözüm:
requirements.txt tek-işlemde kurulur (crawl4ai'siz); crawl4ai ikinci adımda
`requirements-osint.txt` ile gelir. Çalışma-zamanı kanıtı (psutil 7.2.2):
open-interpreter import + virtual_memory/disk_usage OK; crawl4ai +
async_dispatcher OK. Kalıcı test: TestPsutilAdjudicationRuntime.

### Yeni koruma: tests/unit/test_no_mock_in_production.py

- Production Python'da mock import/çağrısı = FAIL (AST; yorumlar etkisiz)
- Dedektör canlılık kanıtı: tests/'te en az 1 mock bulmalı (sahte-geçer
  koruma testi imkânsız)
- frontend/android sahte-veri kalıbı taraması; ölü dosyaların geri dönüş
  yasağı; psutil iki-adım çalışma-zamanı sözleşmesi (7 test)

### Doğrulama

- ruff PASS; pytest **450/450 PASS** (443+7 koruma)
- Kanonik smoke (taze venv, silinmiş ölü kodla): 3 deneysel uç disabled +
  stealth görünümü + root 200 + WS pipeline birebir (halted_evidence/
  [mirror_truth])

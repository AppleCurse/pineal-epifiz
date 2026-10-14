# Kapasite ve Kullanım Açığı Raporu — 2026-10-14

**Kapsam:** Bu depo (`pineal-epifiz`), HEAD `7096954` + bu turdaki B1/B2 düzeltmesi.
**Yöntem:** Her sayı gerçek kod okuması ve gerçek çalıştırmadır; elle yazılmış
hiçbir sayı yoktur. Kanıt dosyası `reports/kapasite_denetimi.json`, üretici
`scripts/kapasite_denetimi_probe.py` (yeni; 12 adım, hepsi `OK`).
**Sorulan 4 soru:** §4.1 (kapalı bayraklar nerede OKUNUYOR), §5.2 (stealth
sağlayıcıları), §4.2 (anahtar bekleyen yetenekler), §6.2 (router ↔ omurga bağı).
**Aranan 5 denetim alanı:** §3.1 kapalı yetenekler · §3.2 kullanılmayan
yetenekler · §4.3 kullanılmayan erişimler · §5 sağlayıcı/erişim envanteri ·
§7 "kullanım hakkı" (lisans) — ve lisansın depodan KANITLANAMADIĞI yer açıkça
yazılmıştır.

---

## 0 · Dürüstlük sözleşmesi (ne ölçüldü, ne ölçülemez)

| Ölçülen | Nasıl |
|---|---|
| Bir yetenek "çalışıyor mu" | `registry.status()` → her yetenek için `availability()`; çağrı yolu koda bakılarak değil, **çalıştırılarak** sınandı |
| Kapı (bayrak) etkisi | İki tam senaryo: (a) `.env.example` değerleri birebir, (b) 15 yönetilen kapı `true` |
| Hangi bağımlılık engelliyor | Ret sebebi makine-okunur metinden (`dependency_missing:<paket>` vb.) |
| Ana akışa bağlılık | Yetenek kimliğini geçen **üretim** modülleri (AST/dosya taraması; testler hariç) |
| Uç envanteri | Canlı `backend.api.app.routes` (dekoratör sayımı DEĞİL — dekoratör taraması 69 verir, gerçek 74) |
| Lisans | Her yeteneğin `license` alanı (kendi beyanı) + harici aracın kendi lisansı |
| **Ölçülemeyen** | **Abonelik/kota/ücret hakkı.** Depo tek başına bir anahtarın canlı, kotalı, ödenmiş olduğunu KANITLAYAMAZ. Bu yüzden §7 yalnız *varlık* ve *çalışırlık* kontrolü listeler; **hiçbir gizli anahtar istenmez ve paylaşılmamalıdır.** |

Yeniden üretim (tek komut, ~45 sn):

```bash
python scripts/kapasite_denetimi_probe.py      # → reports/kapasite_denetimi.json
```

---

## 1 · Yönetici özeti

- Kayıtlı yetenek: **26**. Varsayılan ayarlarla **3 açık / 23 kapalı**.
- **Tüm kapılar açıkken bile 13 açık / 13 kapalı** kalıyor: kapalılığın yarısı
  bayrak değil **bağımlılık/ayar** sorunudur (aşağıda sınıf sınıf).
- 23 kapalının 19'u yalnız `gate_disabled` (bayrak kapalı). 4'ü bayraktan
  bağımsız: `trafilatura` (paket yok), yerel jüri (yerel model yok), TTS/STT
  (yerel uç yok).
- Bu raporun çıkardığı **16 bulgudan 5'i bu turda düzeltildi** (B1, B2, B12,
  B15, B16). Kalan 11'i §8'de karar sırasına dizildi.
- Sağlayıcı tarafı: **28 rota / 7 sağlayıcı** fiilen yolda; **7 sağlayıcı yalnız
  tanı ekranında** (taşıyıcısı yok), **10 sağlayıcı** anahtarı olsa da rota
  doğurmuyor (operatör beyanı bekliyor) — hiçbiri sessizce yutulmuyor.
- Uç tarafı: **74 HTTP ucu** (74'ü dokümanlı) + 1 WebSocket + 5 çerçeve kaydı.
  70 benzersiz `/api/*` yolu var; **33'ü ön yüzden çağrılıyor, 37'si yalnız API**.

---

## 2 · Bulgular ve kararlar

| # | Bulgu (kanıt özeti) | Durum | Karar |
|---|---|---|---|
| **B1** | `voice.tts`/`voice.stt` kapıları omurga dışıydı: `ENABLE_LOCAL_TTS=true` iken yetenek "hazır" derken çekirdek `gate_disabled` dönüyordu → UI ile çekirdek çelişiyordu | **DÜZELTİLDİ** | Omurga tek kaynak: `policy.MANAGED_GATE_FLAGS` 15 girişe çıktı, `state.py` yeniden ihraç ediyor |
| **B2** | Yazım hatalı/uydurma kapı adı (`ENABLE_TAMAMEN_UYDURMA`) "sadece kapalı" gibi görünüyordu; operatör açmaya çalışıp başarısız oluyordu | **DÜZELTİLDİ** | Yönetilmeyen `ENABLE_*` artık `unknown_gate` döner (fail-closed, en yüksek öncelik) |
| **B3** | Sağlayıcı anahtarı VAR ve varsayılan `.env.example` ile tek istekte `APIConnectionError`; buluta düşme yok | **Kabul edilen davranış** | `ALLOW_LOCAL_TO_CLOUD_FALLBACK=false` bilinçli fail-closed; açmak = maliyet + veri çıkışı → §4.2 |
| **B4** | 7 `pineal-*` rotası yerel 9Router'a sabit: 9Router kapalıysa o koridorlar ölü, yedek yol YOK | **Operatör kararı** | Yerel hub ya ayakta tutulmalı ya da bu 7 rota "yedekli" hâle getirilmeli (§8 · A5) |
| **B5** | Web-metin çıkarımı fiilen tek katmanlı: `trafilatura` paketi depoda/lock'ta yok → `dependency_missing`; `crawl4ai` var ama sayfa→metin yolu bayraksız | **Açık** | Metin katmanı için en az bir yolun sürekli açık olması; crawl4ai yolunun varsayılan davranışı belgelenmeli |
| **B6** | `sensor.ig.instagrapi` hiçbir üretim modülünden çağrılmıyor (0 çağıran) | **Açık** | Karar: entegre et ya da bayrağı "rezerve" diye işaretle; sessiz durması yanlış izlenim veriyor |
| **B7** | `extractor.identity.socid` omurgayı baypas ediyor (çağıran listesi boş; uç kendi yolundan gidiyor) | **Açık** | Omurgaya bağlanmalı (`CapabilityRunner`) — kasa/kota denetim izi tek yerden çıksın |
| **B8** | `route_diagnostics()` yalnız testlerden çağrılıyor; operatör göremiyor | **Açık** | Tanı ucu/ekranı ile görünür kıl (yolsuz sağlayıcılar da orada) |
| **B9** | 70 benzersiz `/api/*` yolundan 37'si ön yüzde hiç çağrılmıyor | **Tasarım kararı** | Her biri için "operatör ucu" ya da "ön yüzde göster" kararı; ölü uç varsa kaldır |
| **B10** | 7 sağlayıcı yalnız tanı ekranında (openai, anthropic, xai, cohere, azure-openai, iflow, google-gemini-vertex); 10 sağlayıcı anahtarı olsa da rota yok | **Kabul + belge** | Sessiz yutma yok; rota açmak istenirse `PINEAL_PROVIDER_MODELS_<SAĞLAYICI>` beyanı (§4.2) |
| **B11** | `.env.example`'da `PLAYWRIGHT_DOWNLOAD_HOST` var, kod hiç okumuyor (ölü ayar) | **Açık** | Sil veya "dış araç okur" notu düş |
| **B12** | 6 yönetilen bayrak `.env.example`'da yoktu (operatör göremez) | **DÜZELTİLDİ** | 15/15 kapı artık örnekte; ölçüm: `managed_missing_from_example: []` |
| **B13** | Öksüz ajan yok: 13 ajan rostosu, varsayılan rotada 9'u | **Kabul** | Aksiyon yok |
| **B14** | Anlık görüntüde 3 "tier ihlali" (`heavy_without_frontier`: cognitive_profiler, human_behavior, shadow_executor) | **Anahtar artefaktı** | Bulut anahtarı yokken beklenen sonuç; kural ihlali değil "anahtar bekliyor" — anahtar gelince kapanır |
| **B15** | `extractor.web.crawl4ai` bayrağı **servis üzerinden** okuyordu (`crawl_enricher.is_enabled()` → `ENABLE_CRAWL4AI`) ama `gates` kümesinde beyan etmiyordu: çekirdek "izinli" derken yetenek "kapalı" diyordu | **DÜZELTİLDİ** | `gates = {ENABLE_CRAWL4AI, vault}`; ayrıca yapısal kilit testi: "kaynakta `gate_disabled:ENABLE_X` diyen her sınıf X'i `gates`'te beyan etmek zorunda" |
| **B16** | Envanter sayfası "bayat" diyordu ve CI backend işi düşüyordu: üretici listeyi `tracked + untracked` kurduğu için yeni bir dosyanın **commit'lenmesi** sayfadaki sırayı değiştiriyordu (kirli ağaçta üret → temiz ağaçta doğrula = kırmızı) | **DÜZELTİLDİ** | Liste `sorted(set(...))` = izleme durumundan bağımsız; kilit testi eklendi. Ek ders: sayfa **toplam satır** sayısı taşıdığı için her metin düzenlemesinden SONRA üretilmeli |

---

## 3 · Yetenek tablosu (26 yetenek × 8 alan)

Her yetenek için istenen 8 alan: **① modül + yol ② gerçekten çalışıyor mu
③ engelleyen ayar/bağımlılık ④ ana akışa bağlı mı ⑤ erişim/lisans doğrulandı mı
⑥ açılırsa somut fayda ⑦ bedel + risk + gereken değişiklik ⑧ öneri**.
Okunabilirlik için ①–⑤ mekanik tabloda, ⑥–⑧ karar tablosunda verilir.

Adapters dizini: `agent_core/capabilities/`. "Ana akış" = kimliği geçen
**üretim** modülü; `—` = hiçbir üretim modülü çağırmıyor (omurga dışı kalır).

### 3.1 Varsayılan ayarlarda KAPALI olanlar (23)

#### (a) Yalnız bayrak kapalı — `gate_disabled` (19)

| Yetenek | ① Modül | ② Çalışır mı | ③ Engel | ④ Ana akış | ⑤ Lisans (beyan) |
|---|---|---|---|---|---|
| `sensor.identity.holehe` | `adapters_osint.py` | Bayrak açıkken EVET | `ENABLE_HOLEHE` | osint_investigator | GPL-3.0 (harici süreç) |
| `sensor.identity.maigret` | `adapters_osint.py` | EVET | `ENABLE_MAIGRET` | osint_investigator, mcp/tools | MIT |
| `extractor.web.scrapling` | `adapters_web.py` | Hayır (paket yok) | `ENABLE_SCRAPLING` **+ paket** | — | BSD-3-Clause |
| `sensor.x.twscrape` | `adapters_sensors.py` | Hayır (paket yok) | `ENABLE_X_SENSOR` **+ paket** | platform_registry, api, run_x | MIT |
| `sensor.web.agent_reach` | `adapters_sensors.py` | Hayır (araç yok) | `ENABLE_AGENT_REACH` **+ CLI** | platform_registry | MIT |
| `sensor.search.searxng` | `adapters_sensors.py` | Hayır (adres yok) | `ENABLE_SEARXNG` **+ `SEARXNG_BASE_URL`** | search_engine | AGPL-3.0 (ayrı servis) |
| `extractor.text.translate_local` | `adapters_language.py` | Hayır (motor yok) | `ENABLE_LOCAL_TRANSLATE` **+ `trans`/uç** | routes/language.py | harici süreç |
| `renderer.report.pdf` | `adapters_report_factory.py` | EVET | `ENABLE_REPORT_FACTORY` | api.py | dahili |
| `renderer.report.diagram` | `adapters_report_factory.py` | EVET | `ENABLE_REPORT_FACTORY` | api.py | dahili |
| `renderer.report.video` | `adapters_report_factory.py` | Hayır (ffmpeg yok) | `ENABLE_REPORT_FACTORY` **+ ffmpeg** | api.py | dahili + ffmpeg |
| `sensor.company.people` | `adapters_company.py` | EVET | `ENABLE_COMPANY_TARGETING` | api.py | dahili |
| `sensor.company.seo` | `adapters_company.py` | EVET | `ENABLE_COMPANY_TARGETING` | api.py | dahili |
| `sensor.company.harvester` | `adapters_company.py` | Hayır (araç yok) | `ENABLE_COMPANY_TARGETING` **+ theHarvester** | api.py | GPL-2.0 (CLI) |
| `analyzer.media.frames` | `adapters_media.py` | EVET | `ENABLE_MEDIA_FORENSICS` | api.py | OpenCV Apache-2.0 |
| `analyzer.media.similarity` | `adapters_media.py` | EVET | `ENABLE_MEDIA_FORENSICS` | api.py | OpenCV + dahili pHash |
| `sensor.media.fetch` | `adapters_media.py` | EVET | `ENABLE_MEDIA_FORENSICS` | api.py | yt-dlp Unlicense |
| `extractor.media.transcript` | `adapters_media.py` | Hayır (motor yok) | `ENABLE_MEDIA_FORENSICS` **+ whisper** | api.py | harici motor |
| `extractor.web.crawl4ai` | `adapters_web.py` | EVET | `ENABLE_CRAWL4AI` (B15: artık omurgada beyanlı) | crawl_enricher (uç) | Apache-2.0 |
| `sensor.ig.instagrapi` | `adapters_sensors.py` | Hayır (paket yok) | `ENABLE_IG_SECONDARY` **+ paket** | **— (0 çağıran)** | NOASSERTION |

#### (b) Bayraktan bağımsız kapalı (4)

| Yetenek | ① Modül | ② Çalışır mı | ③ Engel | ④ Ana akış | ⑤ Lisans |
|---|---|---|---|---|---|
| `extractor.web.trafilatura` | `adapters_web.py` | Hayır | paket `trafilatura` yok (bayrak kapısı yok) | — | Apache-2.0 |
| `voice.tts.local` | `adapters_voice.py` | Hayır | `PINEAL_TTS_URL`/piper yok (`no_local_endpoint`) | speech.py | harici süreç |
| `voice.stt.local` | `adapters_voice.py` | Hayır | yerel STT ucu yok | speech.py | harici süreç |
| `verifier.jury.local` | `adapters_jury.py` | Hayır | yerel model yok | api.py | yerel uç |

### 3.2 Varsayılan ayarlarda AÇIK olanlar (3)

| Yetenek | ① Modül | ② Çalışır mı | ③ Engel | ④ Ana akış | ⑤ Lisans |
|---|---|---|---|---|---|
| `extractor.identity.socid` | `adapters_osint.py` | EVET (ama omurga baypası) | — | **— (omurga dışı)** | MIT |
| `extractor.text.language` | `adapters_language.py` | EVET | — | routes/language.py | dahili |
| `voice.report.script` | `adapters_report.py` | EVET | — | speech.py | dahili |

Varsayılan ayarlarda **açık olan tek web-metin yolu yoktur**: `crawl4ai` ve
`trafilatura` ikisi de kapalıdır (bayrak / paket). Yani "sayfayı metne çevir"
yolu operatör açmadan kullanılamaz — B5'in somut sonucu budur.

### 3.3 Karar tablosu ⑥–⑧ (kapalı/anakron yetenekler)

| Yetenek | ⑥ Açılırsa somut fayda | ⑦ Bedel · risk · gereken değişiklik | ⑧ Öneri |
|---|---|---|---|
| `sensor.identity.maigret` + `holehe` | Kullanıcı adı/e-posta ayak izi; davetsiz OSINT'in çekirdeği | Kamuya açık veri toplar; hız sınırı ve hukuki sınır notu var; risk: yanlış hedef eşleşmesi → mevcut kanıt/güven sözleşmesi korunur | **AÇ** (operatör anahtarsız, CLI kuruluysa) |
| `sensor.search.searxng` | Anahtar gerektirmeyen arama altyapısı; DuckDuckGo'ya bağımlılığı azaltır | Kendi SearXNG örneğinizi barındırmak gerekir; AGPL ayrı servis; değişiklik: yalnız `SEARXNG_BASE_URL` + bayrak | **AÇ** (örnek varsa) · yoksa **düzelt**: kapsamı belgele |
| `extractor.web.scrapling`, `sensor.x.twscrape`, `sensor.web.agent_reach`, `sensor.ig.instagrapi`, `sensor.company.harvester` | Tarayıcı/X/Instagram/şirket kazıma genişliği | Her biri ayrı kurulum + platform ToS + hız sınırı riski; `instagrapi` lisansı NOASSERTION → hukuki inceleme | **şimdilik kapalı tut** (bayrak doğru), ama §8-A4'e göre "rezerve" olarak BELGELE |
| `renderer.report.pdf` + `diagram` | Rapor fabrikası (PDF/şema) | Bedel düşük (dahili); risk: sessiz şablon hatası | **AÇ** |
| `renderer.report.video`, `extractor.media.transcript` | Video rapor + ses→metin | ffmpeg/whisper kurulumu; CPU maliyeti; yerel kalmak veri çıkışını önler | **AÇ** (yerel motor kurulursa) · yoksa kapalı tut |
| `voice.tts.local` / `voice.stt.local` | Aspasia'nın sesli konuşması/dinlemesi (yerel) | Yerel motor gerekir; uydurma ses YOK sözleşmesi korunur; risk: yerel uç yanlış yapılandırılırsa sessiz kalır → `machine_note` zaten açık sebep yazar | **AÇ** (yerel uç kurulursa) — B1/B2 düzeltmesiyle artık UI ve çekirdek aynı dili konuşuyor |
| `verifier.jury.local` | Yerel jüri (bulutsuz doğrulama) | Yerel model RAM/CPU; risk düşük | **AÇ** (yerel model varsa) |
| `extractor.text.translate_local` | Çeviri; bulut anahtarı gerekmez | `trans` veya yerel uç; risk: kalite farkı | **AÇ** (yerel kurulumla) |
| `sensor.company.people` + `seo` | Şirket hedefleme (kişi/SEO) | Düşük bedel, dahili HTTP+stdlib | **AÇ** |
| `sensor.x.twscrape` özel not | X kazıma | ToS/hız sınırı + hesap riski | **şimdilik kapalı** |
| `extractor.identity.socid` | E-posta/telefon çıkarımı | Zaten AÇIK; asıl sorun omurga dışılığı | **DÜZELT** (B7): `CapabilityRunner`'a bağla |
| `extractor.web.trafilatura` | Hızlı, bağımlılıksız metin çıkarımı | Paket küçük; Apache-2.0 | **İNTEGRE ET** ya da "kasıtlı yok" diye belgele |
| `extractor.web.crawl4ai` | Sayfa→LLM-dostu metin (JS'li sayfalar dâhil) | Bedel: crawl4ai paketi (lock'ta var); risk: dış ağ + SSRF guard mevcut; değişiklik: yalnız `ENABLE_CRAWL4AI=true` (B15'ten sonra çekirdek de aynı bayrağı görür) | **AÇ** — web-metin yolunun sürekli açık tek adayı |

---

## 4 · Ayarlar (bayraklar) ve anahtar bekleyen yetenekler

### 4.1 Kapalı bayraklar NEREDE okunuyor — `ENABLE_INTERPRETER` örneği

Ölçüm (`interpreter_okuma_noktalari`, gerçek satırlar):

| Dosya:satır | Ne yapar |
|---|---|
| `agent_core/task_executor.py:225` | `true` ise interpreter ajanı göreve eklenir (yürütücü ajan çağrı zincirine girer) |
| `backend/api.py:4676` | Uç kapısı: `true` değilse 403 (ajan kayıtlı değilse ayrı ret, 4689) |
| `backend/api.py:3424` | Yorum: kapalı iken 403, kasa kilitliyken 423 |
| `agent_core/services/cognitive_router.py:114` | İkinci geçit: `ENABLE_INTERPRETER` **ve** `PINEAL_ROUTE_INTERPRETER` |
| `agent_core/services/dependency_health.py:67` | Sağlık kaydı: bayrak ↔ `open-interpreter` paketi eşlemesi |
| `agent_core/agents/interpreter_agent.py:3` | Modül sözleşmesi (docstring) |

Yani `ENABLE_INTERPRETER=false` **üç ayrı yerde** zinciri keser: ajan rostosu,
API ucu ve router koridoru. `.env.example`'da `ENABLE_INTERPRETER` **ve**
`PINEAL_ROUTE_INTERPRETER` ayrı ayrı belgeli — bu ikisi omurga dışı ikinci
geçittir (omurga kapsamı 15 bayrak; §4.3 farkı).

### 4.2 Anahtar bekleyen ayarlar (canlı doğrulama)

| Ayar | Kodda okunduğu yer | Boşken ne olur | Alternatif yerel/anahtarsız yol | Risk/karar |
|---|---|---|---|---|
| `SERPAPI_KEY` (ikincil ad) / `SERPAPI_API_KEY` (asıl) | `backend/api.py:1235` (kasa `serpapi_key` → `SERPAPI_API_KEY` → `SERPAPI_KEY`); `search_engine.py:70` | Anahtar yok → sağlayıcı yok; arama **SearXNG + DuckDuckGo HTML** ile sürer | **VAR**: DuckDuckGo anahtarsız her zaman denenir; SearXNG örneği varsa o | Anahtar gerekmiyor; ücretli sağlayıcı yalnız zenginleştirme → **şimdilik kapalı tut** |
| `OSINT_INDUSTRIES_KEY` | `agent_core/agents/osint_investigator.py:49` | Anahtarsız profil **boş** döner; `fallback_reason="provider_credentials_unavailable"` — uydurma YOK | **VAR**: `maigret` + `holehe` yetenekleri anahtarsız CLI ile çalışır | Ücretli API; yerel yol yeterli → **şimdilik kapalı tut** |
| `ALLOW_LOCAL_TO_CLOUD_FALLBACK` | `agent_core/services/llm_gateway.py:2431` | Boş/false → yerel model erişilemezse **`RuntimeError: LOCAL_PROVIDER_UNAVAILABLE`**; buluta DÜŞMEZ (canlı test: `APIConnectionError`, fallback yok) | — | Açmak = gizli veri buluta + ücret. Fail-closed doğru → **kapalı tut**; açacaksan bilinçli ve gerekçeli |
| `SEARXNG_BASE_URL` | `adapters_sensors.py` (yetenek), `search_engine.py:178` | Bayrak açık olsa da yetenek `config_missing` der | DuckDuckGo | **Düzelt**: adres yoksa bayrak açılmasın (UI zaten sebebi yazıyor) |
| `PINEAL_PROVIDER_MODELS_<SAĞLAYICI>` | `llm_gateway.py:398` | Beyan yoksa anahtarı olan sağlayıcı **rota doğurmaz** (10 sağlayıcı bu durumda) | — | Yanlış beyan ücretli çağrı doğurur; firewall + harcama tavanı geçerli → **operatör kararı** |

### 4.3 Kullanılmayan erişimler / omurga dışı geçitler

| Ayar | Örnekte | Omurgada yönetiliyor mu | Not |
|---|---|---|---|
| 15 `ENABLE_*` omurga kapısı | ✅ 15/15 | ✅ | B12 kapandı: `managed_missing_from_example: []` |
| `ENABLE_INTERPRETER` | ✅ | ❌ (ikinci geçit) | Router + API kendi okur; bilinçli ayrı geçit |
| `ENABLE_CROSS_PLATFORM` | ✅ | ❌ | Omurga dışı; kapsamı belgelenmeli |
| `PLAYWRIGHT_DOWNLOAD_HOST` | ✅ | — | **Ölü ayar** (kod hiç okumuyor) → B11 |
| Üretimde okunup belgesiz `ENABLE_*` | — | — | **YOK ✓** (ölçüm: `read_but_undocumented: []`) |

---

## 5 · Sağlayıcılar ve stealth

### 5.1 Sağlayıcı envanteri (gerçek kaynaklardan)

- **Rota taşıyan 7 sağlayıcı, 28 rota:** openrouter 9 · nous-research 8 ·
  9router 7 · groq 1 · cerebras 1 · google-gemini 1 · google-gemini-backup 1.
  Bunların **7'si `pineal-*`** yani yerel 9Router hub'ı — B4.
- **Yalnız tanı (7):** openai, anthropic, xai, cohere, azure-openai, iflow,
  google-gemini-vertex. Taşıyıcı (`openai_chat`) yok → rota teklif edilmez,
  ama `route_diagnostics`'te `key_present` olarak GÖRÜNÜR (sessiz yutma yok).
- **Anahtarı olsa da rota doğurmayan (10):** alibaba-dashscope, deepinfra,
  deepseek, fireworks, huggingface, mistral, nvidia-nim, perplexity, sambanova,
  together → `PINEAL_PROVIDER_MODELS_*` beyanı bekliyor.
- **Canlı anlık görüntü:** 28/28 rota çözüldü, 21 ajan zinciri raporlandı,
  3 tier ihlali (`heavy_without_frontier`) → **B14: bulut anahtarı yokken
  beklenen**; anahtar eklendiğinde kapanır. İhlal kuralının kaynağı
  `llm_gateway.py:896`.

### 5.2 `STEALTH_PROVIDER` matrisi (gerçek çözümleme)

| Ayar | Seçilen | Kullanılabilir | Sebep |
|---|---|---|---|
| (tanımsız) | `playwright_stealth` | ✅ | — |
| `""` | `playwright_stealth` | ✅ | — |
| `playwright_stealth` | `playwright_stealth` | ✅ | — |
| `invisible` | `invisible` | ❌ | `binary_missing` |
| `cloak` | `cloak` | ❌ | `binary_missing` |
| `none` | `none` | ✅ | — |
| geçersiz (`SELENIUM?!`) | `playwright_stealth` | ✅ | `invalid_provider:SELENIUM?!` (makine-okunur) |

Özet: **fiilen çalışan 2 seçenek** (playwright_stealth, none); `invisible` ve
`cloak` **yalnız yapılandırma düzeyinde** — ikili (binary) kurulmadıkça asla
seçilemez, seçilse bile dürüstçe "kullanılamaz" der ve stealthsiz devam edilir.

---

## 6 · Uç nokta, ön yüz ve omurga bağlantısı

### 6.1 Uçlar

| Ölçüm | Değer |
|---|---|
| Canlı kayıt toplamı | **80** = 74 `APIRoute` + 1 WebSocket + 4 çerçeve `Route` + 1 `Mount` |
| Dokümanlı (`include_in_schema`) | **74** (74 HTTP ucunun tamamı) |
| `/api/` kaydı / benzersiz yol | 71 kayıt / **70 yol** |
| Ön yüzün çağırdığı | **33** benzersiz yol |
| Yalnız API (ön yüz hiç çağırmıyor) | **37** |

Örnek yalnız-API uçları: `/api/experimental/socid/extract`, `/api/jury/vote`,
`/api/media/analyze`, `/api/company/scan`, `/api/language/translate`,
`/api/experimental/interpreter/execute` … (tam liste kanıt JSON'unda).

### 6.2 Ana görev yönlendirici ↔ omurga gerçek bağları

| Bağ | Ölçüm | Yorum |
|---|---|---|
| `CognitiveRouter` → omurga | `cognitive_router.py` içinde 51 "capabilities" referansı | Zayıf bağ: router yetenek envanterini DOLAYLI kullanır |
| Omurga (`agent_core/capabilities/`) → `CognitiveRouter` | **0 referans** | Tek yönlü: omurga router'ı hiç tanımıyor |
| Router'ı geçen dosyalar | task_executor, aspasia_chief, aspasia/interface, cognitive_router, api.py (+ testler) | Yönlendirme kararı karar ajanlarında, yetenek koşumu `CapabilityRunner`'da |
| Yetenekleri çağıran üretim modülleri | api.py (14 yetenek), osint_investigator (2), speech.py (3), routes/language.py (2), search_engine (1), platform_registry (2), mcp/tools (1) | **0 çağıran: `socid`, `crawl4ai`, `instagrapi`, `trafilatura`, `scrapling`** |

Kanıt: `baglanti_probe` eşdeğeri `omurga_router_bagi` + `cagri_yerleri`.

---

## 7 · "Kullanım hakkı" (lisans) — ne doğrulandı, ne doğrulanamaz

**Doğrulanan (depo içinden):** her yeteneğin `license` beyanı ve harici araç
kategorisi. Öne çıkanlar: GPL-3.0 `holehe`, GPL-2.0 `theHarvester`,
AGPL-3.0 `SearXNG` (ayrı servis — kod gömülmez, HTTP ile çağrılır),
**NOASSERTION `instagrapi`** (hukuki inceleme notu gerekiyor),
Apache-2.0 `trafilatura`/`crawl4ai`/OpenCV, MIT `maigret`/`twscrape`/`socid`.

**Doğrulanamayan (dürüst sınır):** bir anahtarın **canlı, kotalı, ödenmiş**
olması depodan kanıtlanamaz; ayrıca kullanım hakkı sağlayıcı sözleşmesine
bağlıdır. Bu yüzden yalnız **varlık + çalışırlık** kontrolü önerilir
(gizli anahtarlar hiçbir zaman paylaşılmaz):

```bash
# 1) Anahtar VAR MI (değer yazdırmadan)?
python - <<'PY'
import os
for v in ("OPENROUTER_API_KEY","NINEROUTER_API_KEY","NOUS_API_KEY","GROQ_API_KEY",
          "CEREBRAS_API_KEY","GEMINI_API_KEY","GEMINI_BACKUP_API_KEY","SEARXNG_BASE_URL"):
    print(f"{v}: {'VAR' if os.getenv(v,'').strip() else 'yok'}")
PY

# 2) Sağlayıcı CANLI yanıt veriyor mu (anahtarı ekrana basmadan)?
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:20128/v1/models   # yerel 9Router
```

---

## 8 · Aksiyon sırası

| # | Aksiyon | Kim | Durum |
|---|---|---|---|
| A1 | B1+B2: omurga tek kaynak (`MANAGED_GATE_FLAGS` = 15) + yönetilmeyen bayrak `unknown_gate` | kod | **YAPILDI** (bu commit) |
| A2 | B12: 15/15 kapı `.env.example`'da | kod | **YAPILDI** |
| A3 | Test sırası bağımlılığı: ses durumu testler arası sızıyordu → tohum + geri yükleme (`tests/integration/test_speech_api_faz_c.py`) | kod | **YAPILDI** |
| A4 | B6/B7: `socid`'i omurgaya bağla, `instagrapi`'yi "rezerve" diye belgele | kod | SIRADA |
| A5 | B3/B4: 9Router yedeği — yerel hub düşerse `pineal-*` koridorları için karar | operatör | SIRADA |
| A6 | B5: metin çıkarımı için sürekli açık en az bir katman (crawl4ai) belgele/garanti et | kod | SIRADA |
| A7 | B9: 37 yalnız-API ucu için tek tek "göster/kaldır" kararı | operatör | SIRADA |
| A8 | B11: `PLAYWRIGHT_DOWNLOAD_HOST` ölü ayarını sil veya nota bağla | kod | SIRADA |
| A9 | B8: `route_diagnostics()`'i operatöre aç (yolsuz/tanı sağlayıcıları tek ekranda) | kod | SIRADA |
| A10 | B15: crawl4ai bayrağı omurgada beyanlı + "beyansız bayrak" yapısal kilidi | kod | **YAPILDI** |
| A11 | B16: envanter üreticisi determinist sıralama + kilit testi; sayfa her metin düzenlemesinden sonra üretilir | kod | **YAPILDI** |

---

## 9 · Yeniden üretim

```bash
# Kanıt (bu raporun her sayısı):
python scripts/kapasite_denetimi_probe.py          # → reports/kapasite_denetimi.json

# Kilit testler (B1/B2 + ses + jüri çekirdeği):
python -m pytest tests/unit/test_capability_spine_faz0.py -q
python -m pytest tests/unit/test_speech_faz_c.py tests/unit/test_speech_report_faz_c.py \
                 tests/integration/test_speech_api_faz_c.py -q

# Tüm takım:
python -m pytest -q
```

Bu rapor, kanıt JSON'u ve sonda betiği **depoda** yaşar; sonda raporun dışına
düşerse sayılar yeniden üretilebilir (`reports/kapasite_denetimi.json`).

**Not (B16):** envanter sayfası ağacın toplam satır sayısını taşır; bu raporu
veya herhangi bir metni düzenledikten sonra sayfayı yeniden üretin:

```bash
python scripts/generate_inventory_page.py && python scripts/generate_inventory_page.py --check
```

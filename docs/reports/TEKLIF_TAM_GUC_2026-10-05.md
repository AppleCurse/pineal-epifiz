# TEKLİF — BUNLAR EKLENİRSE PINEAL ŞU HALE GELİR

**Tarih:** 2026-10-05 · **Girdi:** ürün sahibinin 3 katmanlı tespiti (Retina / Beyin & Hafıza / Ses) + bu checkout'ta yapılan kod okuması.
**Bu belgenin işi:** "hangisi ahlaklı" değil — **ne eklenirse sistem ne yapar.**

---

## 0 · Teklifin özü

Bugün Pineal **tek gözlü ve dilsiz**: sensörü Instagram (Playwright), X deliği açık (`XScraperUnsupportedError → awaiting_authorization`), web kazıma tek yerde dar kullanımda, hafızası görev bitince sıfırlanan bir JSON, arayüzdeki holografik ağ **rastgele düğüm üretiyor** (`HolographicResonanceMesh.svelte` → `generateNodes()`), Aspasia'nın sesi yok.

Senin üç katmanın + benim üstüne eklediğim 12 parça tam güçle bağlanırsa Pineal şuna dönüşür:

> **Tek bir URL veya kullanıcı adı girilir. Sistem o kişinin internetteki bütün açık izini ücretsiz ve paralel toplar; her parçayı mühürlü kanıta çevirir; geçmiş taramalarla karşılaştırıp neyin değiştiğini söyler; üç modelin konsensüsüyle doğrular; sosyal ağını gerçek bir graf olarak çizer; ve bütün bunları sana sesi olan, sen konuşunca susup dinleyen bir varlık anlatır.**

Aşağıda bunun parça parça karşılığı var.

---

## 1 · Bugün ne var (kod kanıtlı, kısa)

| Katman | Bugün | Kanıt |
|---|---|---|
| Instagram sensörü | Var, tek birincil yol (Playwright + stealth) | `agent_core/scraper/instagram_ghost.py` |
| X / Twitter | **YOK** — desteklenmiyor, onay bekliyor | `scraper.py:24` `XScraperUnsupportedError`; `backend/api.py:2238` |
| Kullanıcı adı taraması | Taslak var, kapı arkası, kanıt üretmiyor | `services/maigret_scanner.py`, `ENABLE_MAIGRET=false` |
| Profil→kimlik | Var, dar kullanım | `services/socid_enricher.py` |
| Web kazıma | crawl4ai var ama **yalnız tek yerde**: arama eşleşmesi sonrası URL'lerde | `backend/api.py:3433-3436` |
| Arama | Tavily / Exa / SerpAPI — ücretli, anahtarlı | `services/search_engine.py` |
| Dalga motorları | 7 motor var; **Frequency sin/cos modeli, FFT yok** | `engines/frequency_engine.py` (fft/fourier yok) |
| Zaman adli tıp | Var, gönderi saatlerinden | `services/timing_forensics.py:analyze_timing` |
| Çapraz jüri | Var, kapalı oy sözlüğüyle | `agents/autonomous_verifier.py` (çapraz jüri) |
| Hafıza | Görev başına JSON; opsiyonel semantik | `services/canonical_memory.py`, `hindsight_memory.py` |
| Sosyal graf | **YOK** | — |
| Holografik ağ | **Sahte**: kendi kendine düğüm üretiyor | `HolographicResonanceMesh.svelte` → `generateNodes()` |
| Aspasia'nın sesi | **YOK** | — |
| Yetenek yönetimi | Yeni: tek sözleşme + kayıt defteri | `agent_core/capabilities/` |

---

## 2 · TEKLİF A — RETİNA & SİNİR UÇLARI

### A1 · Agent-Reach (315) → **interneti bedava okuma siniri**
**Eklenen:** `sensor.web.agent_reach` capability. Twitter, Reddit, YouTube, GitHub, Bilibili okuma; tek CLI, API ücreti yok.
**Olan:** Pineal, arama sağlayıcısına para ödemeden 5 platformu okur. Tavily/Exa/SerpAPI yalnız "derin arama" için kalır; günlük kullanımın maliyeti düşer.
**Nasıl tek vücut:** `SearchEngine`'e 4. sağlayıcı olarak girer; `SearchOutcome` semantiği (timeout/auth/rate-limit/no-result ayrımı) **aynı** kalır. Kapı: `ENABLE_AGENT_REACH`.

### A2 · socid-extractor (173) + maigret (262) → **tek URL'den 150+ site ayak izi**
**Eklenen:** Mevcut taslaklar capability'ye dönüşür; çıktıları artık `EvidenceItem` üretir ve **EvidenceTimeline'a mühürlenir** (bugün yalnız profile dict olarak yazılıyor, kanıt zincirine girmiyor).
**Olan:** Bir profil URL'si verildiğinde 150+ sitedeki varlık, tarih-saat ve kaynak bağlantısıyla zaman çizelgesine düşer. "Bu kişi şuralarda var" artık iddia değil, mühürlü kayıt.
**Nasıl tek vücut:** `CapabilityResult.items` → `build_evidence_timeline()` (`services/evidence_timeline.py:82`). Maigret'in site veritabanı WhatsMyName/sherlock/enola listeleriyle tazelenir (aynı işi yapan 24 deponun verisi tek yerde).

### A3 · twscrape (70) + instagrapi (131) → **canlı akış: X deliği kapanır, Instagram çift kaynaklı olur**
**Eklenen:** `sensor.x.twscrape` (gerçek gönderi/etkileşim akışı, çoklu hesap + rate-limit) ve `sensor.ig.instagrapi` (Instagram ikinci kaynak).
**Olan:**
- X URL'si artık `awaiting_authorization`'a düşmez; **gerçek zaman serisi** çıkar.
- Bu seri doğrudan `FREQUENCY` motorunu ve `timing_forensics.analyze_timing`'i besler (`LilithGrowthAgent` da dahil).
- Instagram engellendiğinde Playwright tek nokta olmaktan çıkar: instagrapi yedeğe düşer ve sensör **düşmez**.
**Nasıl tek vücut:** ikisi de `platform_registry`'ye adaptör olarak eklenir (kural [009]: ikinci platform karar katmanı yok).

### A4 · crawl4ai (294) + trafilatura (1) → **saf metin omurgası**
**Eklenen:** `extractor.web.trafilatura` (hafif birincil) + `extractor.web.crawl4ai` (ağır/JS'li sayfa) — sıralı fallback, tek arayüz.
**Olan:** Web sayfası çöp etiketlerden arınıp adli delil seviyesinde metne dönüşür. Bu, `QuoteGuard`'ın "alıntı kaynakta birebir var mı?" kontrolünün **kırılmaz omurgası** olur: alıntı korpusuna giren metin artık makinenin okuduğu temiz metinle birebir aynı kaynaktan gelir.
**Nasıl tek vücut:** bugün crawl4ai yalnız `api.py:3433`'te çağrılıyor; capability'ye taşınınca **her** ajan (özellikle `AutonomousVerifier`) aynı temiz metni kullanır.

---

## 3 · TEKLİF B — BEYİN SAPI, HAFIZA KRİSTALİ & ÇAPRAZ JÜRİ

### B1 · duh (253) → **çapraz jürinin ağırlıklı konsensüsü**
**Eklenen:** çok modelli konsensüs motoru, mevcut jürinin mimari ikizi.
**Olan:** Jüri oyları artık "kaç evet" değil; **ağırlıklı konsensüs** olur. Tek bir modelin hezeyanı, diğerlerinin oyuyla düşer. Çelişkide sistem "kesin" demek yerine **"jüri ayrıştı, şu iki model şu gerekçeyle karşı çıktı"** der — bu Pineal'in dürüstlük sözleşmesiyle birebir uyumlu.
**Nasıl tek vücut:** `autonomous_verifier` içindeki çapraz jüriye konsensüs toplama katmanı olarak girer; kapalı oy sözlüğü **değişmez**.

### B2 · LightRAG (48) → **hafıza kristali (STRATA + GRAVITY ile birleşen)**
**Eklenen:** hem somut olayları (alçak seviye) hem tematik eğilimleri (yüksek seviye) tutan graf-RAG.
**Olan:** Hakkında üçüncü kez tarama yapılan bir hedefte sistem "geçen sefer ne demiştik" diyebilir. `STRATA` (zaman içindeki katman/kayma) ve `GRAVITY` (çekim merkezleri) motorları artık tek görevlik değil, **aylara yayılan** bir hafızanın üzerinde çalışır.
**Nasıl tek vücut:** `memory.graph.lightrag` capability; getirilen her parça kanıt kimliği taşır (kanıt mührünü atlayan bağlam yasak).

### B3 · Osintgraph (124) → **holografik ağ artık sahte değil**
**Eklenen:** takipçi/takip edilen ilişkilerini graf veritabanına döken şema ve adaptör.
**Olan — en görünür değişim:** bugün `HolographicResonanceMesh.svelte` kendi kendine rastgele düğüm üretiyor (`generateNodes()`). Bu entegrasyondan sonra örgü, **hedefin gerçek sosyal yerçekimi ağını** çizer: kim merkezde, kim uydu, hangi kümeler birbirine bağlı — hepsi kanıt kimlikli gerçek veri.
**Nasıl tek vücut:** önce yerel graf (DuckDB/NetworkX), istenirse Neo4j arka ucu; UI bileşeni `nodes/edges` prop'larını gerçek veriden alır.

### B4 · mem0 (49) + cognee (273) → **zaman aşımına uğramayan bilişsel profil**
**Eklenen:** kalıcı bellek katmanı, `canonical_memory` + `hindsight_memory` ile birleşik.
**Olan:** hedefin aylar içindeki davranış değişimi tek bir yerde birikir; "Nisan'daki profil ile Ekim'deki profil arasındaki fark" tek sorguyla alınır.
**Nasıl tek vücut:** `memory.vector.mem0` / `memory.graph.cognee` capability'leri; kanıt deposu JSON olarak kalır (ADR korunur), bellek bunun **üstünde** bir indekstir.

---

## 4 · TEKLİF C — SES, NEFES & YAŞAYAN EPİFİZ (Aspasia'nın bedeni)

### C1 · VoxCPM (324) + MOSS-TTS (323) → **Aspasia konuşur**
**Eklenen:** yerel, tokenizer'sız, gerçekçi ses üretimi; sıfır gecikme, makinede.
**Olan:** Atlas Gözlemevi'ndeki göz artık **sesli**: "Bunu henüz doğrulamadım, Mösyö." cümlesi pirinç yuvanın içinden duyulur. Buluta ses gitmez, kayıt dışarı çıkmaz.
**Nasıl tek vücut:** `voice.tts.local` capability; OpenAI-uyumlu yerel TTS uç noktasına konuşur, yoksa dürüst `available:false`. **Aspasia'nın kendi karakter sesidir; hedefin sesi taklit edilmez.**

### C2 · Open-LLM-VTuber (316) → **dinleyen, susan, gözbebeği oynayan varlık**
**Eklenen:** eller serbest sesli etkileşim + araya girme (voice interruption) + yerel avatar mimarisi.
**Olan:** `OrganikIrisCanvas` ile birleşince göz **canlı bir varlık** gibi davranır: sen konuşurken dinler (gözbebeği büyür), sen araya girince **susar**, o konuşurken iris hafif titrer. Bugün yalnızca_fare hareketini ve işlem yükünü takip eden göz, karşısındaki insanı *duyan* bir göze dönüşür.
**Nasıl tek vücut:** `voice.interaction` capability + WebSocket üzerinden konuşma durumu (`listening / speaking / interrupted`) → Svelte bileşenleri.

### C3 · taste-skill (321) → **sıkıcı laf salatası teknik olarak engellenir**
**Eklenen:** jenerik çıktıyı engelleyen üretim filtresi.
**Olan:** Aspasia'nın tüzüğü ("duvar-metin yazmazsın, yapay samimiyet yok, zekânı sergilemezsin") artık yalnız prompt'ta değil, **teknik bir kalkan**: yanıt çıkmadan önce jenerik kalıplar (gereksiz dolgu, sıfat salatası, "harika bir soru") taranır ve düşürülür.
**Nasıl tek vücut:** Aspasia yanıt hattına son kontrol adımı; düşen yanıt telemetriye `slop_filtered` olarak yazılır.

---

## 5 · BENİM ÜSTÜNE EKLEDİKLERİM

Senin listen doğru ama **tam güç** için eksik kalan 12 parça:

| # | Ek | Ne kazandırır |
|---|---|---|
| 1 | **SearXNG** (28) — ayrı servis, anahtarsız metasearch | Arama faturası sıfırlanır; tek sağlayıcıya bağımlılık biter |
| 2 | **Scrapling** (159) — adaptif kazıma | Retina kırılganlığı biter: site tasarımı değişince sensör düşmez |
| 3 | **yt-dlp** (96) + **opencv** (314) + **PaddleOCR** (269) | Video/ses/görsel kanadı açılır: Reels'ten kare, kareden metin, sesten transkript — hepsi kanıt |
| 4 | **pHash + EXIF** (opencv + pillow) | Bir fotoğrafın başka hesapta kullanımı yakalanır — "bu profil gerçek mi" sorusunun cevabı |
| 5 | **FFT / periodogram** (numpy) | Frequency motoru sin/cos modelinden **gerçek spektral analize** geçer: uykusuzluk döngüsü, paylaşım periyodu ölçülür |
| 6 | **DuckDB + scikit-learn** (40) | Zaman serisi deposu + kalibrasyon: 0.70 eşiği "sabit" olmaktan çıkar, **ölçülmüş** değere dönüşür |
| 7 | **Değişim izleme** (instatracker deseni, 7) | İki tarama arasındaki fark raporlanır — bugün bu yok |
| 8 | **Dil tespiti + çeviri** (surya/HanLP, 42/82) | Yabancı hedef; orijinal metin korunarak (QuoteGuard bozulmaz) |
| 9 | **phonenumbers** (109) + **theHarvester/open-seo** (117/161) | Kişi + kurum hedefi aynı çatıda |
| 10 | **MCP sunucusu + Agent Skills** (322/318/228) | Pineal'in yetenekleri dışarıya da satılır/çağrılır: tek kayıt defterinden otomatik ihracat |
| 11 | **Yerel jüri** (ollama/vllm/llmfit, 102/60/193) | Donanımın var: jüri yerelde koşar, maliyet 0, hedef verisi makineden çıkmaz |
| 12 | **Rapor fabrikası** (archify 144, diagram-design 146, hyperframes 134) | Kanıt bağlantılı PDF/diyagram; istersen raporun videosu |

---

## 6 · ÖNCE / SONRA — "bu hale gelir"

| Yetenek | ÖNCE | SONRA |
|---|---|---|
| Platform kapsamı | Yalnız Instagram (+ ücretli web arama) | Instagram (çift kaynak) + X + TikTok + Reddit + YouTube + GitHub + 150+ site varlık taraması |
| X / Twitter | Desteklenmiyor, onay bekliyor | Gerçek zamanlı gönderi akışı, zaman serisi motora bağlı |
| Arama maliyeti | Tavily/Exa/SerpAPI — her sorgu para | SearXNG + Agent-Reach: bedava; ücretli yollar yalnız derin arama için |
| Kazıma dayanıklılığı | Site değişirse kırılır | trafilatura → crawl4ai → Scrapling sıralı fallback, adaptif |
| Kanıt kalitesi | Alıntı kontrolü ham metne bakıyor | Temiz metin omurgası: QuoteGuard kırılmaz |
| Hafıza | Görev bitince sıfır | Graf + vektör bellek: hedefin aylar içindeki değişimi tek yerde |
| Doğrulama | Jüri var, oy sayımı düz | Ağırlıklı çok modelli konsensüs; çelişki açıkça raporlanır |
| Sosyal ağ | Yok | Gerçek graf: merkez/uydu/kümeler kanıt kimlikli |
| Holografik örgü | **Sahte**: rastgele düğüm | **Gerçek**: hedefin sosyal yerçekimi ağı canlı çizilir |
| Skor güveni | 0.70 sabit, ölçülmemiş | Kalibre edilmiş eşik + güven aralığı + backtest |
| Video / ses | Metadata bile profile girmiyor | Kare + OCR + transkript kanıt; Frequency motoru gerçek veriyle |
| Arayüz | Göz bakar, konuşmaz | Göz duyar, dinler, susar, konuşur (yerel ses) |
| Aspasia dili | İyi prompt umudu | Teknik filtre: jenerik laf salatası düşer |
| Dışa açılım | Kapalı kutu | MCP sunucusu + Skills paketi: her yetenek dışarıdan çağrılabilir |
| Çalışma maliyeti | Her adım ücretli model | Yerel jüri: maliyet 0, veri makineden çıkmaz |

---

## 7 · PROGRAM

**FAZ A — RETİNA (önce her şey buradan geçer)**
A1 trafilatura + crawl4ai capability'leri (temiz metin omurgası) · A2 maigret/socid → EvidenceTimeline mührü · A3 Agent-Reach (ücretsiz 5 platform) · A4 SearXNG ayrı servis · A5 twscrape (X deliği kapanır) · A6 instagrapi (IG ikinci kaynak) · A7 Scrapling (kırılganlık biter) · A8 WhatsMyName/sherlock verisiyle maigret DB tazeleme.
*Kabul:* X URL'si artık onay beklemiyor; trafilatura kapalıyken crawl4ai devralıyor; her sensörün `available:false` yolu var; maigret bulgusu zaman çizelgesinde kanıt kimliğiyle görünüyor.

**FAZ B — BEYİN & HAFIZA**
B1 duh konsensüsü jüriye bağlanır · B2 LightRAG hafıza kristali · B3 mem0/cognee kalıcı bellek · B4 Osintgraph şeması → yerel graf → **HolographicResonanceMesh gerçek veriyle çizer** · B5 DuckDB zaman serisi + scikit kalibrasyon · B6 FFT ile Frequency motoru · B7 değişim izleme.
*Kabul:* aynı hedefin iki taraması arasındaki fark raporlanır; örgü rastgele düğüm üretmiyor; eşik kalibrasyon verisi olmadan değiştirilemiyor.

**FAZ C — SES & NEFES**
C1 taste-skill filtresi (önce bu, bağımlılık yok) · C2 yerel TTS (VoxCPM/MOSS-TTS) → Aspasia konuşur · C3 sesli etkileşim + araya girme (Open-LLM-VTuber mimarisi) → göz dinler ve susar · C4 sesli rapor okuma.
*Kabul:* jenerik yanıt filtrelenip telemetriye yazılıyor; TTS yerelde, ses dışarı çıkmıyor; konuşma durumu (`listening/speaking/interrupted`) WebSocket'ten UI'a akıyor.

**FAZ D — BİRLEŞİM & İHRACAT**
D1 MCP sunucusu + Skills ihracı · D2 yerel jüri (donanımın var) · D3 medya adli hattı (yt-dlp + opencv + OCR + pHash) · D4 dil tespiti/çeviri · D5 rapor fabrikası (PDF + diyagram + video) · D6 kurum hedefi (theHarvester/open-seo).
*Kabul:* kasa açık + internet yokken temel hat çalışır; her yetenek MCP aracı olarak listelenir; rapor hash'li ve kanıt bağlantılı.

---

## 8 · BAŞLAMAK İÇİN

Faz A'yı **şimdi** başlatıyorum: önce temiz metin omurgası (trafilatura → crawl4ai → Scrapling), sonra maigret/socid'in kanıt mührü, sonra X deliği. Sırayı bu şekilde öneriyorum çünkü geri kalan her şey (jüri, hafıza, rapor) temiz metin ve kanıt akışının üstüne kuruluyor; retina zayıfsa beyin de yanlış öğrenir.

Onay ver, giriyorum.

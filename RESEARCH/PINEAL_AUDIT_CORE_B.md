---
title: "PINEAL Audit CORE-B: psychology nlp safety shadow scraper services utils workers"
tags: [pineal, audit]
status: active
created: 2026-11-09
---

# PINEAL_AUDIT_CORE_B — Derin Denetim Raporu (`agent_core` Alt Sistemleri)

- **Hedef Depo:** `C:\Projects\pineal-epifiz` (`@61c414c5`, salt-okunur denetim)
- **Kapsam:** `agent_core/services/` (72 dosya), `agent_core/scraper/` (4 dosya), `agent_core/psychology/` (2 dosya), `agent_core/nlp/` (2 dosya), `agent_core/safety/` (2 dosya), `agent_core/shadow/` (2 dosya), `agent_core/utils/` (3 dosya), `agent_core/workers/` (2 dosya)
- **Not:** Görev tanımında örnek olarak geçen `epifiz_engine.py` ve `memory_manager.py` dosyaları depoda mevcut değildir; bellek katmanı fiilen `canonical_memory.py`, `hindsight_memory.py`, `memory_crystal.py` ve `memory_injector.py` olarak yapılandırılmıştır.

---

## 1. Modül Envanteri ve Mimari Özet

| Alt Dizin / Modül | Satır | İşlev | Durum / Kritik Not |
|---|---:|---|---|
| `safety/minor_gate.py` | 272 | `MinorGate.evaluate()` ve `MinorCaseLedger` (reşit olmayan hedef kilidi) | Yalnız operatör beyanına (`subject_is_minor`) bağlı; otomatik yaş tespiti yok, CLI/Shadow yollarında çağrılmıyor (**P0**) |
| `scraper/vault_gate.py` | 223 | OSINT/Scraper çıkışları için Kasa kilidi (`contextvar` / `.pineal_vault.json` / `PINEAL_ENV`) | `PINEAL_ENV` tanımsızken `security.py` ile ters düşüp fail-open (`dev_boundary_deferred`) açılıyor (**P1**) |
| `scraper/instagram_ghost.py` | 1163 | Playwright tabanlı Instagram profil/gönderi kazıyıcı ve anti-halüsinasyon şeması | `_paginate_grid` ilk gönderide profilden çıkıyor (**P0**); Türkçe sayı ayrıştırma bozuk (**P1**); ms epoch çöküyor (**P2**) |
| `scraper/run_scraper.py` | 64 | CLI Instagram kazıyıcı sarmalayıcı | Hata durumunda `exit(0)` dönüyor (**P2**) |
| `services/llm_gateway.py` | 3560 | Çoklu sağlayıcı LLM yönlendirici (9Router, OpenRouter, doğrudan sağlayıcılar, bütçe, RTK) | `query_json` 9Router/vision varsayılan model seçimini eziyor (**P1**); `route_diagnostics` vs `agent_route_variants` tutarsız (**P1**); stream `GeneratorExit` hatası (**P2**) |
| `services/hindsight_memory.py` | 334 | `CanonicalMemory` alt sınıfı; SQLite + `sentence-transformers` semantik bellek | `merge_evidence` imza uyumsuzluğu (`metadata` eksik -> `TypeError`) (**P0**); global aramada `task_id` kaybı (**P1**); event-loop bloklama (**P2**) |
| `services/canonical_memory.py` | 375 | Görev bazlı JSON kanonik bellek ve çelişki çözümleyici (`ConflictRecord`) | Atomik yazım ve görev kilidi (`_task_lock`) mevcut |
| `services/memory_crystal.py` | 492 | Görevler arası hedef belleği (CRC32 hashing-trick vektör + prompt çiti) | Aynı hedefe eşzamanlı yazımlarda dosya kilidi yok (**P2**) |
| `services/memory_injector.py` | 157 | `learnings.json` operatör kurallarını prompt-injection filtresiyle enjekte eder | `hash` alanı olmayan bozuk kuralda `unhashable type` hatası (**P3**) |
| `services/browser_session.py` | 280 | Canlı Chromium oturumu (operatör login + domain allowlist) | Allowlist kontrolü `goto` sonrasında yapılıyor ve `click`/`press` navigasyonlarında hiç yapılmıyor (**P1**) |
| `services/maigret_scanner.py` | 325 | Maigret kullanıcı adı tarayıcı | Egress omurgasını (`vault_gate`) tamamen atlayarak doğrudan ağa çıkıyor (**P1**) |
| `services/media_forensics.py` | 637 | `yt-dlp`/`httpx` medya indirme, OpenCV kare analizi, yerel Whisper STT, pHash | `yt-dlp` en son değiştirilen dosyayı seçiyor (yarış durumu) ve SSRF kontrolü yalnızca ilk URL'de (**P1**) |
| `services/frame_evidence.py` | 516 | Görsel karelerden EXIF, pHash, parlaklık ve değişim noktası çıkarımı | `decode_image` içinde `.convert("RGB")` EXIF verisini sildiği için `extract_exif` her zaman boş dönüyor (**P1**) |
| `services/deep_profile_resolver.py` | 281 | Sosyal profil URL'lerini platform yeteneklerine (`instagram`, `x`, `socid`) yönlendirir | Tek bir rotada `socid_extractor` eksikse tüm planı (`instagram`/`x` dahil) iptal ediyor (**P1**) |
| `services/redis_bus.py` | 214 | Redis pub/sub + bellek içi yedek veri yolu | Senkron `redis` istemcisi kullanıldığında `disconnect()` bağlantıyı kapatmıyor (**P2**) |
| `shadow/shadow_executor.py` | 386 | Dark Triad + NLP tabanlı gölge mesaj sentezleyici | İki LLM çağrısı da çöktüğünde statik şablon mesajı `data_confidence=True, fallback_reason=None` ile gerçek sentez gibi döndürüyor (**P1**) |
| `psychology/dark_triad.py` | 182 | `DarkTriadAnalyzer` ve `strategy_from_depth` | Kanıt alıntısı (`evidence_quotes`) yokken profilin ilk 2 rastgele cümlesini kanıt diye etiketleyip `measured=True` yapıyor (**P1**) |
| `nlp/dark_nlp.py` | 103 | Temsil sistemi (V/A/K), gömülü komut ve önvarsayım zinciri | `beliefs` girdi doğrulaması eksik (**P3**) |
| `workers/agent_worker.py` | 375 | Redis liveness beacon işçisi | `SIGTERM` altında `loop.stop()` yüzünden `alive=False` son sinyali gönderilemiyor (**P2**) |
| `utils/security.py` | 501 | Token doğrulama, SSRF DNS sabitleme, gizli anahtar maskeleme | `PINEAL_ENV` varsayılanı `vault_gate.py` ile uyumsuz (**P1**) |

---

## 2. Detaylı Denetim Bulguları (P0 – P3)

---

### [P0-1] `InstagramGhostScraper._paginate_grid`: İlk gönderi detayına gidildiğinde ana profil sayfasından çıkılması (Grid Pagination tamamen kırık)
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\scraper\instagram_ghost.py:944-992` ve `884-892`
- **Kanıt:**
  ```python
  # instagram_ghost.py:953-988
  for _ in range(max_scrolls):
      if len(collected) >= target_count:
          break
      try:
          await playwright_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
          ...
          anchors = await playwright_page.query_selector_all("a[href]")
      ...
      for code in new_codes:
          if len(collected) >= target_count:
              break
          post = await self._post_from_detail_page(playwright_page, code)  # <-- AYNI page NESNESİ!
  ```
  ```python
  # instagram_ghost.py:884-892
  async def _post_from_detail_page(self, playwright_page: Any, shortcode: str) -> Optional[InstagramPost]:
      post_url = f"{self.base_url}/p/{shortcode}/"
      try:
          await playwright_page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
  ```
- **Önem Derecesi:** **P0 (Kritik Mantık Hatası / Instagram Scraper Engelleyici)**
- **Açıklama:** `_paginate_grid` fonksiyonu profil sayfasını aşağı kaydırıp (`window.scrollTo`) yeni gönderi linklerini toplamak için tasarlanmıştır. Ancak döngünün ilk turunda bulunan ilk `shortcode` için `self._post_from_detail_page(playwright_page, code)` çağrılır ve bu fonksiyon **aynı `playwright_page` sekmesini** `/p/{shortcode}/` adresine yönlendirir (`goto`). Sayfa artık profil grid'inde değil, tekil gönderi sayfasındadır! Sonraki kaydırma (`scrollTo`) ve `query_selector_all("a[href]")` işlemleri profil yerine son açılan gönderi sayfasında çalışır; dolayısıyla grid sayfalama ilk turdan sonra tamamen bozulur.
- **Düzeltme Talimatı:**
  1. `_paginate_grid` içinde önce tüm `max_scrolls` boyunca yalnızca profil sayfasında kalıp `seen_codes` / `ordered_codes` listesini `target_count` sınırına kadar toplayın (`goto` yapmadan).
  2. Kaydırma döngüsü bittikten **sonra** (veya `playwright_page.context.new_page()` ile açılan ayrı bir detay sekmesi üzerinden) `ordered_codes` listesindeki her `code` için `_post_from_detail_page` çağrısını çalıştırın.

---

### [P0-2] `HindsightMemory.merge_evidence`: Üst sınıf `CanonicalMemory.merge_evidence` ile imza uyumsuzluğu (`TypeError`)
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\hindsight_memory.py:194-199` vs `C:\Projects\pineal-epifiz\agent_core\services\canonical_memory.py:181-186`
- **Kanıt:**
  ```python
  # canonical_memory.py:181-186
  async def merge_evidence(
      self,
      task_id: str,
      evidence_chain: List[Dict],
      metadata: Optional[Dict] = None,
  ) -> Dict[str, Any]:
  ```
  ```python
  # hindsight_memory.py:194-199
  async def merge_evidence(self, task_id: str, evidence_chain: List[Dict]):
      """Override CanonicalMemory.merge_evidence to also index into SQLite."""
      result = await super().merge_evidence(task_id, evidence_chain)
  ```
- **Önem Derecesi:** **P0 (Çalışmayan Entegrasyon / Bellek & Vektör DB Hatası)**
- **Açıklama:** `PINEAL_MEMORY_ENGINE=hindsight` etkinleştirildiğinde `get_memory_engine()` `HindsightMemory` döndürür. Ancak `HindsightMemory.merge_evidence`, üst sınıftaki `metadata: Optional[Dict] = None` parametresini kabul etmez ve `super().merge_evidence(task_id, evidence_chain)` çağrısına iletmez. `metadata` geçiren herhangi bir çağrıda çalışma zamanında `TypeError: HindsightMemory.merge_evidence() takes 3 positional arguments / unexpected keyword argument 'metadata'` fırlatılır.
- **Düzeltme Talimatı:** `HindsightMemory.merge_evidence` imzasını `async def merge_evidence(self, task_id: str, evidence_chain: List[Dict], metadata: Optional[Dict] = None) -> Dict[str, Any]:` olarak güncelleyin ve `await super().merge_evidence(task_id, evidence_chain, metadata=metadata)` çağrısı yapın.

---

### [P0-3] `MinorGate` (Çocuk Koruma Kırmızı Çizgisi): Yalnızca operatör beyanına bağlı ve CLI / Shadow / TaskExecutor yollarında devre dışı
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\safety\minor_gate.py:177-178` ve `C:\Projects\pineal-epifiz\agent_core\capabilities\runner.py:78-102`
- **Kanıt:**
  ```python
  # safety/minor_gate.py:177-178
  if case is None or not case.subject_is_minor:
      return MinorDecision.allow("not_minor")
  ```
- **Önem Derecesi:** **P0 (Güvenlik ve Etik Kırmızı Çizgi Açığı)**
- **Açıklama:** Hedefin 18 yaş altı olup olmadığı biyografi, doğum yılı, okul bilgisi veya görsel/metinsel sinyallerden otomatik olarak hiç denetlenmemektedir. Operatör `subject_is_minor=True` bayrağını elle göndermediği sürece kapı her zaman `allow("not_minor")` döner. Üstelik `MinorGate` yalnızca `CapabilityRunner.run` ve `backend/api.py` içinde çağrılmakta; `shadow/shadow_executor.py` ve `scraper/run_scraper.py` CLI yolları bu kapıdan hiç geçmemektedir.
- **Düzeltme Talimatı:**
  1. `task_executor.py`, `shadow/shadow_executor.py` ve `scraper/run_scraper.py` giriş noktalarına zorunlu `MinorGate.evaluate` kontrolü ekleyin.
  2. Kazınan profil biyografisi/gönderilerinde yaş sinyali (ör. `<18` yaş ifadeleri, lise/ortaokul ibareleri, doğum yılı `> current_year - 18`) yakalayan deterministik bir ön-denetleyici (`detect_minor_signals(profile_data)`) yazarak eşleşme halinde otomatik `MinorGate` kilidi tetikleyin.

---

### [P1-1] `vault_gate.py` vs `security.py`: `PINEAL_ENV` ortam tespiti çelişkisi (Varsayılan durumda Kasa Kilidi Fail-Open)
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\scraper\vault_gate.py:171-185`, `C:\Projects\pineal-epifiz\agent_core\utils\security.py:77-86`, `C:\Projects\pineal-epifiz\agent_core\workers\agent_worker.py:134`
- **Kanıt:**
  ```python
  # scraper/vault_gate.py:171 & 183-185
  production = os.getenv("PINEAL_ENV", "").strip().lower() == "production"
  ...
  if not production:
      return True, "dev_boundary_deferred"
  ```
  ```python
  # utils/security.py:77-86
  def _is_production() -> bool:
      return _environment_name() not in _DEVELOPMENT_ENVIRONMENTS
  ```
- **Önem Derecesi:** **P1 (Güvenlik Açığı — Kasa Kilidi Atlatma)**
- **Açıklama:** `security.py` içinde `PINEAL_ENV` tanımsız (`""`), `prod` veya `staging` olduğunda sistem **production (fail-closed)** kabul edilirken; `vault_gate.py` yalnızca tam `"production"` dizgesini üretim saymaktadır. `PINEAL_ENV` ayarlanmamış bir sunucuda `.pineal_vault.json` hiç olmasa veya kilitli olsa bile `vault_gate.check()` `(True, "dev_boundary_deferred")` dönerek tüm OSINT/scraper çıkışlarına izin verir.
- **Düzeltme Talimatı:** `utils/security.py` içindeki `_is_production()` fonksiyonunu `is_production()` olarak dışa aktarın ve `vault_gate.py:171` ile `workers/agent_worker.py:134` içinde tek kaynak olarak bu fonksiyonu çağırın.

---

### [P1-2] `InstagramGhostScraper`: Türkçe binlik/ondalık sayı ayrıştırma hatası, 24 gönderi tavanı ve bozuk DOM bio/link enjeksiyonu
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\scraper\instagram_ghost.py:325-327`, `367-402`, `413`, `1074-1092`
- **Kanıt:**
  ```python
  # instagram_ghost.py:325-327 (_collect_structured_posts)
  if len(found) >= 24:
      return
  ```
  ```python
  # instagram_ghost.py:367-376 (_parse_num)
  s = s.strip().upper().replace(",", "")
  try:
      if "M" in s:
          return int(float(s.replace("M", "").strip()) * 1_000_000)
      if "K" in s:
          return int(float(s.replace("K", "").strip()) * 1_000)
      return int(float(s.replace(".", "")))
  ```
  ```python
  # instagram_ghost.py:1082-1091 & 413
  safe_bio = dom_bio_text.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
  html += f'\n<meta content="Instagram\'da: &quot;{safe_bio}&quot;" />'
  for elink in dom_ext_links:
      html += f'\n<link rel="me" href="{elink}" />'
  # Satır 413:
  bio_match = re.search(r'(?:Instagram\'da|on Instagram):\s*&quot;([^&]*)&quot;', html)
  ```
- **Önem Derecesi:** **P1 (VeriBozulması / Scraper Ayrıştırma Hatası)**
- **Açıklama:**
  1. **Türkçe Sayı Bozulması (`367-376`):** Türkçe `og:description` içinde `"1,5M Takipçi"` veya `"12,4B Takipçi"` (Bin = `B`) yazar. `_parse_num` önce virgülü siler (`"1,5M"` -> `"15M"` -> **15.000.000**, 10 kat şişirme!), `"B"` (Bin) sonekini ise hiç tanımaz ve `ValueError` ile `0` döndürür. Ayrıca `"1.250K"` gibi noktalı ifadelerde `float("1.250") * 1000` yanlış çalışır.
  2. **Sabit 24 Gönderi Tavanı (`325-327`):** `DEFAULT_MAX_POSTS = 48` olmasına rağmen `_collect_structured_posts` içindeki `_walk` `len(found) >= 24` sınırında durmaktadır.
  3. **DOM Bio `&` Kırpılması ve Ölü `<link rel="me">` Kodu (`1074-1092`):** `dom_bio_text` içindeki `&` karakteri kaçırılmaz ama satır 413'teki regex `([^&]*)` kullandığı için biyografideki ilk `&` karakterinde metin kesilir. Ayrıca `dom_ext_links` HTML sonuna `<link rel="me" href="...">` olarak eklenir fakat `_parse_real_profile` içinde `<link rel="me">` arayan hiçbir kod yoktur (tamamen ölü kod).
- **Düzeltme Talimatı:**
  1. `_parse_num` içinde Türkçe ondalık virgülü (`1,5M` -> `1.5M`) ve Türkçe `"B"` / `"BİN"` sonekini (`* 1_000`) destekleyin.
  2. Satır 325'teki `24` sabitini `self._max_posts()` (veya parametre olarak geçirilen `max_posts`) ile değiştirin.
  3. `dom_bio_text` ve `dom_ext_links` değerlerini HTML'e sahte meta/link etiketi olarak gömmek yerine doğrudan `_parse_real_profile(..., dom_bio=dom_bio_text, dom_links=dom_ext_links)` parametreleri olarak geçirin.

---

### [P1-3] `LLMGateway`: `query_json` 9Router/Vision model seçimini eziyor ve `route_diagnostics` ile `agent_route_variants` birbirini tutmuyor
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\llm_gateway.py:1798-1810`, `1993-1995`, `3370-3393`
- **Kanıt:**
  ```python
  # llm_gateway.py:3385-3393 (query_json)
  selected_model = model or (self.TIER_1_MODEL if tier == 1 else self.TIER_2_MODEL)
  ...
  response = await self.query(
      prompt=full_prompt,
      system_prompt=json_system_prompt,
      temperature=temperature,
      model=selected_model,
      tier=tier,
  )
  ```
  ```python
  # llm_gateway.py:2934-2939 (query)
  if "20128" in self.openrouter_base_url and not model:
      selected_model = self._default_9router_model(tier=tier, has_images=bool(images))
  elif images and not model:
      selected_model = self.VISION_MODEL
  ```
- **Önem Derecesi:** **P1 (Kırık LLMGateway Fallback / Yönlendirme Hatası)**
- **Açıklama:**
  1. `query_json` çağrıldığında `model=None` olsa bile `selected_model` hemen `self.TIER_1_MODEL` / `self.TIER_2_MODEL` (OpenRouter model ID'si) olarak doldurulup `self.query(..., model=selected_model)` çağrılır. Bu yüzden `self.query` içindeki `if "20128" in self.openrouter_base_url and not model:` dalına **asla girilemez** ve 9Router'a varsayılan `free-unlimited`/`pineal-quick` yerine OpenRouter model adı gönderilir.
  2. `agent_route_variants` (satır 1993) `_tier_route_decision` kullanarak `simple` ajanlarda ücretli rotaları engellerken ve `heavy` ajanlarda indirimli doğrudan sağlayıcıları (`PINEAL_ALLOW_PAID_ESCALATION` olmasa bile) açarken; `route_diagnostics` (satır 1798) `_active_agent_tier` bağlamını tamamen yok sayar. Bu durum kokpit tanılaması ile gerçek yürütme rotalarının ayrışmasına yol açar.
- **Düzeltme Talimatı:**
  1. `query_json` içinde `model=model` (yani `None` ise `None`) değerini doğrudan `self.query` fonksiyonuna iletin; model çözümlemesini yalnızca `self.query` yapsın.
  2. `route_diagnostics` içinde `paid_escalation_enabled()` kontrolü yerine `self._tier_route_decision(variant)` çağrısını kullanın.

---

### [P1-4] `HindsightMemory.semantic_search`: Görevler arası (`task_id=None`) aramada `task_id` bilgisinin kaybolması (`None` dönmesi)
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\hindsight_memory.py:242-258` ve `283-294`
- **Kanıt:**
  ```python
  # hindsight_memory.py:249-258 (_fetch_rows)
  else:
      cursor = conn.execute(
          "SELECT fact_id, text_content, source, confidence, embedding, timestamp "
          "FROM semantic_memories"
      )
  ```
  ```python
  # hindsight_memory.py:283-290 (semantic_search)
  results.append({
      "fact_id": row[0],
      "text": row[1],
      "source": row[2],
      "confidence": row[3],
      "task_id": task_id,  # <-- task_id parametresi None ise her zaman None yazar!
  ```
- **Önem Derecesi:** **P1 (Bellek / Vektör DB Veri Kaybı)**
- **Açıklama:** `semantic_search(query, task_id=None)` tüm görevler üzerinde çapraz semantik arama yapmak için tasarlanmıştır. Ancak `_fetch_rows` SQL sorgusunda `task_id` sütununu seçmez ve `semantic_search` sonuç sözlüğüne `"task_id": task_id` (yani `None`) yazar. Bulunan kanıtın hangi görevden geldiği tamamen kaybolur. Ayrıca `self.dedup_threshold` (`satır 64`) tanımlanmasına rağmen kodun hiçbir yerinde kullanılmamaktadır.
- **Düzeltme Talimatı:** `_fetch_rows` içindeki her iki `SELECT` sorgusuna `task_id` sütununu ekleyin ve sonuç sözlüğünde `"task_id": row[6]` olarak gerçek veritabanı değerini döndürün.

---

### [P1-5] `BrowserSession`: Alan adı beyaz listesi (`_ALLOWED_DOMAINS`) kontrolünün `goto` sonrasında yapılması ve `click`/`press` navigasyonlarında hiç yapılmaması
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\browser_session.py:131-141` ve `203-236`
- **Kanıt:**
  ```python
  # browser_session.py:131-139
  await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
  final_url = page.url
  if not _domain_ok(final_url):
      raise ValueError(f"Yonlendirme izin verilmeyen alana gitti: {final_url}")
  ```
  ```python
  # browser_session.py:203-211 (click)
  async def click(self, selector: str) -> Dict[str, Any]:
      async with self._lock:
          page = self._require_page()
          await page.click(selector, timeout=8_000)
          await page.wait_for_timeout(600)
          return await self._snapshot()
  ```
- **Önem Derecesi:** **P1 (Güvenlik Açığı — Tarayıcı Alan Adı Sınırı Aşımı)**
- **Açıklama:** `open()` metodunda hedef URL izin verilmeyen bir alana yönlendirildiğinde `ValueError` fırlatılır ancak `self._page` o yasaklı sayfada **açık bırakılır**; sonraki `state()` veya `click()` çağrıları yasaklı sayfayı okumaya ve ekran görüntüsünü almaya devam eder. Ayrıca `click()`, `press()` veya `back()` ile gerçekleşen sayfa geçişlerinde `_domain_ok(page.url)` hiç kontrol edilmez.
- **Düzeltme Talimatı:** `_domain_ok(page.url)` kontrolünü `_snapshot()` öncesinde merkezi bir `_enforce_domain_guard(page)` yardımcı metoduna taşıyın; ihlal durumunda `await page.goto("about:blank")` çalıştırıp `ValueError` fırlatın.

---

### [P1-6] `maigret_scanner.py`: Egress omurgası ve `vault_gate` (Kasa Kilidi) tamamen atlanarak doğrudan ağ taraması yapılması
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\maigret_scanner.py:202-216` ve `219-265`
- **Kanıt:**
  ```python
  # maigret_scanner.py:202-216
  async def _run_library_scan(username: str, site_dict: Dict[str, object], timeout: int):
      from maigret.maigret import maigret as maigret_fn
      return await maigret_fn(username, site_dict, _SILENT_LOGGER, timeout=timeout, ...)
  ```
- **Önem Derecesi:** **P1 (Mimari Güvenlik İhlali — Kasa Kilidi ve Sorumluluk Zinciri Bypass)**
- **Açıklama:** `holehe_scanner.py:113-115` içinde `require_open(purpose="osint")` ve `open_client(purpose="osint")` zorunlu tutulurken; `maigret_scanner.py` kendi `aiohttp` istemcisini kullanan `maigret_fn` çağrısını yapmadan önce `vault_gate.require_open(purpose="osint")` kontrolünü **hiç çağırmaz** ve `egress` Sorumluluk Zinciri'ne (`EgressAttempt`) hiçbir iz bırakmaz.
- **Düzeltme Talimatı:** `scan_username` içinde `_run_library_scan` çağrısından hemen önce `from agent_core.scraper.vault_gate import require_open; require_open(purpose="osint")` kontrolünü ekleyin.

---

### [P1-7] `frame_evidence.py`: `decode_image` içinde `.convert("RGB")` çağrısının EXIF verisini silmesi (`extract_exif` her zaman boş)
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\frame_evidence.py:242-248` ve `343-355`
- **Kanıt:**
  ```python
  # frame_evidence.py:242-248
  def decode_image(data: bytes) -> Optional["Image.Image"]:
      ...
      with Image.open(io.BytesIO(data)) as image:
          image.load()
          return image.convert("RGB")
  ```
  ```python
  # frame_evidence.py:345-355
  image = decode_image(data)
  ...
  exif = extract_exif(image)
  ```
- **Önem Derecesi:** **P1 (Çalışmayan Özellik — Görsel Adli EXIF Çıkarımı Kaybı)**
- **Açıklama:** Pillow'da `image.convert("RGB")` yeni bir `Image` nesnesi döndürür ve `with Image.open(...)` bloğu kapandığında orijinal görüntüye ait `_getexif` / format-özel EXIF okuyucusu kaybolur. Bu nedenle `extract_frame_features` içindeki `extract_exif(image)` gerçek JPEG/TIFF karelerde bile EXIF etiketlerini (`DateTimeOriginal`, `Make`, `Model`, GPS) kaçırır.
- **Düzeltme Talimatı:** `decode_image` içinde `with Image.open(...) as image:` bloğu kapanmadan önce `exif = extract_exif(image)` bilgisini okuyun (veya `rgb = image.convert("RGB"); rgb.info["exif"] = image.info.get("exif")` ile EXIF baytlarını koruyun).

---

### [P1-8] `deep_profile_resolver.py`: Tek bir rotada `socid_extractor` eksikse tüm derin profil tarama planının iptal edilmesi
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\deep_profile_resolver.py:243-253`
- **Kanıt:**
  ```python
  # deep_profile_resolver.py:243-253
  needs_socid = any(route.capability_id == CAPABILITY_SOCID for route in plan.routes)
  if needs_socid and not module_available("socid_extractor"):
      return DeepProfileResolution(
          records={},
          channel_status=not_run(
              CHANNEL_DEEP_SCAN,
              reason="dependency_missing:socid_extractor",
              detail="Requires optional dependency socid-extractor",
          ),
      )
  ```
- **Önem Derecesi:** **P1 (Mantık Hatası — Çalışan Instagram/X Taramalarının Engellenmesi)**
- **Açıklama:** `plan.routes` içinde hem Instagram/X (`profile.deep.instagram`, `profile.deep.x`) hem de genel bir profil URL'si (`osint.socid.extract`) bulunduğunda, sistemde `socid_extractor` kurulu değilse fonksiyon daha döngüye girmeden **tüm planı** iptal eder. Instagram ve X yetenekleri `socid_extractor` paketine ihtiyaç duymadığı halde hiç çalıştırılmaz.
- **Düzeltme Talimatı:** Erken dönüşü (`return DeepProfileResolution(...)`) kaldırın; `socid_extractor` kontrolünü yalnızca `route.capability_id == CAPABILITY_SOCID` olan rotalar için döngü içinde uygulayın veya yalnız tüm rotalar `CAPABILITY_SOCID` ise erken dönün.

---

### [P1-9] `ShadowExecutor` ve `DarkTriadAnalyzer`: LLM çöktüğünde veya kanıt alıntısı yokken sahte/statik çıktının `measured=True` / `data_confidence=True` olarak işaretlenmesi
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\shadow\shadow_executor.py:345-378` ve `C:\Projects\pineal-epifiz\agent_core\psychology\dark_triad.py:67-101`
- **Kanıt:**
  ```python
  # shadow_executor.py:357-376
  if not pattern_message:
      pattern_message = strategy.get("tactic") or strategy.get("vector") or "Doğal ve dengeli ilk temas."
  ...
  return ShadowExecutionOutput(
      ...
      synthesized_message=pattern_message,
      data_confidence=True,
      fallback_reason=None,
  )
  ```
  ```python
  # psychology/dark_triad.py:70-72 & 100
  if not valid_quotes:
      texts = self._collect_texts(profile_data)
      valid_quotes = [t for t in texts if len(t.split()) >= 4][:3]
  ...
  measured = True
  ```
- **Önem Derecesi:** **P1 (Anti-Halüsinasyon Sözleşmesi İhlali / Sahte Kanıt Üretimi)**
- **Açıklama:**
  1. `ShadowExecutor.execute` içinde hem Mirror LLM hem de PatternInterrupt LLM çağrısı hata verdiğinde (`mirror_failed` + `pattern_failed`), kod statik `"Doğal ve dengeli ilk temas."` metnine düşmekte fakat çıktıyı `data_confidence=True, fallback_reason=None` ile sanki LLM başarıyla mesaj sentezlemiş gibi döndürmektedir.
  2. `DarkTriadAnalyzer.analyze` içinde `depth_data` `verdict="ok"` döndüğünde fakat hiçbir `evidence_quotes` bulunmadığında, satır 72 profilin ilk 3 rastgele cümlesini (`len(t.split()) >= 4`) narsisizm/makyavelizm/psikopati kanıt alıntısı olarak atamakta ve `measured=True` yapmaktadır.
- **Düzeltme Talimatı:**
  1. `shadow_executor.py` içinde her iki LLM çağrısı da başarısız olduğunda `self._fallback("llm_synthesis_failed", ...)` döndürün (`data_confidence=False`).
  2. `dark_triad.py:70-72` içindeki rastgele metin dilimleme (`texts[:3]`) yedeklemesini kaldırın; gerçek kanıt alıntısı yoksa ilgili özelliğin `evidence_quotes` listesini boş bırakın ve `measured=False` olarak işaretleyin.

---

### [P1-10] `media_forensics.py`: `fetch_media` içinde `yt-dlp` yarış durumu, `open_client` yönlendirme SSRF açığı ve `subprocess.run` ile event-loop bloklaması
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\media_forensics.py:184-195`, `211`, `439`, `495`
- **Kanıt:**
  ```python
  # media_forensics.py:184-195
  proc = subprocess.run(
      [exe, "-o", str(target_dir / "%(id)s.%(ext)s"), "--no-playlist", value],
      capture_output=True, timeout=timeout,
  )
  ...
  newest = max(target_dir.glob("*"), key=lambda p: p.stat().st_mtime, default=None)
  ```
  ```python
  # media_forensics.py:211
  async with open_client(purpose="media", target=str(value)[:200], timeout=timeout, follow_redirects=True) as client:
  ```
- **Önem Derecesi:** **P1 (Güvenlik / Eşzamanlılık / Event-Loop Bloklama Hatası)**
- **Açıklama:**
  1. **Eşzamanlı Dosya Karışması ve Bayat Dosya Seçimi (`184-195`):** `yt-dlp` zaten indirilmiş bir dosyayı tekrar indirmezse `st_mtime` güncellenmez ve `max(target_dir.glob("*"), key=st_mtime)` başka bir göreve ait en son dosyayı (hatta `index.json` dosyasını!) döndürür.
  2. **Redirect SSRF (`211`):** İlk URL için `net_hygiene.is_private_host(host)` kontrol edilse de `follow_redirects=True` ile açılan `open_client` 302 yönlendirmeyle `http://127.0.0.1/...` veya iç ağ adreslerine yönlendirildiğinde özel IP kontrolü yapılmaz.
  3. **Async Fonksiyon İçinde Bloklayıcı `subprocess.run` (`184, 439, 495`):** `async def fetch_media` ve `async def transcribe` doğrudan `subprocess.run(..., timeout=600)` çağırarak tüm `asyncio` event loop'unu dakikalarca dondurur.
- **Düzeltme Talimatı:**
  1. `yt-dlp` çağrısında `--print after_move:filepath` argümanını kullanarak indirilen dosyanın tam yolunu stdout'tan okuyun ve `index.json` dosyasını glob dışında tutun.
  2. `follow_redirects=False` kullanın veya her yönlendirme adımında `net_hygiene.is_private_host` doğrulaması yapın.
  3. `subprocess.run` çağrılarını `await asyncio.to_thread(subprocess.run, ...)` ile sarmalayın.

---

### [P2-1] `InstagramGhostScraper._parse_dt`: Milisaniye (ms) Unix epoch zaman damgalarında çökme
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\scraper\instagram_ghost.py:204-225`
- **Kanıt:**
  ```python
  # instagram_ghost.py:204-213
  """ISO-8601 veya unix-epoch (sn/ms) degerini UTC ISO-8601 dizgesine cevirir."""
  if isinstance(value, (int, float)) and not isinstance(value, bool):
      try:
          return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
      except (OSError, OverflowError, ValueError):
          return None
  ```
- **Önem Derecesi:** **P2 (Mantık Hatası)**
- **Açıklama:** Docstring hem saniye hem milisaniye (`sn/ms`) desteklediğini belirtir; ancak `value > 1e11` (ör. `1700000000000` ms) olduğunda `1000.0`'a bölünmediği için Windows'ta `OSError`/`ValueError` fırlatılır ve `None` döner.
- **Düzeltme Talimatı:** `ts = float(value); ts = ts / 1000.0 if ts > 1e11 else ts` dönüşümünü ekleyin.

---

### [P2-2] `LLMGateway.start_chat_stream`: Async generator `finally` bloğunda `GeneratorExit` hatası ve eksik RTK sıkıştırması
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\llm_gateway.py:3000-3030` ve `3273-3280`
- **Kanıt:**
  ```python
  # llm_gateway.py:3273-3280
  finally:
      await close_upstream()
      await self._settle_budget(...)
  ```
- **Önem Derecesi:** **P2 ( Çalışma Zamanı Hatası — `RuntimeError: async generator ignored GeneratorExit`)**
- **Açıklama:** İstemci SSE akışını erken kapattığında Python async generator içine `GeneratorExit` fırlatır. `finally:` bloğu içinde `GeneratorExit` yakalanmadan `await close_upstream()` çalıştırıldığında Python `RuntimeError: async generator ignored GeneratorExit` fırlatır ve altındaki `self._settle_budget(...)` çağrısına ulaşılamadığı için bütçe rezervasyonu asla kapatılmaz (bütçe sızıntısı). Ayrıca `start_chat_stream`, `query` ve `chat_completion`'ın aksine `_compress_chat_messages` (RTK sıkıştırması) uygulamamaktadır.
- **Düzeltme Talimatı:** `close_upstream()` ve `_settle_budget()` işlemlerini `asyncio.create_task(...)` ile arka plana alın veya `except GeneratorExit:` bloğunda senkron kapanış planlayın; `start_chat_stream` başında `messages = self._compress_chat_messages(messages, ...)` çağrısını ekleyin.

---

### [P2-3] `HindsightMemory`: `semantic_search` ve `merge_evidence` içinde `SentenceTransformer` yükleme ve embedding işlemlerinin event loop'u bloklaması
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\hindsight_memory.py:130-156`, `205`, `271`
- **Kanıt:**
  ```python
  # hindsight_memory.py:271
  query_vec = self._embed(query)
  ```
- **Önem Derecesi:** **P2 (Performans / Event-Loop Bloklama)**
- **Açıklama:** `async def semantic_search` ve `async def merge_evidence` içinden çağrılan `self._embed(...)`, ilk çağrıda `SentenceTransformer("all-MiniLM-L6-v2")` modelini diskten/ağdan senkron olarak yükler ve CPU üzerinde vektör hesaplamasını doğrudan `asyncio` ana döngüsünde çalıştırır.
- **Düzeltme Talimatı:** `self._embed` ve `self._index_evidence_chain` çağrılarını `await asyncio.to_thread(...)` üzerinden çalıştırın.

---

### [P2-4] `memory_crystal.py`: Eşzamanlı görevlerde hedef kristal dosyası (`memory/crystals/<slug>.json`) için kilit eksikliği
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\memory_crystal.py:282-340`
- **Kanıt:**
  ```python
  # memory_crystal.py:293-339
  existing = load_crystal(target)
  ...
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_suffix(".json.tmp")
  tmp.write_text(json.dumps(payload, ...), encoding="utf-8")
  os.replace(tmp, path)
  ```
- **Önem Derecesi:** **P2 (Eşzamanlılık / Yarış Durumu)**
- **Açıklama:** Aynı hedef (`target`) için çalışan iki paralel görev aynı `.json.tmp` dosya adını (`<slug>.json.tmp`) kullanır ve kilitsiz (`lock` olmadan) okuma-değiştirme-yazma yapar. Biri diğerinin yazdığı kanıtları ezer veya Windows'ta `os.replace` sırasında `PermissionError` oluşur.
- **Düzeltme Talimatı:** Hedef `slug` başına bir `threading.Lock()` tablosu ekleyin ve geçici dosya adına `uuid4().hex[:8]` soneki verin.

---

### [P2-5] `redis_bus.py`: Senkron `redis` paketine düşüldüğünde `disconnect()` bağlantıyı kapatmıyor
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\redis_bus.py:189-196`
- **Kanıt:**
  ```python
  # redis_bus.py:189-196
  async def disconnect(self) -> None:
      if self._client and aioredis:
          try:
              await self._client.close()
          except Exception:
              pass
          self._client = None
  ```
- **Önem Derecesi:** **P2 (Kaynak Sızıntısı)**
- **Açıklama:** `aioredis` (`redis.asyncio`) yokken modül senkron `redis.from_url` istemcisine düşer (`satır 59`). Ancak `disconnect()` yalnızca `if self._client and aioredis:` koşulunda kapanış yapar; senkron istemci açık kalır ve `self._use_redis` bayrağı `False`'a çekilmez.
- **Düzeltme Talimatı:** `disconnect()` içinde `aioredis` yoksa `self._client.close()` çağırın, `self._client = None` ve `self._use_redis = False` atamalarını her durumda yapın.

---

### [P2-6] `workers/agent_worker.py` ve `scraper/run_scraper.py`: Sinyal ve çıkış kodu yönetim hataları
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\workers\agent_worker.py:349-371` ve `C:\Projects\pineal-epifiz\agent_core\scraper\run_scraper.py:55-61`
- **Kanıt:**
  ```python
  # agent_worker.py:350 & 368
  loop.add_signal_handler(sig, lambda: loop.stop())
  ...
  loop.run_until_complete(run_worker(args.agent, args.interval))
  ```
  ```python
  # run_scraper.py:55-61
  except Exception as e:
      print(json.dumps({"error": f"Beklenmeyen hata: {str(e)}", "code": "SCRAPER_ERROR"}))
  ```
- **Önem Derecesi:** **P2 (Operasyonel Güvenilirlik Hatası)**
- **Açıklama:**
  1. `agent_worker.py` içinde `SIGTERM` geldiğinde `loop.stop()` çağrıldığı için `run_worker` içindeki `except asyncio.CancelledError:` bloğu hiç çalışmaz ve Redis'e son `alive=False` (offline) sinyali gönderilmez; işçi kokpitte çevrimiçi görünmeye devam eder.
  2. `run_scraper.py` hata yakaladığında JSON basıp `0` çıkış koduyla (`exit code 0`) sonlanır.
- **Düzeltme Talimatı:** `agent_worker.py` içinde ana görevi `task = loop.create_task(run_worker(...))` olarak başlatıp sinyal yakalayıcıda `task.cancel()` çağırın. `run_scraper.py` hata bloklarının sonuna `sys.exit(1)` ekleyin.

---

### [P3-1] `nlp/dark_nlp.py` ve `services/memory_injector.py`: Bozuk girdi tiplerinde `TypeError`
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\nlp\dark_nlp.py:96-101` ve `C:\Projects\pineal-epifiz\agent_core\services\memory_injector.py:102-103`
- **Kanıt:**
  ```python
  # dark_nlp.py:98
  sentence = template.replace("{X}", belief).replace("{Y}", "bu doğal bir süreç")
  # memory_injector.py:102-103
  elif "hash" not in rule:
      unique_rules[rule.get("fact")] = rule
  ```
- **Önem Derecesi:** **P3 (Savunmacı Programlama / Girdi Doğrulama)**
- **Açıklama:** `dark_nlp.py` içinde `beliefs` listesindeki elemanların `str` olduğu doğrulanmaz (`TypeError`). `memory_injector.py` içinde ise `learnings.json` içindeki bir kuralda `"hash"` yok ve `"fact"` alanı liste/sözlük ise `unique_rules[rule.get("fact")]` `TypeError: unhashable type` fırlatır.
- **Düzeltme Talimatı:** `dark_nlp.py` başında `beliefs = [str(b).strip() for b in beliefs if isinstance(b, str) and b.strip()]` filtrelemesi yapın; `memory_injector.py:102` içinde anahtar olarak `str(rule.get("fact") or "")` kullanın.

---

### [P3-2] `services/platform_registry.py`: Sabit kodlanmış `C:\Program Files\Google\Chrome\...` Windows yolları
- **Dosya Yolu + Satır Numarası:** `C:\Projects\pineal-epifiz\agent_core\services\platform_registry.py:394-401`
- **Kanıt:**
  ```python
  # platform_registry.py:396-399
  win_paths = (
      r"C:\Program Files\Google\Chrome\Application\chrome.exe",
      r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  )
  ```
- **Önem Derecesi:** **P3 (Ortam / Sürücü Bağımlılığı)**
- **Açıklama:** Depoda herhangi bir `D:\` sürücüsü bağımlılığı bulunmamıştır (`Select-String` ile tüm `agent_core` tarandı). Ancak `platform_registry.py` içinde Chrome ikili dosyası aranırken yalnızca `C:\Program Files...` sabit yollarına bakılmakta; kullanıcı yerel kurulumu (`%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`) veya `CHROME_PATH` ortam değişkeni kontrol edilmemektedir.
- **Düzeltme Talimatı:** `os.getenv("CHROME_PATH")` ve `os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")` yollarını da arama listesine ekleyin.

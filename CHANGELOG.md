# Changelog

## Unreleased — 2026-10-05 — FAZ B · BEYİN & HAFIZA (1): spektrum, gerçek örgü, değişim izleme

- **B6 · GERÇEK SPEKTRAL ANALİZ (FFT).** `FrequencyReport.dominant_period_days`
  declared ama HİÇ doldurulmayan bir kabuktu. Artık `agent_core/engines/
  spectrum.py` ile ÖLÇÜLÜYOR: Hann pencereli `rfft` periodogramı, DC ve Nyquist
  hariç, normalize güç spektrumu. Harmonik tuzağı çözüldü — haftalık dürtü
  treninde 2.33/3.5 gün değil **7 gün** temel periyot raporlanır. Yetersiz kova
  (<8) veya sabit seride periyot **uydurulmaz**: alan `None` + makine-okunur
  sebep (`insufficient_samples` / `flat_signal`). Ölçüm doğrulandı: 7g→7.0g,
  14g→14.0g, saf sinüs 4g→4.0g.
- **B4 · ÖRGÜ ARTIK GERÇEK VERİ ÇİZİYOR.** `HolographicResonanceMesh.svelte`
  içindeki `generateNodes()` (12+8 **rastgele** düğüm) KALDIRILDI. Yerine
  `agent_core/services/graph_builder.py`: düğümler yalnız kanıttan doğar
  (hedef · kaynak sunucu · çıkarıcı motor · gözlem günü), kenarlar yalnız
  birlikte-geçme ilişkisidir. Yerleşim **deterministik** (`Math.random()` yok).
  Yeni uç: `GET /api/tasks/{task_id}/graph`. Kanıt yoksa graf BOŞ — arayüz
  uydurma düğüm çizmez, "KANIT YOK" yazar.
- **B7 · DEĞİŞİM İZLEME.** `agent_core/services/change_tracker.py`: her biten
  görev hedefin geçmişine parmak izi bırakır (`memory/changes/<hedef>.json`),
  ikinci tarama "ne değişti?" sorusunu cevaplar: **+yeni · -kayıp · ~değişen ·
  aynı**. Parmak izi kanıdın KENDİSİNDEN üretilir (`evidence_id` her görevde
  yeniden üretildiği için kullanılmaz); önceki kayıt yoksa fark UYDURULMAZ
  (`no_baseline`). Yeni uç: `GET /api/tasks/{task_id}/changes`.
- **Bellek üst verisi artık SİLİNMİYOR.** `CanonicalMemory.merge_evidence`
  metadata kabul ediyor; eskiden her birleştirmede hedef profili (ve kurtarma
  kaydı) kayboluyordu. `PinealExecutor` artık `target_profile`'ı kanıtla
  birlikte yazıyor — değişim izleme ve graf aynı hedefi kararlı anahtarla
  buluyor.
- **Test:** +35 (spektrum 12 · graf 12 · değişim 11). Tam koşu: **birim
  1291P/0F**, **entegrasyon 88P/0F** — gerileme yok. Frontend: `npm run build`
  + `svelte-check` **0 hata 0 uyarı**.

## Unreleased — 2026-10-05 — FAZ B · BEYİN & HAFIZA (2): konsensüs denetçisi, eşik kalibrasyonu

- **B1 · BAĞIMSIZ JÜRİ KONSENSÜS DENETÇİSİ.** Panel oylarını sayan kod,
  sayımın doğruluğunu KENDİSİNE soruyordu. Artık ikinci ve bağımsız bir kafa
  var: `agent_core/services/jury_consensus.py` oyları yeniden sayar, panelin
  bildirdiği hükümle karşılaştırır ve uyuşmazlığı **gizlemez** (`VerifierReport.
  consensus` + karar kuralında `konsensüs:uyuşmazlık=X/Y yeter_sayı=A/B(q)
  bağlayıcı=evet|hayır`). Yeter sayı altındaki hüküm konsensüs SAYILMAZ; tek
  koltuk "konsensüs" diye geçmez; berabere dürüstçe `BİLİNMİYOR`'a düşer.
  `PINEAL_JURY_QUORUM` (varsayılan 1 = bugünkü davranış) ve
  `PINEAL_JURY_BINDING` (varsayılan **kapalı** = salt denetim). Bağlayıcı kipte
  denetçinin bulduğu hüküm GEÇERLİ olur ve tüm sayılar (doğrulanan/çürütilen/
  kesin/bilinmeyen/skor/güven) yeniden hesaplanır. LLM yok, ağ yok.
- **B5 · EŞİK ARTIK ÖLÇÜLÜYOR (kalibrasyon + geri test + güven aralığı).**
  Sistemin en kritik eşiği **0.70** kodun içine sabitlenmişti ve hiç
  ölçülmemişti. `agent_core/services/threshold_calibration.py`: her eşik kararı
  skoruyla birlikte eklemeli bir ledger'a yazılır (`memory/calibration/`),
  operatör daha sonra **etiket** koyar (karar mercii operatör), eşik o
  etiketlerden kalibre edilir — Youden J ile seçilir, veri azken varsayılana
  çekilir (shrinkage), **Wilson güven aralığı**, **46 adetlik geri test
  ızgarası** ve **güvenilirlik diyagramı (ECE)** ile birlikte raporlanır.
  **Kilit:** etiketli örnek `PINEAL_CALIB_MIN_SAMPLES` (varsayılan 30) altındaysa
  eşik DEĞİŞMEZ ve kaynağı `varsayılan` olarak açıkça yazar — veri olmadan eşik
  değiştirilemez. Elle sabitleme (`PINEAL_THRESHOLD_QUOTE`) her zaman kazanır.
  Ledger'a **ham metin yazılmaz** (yalnız skor + kimlik).
- **Alıntı kapısı ölçülen eşiğe bağlandı.** `quote_guard.quote_matches` artık
  sabit 0.70 kullanmıyor: `resolved_threshold("quote")`'tan okur. Ayrıca korpus
  da normalize ediliyor — eskiden büyük/küçük harf farkı yüzünden kaynakta
  **birebir var** olan alıntı "yok" sayılıp eşiğin altında kalabiliyordu.
  Yeni uçlar: `GET /api/calibration` · `POST /api/calibration/observations` ·
  `POST /api/calibration/adjudicate`. Arayüzde gözün yanında **EŞİK** pili:
  ölçüldüyse yeşil "ÖLÇÜLDÜ", ölçülmediyse gri "ÖLÇÜLMEDİ".
- **Test:** +35 (konsensüs 15 · kalibrasyon 15 · kalibrasyon API 5). Tam koşu:
  **birim 1321P/0F**, **entegrasyon 93P/0F** — gerileme yok. Frontend:
  `npm run build` + `svelte-check` **0 hata 0 uyarı**.

## Unreleased — 2026-10-05 — FAZ A · RETİNA TAMAM: Agent-Reach + SearXNG + Scrapling

- **A3 Agent-Reach (son kademe).** Temiz metin omurgası dört kademeye çıktı:
  trafilatura → crawl4ai → scrapling → **agent-reach**. Sosyal/medya sayfasını
  normal çıkarıcılar alamazsa harici CLI okur (kod gömülmez, API ücreti yok;
  kapı `ENABLE_AGENT_REACH`).
- **X'in ikinci okuma yolu.** twscrape yok/reddedilirse X büsbütün kaybolmuyor:
  `scrape_x` agent-reach'e düşer ve profili **zaman damgası olmadan** kurar
  (uydurma saat YOK). Hangi yolun okuduğu `sensor`/`sensor_note` alanında yazar.
- **A4 SearXNG (ücretsiz arama).** `SearchEngine`, anahtar yokken DuckDuckGo'ya
  ek olarak omurgadan `sensor.search.searxng`'i koşturur; bulgular
  `provider: searxng` işaretli gelir. Ayrı servis (AGPL-3.0) — kod gömülmez,
  yalnız HTTP (`SEARXNG_BASE_URL`). Kasa kapalıyken **dışarı istek çıkmaz**
  (bunu kanıtlayan test: HTTP istemcisi "patlayan" istemciyle değiştirilir).
- **Kasa gerçeği arama motoruna da taşındı.** `SearchEngine.set_policy`;
  `/api/initiate` ve `/api/vault` interlock'tan okuyup yazıyor. Bu sınıf kasa
  kararını **uydurmuyor**, dışarıdan alıyor.
- **A7 Scrapling** kademesi ve kapısı omurgada hazır (`ENABLE_SCRAPLING`).
- **Yeni dosya:** `requirements-retina.txt` — ÜÇÜNCÜ ve isteğe bağlı kurulum
  adımı (trafilatura · scrapling · twscrape · instagrapi). Kurulmazsa ilgili
  yetenek dürüst `dependency_missing` döner; sistemin geri kalanı aynı çalışır.
  `.env.example` + `RUNBOOK.md` tüm Faz A kapılarıyla güncellendi.
- **Test:** +7 (A3/A4/A7) → Faz A toplamı **37 test**. Birim koşusu bazla
  aynı (58F), entegrasyon bazla aynı (16F) — gerileme yok.

## Unreleased — 2026-10-05 — FAZ A · RETİNA: omurga ÜRETİM yoluna bağlandı

- **X deliği KAPANDI.** X artık "yetki bekleyen" bir boşluk değil:
  `platform_registry.scrape_x` → capability omurgası → `sensor.x.twscrape`.
  Sensör kanıt üretemezse profil **uydurulmaz**: görev dürüstçe durur
  (`scripts/run_task.py` → `halted_evidence` + exit 3), API'de ise açık kaynak
  dosyası `platform: web_dossier` olarak işaretlenip devam eder. Eski
  `awaiting_authorization` yolu ve `pending_alternative_authorization` akışı
  kaldırıldı.
- **Uydurma veri temizlendi.** X dalında arama snippet'i biyografi diye
  sunulmuyordu artık sunulmuyor; sabit **`followers: 150`** de kalktı —
  ölçülmeyen alan `None` (0 = ölçüm, None = ölçülmedi).
- **Temiz metin omurgası üretimde.** Public-web araştırması artık tek crawl4ai
  çağrısı değil: `extract_web_text` **trafilatura → crawl4ai → scrapling**
  sırasıyla dener, ilk kanıt üreten kademeyi kullanır ve hangi kademenin
  ürettiğini kayda yazar. Çekilemeyen sonuca alan EKLENMEZ (sözleşme korunur).
- **maigret/holehe artık MÜHÜRLÜ KANIT.** `osint_investigator` taramaları
  doğrudan servise değil omurgaya gider; çıktı `timeline_bridge` ile
  `EvidenceTimeline`'a mühürlenir (`username_scan_evidence` /
  `email_scan_evidence`). Böylece kasa, env kapıları ve **çocuk kilidi**
  otonom görevlerde de uygulanır.
- **Kasa gerçeği payload'a yazılıyor.** `/api/initiate` görev payload'ına
  `{"policy": {"vault_locked": ...}}` enjekte eder; ajanlar kasa durumunu
  tahmin etmez. Tek üretim yeri: `agent_core/capabilities/state.py`.
- **Telemetri dürüstleşti.** `/api/telemetry` alanı `x_scraper` sabit `False`
  değil; sensörün gerçek durumunu omurgadan okur (`_x_sensor_ready`).
- **Yeni dosyalar:** `capabilities/adapters_web.py` · `adapters_sensors.py` ·
  `timeline_bridge.py` · `state.py`. Kayıtlı yetenek: 10.
- **Test:** `tests/unit/test_retina_faz_a.py` (20) +
  `tests/unit/test_retina_faz_a_wiring.py` (10) → 30 yeni test geçiyor.
  Tam birim koşusu: **58F/1177P/5S** — hata sayısı BAZLA AYNI (58), hiçbir
  gerileme yok; entegrasyon koşusu da bazla birebir aynı (16F).

## Unreleased — 2026-10-05 — TEKLİF: "bunlar eklenirse Pineal şu hale gelir"

- **Yeni:** `docs/reports/TEKLIF_TAM_GUC_2026-10-05.md`. Ürün sahibinin üç
  katmanlı tespiti (Retina & Sinir Uçları · Beyin Sapı/Hafıza/Jüri · Ses &
  Yaşayan Epifiz) esas alındı; her depo için **"eklenen → olan"** ve
  **ÖNCE/SONRA** tablosu yazıldı. Ahlaki değerlendirme içermez.
- **Kod okumasıyla tespit edilen mevcut durum:** X sensörü yok
  (`scraper.py:24`, `api.py:2238`) · crawl4ai yalnız tek yerde çağrılıyor
  (`api.py:3433-3436`) · `HolographicResonanceMesh.svelte` **rastgele düğüm
  üretiyor** (gerçek graf verisi yok) · Frequency motorunda FFT yok (sin/cos
  modeli) · maigret/socid çıktısı kanıt zincirine (EvidenceTimeline) girmiyor.
- **Teklifin üstüne eklenen 12 parça:** SearXNG (ücretsiz arama) · Scrapling
  (kırılganlık) · yt-dlp+opencv+PaddleOCR (medya) · pHash+EXIF (catfish) ·
  FFT/periodogram (gerçek spektral analiz) · DuckDB+scikit (zaman serisi +
  kalibrasyon) · değişim izleme · dil tespiti/çeviri · phonenumbers +
  theHarvester/open-seo (kişi + kurum) · MCP + Skills ihracı · yerel jüri ·
  rapor fabrikası.
- **Program:** Faz A Retina → Faz B Beyin & Hafıza → Faz C Ses & Nefes →
  Faz D Birleşim & İhracat; her fazın kabul testiyle.

## Unreleased — 2026-10-05 — AHLAKİ DÖKÜM: 325 depo → 99 fikir

- **Yeni:** `docs/reports/AHLAKI_DOKUM_2026-10-05.md`. 325 depo, aynı fikri
  satan tekrarlarıyla birlikte açıldı; **99 ayrı fikir**e indirildi. Her fikre
  çıplak bir ahlaki hüküm yazıldı.
- **Ahlak testi (3 soru):** (1) Kapıyı mı kırıyor, açık olanı mı okuyor?
  (2) Kırılan şey bir insanın bedeni/kimliği/sesi mi? (3) Başkasının emeğini,
  hesabını veya sırrını mı sömürüyor? Bir cevap bile kötüyse depo biter.
- **Dağılım:** T1 temiz alet 232 depo (67 fikir) · T2 gri 45 depo (14 fikir) ·
  T3 sınır ihlali 10 depo (6) · T4 saldırı/karanlık 16 depo (4) · T5 kimlik
  hırsızlığı 8 depo (2) · T6 hile/asalaklık/yanıltma 14 depo (6).
- **En kalabalık üç fikir:** kullanıcı adı taraması (24 depo), çok ajanlı
  orkestrasyon (20), Agent Skills standardı (14) — yani 325 kaydın büyük
  bölümü birbirinin tekrarı.
- **Kırmızı çizgi ayrı tutuldu:** 18 yaş altı hiçbir sınıfla kıyaslanmaz;
  hükmü Tüzük Madde 4/A ve `agent_core/safety/minor_gate.py` içinde.

## Unreleased — 2026-10-05 — ÇOCUK KIRMIZI ÇİZGİSİ (sistemin TEK kırmızı çizgisi)

- **Ürün sahibi kuralı, değiştirilemez:** 18 yaşından küçük her birey çocuktur.
  Normal koşulda **hiçbir çocuk, hiçbir sebeple araştırılamaz.** Sistemin bildiği
  tek yasak budur. Yetişkin için sistem hiçbir engel koymaz (bkz. K1 iptal).
- **TEK İSTİSNA — kayıp / başına bir şey gelmiş olması (Allah korusun):** bu
  durumda çocuğun KENDİSİ, SOSYAL MEDYASI ve ARKADAŞLARI araştırılabilir, ancak
  dört şartın **tamamı** sağlanmışsa:
  1. **Ailenin bilgisi var** · 2. **Sebep net yazılmış** (≥25 karakter, boş geçilemez)
  · 3. **Doğrulanmış** (emin olunmadan başlanmaz) · 4. **Konsorsiyum onayı** (≥2 farklı onaylayıcı).
  Bir şart eksikse sistem durur ve eksik şartın adını söyler:
  `family_not_notified` / `reason_missing` / `not_verified` / `council_approval_missing` / `case_type_not_allowed`.
- **Yeni:** `agent_core/safety/minor_gate.py` — `MinorGate` (karar), `MinorCaseContext`
  (vaka), `MinorCaseLedger` (kayıt). Koşucu (`runner.py`) bu kilidi politika
  kapılarından **önce**, küresel ve istisnasız uygular: kasa açık olsun olmasın,
  env bayrağı açık olsun olmasın hiçbir yetenek atlayamaz. Kasa hâlâ üstündür
  (onaylı vakada kasa kapalıysa yine koşmaz).
- **Kayıt:** onaylanan ve reddedilen her deneme `memory/ledger/minor-cases.jsonl`
  dosyasına yazılır. Hedefin **ham kimliği dosyaya girmez** (sha256 hash);
  zaman damgası, gerekçe uzunluğu, onaylayıcılar, vaka tipi saklanır.
  `memory/ledger/` `.gitignore`'a eklendi (kayıt depoya girmez).
- **Kilit testleri (yeni):** `tests/unit/test_minor_gate_faz0.py` — 14 test:
  her şartın tek tek engellediği, dört şart tamamken istisnanın çalıştığı,
  kayıtlı **her** yeteneğin çocuk kilidini atlayamadığı, kasanın hâlâ üstün
  olduğu, yetişkinde hiçbir engel olmadığı, kaydın ham kimlik yazmadığı.
- **Tüzük:** yeni **Madde 4/A — Çocuk Kırmızı Çizgisi** (8 bent). Kısa forma
  "TEK KIRMIZI ÇİZGİ: ÇOCUK" satırı eklendi. Karar belgesine **K4** eklendi;
  §9'da Y2 satırı "yetişkin rızası yok → yerine çocuk kilidi" olarak güncellendi.
- **Ölçüm:** `pytest tests/unit` — 58 failed / 1145 passed → 58 failed /
  **1159** passed (+14). **Yeni düşüş yok.**

## Unreleased — 2026-10-05 — DÜZELTME: hedef rızası/yaş kapısı KALDIRILDI

- **Ürün sahibi kararı:** Pineal bir gözlem aracıdır; **rıza makamı hedef değil
  OPERATÖRDÜR.** Önceki turda koyduğum "rıza kaydı olmayan hedefte analiz
  başlamaz" ve "yaş kapısı" kuralları **kaldırıldı.** Sistem, operatörün kendi
  koyduğu kural dışında engel çıkarmaz. Benim uygulamaya kısıtlama koyma
  yetkim yoktu — hatalı bir karardı.
- **Kod:** `consent` kapısı `PolicyKernel`'den ve üç kimlik yeteneğinden
  (`sensor.identity.maigret`, `sensor.identity.holehe`, `extractor.identity.socid`)
  çıkarıldı. Artık `consent` **bilinmeyen kapı** sayılır ve fail-closed
  reddedilir — yani kimse arkadan geri getiremez. Kalan kapılar:
  `vault` (operatörün kendi mandalı), `budget`, `rate`, `ENABLE_*`.
- **Tüzük (Madde 4) yeniden yazıldı:** "Kasa ve rıza" → **"Kasa: yetki
  operatördedir"**. Yeni hükümler: (1) kasa mandalı operatörün iradesidir;
  (2) karar mercii operatör — hedef/sensör/derinlik/sıklık; (3) hedef rızası
  veya yaş kapısı diye bir şey yoktur, eklenmesi tüzük ihlalidir; (4) koşular
  engel değil **operatörün kendi kaydı** olarak tutulur; (5) silme her an
  operatörün elindedir, otomatik saklama engeli yoktur. Kısa form (duvar yazısı)
  güncellendi.
- **Karar belgesi:** §10 K1 "İPTAL EDİLDİ" olarak işaretlendi; §9 boşluk
  matrisinde Y2 satırı "kaldırıldı" olarak değiştirildi; Faz 1 başlığındaki
  rıza şartı kaldırıldı; K1/K2/K3 kapıları `{"vault","rate","ENABLE_X_SENSOR"}`
  oldu; §5.8 kısıtlı yetenekler maddesi "yalnız operatörün kendi kimliğiyle,
  ek izin yok" olarak yeniden yazıldı; K3 karma kapısındaki "rıza" ifadesi
  "operatör" ile değiştirildi.
- **Test:** rıza testi kaldırıldı, yerine **"hedef rıza kapısı geri gelmesin"**
  testi eklendi (`test_no_consent_gate_exists`, `test_person_data_capabilities_carry_vault_gate`).
- **Ölçüm:** `pytest tests/unit` — 58 failed / 1145 passed. **Yeni düşüş yok.**

## Unreleased — 2026-10-05 — TÜZÜK v2 + üç politika kararının kilitlenmesi

- **Tüzük (yeni, yürürlükte):** `docs/PINEAL_TUZUK.md` — **ATLAS PINEAL TÜZÜĞÜ v2**,
  10 madde. Nedeni (Madde 0): sistem kurulurken tek işi "bir insanı analiz et,
  karşısındakiyle tartıya koy, uyuyorlar mı?" idi; sistem o işten büyüdü.
  **Uyum / ilk temas / rezonans artık sistemin TANIMI değil, SAHALARINDAN BİRİDİR**
  (Madde 9). Yeni tanım: *kamuya açık kaynaklar üzerinde çalışan adli gözlem ve
  doğrulama istasyonu.* Eski 4 dokunulmaz ilke tüzüğün Madde 1–4'ü olarak korunur
  (ilke değişmedi, bağlam büyüdü). Yasaklar (Madde 8) ve kısa form (duvar yazısı)
  eklendi. `README.md` §1 ve `ARCHITECTURE.md` bileşen haritası tüzüğe bağlandı.
- **Kilitlenen üç politika kararı** (karar belgesi §10):
  - **K1 · Rıza/yaş kapısı ZORUNLU** → Faz 5'ten **Faz 1'e** çekildi. Rıza kaydı
    olmayan hedefte hiçbir kişi-verisi yeteneği koşmaz; reşit olmayan şüphesinde
    `halted_consent` + gerekçe. `A†` sınıfı yetenekler bu kapı açılmadan açılamaz.
  - **K2 · Platform sensörleri operatörün KENDİ hesabıyla** (X/twscrape dâhil):
    kapılar `{"vault","consent","rate","ENABLE_X_SENSOR"}`; kimlik bilgileri
    log/telemetri/kanıt/rapora sızamaz; anonim-taklit, kiralık hesap havuzu ve
    imza kırma yasak (Tüzük Md.5). Hesapsız ücretsiz yollar (SearXNG, public-web)
    birincil kalır.
  - **K3 · Yerel jüri öne alındı** (donanım mevcut): Faz 8, Faz 2'nin hemen ardına
    **paralel hat** olarak alındı — yerel 3'lü jüri, maliyet 0, veri makineden
    çıkmaz; yerel model yoksa dürüst `UNAVAILABLE` (buluta sessiz düşüş yok).
- **Kod — tüzük yaptırımı:** kişi verisi işleyen tüm yetenekler artık
  `vault` + `consent` kapılarını zorunlu taşır (`sensor.identity.maigret`,
  `sensor.identity.holehe`, `extractor.identity.socid`). Bunu koruyan 3 yeni
  test eklendi (tüzük ↔ kod bağı).
- **Davranış düzeltmesi (önemli):** `PolicyKernel` kapıları artık **alfabetik
  değil öncelik sırasına göre** değerlendirir:
  bilinmeyen kapı → kasa → rıza → bütçe → hız → env bayrakları. Önceden
  `ENABLE_*` bayrakları alfabetik olarak önce geliyor ve **kasa kilidi ihlali
  "gate_disabled" olarak maskeleniyordu** (Tüzük Md.4.1 ihlali). Artık kasa
  kilitliyken sebep her zaman `vault_locked` olur.
- **Ölçüm:** `pytest tests/unit` — önce 58 failed / 1113 passed, sonra
  58 failed / **1145** passed (+32). **Yeni düşüş yok.**

## Unreleased — 2026-10-05 — FAZ 0: Capability Spine + 325 depo karar ağacı

- **Karar belgesi (yeni):** `docs/reports/YILDIZ_DEPO_KARAR_AGACI_2026-10-05.md`.
  325 yıldızlı depo, 8 kapılı karar ağacından (felsefe → zarar → kanıt mührü →
  rıza/hukuk → lisans → ayak izi → benzersizlik → birleşme → bakım) geçirildi;
  her biri `E / A / İ / T / R / MEVCUT` hükümlerinden birine bağlandı
  (17 entegrasyon + 51 adaptör + 191 ilham + 16 erteleme + 43 red + 7 mevcut).
  Şunlar açıkça REDDEDİLDİ ve §5'e gerekçeleri yazıldı: karanlık ağ tarayıcıları
  (TorBot, darkfox, robin…), ihlal/şifre verisi (WhatBreach, pwnedOrNot, GHunt),
  ses/yüz klonlama (RVC, GPT-SoVITS, facefusion, Deep-Live-Cam…), jailbreak ve
  sızdırılmış prompt külliyatı (L1B3RT4S, CL4R1T4S, G0DM0D3, heretic…),
  filtresiz üretim ve otomatik mesaj gönderimi (postiz-app).
- **Kod (Faz 0 omurgası — yeni paket `agent_core/capabilities/`):**
  - `base.py`: `CapabilityKind`, `Availability`, `CapabilityContext`,
    `CapabilityResult`, `Capability` protokolü, `BaseCapability` ve
    `make_evidence()` (kanıt mührü: boş içerik/kaynak adı kabul edilmez).
  - `policy.py`: `PolicyKernel` — `vault / consent / budget / rate / ENABLE_*`
    kapıları. **Bilinmeyen kapı = ret** (fail-closed); `rate` durumu bilinmiyorsa
    ret. Çekirdek hiçbir ortam değişkenini kendisi okumaz (durum `PolicyState`
    ile verilir).
  - `registry.py`: `CapabilityRegistry` — yetenek envanterinin TEK kaynağı.
    Kimlik sözdizimi, tür ve sözleşme kayıt anında doğrulanır; aynı kimlik ikinci
    kez kaydedilemez. `status()` UI/telemetri için makine-okunur sebep döner.
  - `runner.py`: `CapabilityRunner` — tek geçit: çöz → politika → kullanılabilirlik
    → koşu (+timeout). Bilinmeyen yetenek/kapı reddi/hatası **istisna değil,
    0 kanıt + makine-okunur sebep** üretir; hiçbir adımda kanıt uydurulmaz.
  - `adapters_osint.py`: mevcut `maigret` / `holehe` / `socid` tarayıcılarını
    sözleşmeye bağlayan ilk üç adaptör (kanıt üretimi + `payload` geçişi).
- **Kilit:** `tests/unit/test_capability_spine_faz0.py` (29 test): registry tek
  kaynak ve tekrar-reddi, bilinmeyen kapıda fail-closed, kasa kilidi, timeout ve
  istisnada 0 kanıt, sözleşme ihlali reddi, kanıt şeması (`ev_` kimliği),
  adaptör ↔ eski tarayıcı **eşdeğerlik** testleri (Faz 0.2 taşıması bitene kadar
  çift-kaynak sapmasını önler).
- **Ölçüm:** `pytest tests/unit` — değişiklikten ÖNCE 58 failed / 1113 passed,
  SONRA 58 failed / 1142 passed (+29). **Yeni düşüş yok.** (58 failure, sandbox
  ortamında eksik opsiyonel bağımlılıklardan — playwright/maigret/vision —
  kaynaklanan önceden var olan toplama/koşu hatalarıdır; bu değişiklikle ilgisiz.)
- **Kapsam dışı (bilinçli):** Faz 0.2 — `backend/api.py` ve `osint_investigator`
  içindeki eski doğrudan çağrıların bu adaptörlere taşınması. Taşıma yapılana
  kadar eşdeğerlik testleri iki yolun aynı dürüst sonucu verdiğini kanıtlar.

## Unreleased — 2026-09-26 — A-KAPANIŞ: Verifier → DepthReport izlenebilirliği

- **Ölçülen kusur (A1 CONTROL/TREATMENT diff):** DepthAnalyst, prompt'taki hakem
  `evidence_quote`'unu birebir alıntılayıp çelişki üretiyordu; `quote_guard`
  korpusu yalnız profil/görsel/timing/public_web metinlerinden oluştuğu için bu
  KANITLI çelişki "uydurma alıntı" sayılıp imha ediliyordu
  (`dropped_fake_quote=1`, `contradictions=[]`). Geriye yalnız `reality_rationale`
  kalıyor; onda da hangi `claim_id`'nin kararı değiştirdiği izlenemiyordu.
- **Düzeltme 1 — `agent_core/services/quote_guard.py`:** yalnız KESİN statülü
  (DOĞRULANDI/YALAN/ÇELİŞKİLİ) `bio_extracted` hakem alıntıları korpusa girer.
  Güvenlik gerekçesi: AutonomousVerifier kanıt alanlarını SADECE kanıt
  kapısından geçen oydan doldurur (url ∈ arama sonuçları + alıntı kaynakta
  birebir + destek oranı); BİLİNMİYOR/sözlük-dışı statü, kimliksiz kayıt,
  `canonical_observation_checks` ve çağıran-enjekte `verifications`
  (executor görev başında siler) çıpa OLAMAZ. `verifications` yoksa korpus
  BİREBİR eski hâli.
- **Düzeltme 2 — `DepthFinding.source_claim_id / verification_status /
  verification_link_basis` + `DepthReport.verification_trace`:** bağ
  deterministik kurulur — (a) LLM'in yazdığı `source_claim_id` hakemin ürettiği
  bir kimlik değilse bağ düşer (`rejected_claim_ids`), (b) kimlik yoksa ayakta
  kalan alıntı bir hakem alıntısıyla eşleşiyorsa `quote_match` ile bağlanır,
  (c) `verification_status`'u YALNIZ kod yazar (LLM statüsü bağ yoksa silinir,
  varsa hakem kaydıyla ezilir). Rapor düzeyi iz: `claims_available`,
  `quote_anchors`, `linked_findings[]`, `claim_ids_used[]`,
  `rationale_claim_ids[]`, `rationale_anchored_to_verification`.
  Executor log satırı: `HAKEM İZİ: n bulgu … kimliğe bağlı`.
- **Kilit:** `tests/unit/test_depth_verification_trace.py` (A1 CONTROL vs
  TREATMENT alan-diff'i kalıcı test) + `tests/integration/
  test_depth_verification_trace_executor.py` (executor içinde WRITE→READ→USE→
  ALTER→FINAL; negatif kol: enjekte `verifications` çıpa olamaz).
  Tam paket: 1410 passed / 25 failed — 25'i değişiklik öncesiyle birebir aynı
  (opsiyonel OSINT bağımlılıkları maigret/holehe/socid/invisible_playwright +
  uvicorn bayrağı; bu değişiklikle ilgisiz).
- **Kapsam dışı (bilinçli):** B6 legacy kolunda (`PINEAL_ENABLE_CANONICAL_
  MESSAGE_CONTEXT` kapalı) PatternInterrupt `target_analysis`'i ham okur;
  bu deneyin kontrol koludur, varsayılanı değiştirmek ayrı karar.

## Unreleased — 2026-09-18 — C8: decision_config.yaml ÖLÜ ANAHTAR TEMİZLİĞİ

- **[C8] `config/decision_config.yaml` içinden 4 ölü anahtar kaldırıldı:**
  `pipeline.default.require_data_confidence`, `agents.mirror_truth.min_final_confidence`,
  `agents.mirror_truth.critical`, `agents.osint_investigator.fallback_enabled`.
  **Ölçüm:** `grep -rn` (agent_core/, backend/) → bu isimlerin hiçbiri
  `config_loader.py` dışında hiçbir yerde okunmuyor; `config_loader.py` de
  yalnızca `min_data_score / min_llm_confidence / graceful_degradation /
  field_weights / empty_list_penalty` + `pipeline.critical_agents` okuyor.
  `DecisionConfig.load()` çıktısı önce/sonra JSON-diff: tüketilen alanlarda
  fark YOK (davranış aynı).
  **Karar gerekçesi (kaldır, bağlama):**
  - `require_data_confidence`: data_confidence sözleşmesi zaten KOŞULSUZ
    uygulanıyor (`decision_engine._run_bears_evidence` + `_unavailable_reasons`);
    bir "kapatma anahtarı" bağlamak kanıt kapısını yumuşatma yolu açar.
  - `critical: true`: kritik ajanların TEK kaynağı `pipeline.critical_agents`
    (decision_engine.py:82, task_executor.py ×6). İkinci bir bayrak ikili
    kaynak = sapma riski ([009] duplication dersi).
  - `min_final_confidence`: UncertaintyEngine tek eşik (`min_llm_confidence`)
    kullanıyor; ikinci bir "final" eşik tasarlanmış bir katman değil.
  - `fallback_enabled`: OSINT fallback'i `fallback_reason` alanıyla dürüst
    raporlanıyor, kapatılabilir bir davranış değil.
  **Kilit:** `tests/unit/test_config_contract.py::test_decision_config_has_no_dead_keys`
  loader'ın okuduğu anahtar kümesini YAML'a karşı doğrular; mutasyon
  (`critical: true` geri eklenince) → 1 failed, geri alınca yeşil.
  `test_critical_agents_single_source_is_pipeline_list` mirror_truth/passion_mapper'ın
  listede kalmasını kilitler.

## Unreleased — 2026-09-06 — S1: PROD SPEND-CAP FAIL-CLOSED + N7 DOKÜMAN

Kapanış kararı (üretim onayı) ile kapatılan son açık madde.

- **[S1] Production + spend cap 0/tanımsız → ARTIK AÇILIŞ REDDİ (fail-closed).**
  Runtime enforce zaten var (`llm_gateway.py:630-634` cap>0 iken reddetmek;
  `:670-673` cap≤0 → SINIRSIZ), ama production'da cap 0/tanımsız kalırsa
  enforce devre dışı kalıyordu ve tek sinyali /health "SPEND_CAP_UNLIMITED"
  degraded bayrağıydı — P2-10 sınıfı (production env eksikliği → tehlikeli
  varsayılan). `security_posture()` artık production + cap≤0 →
  `SecurityConfigurationError("PRODUCTION_SPEND_CAP_REQUIRED")`; lifespan
  bunu `CRITICAL` + raise ile açılış REDDİ'ne çevirir
  (`backend/api.py:121-124`) — aynen `PRODUCTION_AUTH_REQUIRED`
  (P2-10) ile aynı mekanizma. Geliştirme ortamı etkilenmez (cap 0 = kendi
  hesabınız). Canlı kanıt: prod+cap0 → uvicorn exit 3, log
  "PRODUCTION_SPEND_CAP_REQUIRED ... Application startup failed. Exiting.";
  prod+cap50 → boot, /health `ready` + `spend_cap_unlimited: false`.
  Testler: `test_production_without_spend_cap_cannot_start`,
  `test_production_missing_spend_cap_env_cannot_start`,
  `test_development_without_spend_cap_still_starts`
  (test_security_hardening.py) + `test_spend_cap_unlimited_in_production_
  refuses_to_start` (test_health_degraded.py — eski degraded-özeti testinin
  S1 sözleşmesiyle değiştirilmiş hali). Mutasyon: gate silinince 3/3 test
  KIRMIZI (dev testi yeşil kalır — kapı production-only, doğru).
  `SPEND_CAP_UNLIMITED` degraded bloğu (api.py:85-107) savunma derinliği
  olarak yerinde bırakıldı: gate'in arkasında ikinci bir kat.
- **[N7] Rate-limit kimlik modeli .env.example'de DOKÜMANTALENDİ.**
  Kimlik = `sha256(presented_token or client_ip or "unknown")[:16]`
  (api.py:247-253): geliştirmede IP → aynı IP arkasındaki kullanıcılar
  tek kovaya girer (canlı ölçüm R4: 12 istemci/1 IP → 5×200 + 7×429);
  production'da token varsa istemci token kullanıp kovasını kendine alır.
  `.env.example` PINEAL_TOKEN bloğu altına açıkça yazıldı.

## Unreleased — 2026-09-06 — ROUND 3: N1-N6 ARTIK MADELERİ (3fc89fc üzerine)

Bağımsız doğrulama turu R1-R6+F3 çekirdeğini doğruladı; 6 artık madde
(N1-N6) kapatıldı. Her fix önce canlı ölçümle doğrulandı (önce/sonra),
`tests/audit/test_round3_residue_findings.py` (16 test) ile korunuyor ve
**mutasyon testiyle** kanıtlandı (8/8 mutasyon KIRMIZI).

- **[N1] Hayalet görev + GİZLİ ENUM HATASI.** `active_tasks` tavan trim'i
  en eskiyi durum gözetmeksizin siliyordu (ölçülen: 300 aktiften 44 hayalet).
  Trim artık YALNIZ terminal kayıtlara düşer; aktifler sessizce ASLA silinmez.
  Aktif tek başına tavanı aşıyorsa oda "doymuş" sayılır: `/api/initiate`
  → **503 ACTIVE_TASKS_FULL**, ASPASIA dispatch → None → gateway
  `accepted=False, reason="dispatch_rejected"` (eski kod dispatch=None'i
  `accepted=True + task_id=None` ile "dispatched" kaydediyordu — yalan kabul).
  **Canlı testte çıkan GİZLİ hata:** `PipelineStatus` str-mixin enum'da
  Python 3.11'de `str(uye)` → `"PipelineStatus.COMPLETED"`; eski
  `str(snap.status).lower()` karşılaştırması GERÇEK TaskSnapshot'larda ASLA
  terminal eşleştiremiyordu → retention trim'i canlıda hiç çalışmıyordu
  (üniteler string-tabanlı sahte sınıf kullandığı için yeşildi). Yeni
  `_snapshot_status()` `.value` üzerinden gider; regresyon testleri GERÇEK
  modeli kullanır. Ölçüm: 300 terminal+10 aktif → 256 (10 aktifin TAMAMI
  korunur); 300 aktif → 0 silme; terminal yoğunluğu doyma YARATMAZ.
- **[N2] RecursionError → kalıcı 500.** `_read_learnings_safe` catch
  tuple'ına `RecursionError` eklendi: 60.000 seviyeli (geçerli ama derin)
  `learnings.json` artık quarantine edilir → 200 (önce: 500 ×N, dosya
  yerinde kalıyordu; ölçüldü).
- **[N3] Yedek birikimi sınırlı.** `learnings.json.corrupt.*` / `.schema.*`
  yedekleri `PINEAL_LEARNINGS_BACKUP_KEEP` (5) son yedekle sınırlı; en eski
  fazlası silinir (önce: 20 olay → 20 dosya; sonra: 20 olay → 5 dosya).
- **[N4] Host substring → tam eşleşme.** `extract_username` host kontrolü
  `"instagram.com" in host` (substring) idi → `notinstagram.com`,
  `www.instagram.com.evil.com`, `evilinstagram.com` kabul ediliyordu
  (3/20 adversarial URL). Yeni `_is_instagram_host`: `host == "instagram.com"`
  veya `host.endswith(".instagram.com")` (www dahil tüm meşru alt alanlar).
  Ölçüm: 20/20 adversarial URL doğru (önce 17/20).
- **[N5] Doküman:** R3 maddesine `ChatPayload.target_message ≤ 32.000`
  davranış değişikliği eklendi (422; önceki turda belgelenmemişti).
- **[N6] Doküman rotu:** `test_production_audit_findings.py` başlığındaki
  stale "AÇIK/xfail" listesi güncellendi (0 xfail gerçeği); CHANGELOG'daki
  "832 passed"/"%84.66"/"19/19" satırları DÜZELTİLMİŞ değerlerle (842/5/2/9,
  %85.04, 18/19) değiştirildi, orijinal iddialar "alıntılanmasın" notuyla
  alıntı bloğuna itildi.

#### Doğrulama (bu turun, ölçülmüş)
CI'nın birebir komutu (`ci.yml` backend job) → **895 passed, 2 skipped,
0 failed, 0 xfailed** (önceki tur: 879; +16 = bu turun regresyon testleri) ·
coverage **%85.13 ≥ %80** · ruff → temiz · mutasyonlar 8/8 KIRMIZI ·
N1/N2/N3/N4 önce-sonra canlı ölçümleri (bkz. üst maddeler).

## Unreleased — 2026-09-06 — 3. GÖZ DENETİMİ ONARIM TURU (bağımsız denetim, 2026-09-06)

Bağımsız denetim (F1–F17 bulgu, R1–R8 risk sıralaması) kapatılan bulguları
kod + mutasyon testiyle doğruladı. Bu tur denetimci önceliğiyle sıralandı:
**R1 → R2 → F3 → R3/R4/R5/R6**. Her onarım `tests/audit/test_auditor_round2_findings.py`
(yeni) + mevcut audit testleri içinde **mutasyon testiyle doğrulanmış** regresyon
testiyle korunuyor (10/10 mutasyon KIRMIZI; 1 mutasyon test yarışından
kurtarıldı: `room['events']` testi artık gönderim katmanını senkron çağırır).

- **[R1] Oda-özel sözlüklerin süresiz büyümesi kapatıldı** (ölçülen alt sınır:
  2000 görev/oda → 4.6 MB; gerçek görev ~30–60 event ile 50–100 KB/görev;
  WS'li oda evict'ten muaf = ölümsüz oda; P0-2/P0-5 deseninin üçüncü tekrarı).
  - `TaskLifecycleRegistry`: run başına `last_activity`; throttled (30 sn)
    `sweep()` — terminal run retention dolunca düşer (varsayılan 1800 sn,
    `PINEAL_LIFECYCLE_RETENTION_SECONDS`, taban 60); ACTIVE run yalnız
    `mission_tasks`'ta DEĞİLSE ve stale ise düşer. Boyut artık
    "retention × görev hızı" ile sınırlı, toplam görev sayısı ile değil.
  - `room["active_tasks"]`: terminal snapshot retention + sert tavan
    (`PINEAL_ROOM_ACTIVE_TASKS_CAP`, 256; en eski terminal önce düşer).
  - `room["events"]`: **ölü yapıydı** (append-only, okuyucusu yok — grep ile
    doğrulandı) → append KALICI SİLİNDİ.
  - `room["interventions"]`: sert tavan (`PINEAL_ROOM_INTERVENTIONS_CAP`, 512).
  - Pruning tek hizada: `get_room`/`broadcast_event`/`broadcast_result`/
    `broadcast_snapshot` → `_prune_room_stale_state` (oda başına 30 sn throttle;
    kalan çağrılar 1 float karşılaştırması).
- **[R2] Compose fail-closed PINEAL_ENV sabiti.** `docker-compose.yml` artık
  `PINEAL_ENV=${PINEAL_ENV:-production}` explicit taşır (env_file, imaj ENV'ini
  ezemiyor artık); `.env.example` içindeki AKTIF `PINEAL_ENV=development` satırı
  amacılı yorumlandı (compose interpolation .env'den okurdu → development
  sızması). Reponun kendi "cp .env.example .env" akışı artık production
  default'ını korur; yerel geliştirme açık seçimle (baslat.bat otomatik,
  compose için bilinçli PINEAL_ENV=development). Sözleşme:
  `tests/unit/test_compose_env_contract.py` (yeni).
- **[F3/W1–W4] Frontend-UI bridge TAMAMLANDI** (5 kırmızı sözleşme testi yeşile
  döndü; önceki turun "UI köprüsü" iddiası PANELDE yoktu — yalnız `initiate()`
  çağrıyordu; ölçülen: 18/19). `UnifiedCompactPanel.svelte`:
  - `sendMessage()`: ASPASIA serbest metin ÖNCE `/api/aspasia/command`
    (`accepted && task_id` → `taskStatus` görev kartına bağlanır); yoksa
    chat fallback (`/api/aspasia/chat`) — mesaj kaybı yok.
  - Forensic modallar GERÇEK backend anahtarlarını okur: timing →
    `night_share`/`peak_hour`/`median_drift_hours`; takipçi → `verdict_code`
    (+verdict/engagement_rate/expected_rate_range/data_completeness).
    Uydurma anahtarlar (`night_owl_score`, `bot_probability`, …) dosyadan
    kalktı (testler "must-not-contain" ile korur).
  - Yeni 7. forensic modal **RESONANCE**: `runs.resonance_calc.output_summary`
    → `compatibility_score`/`recommended_approach`/`red_flags`.
  - Agent kartları `run.output_summary._provenance.call_id` gösterir
    (uydurma satır değil; boşsa "—").
  - Ek: mevcut `{$isSending}` store-sözdüzgüsü hatası düzeltildi
    (`isSending` düz boolean; svelte-check 1 error → 0).
  - `npm run check` → 0 error · `npm run build` → yeşil (84.6 kB js / 31 kB gzip).
- **[R3] Identifier uzunluk sınırı eksik giriş noktalarına taşındı.**
  `validate_identifier` regex'i uzunluk SINIRLAMIYORDU: `ChatPayload.task_id`
  (gövde, sınırsız), `/api/tasks/{id}/cancel|halt` (path, doğrulamasız) —
  artık `PINEAL_MAX_TASK_ID_LENGTH` (128): gövde `Field(max_length)`,
  path `Path(max_length)` → 422; biçim `validate_identifier` → 400
  `INVALID_TASK_ID` (DELETE sözleşmesiyle eş); `reason` ≤ 500 → 400.
  `DELETE /api/tasks/{id}`'e de uzunluk kontrolü eklendi.
  **Davranış değişikliği (N5, bu round belgelendi):** aynı turda
  `ChatPayload.target_message`'a `Field(max_length=32_000)` eklendi —
  32.001 karakterden uzun mesaj artık **422** (ölçüldü: 32.001 → 422,
  100 → 200). Gerekçe: sınırsız gövde alanı, DialogueManager oturum
  sözlüğüne ve LLM promptuna aktığı için bellek/prompt şişirme yüzeyiydi;
  32.000 normal sohbet mesajı için geniş paydır.
- **[R4/P1-6] `extract_username` yalnız profil URL'si.** `/p/…`, `/reel/…`,
  `/explore/tags/kedi/`, `/accounts/login/`, host URL'leri artık "" üretir ve
  `scrape_instagram` kazımayı başlatmaz (`InsufficientEvidenceError`).
  Kurallar: tek path segmenti, Instagram hostu, rezerv segment yasağı
  (p/reel/explore/…), `^[A-Za-z0-9._]{1,30}$`, nokta kuralları. 9 xfail (6
  parametre) işaretten düşürüldü.
- **[R5/P2-9] Bozuk `learnings.json` → kalıcı 500 YOK.** `/api/override`:
  bozuk/şemasız dosya `.corrupt.<ts>`/`.schema.<ts>` yedeklenir, boş listeden
  devam edilir; yazım **atomik** (tmp+fsync+replace) → yarım dosya bir daha
  oluşamaz. Yanıt `quarantined` yolunu taşır. 2 xfail işaretten düşürüldü.
- **[R6/P1-7] Anti-halüsinasyon kapısı üretimde.** `scrape_instagram` kazıma
  sonrası `check_scrape_confidence` çağırır; `PINEAL_MIN_SCRAPER_CONFIDENCE`
  (0.6) altında `InsufficientEvidenceError` → görev HALT (düşük güvenli
  profil işleme sokulmaz). 1 xfail işaretten düşürüldü.
- **CHANGELOG düzeltmeleri:** 09-04 turundaki "832 passed" doğrulama bloğu ve
  09-05 turundaki "19/19" satırı ölçülmüş değeri EŞLEMEMEKTEYDİ (bağımsız
  denetimde 842 passed / 5 failed / 2 skipped / 9 xfailed ve 18/19 ölçüldü;
  5 kırmızı = bu turda kapatılan F3 frontend sözleşme testleri). Eski değerler
  aşağıda DÜZELTME NOTU ile işaretlendi.

#### Doğrulama (bu turun, ölçülmüş)
`ruff check .` → temiz · `pytest tests/ -q` → **879 passed, 2 skipped,
0 failed, 0 xfailed** (önce: 842/5/2/9) · `npm run check` → 0 error ·
`npm run build` → yeşil · mutasyon testleri 10/10 KIRMIZI (bkz. üstte).
2 skipped = çevre-skip'leri (LLM/playwright gerektiren, denetimden önce de
aynıydı).

## Unreleased (post-rc.2) — 2026-09-04

### ÜRETİM DENETİMİ ONARIM TURU (docs/reports/PRODUCTION_AUDIT_2026-09-04.md) — 7 bulgu kapatıldı
Denetim 10 kusur buldu; bu tur ilk 6 önceliği + bir ek boşluğu kapattı.
Her onarım `tests/audit/test_production_audit_findings.py` içinde **mutasyon
testiyle doğrulanmış** bir regresyon testiyle korunuyor (bkz. aşağıda).

- **[P2-10] Kimlik doğrulama artık FAIL-CLOSED.** `_is_production()` eskiden
  yalnızca `{"production","prod"}` değerlerini üretim sayıyordu; `PINEAL_ENV`
  unutulduğunda (en olası dağıtım hatası) tüm `/api/*`, `/v1/*` ve `/ws/*`
  kimlik doğrulamasız açılıyordu. Artık yalnızca açık bir geliştirme adı
  (`development|dev|local|localhost|test|testing|ci`) geliştirme sayılır;
  boş/yazım-hatalı/tanınmayan her değer üretim kabul edilir ve `PINEAL_TOKEN`
  zorunlu olur. `.env.example` ve `baslat.bat` güncellendi; Railway/Vercel
  etkilenmiyor (ikisi de `Dockerfile` üzerinden `PINEAL_ENV=production` devralıyor,
  `tests/unit/test_dockerfile_contract.py` bunu sözleşmeye bağlıyor).
- **[P0-1] Redaksiyon 31× hızlandı** (67.8 ms → 2.20 ms / 900 string; 200 telemetri
  mesajı 13.60 s → 0.43 s). İki neden vardı: `_environment_secret_values()` her
  metin alanı için yeniden çalışıyordu (900 env taraması) ve her sır için ayrı
  `str.replace` geçişi yapılıyordu. Çözüm: sır listesi `redact_structure` başına
  BİR kez toplanıp özyinelemeye taşınıyor; tüm sırlar + genel kalıplar tek
  derlenmiş alternation regex'inde birleşiyor (sır kümesiyle önbellekli).
  Genel `(?i)` bayrakları kapsamlı `(?i:...)` grubuna taşındı — aksi halde
  alternation ortasında `re.error` üretiyordu. **11/11 girdide çıktı birebir aynı.**
- **[P0-2] `ResponseCache` disk sızıntısı kapatıldı.** Süresi dolan satırlar
  yalnızca yok sayılıyor, hiç silinmiyordu. Artık: `get()` rastladığı süresi
  dolmuş satırı anında siler; periyodik `prune()` TTL + satır tavanı
  (`PINEAL_CACHE_MAX_ROWS`, varsayılan 50.000) uygular; açılışta bir kez buda
  çalışır. **İlk onarımın boşluğu çapraz denetimde yakalandı:** budama yalnızca
  yazım SAYISINA bağlıydı (her 256), düşük trafikte eşik hiç aşılmıyordu →
  10 satır süresiz diskte kalıyordu. Tetikleyici ZAMAN temelli yapıldı
  (`PINEAL_CACHE_PRUNE_INTERVAL_SECONDS`, varsayılan 900 s) ve her `get`/`put`
  tek float karşılaştırmasıyla kontrol ediyor.
- **[P0-6] `ResponseCache` artık event loop'u bloke etmiyor.** Her `get`/`put`
  yeni bir `sqlite3.connect()` açıyordu (ölçülen: 300 okuma = 28.6 ms kesintisiz
  loop blokesi). Çözüm: tek paylaşılan bağlantı (`check_same_thread=False` +
  `threading.Lock`), `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` +
  `auto_vacuum=INCREMENTAL`, ve gateway tarafında `asyncio.to_thread`.
  Ölçüm: loop blokesi **28.59 ms → 2.08 ms** (bağlantı yeniden kullanımı),
  `to_thread` ile medyan gecikme **0.59 ms**. PRAGMA sırası sözleşmeye bağlandı:
  `journal_mode=WAL` önce çalışırsa `auto_vacuum` sessizce 0 kalıyor.
- **[P0-4] `app.state.rooms` için TTL eviction + tavan + kimlik doğrulama.**
  Her farklı `client_id` kalıcı bir oda yaratıyordu (ölçülen: 300 farklı
  `client_id` → 300 tam executor + sender task; eviction yok). Artık:
  `PINEAL_ROOM_TTL_SECONDS` (1800 s) boşta kalan odaları geri kazanır — aktif
  görevi veya WebSocket'i olan oda ASLA dokunulmaz; `PINEAL_MAX_ROOMS` (512)
  tavanı aşılınca `RoomCapacityExceeded` → **503** (500 değil, geçici hata);
  `client_id` biçim VE uzunluk doğrulanır (`PINEAL_MAX_CLIENT_ID_LENGTH`, 64 —
  `validate_identifier` regex'i uzunluk sınırlamadığı için 5 KB'lık anahtar
  kabul ediliyordu). Kapanış yolu da aynı `_close_room` sözleşmesini kullanıyor.
- **[P0-5] `_rate_buckets` bellek sızıntısı kapatıldı** (ölçülen: 5000 farklı
  kimlik → 5000 kalıcı deque). `_sweep_rate_buckets` önce kesinlikle süresi
  dolmuş/boş kovaları siler, tavan hâlâ aşıldıysa EN ESKİ (LRU) kovaları düşürür;
  tavan `PINEAL_MAX_RATE_BUCKETS` (100.000). **Ölü kod silindi:** boşalan kovayı
  `rate_limit` içinde silmek hiçbir işe yaramıyordu — izin verilen her çağrı
  hemen `append` ile anahtarı geri koyuyordu (mutasyon testi bunu kanıtladı:
  satırı kaldırmak hiçbir testi kızartmadı).
- **[P1-18a] Hız sınırı kimliği istemci kontrollüydü — KRİTİK.** Middleware
  hız sınırını sunucudan türetilen `identity_hash` ile kurarken üç handler
  (`/api/initiate`, `/api/aspasia/command`, `/api/aspasia/chat`) istemcinin
  gövdede gönderdiği `client_id`'yi anahtar olarak kullanıyordu. Ölçülen:
  aynı `client_id` ile 8 istek → 3/8 429 (sınır çalışıyor); **her istekte
  farklı `client_id` → 200 istek, 0/200 429** — sınır hiç devreye girmiyordu.
  → middleware `request.state.rate_identity` yazar, handler'lar
  `_rate_identity(request)` okur. Kimlik yoksa fail-safe: tüm kimliksiz
  çağıranlar **tek ortak kovayı** paylaşır (sınırsız değil).
  **Davranış değişikliği:** bu üç uçta limit artık *token/IP başına*,
  `client_id` başına değil. Aynı token arkasındaki tüm istemciler 5 görev/60sn
  bütçesini paylaşır; çok istemcili kurulumda `RATE_LIMITS` değerleri
  gözden geçirilmelidir.
- **[P1-18b] 7 `/api/` ucu tamamen hız sınırsızdı** (`/api/vault`,
  `/api/override`, `/api/executor/intervene`, `/api/scraper/authorize-alternative`,
  `/api/tasks*`, `/api/telemetry`, `/api/aspasia/state`). → middleware'e genel
  `api` kovası (300/60sn), **yalnızca mutasyon yöntemleri** için. GET'lerin
  dahil edilmemesi ölçümle karar verildi: tek paylaşımlı kova tüm yöntemleri
  kapsayınca 305 GET aynı kimliğin sonraki POST'larında erken 429 üretti.
- **[P1-18c] `api.py:1229` bare `except:` `CancelledError`'ı yutuyordu.**
  Ölçülen: gerçek `websocket_endpoint` park halindeyken iptal edilince
  `task.cancelled() == False`, görev normal dönüyordu. Kontrol ölçümü
  `except Exception:`'ın **tek başına yetmediğini** gösterdi: iptal durumunda
  websocket odadan düşmüyordu. → `except Exception:` + temizlik `finally:`.
  Onarım sonrası: `CancelledError` yayılıyor **ve** temizlik korunuyor.
- **[test altyapısı] `tests/conftest.py`'ye `_isolate_rate_limit_state` eklendi.**
  `_rate_buckets` süreç genelinde paylaşılan mutable durumdur; anahtar sunucu
  kimliğine geçince testler arası izolasyon kayboldu ve 2 test tam pakette
  kırmızı, tek başına yeşil oluyordu. Her testten önce/sonra temizlenir.
- **[P0-2 v3] Cache süresi artık satırda saklanıyor** (`widest_window` ikizi
  burada da vardı). Satır `created_at` tutuyor ama kendi TTL'ini tutmuyordu;
  süre her okumada güncel `PINEAL_CACHE_TTL`'den yeniden hesaplanıyordu.
  Ölçülen: TTL 7 gün → 1 sn yapınca **7 günlük kayıt 1.2 sn'de yok oluyordu**;
  TTL 1 sn → süresiz yapınca **süresi dolmuş kayıt sonsuza dek yaşıyordu**
  (`prune()` 0 satır). → `expires_at` kolonu + eski db'ler için tek seferlik
  `ALTER TABLE` + doldurma + `idx_rc_expires`.
  **Dikkat (davranış değişikliği):** `PINEAL_CACHE_TTL=0` artık mevcut
  satırları silmez, yalnızca yeni yazılanları anında süresi dolmuş yapar.
- **[P2-13] Sınırsız büyüyen iki sözlük kapatıldı** (desen üçüncü kez çıktı:
  P0-2 `prune`, P0-5 `_sweep_rate_buckets`, şimdi bu ikisi).
  - `canonical_memory._locks` (`defaultdict(asyncio.Lock)`) — ölçülen: 5.000
    sıralı `merge_evidence` → **5.000 kalıcı kilit** (izole 0.80 MB, 167 B/girdi),
    asla silinmiyordu. → `_LockEntry` + bekleyen sayaçlı `_task_lock()`:
    sözlük artık yalnızca AKTİF bekleyeni olan kilitleri tutuyor.
    **Kapanış: 5.000 merge → 0 girdi.** Doğruluk kanıtı: 8 eşzamanlı merge,
    aynı `task_id` → aynı anda en fazla 1 içerde, 0/8 hata; kilit no-op
    yapılırsa **6/8 `FileNotFoundError`** (aynı `.tmp` yolu çakışıyor) —
    kilit gerçekten yük taşıyor.
  - `dialogue_manager.sessions` — ölçülen: 50.000 `start_session` →
    **50.000 kalıcı `DialogueContext` / 58.0 MB** (1.217 B/girdi), asla
    silinmiyordu; üstelik `"Oturum bulunamadı veya süresi doldu"` hatası bir
    süre ima ediyordu ama süreyi uygulayan tek satır kod yoktu.
    → `PINEAL_DIALOGUE_SESSION_TTL_SECONDS` (1800) +
    `PINEAL_MAX_DIALOGUE_SESSIONS` (512), her işlemde kontrol edilen eviction.
    **Kapanış: tavan 100 iken 5.000 → 100; TTL 1 sn iken 200 → 1.**
    Maruziyet `api.py:210` auth middleware + `experimental` hız limiti
    (10/60 sn; ölçülen 10×200 + 5×429) ile sınırlı, ama sızıntı monotondu.
- **[P0-5 v3] `_rate_buckets` — ikiz kusur kapatıldı (çapraz denetim bulgusu).**
  P0-2'deki "eşiğe hiç ulaşılmama" hatasının aynısı buradaydı; üç ayrı kusur:
  - **(a) Zaman temelli tetikleyici yoktu** — süpürme yalnızca tavan
    (100.000) aşıldığında çalışıyordu. Ölçülen: 30.000 tekil anahtar,
    pencereleri dolmuş, **30.000 kova / 26.4 MB süresiz bellekte**.
    → `PINEAL_RATE_SWEEP_INTERVAL_SECONDS` (60 sn) + her çağrıda kontrol
    edilen `_rate_sweep_deadline` (P0-2 ile aynı desen).
  - **(b) Histerezis yoktu → kendi kendine DoS** — tavan-1'e kırpma, her yeni
    isteğin tüm sözlüğü yeniden süpürmesi demekti. Ölçülen: üretim tavanında
    **48-57 ms/istek** → hedef tavanın ~%80'i, **en yavaş istek 0.53 ms**.
  - **(c) Süpürme kovanın kendi penceresini bilmiyordu** — kova adı
    saklanmadığı için "en geniş pencere" (60 sn) kullanılıyordu; (a)+(b)
    onarıldıktan sonra bile 1 sn'lik kova 60 sn bekliyordu. → `_RateBucket`
    (`__slots__ = ("events", "window")`), ayıklama `b.window` ile.
    Sonuç: **30.000 kova / 26.4 MB → 1 kova / 0.9 MB**.
- **[P1-8] Scraper artık event loop'u dondurmuyor.** `_random_delay` senkron
  `time.sleep(2-5 s)` kullanıyordu ve async `scrape_async` içinden çağrılıyordu
  → tek kazıma boyunca tüm süreç (health check, WebSocket, diğer kullanıcıların
  LLM istekleri) donuyordu; 3 denemeli retry'da 15 saniyeye kadar. `async def` +
  `await asyncio.sleep` yapıldı; 5 mevcut testin senkron mock'u `AsyncMock`'a taşındı.
- **Küçük:** `backend/api.py` içindeki fonksiyon-seviyesi `import os` /
  `from fastapi import HTTPException` modül seviyesine alındı; `security.py`'ye
  yapılandırılmış logger eklendi.

#### Onarım doğrulaması: mutasyon testi (14 mutasyon, 0 sahte test)
Her onarım geçici olarak geri alınıp ilgili testin KIZARDIĞI doğrulandı.
Bu tur **iki sahte testi ortaya çıkardı ve düzeltti**:
- `P0-5/test_rate_bucket_count_is_bounded` — `window=0` ile tüm kovalar aşama 1'de
  siliniyor, **LRU tavan kırpma hiç çalışmıyordu**; `overflow = 0` mutasyonu testi
  yeşil bıraktı → pencere uzun tutularak yalnızca LRU yolu zorlanacak şekilde düzeltildi.
- `P0-5/bos-kova` — silinen ölü kodu test ediyordu (yeşil kaldı) → ölü kod silindi,
  gerçek geri kazanım yolu (`_sweep_rate_buckets`) ayrıca mutasyonla doğrulandı.
- `P0-2/acilista-buda` — açılış budaması hiç test edilmiyordu (yeşil kaldı) →
  `test_startup_prune_clears_rows_left_by_previous_process` eklendi.
Ayrıca `P1-8` testinin ilk hâli kaynak metninde `"time.sleep"` arıyordu ve
docstring eşleştiği için kendi kendini kandırıyordu → `inspect.iscoroutinefunction`
+ çağrı noktasında `await` kontrolüne çevrildi.

#### Bu turun sonunda AÇIK kalanlar (2026-09-06 round-2 turunda KAPATILDI)
- **P1-6** `extract_username` profil olmayan URL'yi hedef kullanıcı adı sanıyor
  (`/p/…`, `/reel/…`, `/explore/tags/kedi/` → `kedi`). → 2026-09-06 kapatıldı.
- **P1-7** `InstagramGhostScraper.evaluate_confidence` üretimde HİÇ çağrılmıyor
  (anti-halüsinasyon kapısı ölü kod; testler yeşil olduğu için görünmüyor).
  → 2026-09-06 kapatıldı.
- **P2-9** Bozuk `learnings.json` → `/api/override` kalıcı 500 (atomik yazma yok).
  → 2026-09-06 kapatıldı.

#### Doğrulama (düzeltildi: 2026-09-06 bağımsız denetimi)
`ruff check .` → temiz · `pytest -q` → **842 passed, 5 failed, 2 skipped,
9 xfailed** (d651a7b, 2026-09-06 ölçümü — bu turun gerçek başlangıç durumu;
5 kırmızı test = 09-05 turunun F3 frontend sözleşme testleri, round-2 turunda
kapatıldı; 9 xfail = yukarıdaki 3 açık bulgu, round-2 turunda işaretten
düşürüldü) · CI kapsam kapısı → **%85.04 ≥ %80** (CI aralığı ölçümü).
> **Orijinal tur kaydı — ölçülmüş değeri EŞLEMEZ, alıntılanmasın:**
> "832 passed, 2 skipped, 9 xfailed" ve "CI kapsam kapısı %84.66 ≥ %80"
> ve "tek başarısız test: test_open_interpreter_imports_with_installed_psutil".
> Bağımsız denetim (2026-09-06) bu üç iddianın da doğru olmadığını ölçtü
> (gerçek: 842/5/2/9, %85.04; 5 kırmızı F3 sözleşme testleriydi).

## Unreleased (post-rc.2) — 2026-09-05

### ASPASIA TRUE CHIEF LAYER: amaç taşımı + kanonik sonuç döngüsü + UI köprüsü
- **Goal sözleşmesinin TEK kaynağı** `CognitiveRouter.GOAL_FOCUS` (7 goal id;
  her biri router'ın GERÇEK uzmanlarına harita — uydurma capability yok).
  `AspasiaIntent.goals` bu sözlükten türetilen Literal allowlist; drift testli.
- **Amaç kaybı fix:** `USER → Aspasia(intent+goals) → CommandGateway →
  InitiatePayload.aspasia_goals → input_data["aspasia_goals"] → CognitiveRouter`.
  Goal YOKSA plan birebir eski; uydurma goal şemada reddedilir (dispatch doğmaz);
  `/api/initiate` üzerinden gelen bilinmeyen goal planı değiştiremez (not düşer).
- **Kanıt kapısı üstünlüğü:** goals yalnız tercih bacaklarını daraltır;
  `autonomous_verifier` (policy) ve kanıt-kapılı `authenticity_auditor`
  goal'la eklenmez/silinmez; kanıt yoksa honest-skip notu — sahte yürütme yok.
- **Sonuç döngüsü (paralel store YOK):** `MissionResultReader` yalnız
  `CanonicalMemory.get_task_memory` okur; bozuk kayıt "corrupted + kurtarma
  gerekir" olarak taşınır. `room["active_tasks"]` terminal durumdaysa digest
  `"BAYAT-snapshot"` etiketler (kanonik = memory).
- **Model-mismatch görünürlüğü:** DENETİM bloğu artık `SUBSTITUTION DENIED:
  istenen=X — dönen=Y (provider)` satırını taşır (kaynak: mevcut call_log).
- **UI köprüsü:** ASPASIA seçiliyken serbest metin ÖNCE `/api/aspasia/command`;
  `accepted && task_id` → görev kartına bağlanır; değilse chat fallback (mesaj
  kaybı yok). Yapılandırılmış form `/api/initiate`'te kalır (programatik hat).
- Cancel/halt: bu fazda YOK (yalnız extension noktası: gateway dispatch şeması).
- Testler: `tests/unit/test_aspasia_chief_layer.py` **18/19** (2026-09-06
  ölçümü — kırmızı: `test_panel_ui_bridges_to_command_and_chat`; panelde
  komut köprüsü yoktu, round-2 turunda `sendMessage()` köprüsüyle kapatıldı
  ve dosya 19/19).
  > **Orijinal tur kaydı — alıntılanmasın:** "19/19". Bağımsız denetim
  > (2026-09-06) bu dosyada 18/19 ölçtü; ayrıca aynı turun "UI köprüsü"
  > maddesi panelde gerçekleşmemişti (yalnız `initiate()` çağrısı vardı).
- Promosyon testleri 16/16; routing regresyonu
  (provider-aware+firewall+compliance+policy+aspasia+wiring) 92/92.

### ASPASIA-PROMOTION: merkezi doğal-dil arayüzü + komut ağzı (orkestrasyon yetkisi DEĞİL)
- `agent_core/aspasia/interface.py` (yeni): salt-okur denetçiler
  (Routing/Telemetry/Quota/Cost/Agent) mevcut SoT'ları okur; Governor'u olmayan
  gateway'den "HEALTHY" uydurulmaz (`unavailable`), unknown kota asla
  unlimited sayılmaz.
- `AspasiaCommandGateway`: doğal dil → `AspasiaIntent` (extra=forbid; model/
  agent/quota alanları şema düzeyinde reddedilir) → hedef URL doğrulaması →
  TEK dispatch kanalı `api._aspasia_command_dispatch`, ki bu `/api/initiate`
  akışının kendisidir (lifecycle + mission_tasks + run_mission; ikinci
  orchestrator yok). Niyet çıkarımı gerçek `aspasia` dialogue zincirinden
  geçer ve `capture_calls` ile `agent_id=aspasia` etiketlenir.
- `AspasiaChief`: `commands`/`executor` bağlama + chat promptuna DENETİM
  KATMANI digest'i (yalnız gerçek içerik varsa; uydurma blok yok). Sistem
  promptu persona + SINIR korunarak "merkezi arayüz ve denetim" rolüyle
  genişletildi.
- Uçlar: `POST /api/aspasia/command`, `GET /api/aspasia/state`.
- Gateway gözlemlenebilirlik düzeltmesi: `MODEL_SUBSTITUTION_DENIED` artık
  call_log'a `requested → returned` detayıyla yazılıyor (detay eski halinde
  yalnız exception metnindeydi, log'da kayboluyordu).
- Testler: `tests/unit/test_aspasia_promotion.py` 16/16 (görünürlük, komut
  akışı, şema güvenliği, dispatch tek kanalı, statik mutasyon-yüzeyi taraması,
  chat geri dönüşüm uyumu). Tam süit: 749P/32F(env-only)/2S — yeni başarısızlık yok.

### FINAL-SPEC: agent-level bypass kapıları (F-1/F-2/F-3/F-4) + transport-kanıtlı uygunluk

- **F-1 Aspasia:** `AspasiaChief.chat()` artık kimliksiz `query()` yerine
  `query_chain(task="dialogue", agent_name="aspasia")` yürütüyor →
  `AGENT_CHAINS["aspasia"]` + provider merdiveni + fallback zinciri devrede.
  Kullanıcının AÇIK `preferred_model`/`model_override` pini bilinçli olarak
  korunur (pin = tercih, bypass değil).
- **F-2:** `authenticity_auditor` ve `depth_analyst` çağrıları
  `agent_name=None + task fallback` olmaktan çıkarıldı; kendi matrix
  satırlarına bağlandı (depth zinciriyle BİLİNÇLİ paylaşım, matrix değişimi
  artık bu iki ajanın davranışını otomatik taşır).
- **F-3:** `human_behavior`, `mirror_truth`, `pattern_interrupt` tek-model
  tier-default yolundan zincirli agent-aware yola geçirildi (dönüş sözleşmesi
  aynı; mock dikişleri güncellendi).
- **F-4:** `get_agent_chain` zincirin KAYNAĞINI (`agent_matrix` /
  `env_override` / `task_chain`) her telemetri kaydına `chain_source` olarak
  yazıyor; RUNBOOK'a precedence sözleşmesi eklendi. ENV override kaldırılmadı
  — belgeli, testli, işaretli acil durum düğmesi.
- **Substitution firewall genişletildi (spec #27):** sessiz model ikamesi
  reddi artık OpenRouter legacy yolunda da geçerli ve hem iç retry'ı hem
  zincir fallback'ini tetiklemeyen non-retryable politika kararı
  (`model_substitution_denied` guard marker'ı).
- **Kota agregasyon hatası düzeltildi:** routed taşıma denemeleri governor'a
  provider-agrega pencerede (`*`) yazılıyor; `status(provider)` okuması artık
  gerçek akışta görünebilir (önceki per-model yazım, resolver skip'ini fiilen
  etkisiz bırakıyordu).
- **Liste vs effective fiyat:** `GatewayRoute.list_*` alanları + telemetri
  `route_key / pricing_* / list_pricing_* / discount_pct` backward-compatible
  alanları; Nous indirimi spend accounting'in TEK fiyat kaynağı (test: OR
  çağrısı sıfır, $3.20/$1M+0.2M settlement).
- Yeni: `tests/unit/test_final_spec_compliance.py` (23 test; transport
  boundary'de HTTP-level provider kanıtı dahil).

### MP-ROUTING: ajan hattı gerçek çok-sağlayıcılı yürütmeye geçti

- **OpenRouter artık santral değil, havuzun bir üyesi:** `LLMGateway.query()` ve
  `query_chain`/`query_json_chain` zincirleri, her model için önce o modelin
  `MODEL@PROVIDER` taşıma merdivenini yürür (Groq/Cerebras/Nous/DeepSeek doğrudan
  API'leri; kendi base_url, anahtar, fiyat ve kotasıyla). Kaynak:
  `agent_core/services/llm_gateway.py::agent_route_variants`.
- **Maliyet merdiveni free → indirimli → OpenRouter:** fiyat sıralaması
  `final_routing_policy.ROUTES` + provider kataloğundan; fiyatı bilinmeyen rota
  en sonda teklif edilir, spend-cap aktifse hiç teklif edilmez.
- **Kapılar aynı, bypass yok:** doğrudan rota ancak (1) credential env tanımlıysa,
  (2) katalog o modeli gerçekten sunuyorsa, (3) politika `is_paid` fail-closed
  kontrolünden (ücretli rota yalnız `PINEAL_ALLOW_PAID_ESCALATION=1`) ve kota
  sayacı EXHAUSTED değilse geçerse merdivene girer. Geçici hatada sıradaki taşıma,
  o da biterse zincirdeki sıradaki MODEL denenir; SpendCap/paid-escalation/
  unknown-pricing reddi tüm merdiveni DURDURUR (mevcut `_is_fallback_allowed`
  doktrini korunur).
- **Sessiz model ikamesi firewall'u `query()` routed yoluna da bağlandı**
  (`MODEL_SUBSTITUTION_DENIED`), telemetri `requested_model`/`actual_model`
  ayrımı sağlayıcı-gerçek kimliğiyle yazılır.
- **Anahtarsız varsayılan = birebiren eski davranış:** `agent_route_variants()`
  credential yoksa `[None]` döner; üretim yolunda sıfır değişiklik riski.
- Yeni env: `DEEPSEEK_API_KEY` (`.env.example`); test:
  `tests/unit/test_provider_aware_agent_chains.py` (12 test).

## Unreleased (post-rc.2) — 2026-09-03

### G7 release gate'leri koşulabilir hale getirildi (mekanizma onarımı)

- **`.github/workflows/release-gates.yml` eklendi** — gövde kanonik kaynakla
  (`release/release-gates.yml`) birebir. Önceki durumda dosya yalnız `release/` altındaydı;
  GitHub `on:` anahtarını default branch'in `.github/workflows/` dizininden okuduğu için
  `Actions → Release Gates` hiç görünmüyor, dolayısıyla **Gate A (`live_llm_openrouter_e2e`) ve
  Gate B (`docker_chromium_smoke`) koşulamıyordu** ("yeşil koşu kaydı yok" kırmızısının kök nedeni).
  "Operatör `cp`'lesin" adımı böylece kaldırıldı.
- **`tests/unit/test_release_gates_workflow.py`** (7 test) — dosya konumu, kaynak↔kopya bayt
  eşitliği (gövde kayması yasağı), **yalnızca** `workflow_dispatch` (push/PR/`schedule` yasağı —
  Gate A paralı çağrı içerir), Gate A fail-closed secret kontrolü + `LIVE_LLM_E2E=1` +
  `OPENROUTER_MAX_SPEND_USD`, Gate B'nin gerçek imaj/health/production-auth/Chromium/teardown
  adımları ve `concurrency.cancel-in-progress: false`.
- **Merge kanıtı** — PR #60 squash-merge ile main'de (`68fa552`); ardından `gh workflow list` →
  `Release Gates active` (id `349137796`). Dispatch'in kendisi agent token'ında Actions-write olmadığı
  için **403** döndü → Gate A/B'nin yeşil koşu kaydı operatör adımı olarak `NOT_EXECUTED` yazıldı.
- **Belge hizalama** — `docs/reports/RELEASE_EVIDENCE.md` §12'ye 2026-09-03 güncelleme tablosu (mekanizma
  kapandı ≠ gate kapandı; run URL'si işlenmeden gate'ler açık sayılır),
  `docs/reports/SON_HUKUM_DENETIM.md`'ye eski "kırmızı" hükümlerinin `f1e4602` üzerindeki yeniden
  ölçümü (`723 passed, 2 skipped` · coverage `%84.13` · ruff clean · main CI `success`).
- **Kapanmayan (bilinçli, operatörde):** `OPENROUTER_API_KEY` secret'ı + manuel dispatch (Gate A);
  docker'lı runner + Instagram initiate (Gate B). Bu ikisi yeşil olmadan stable ilan edilmez.

## Unreleased (post-rc.2) — 2026-09-02

### FINAL-KARAR-MATRIX production routing

- **`final_routing_policy.py`** — the FINAL decision matrix becomes the runtime
  economic source of truth: verified free routes (Groq/Cerebras GPT-OSS + Nous
  `:free` routes), paid routes (Nous Step/Solar/LongCat/Luna/Sonnet + OpenRouter
  Gemini 3.7 Flash / GPT-5.6 Sol Pro) with the fixed Nous discounts (Luna 80%,
  Sonnet 20%). Free-first task ordering; paid escalation `DENY` by default,
  gated by `PINEAL_ALLOW_PAID_ESCALATION=1`.
- **`quota_governor.py`** — header-aware RPM/TPM/RPD/TPD accounting seeded from
  the account-verified Groq (30 RPM / 14,400 RPD) and Cerebras (5 RPM / 30K TPM
  / 1M TPD) quotas. Unknown quota is reported `unknown`, never unlimited.
- **`routed_chat.py`** — `default_routing_mapping` is now policy-driven (free
  first); Nous connections are policy-gated so catalog presence alone never
  turns a paid route into an executable fallback; the executor enforces the
  FINAL policy before leasing, records quota state, and annotates
  `fallback_reason`/`quota_status` on every call.
- **`llm_gateway.py`** — telemetry contract extended (`requested_model`,
  `actual_model`, `fallback_reason`, `quota_status`); provider default-model
  substitution is denied; `query_chain`/`query_json_chain` now fall back only
  on transient errors (and genuine JSON parse/schema failures) — never on auth,
  spend-cap, unknown-pricing, paid-escalation, or model-unavailable.
- **`config/provider_catalog.json`** — added `nous-research` provider with
  verified free + paid models and effective Nous prices.
- **`scripts/verify_openrouter_catalog.py`** + CI step — deterministic local
  catalog contract gate (plus a live OpenRouter cross-check when a key is
  present). OpenRouter absence is never treated as Nous evidence.

### FINAL policy hardening (review follow-up)

- Canonical policy key is now `model@provider`; `routed_chat.default_routing_mapping`
  translates to the catalog's `provider/model` form at the boundary.
- Fail-closed by construction: `is_paid`/`is_free` treat unknown model/provider
  as DENY (never free, never order-dependent); `verification_status` defaults to
  `unverified` (opt-in); `quota_limit()` raises `UnknownQuotaDenied` for unknown
  quota instead of allowing an `inf`/unlimited interpretation.
- Import-time `_validate_catalog()`: every task-group candidate must resolve to a
  verified spec (no silent catalog-drift swallowing), forbidden aliases and
  vision/video capability cross-checks are enforced.
- `assert_executable(explicit=True)` is audited (logs a warning) and a `frontier`
  tier requires **both** `PINEAL_ALLOW_PAID_ESCALATION=1` and `explicit=True`.
- Nous Step 3.7 Flash catalogued as vision-capable (matches the policy's
  vision/video task groups).

### Cross-audit fixes + consolidated verdict

- **JSON repair exception scope** (`llm_gateway.query_json`): repair path now catches only parse/schema failures (`ValueError`, `ValidationError`, `TypeError`, `KeyError`, `JSONDecodeError`). Transport/auth/spend-cap/cancellation errors re-raise immediately — no second paid repair call on a dead upstream.
- **Depth failure wiring** (`task_executor`): `depth_analyst` success/failure is recorded on `status.agent_runs` + `evidence_chain` (execution_failure) + explicit `depth_report.available=False` metadata. Silent WARNING-only gaps removed so DecisionEngine sees the miss.
- **Prompt injection close-out**:
  - `autonomous_verifier`: bio + search snippets fenced as `<UNTRUSTED_*>`; model told content is not instructions.
  - `memory_injector`: operator rules no longer claim "KUTSAL OVERRIDE"; sanitised, fence-safe, injection-pattern rejected; host system prompt remains supreme.
- **Authentic vector epistemic marker**: successful vectors stamped `_epistemic=model_estimate` + status metadata; unavailable path carries `epistemic=unavailable`.
- **Slug drift fix**: docs/`.env.example`/`router.example.json`/`interpreter_agent` defaults aligned to the 2026-09-02 decision matrix (`claude-sonnet-5` / `deepseek-v4-flash` / `gemini-3.7-flash` / `grok-4.6`). Retired promo slugs (`solar-pro4`, `ling-3.0-flash`, `glm-5.2`) are not bare defaults.
- **G7 release gates**: `.github/workflows/release-gates.yml` (kaynak kopya: `release/release-gates.yml` — GitHub App `workflows` izni olmadığı için bu PR workflow dosyasını doğrudan yazamaz; yazma yetkili aktör `cp release/release-gates.yml .github/workflows/release-gates.yml` ile ekler) (workflow_dispatch only) wires Gate A live LLM E2E + Gate B docker/Chromium smoke. Docs already described Section 12; workflow file is now present.
- Audit reports: `docs/reports/CROSS_AUDIT_FIXES_2026-09-02.md`, `docs/reports/SON_HUKUM_DENETIM.md`.
- Verification: **645 passed, 2 skipped** · **%83.32** coverage · ruff clean.

### Release gates (G7)

- Added `.github/workflows/release-gates.yml` (kaynak kopya: `release/release-gates.yml` — GitHub App `workflows` izni olmadığı için bu PR workflow dosyasını doğrudan yazamaz; yazma yetkili aktör `cp release/release-gates.yml .github/workflows/release-gates.yml` ile ekler) — manual-only (`workflow_dispatch`) wiring for the two open rc.2 live gates; never triggers on push/PR (Gate A is a paid live LLM call); single-flight concurrency (no cancellation of a running paid gate).
  - `live-llm-e2e` (`live_llm_openrouter_e2e`): runs `live_llm_gate.py` with `secrets.OPENROUTER_API_KEY` + `LIVE_LLM_E2E=1`. Fail-closed: rejects the run up front when the secret is missing; bounded by `OPENROUTER_MAX_SPEND_USD=5`.
  - `docker-chromium-smoke` (`docker_chromium_smoke`): real `docker compose up --build`; health gate (`ready|degraded` → 200); real Svelte dist served (`id="app"`); production auth verified both ways (no token → 401, `X-API-Key` → 200); in-container Playwright/Chromium smoke via `scripts/smoke_test_browser.py`.
- `docs/reports/RELEASE_EVIDENCE.md` — added post-seal **Section 12**: gate execution mechanism + honest scope note (the Instagram-initiate leg of Gate B stays operator-manual; GitHub runner IPs hit platform limits).
- `docs/reports/GENEL_DURUM_HARITASI_2026-09-02.md` — G7 rows updated: mechanism established; closure now requires a green manual run (Gate A) plus the manual Instagram leg (Gate B).
- Gates remain **open** until a green workflow run is recorded — this change wires the button, it does not claim the gates passed.

## 3.0.0-rc.2 — 2026-09-02

### Release evidence

- Integrated the sealed rc.2 evidence record (`docs/reports/RELEASE_EVIDENCE.md` + `release/3.0.0-rc.2.json`, sealed 2026-09-01 on branch `8e3b2918`): 14/14 static + runtime checks PASS, 6 negative security tests PASS, DR 63→0→63 verified, deployment gates PASS; 2 live gates remain open (live LLM E2E + Docker/Chromium smoke).
- `VERSION` bumped `3.0.0-rc.1` → `3.0.0-rc.2`.

### Routing (post-seal main work)

- `#50` — WebSocket/token handling + UnifiedRouter gap closures.
- `#52` — UnifiedRouter connected to `/v1`, capability-based agent routing, catalog auto-config.
- `#53` — 2026-09-02 decision matrix: Sonnet-5 primaries (profiler/mapper/aspasia/synthesizer+friction, V4-Pro fallback), vision = Gemini 3.7 Flash + Grok 4.6, OSINT synthesis = Grok 4.6, verifier extract (V4-Flash) split from judgment (Sonnet-5); catalog/pricing + `claude_sonnet_5`, `grok_4_6`; retired slugs (`solar-pro4`, `ling-3.0-flash`, `glm-5.2`) out of every chain.

### Performance / fixes

- Hindsight Memory semantic index: batched inserts via single-connection `executemany` (revived from PR #49) — O(N) commits → 1 commit.
- WaterHoseVisualizer: PR #49's implicit-`any` fix confirmed **superseded** — current main already types particles via the `Particle` interface (no code change needed).

### Re-validation at `b14a8e16`

- Backend: 634 passed, 2 skipped, 0 failed; coverage 83.31% ≥ 80%; `ruff check .` clean.
- Main CI matrix green (run `33590408702`): backend · frontend · rust-core · android · smoke.
- Open gates unchanged: `live_llm_openrouter_e2e`, `docker_chromium_smoke` → GO LIVE pending.

## 3.0.0-rc.1 — 2026-09-01

### Production repair

- Made backend coverage, frontend check/build, Rust check/test, Android lint/test/assemble, and uvicorn smoke mandatory CI gates.
- Restored a reproducible Android Gradle wrapper/toolchain and validated a real APK build on clean CI runners.
- Replaced gateway-global LLM provenance with immutable call IDs and task/agent-local call scopes.
- Added atomic concurrent spend reservations, fail-closed unknown pricing, cancellation release, and settlement-before-parse for malformed paid responses.
- Distinguished empty canonical memory from corruption, preserved corrupt bytes, and added explicit quarantine/reset recovery.
- Classified missing dependencies separately from broken imports and made required startup failures machine-readable.
- Enforced deterministic task lifecycle sequencing, terminal-state immutability, idempotent termination, and visible queue degradation metrics.
- Added production fail-closed authentication, first-message WebSocket auth, DNS-pinned outbound requests, redirect/private-address rejection, path containment, secret redaction, and bounded rate/timeout/retry controls.
- Classified `rust_core/` as CI-validated experimental/optional code with no Python product-runtime or product-decision effect.
- Added a no-method-mock cross-stack test using a real OpenAI-compatible local HTTP provider through API, executor, agent, LLM gateway, provenance, canonical memory, telemetry, WebSocket, and UI protocol contracts.
- Added task IDs to initiation/results, cancellable mission handles, cancellation/halt APIs, and a UI cancellation control.

### Regression evidence

- Local release suite: 515 passed, 2 skipped; 85.64% backend coverage before final RC-only regressions.
- Frontend: `npm run check` and `npm run build` pass with zero diagnostics.
- Phase 10 CI: GitHub Actions run `33462022412` passed backend, frontend, Rust, Android, and smoke jobs.
- The final `v3.0.0-rc.1` tag is created only after the release-candidate commit passes the same mandatory CI matrix.

### Deliberate boundaries

- `rust_core/` and the Tauri draft are not product-integrated.
- X scraping and experimental OSINT/code-execution routes remain disabled or explicit opt-ins.
- A live third-party OpenRouter credential gate remains operator-triggered; the mandatory hermetic E2E uses the actual HTTP/SDK/runtime path against a deterministic local provider and does not claim external-provider availability.## [Unreleased] - 2026-09-04 (routing-hardening)
- O-1: substitution denials now carry structured requested_model/actual_model call-log
  fields in BOTH query() and legacy chat_completion (single-log doctrine kept);
  ModelSubstitutionDeniedError introduced; Aspasia TelemetryReader reads fields first,
  regex only as legacy fallback.
- O-2: bounded transient-only provider health breaker (env-tunable threshold/cooldown);
  consumed by agent_route_variants; policy denials and auth errors never counted;
  provider_health() surfaces remaining cooldown, Aspasia digest gains a SAĞLIK line only
  while blocked.
- O-3: model ladder filters direct candidates by RouteSpec.capabilities against
  required_capabilities (single source); quota/api-key isolation unchanged.
- O-4: guard test asserts ROUTES<->provider_catalog effective-price equality for every
  dual-priced route (precedence untouched; ROUTES remains SoT).
- Evidence: targeted 170/170, full suite 809P/0F/0S, ruff clean; proofs use fake transport
  only (no live/paid calls). CI not verified (session push-disabled). See
  docs/reports/ROUTING_HARDENING_2026-09-04.md.



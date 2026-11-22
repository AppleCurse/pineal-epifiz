
## 1 · Bu README nasıl okunur

| Sen | Burada |
|---|---|
| Yeni misin, ne yaptığını bilmiyorsun | 2, 3, 4 ve 9. bölümler |
| Kullanıcısın, arayüzü arıyorsun | 4 ve 10. bölümler |
| Geliştiricisin, koda bakacaksın | 5–8 ve 11–14. bölümler |
| "Bu gerçekten çalışıyor mu?" diye soruyorsan | 13. bölüm (ölçülen ↔ ölçülemeyen) |

Her bölümde geçen dosya yolları **gerçek kod yollarıdır**; iddiaların hepsi
`pytest`, `ruff`, `npm run check` ve canlı komut çıktılarıyla doğrulanmıştır.
Doğrulanamayan hiçbir şey "çalışıyor" diye yazılmamıştır.

---

## 2 · Sistem ne işe yarar

Bir Instagram (veya X) profilinin **herkese açık** sayfasını alırsın. Sistem:

1. **Toplar** — açık gönderiler, biyografi, fotoğraflar, paylaşım saatleri, açık web araması
   sonuçları, varsa e-posta/kullanıcı adı ayak izleri.
2. **Ölçer** — 7 dalga motoru zaman serisini ve metni **deterministik formüllerle** inceler
   (yapay zeka tahmini değil; FFT/Lomb-Scargle, istatistik, sözlük ölçümleri).
3. **Ajanlarla derinleştirir** — 14 görev ajanı sırayla çalışır; her biri kanıtını
   üretir, kararını ve güven puanını yazar.
4. **Doğrular** — iddialar dış kaynaklarla teyit edilir, yerel jüri oylar.
5. **Anlatır** — Aspasia seninle konuşur, Kontrol Paneli her şeyi canlı gösterir.

Çıktı bir "karakter analizi" değil, **kanıtıyla birlikte bir profil raporu**dur.

---

## 3 · Nasıl çalışıyor (akış)

```
sen: "https://instagram.com/kullanici/ hesabını incele"
  │
  ├─ POST /api/aspasia/command  → doğal dil komutu, hedef URL doğrulanır
  │     └─ kabul edilmezse sebep yazılır, görev UYDURULMAZ
  │
  ├─ POST /api/initiate         → görev başlar (kasa açık olmalı)
  │     ├─ yetenek omurgası: IG/X/web/e-posta/kullanıcı adı (her şey kasa kapısından)
  │     ├─ 7 dalga motoru → zaman serisi + metin ölçümleri
  │     ├─ 14 ajan sırayla çalışır → her ajan kanıt + karar + güven yazar
  │     └─ WS /ws/{client_id} → her an "ne oluyor" akışı
  │
  └─ GET /api/aspasia/state     → denetim görünümü (bütçe, kota, çağrı izi, anomali)
```

Kod yolları: `backend/api.py` → `agent_core/task_executor.py` (görev) →
`agent_core/services/cognitive_router.py` (ajan sırası) →
`agent_core/capabilities/` (dış dünyaya çıkış kapısı) → `agent_core/engines/` (ölçüm).

Toplanan biyografi/gönderi adresleri (`detected_urls`) görev yürütücüsünde
`agent_core/services/deep_profile_resolver.py` → `profile_router` →
`CapabilityRunner` zincirine girer; yani "bulundu" demek "tarandı" demektir.

---

## 4 · Ekranda ne görürsün

Uygulama tek sayfa; `frontend/src/App.svelte` iki dal çizer:

* **`cockpit`** (`UnifiedPinealCockpit.svelte`) — ana operasyon kokpiti: kasa
  mandalı, agent rafı, Aspasia komut/sohbet katmanı ve canlı görev/kanal
  durumu. Kokpitte `NeuralTelemetryBoard.svelte` (telemetri panosu, açılıp
  kapatılabilir) ve `SupportPanel.svelte` (açık talepler) ile birlikte render
  edilir.
* **Diğer tüm kipler** — `AtlasPortal.svelte` hizmet portalı. Varsayılan açılış
  görünümü `observatory`'dir (`frontend/src/store.ts`; `localStorage`
  `pineal_view_mode` ile değiştirilebilir) ve portaldaki "Gelişmiş: Teknik Konsol"
  düğmesi `cockpit`'e geçer. Portal sade, görev odaklı akıştır ("Neye ihtiyacınız
  var?" — 3 adım: konu → hedef → ne olacak); teknik derinlik tek tıkla ulaşılan
  konsolda toplanır.

`store.ts` içindeki `ViewMode` tipi gelecek/legacy kipleri de listeler, ama
`App.svelte`'in çizdiği yalnız yukarıdaki iki daldır — listelenmeyen kipler
için ayrı ekran YOKTUR.

**ASPASIA** — seninle konuşan katman (`POST /api/aspasia/chat`). Normal dille soru
sorarsın, sistem durumu anlatır. Kokpitin serbest metin kutusu önce
`/api/aspasia/command`'u dener (yani komut verip **görev başlatabilirsin**);
reddedilirse sebebi söyler, sahte bir "emir alındı" cevabı üretmez.

---

## 5 · Yedi dalga motoru (yapay zekasız, saf ölçüm)

Sistemde **7 dalga motoru** var (`agent_core/engines/`) — hepsi deterministik formülle
çalışır, LLM çağırmaz.

| Motor | Ne ölçer | Dosya |
|---|---|---|
| Frequency | Paylaşım saatlerinin ritmi, gece/gündüz dağılımı, periyodisite (FFT / Lomb-Scargle) | `frequency_engine.py` |
| Seismos | Ani durum sıçramaları, "kırılma" anları | `seismos_engine.py` |
| Void | Profilde **hiç** bahsedilmeyen konular (para, aile, zaaf…) | `void_engine.py` |
| Strata | Yıllar içindeki üslup kaymaları, terk edilen maskeler | `strata_engine.py` |
| Gravity | Kişinin sürekli döndüğü ana konular | `gravity_engine.py` |
| Pulse | Cümle ritmi, virgül/ünlem, duraksama | `pulse_engine.py` |
| Key | Altı motorun çıktısını birleştiren rezonans vektörü | `key_engine.py` |

---

## 6 · On dört görev ajanı

Sistemde **14 görev ajanı** var (`agent_core/task_executor.py:220`) — hepsi aynı süreç içinde, kural tabanlı
`CognitiveRouter` sırasıyla çalıştırır. (Docker'daki `beacon-*` servisleri yalnızca
canlılık işaretidir, analiz yapmaz.)

| Ajan | Ne yapar |
|---|---|
| `osint_investigator` | Kullanıcı adı (Maigret) ve e-posta (Holehe) ile açık kaynak ayak izi |
| `autonomous_verifier` | Profildeki iddiaları dış kaynaklarla teyit eder |
| `authenticity_auditor` | Beyan edilen ile görülenin tutarlılığını denetler |
| `human_behavior` | İlgi alanları ve davranış kalıpları |
| `passion_mapper` | Tutku, yaratıcılık ve entelektüel ilgi haritası |
| `friction_detector` | Sınırlar, hassasiyetler, yorulma ve şikâyet noktaları |
| `cognitive_profiler` | Dil tonu, iletişim üslubu, karmaşıklık düzeyi |
| `mirror_truth` | Kör noktalar ve derin ayna refleksiyonu |
| `resonance_calc` | İki profil arasındaki benzerliği **kanıt alanlarında** karşılaştırır |
| `pattern_interrupt` | Beklenti kırma ve temas stratejisi |
| `resonance_synthesizer` | İlk temas ve rezonans köprüsü sentezi |
| `depth_analyst` | 7 sütunlu derinlik çıktısının adli analizi |
| `shadow_executor` | Gölge arketip ve bastırılmış motivasyon (kanıt zinciri dışı strateji hattı) |
| `lilith_growth` | 360° profil + motor çıktılarından nörobilişsel strateji ve karşı-hamle paketi; nöro formülü yalnız motor ölçümü eksiksizse üretilir, motor sinyali yoksa `metrics_source="engine_signals_missing"` yazılır ve sabit değer UYDURULMAZ (`status.lilith_report`, kanıt zincirini kirletmez) |

`ENABLE_INTERPRETER=true` ile 15. ajan (`interpreter`) devreye girer.
`LilithGrowthAgent` hem `run_lilith.py` CLI'si hem de `PinealExecutor` + `POST /api/lilith/strategy` hattından tek kaynak olarak çalışır.

---

## 7 · Veri toplama kanalları (28 yetenek)

Sistemde **28 yetenek** var. `agent_core/capabilities/` — dış dünyaya **tek kapı**.
Hiçbir yetenek dış servise doğrudan gitmez; önce politika ve kasa kapısından geçer.
Canlı liste: `GET /api/telemetry` → 28 yetenek · 2-profil özeti: `GET /api/brain/capabilities`.

> **Kapı Kuralı (`PINEAL_CAPABILITY_PROFILE`):** Varsayılan `strict` (fail-closed; tüm `ENABLE_*` kapıları kapalı). `PINEAL_CAPABILITY_PROFILE=local_core` ücretli API anahtarı istemeyen **7** modülü tek şalterde açar — ancak **"anahtarsız" = "ağsız" değildir**: kasa kilitliyken dışarı çıkış olmaz, fakat kasa açıldığı anda bu modüller dış ağa (`egress`) aktif tarama yapar. Kapalı tutmak için `strict` profilinde kalın (tekil `ENABLE_*=false` satırları her zaman baskındır). `ENABLE_CROSS_PLATFORM` profile **bağlı değildir**: yalnız görev bazlı açık operatör onayı (`with_operator_consent`) veya `.env`'de açık `ENABLE_CROSS_PLATFORM=true` açar (`CONSENT_ONLY_FLAGS`; `GET /api/brain/capabilities` → `profiles.consent_only`).

| Grup | Yetenekler |
|---|---|
| Toplama (sensör) | `sensor.ig.instagrapi` (Instagram) · `sensor.x.twscrape` (X) · `sensor.search.searxng` (web arama) · `sensor.web.agent_reach` · `sensor.identity.holehe` (e-posta) · `sensor.identity.maigret` (kullanıcı adı) · `sensor.identity.handle_probe` (çapraz platform: IG/FB/Threads/X/TikTok…) · `sensor.identity.phone_probe` (telefon OSINT: operatör/şebeke/mesajlaşma) · `sensor.company.harvester` · `sensor.company.people` · `sensor.company.seo` · `sensor.media.fetch` |
| Çıkarma | `extractor.identity.socid` · `extractor.web.crawl4ai` · `extractor.web.scrapling` · `extractor.web.trafilatura` · `extractor.text.language` · `extractor.text.translate_local` · `extractor.media.transcript` |
| Analiz | `analyzer.media.frames` · `analyzer.media.similarity` |
| Doğrulama | `verifier.jury.local` (yerel jüri) |
| Sunum | `renderer.report.pdf` · `renderer.report.diagram` · `renderer.report.video` · `voice.report.script` |
| Ses | `voice.tts.local` · `voice.stt.local` |

**Bulunan adresler çöpe gitmez.** Instagram biyografisindeki link-in-bio adresleri
(Linktree/beacons/X/Threads…) ve X gönderi **ve** biyografi metinlerindeki
adresler `target_profile.detected_urls` alanına çıkarılır
(`agent_core/services/platform_registry.py::detected_profile_urls`), OSINT
kullanıcı-adı yoklamasının bulgularıyla
`agent_core/services/deep_url_cables.py::merge_detected_profile_urls` içinde
birleşir ve **derin taramaya** verilir. Profil olmayan adres (haber sitesi,
YouTube videosu) elenir — yanlış hedefe tarama yok.

**Gönderi tavanı tek yerden:** `PINEAL_IG_MAX_POSTS` (varsayılan **48**, üst
sınır 200) hem Playwright hattını hem `instagrapi` ikinci kaynağını bağlar;
sabit 12/20 tavanı kalmadı. Sayfalama kaydırma + `page_info.end_cursor` ile
ilerler, tavan operatörün kararıdır.

**Üçüncü taraf OSINT iddiası kanıt değildir.** `holehe` isabetleri
`epistemic_type="inference"` + `verification="unverified_third_party"` olarak
işaretlenir; tarama hata oranı yüksekse `reliability="low"` yazılır ve
"kayıtlı değil" iddiası yalnız **sıfır hatada** üretilir
(`agent_core/capabilities/adapters_osint.py`).

---

## 8 · Güvenlik: dört kilit

| Kilit | Ne yapar | Kod |
|---|---|---|
| **Kasa (vault)** | Anahtar girilmeden dışarı **tek bir** OSINT/kazıma isteği çıkamaz. Kasa girilince anahtar `set_key(..., unlock_live=True)` ile canlı LLM çağrıları da açılır. | `backend/api.py:3608` (`_check_vault_interlock`) · `llm_gateway.py:1412` (`set_key`) |
| **Çocuk kilidi** | Yaş tahmini yapılmaz; operatör beyanı varsa araştırma fail-closed durur. | `agent_core/safety/minor_gate.py` · `/api/minor/*` |
| **Fail-closed kanıt** | Veri/kanıt yoksa iddia üretilemez; kanal dürüstçe kapanır. | `InsufficientEvidenceError` |
| **Egress politikası** | Her dış çağrı yetenek omurgasından geçer; kapı kapalıyken "çalışıyor" denmez. | `agent_core/capabilities/policy.py` |

**Kapıların açılması (kilit değil, izin):** X ve Instagram sensörleri ile çapraz
platform yoklaması varsayılan olarak **kapalıdır**. Operatör
`POST /api/scraper/authorize-alternative` ile o görev için onay verdiyse
(`cross_platform` / `public_web_search`), onaya bağlı kapılar
(`ENABLE_CROSS_PLATFORM`, `ENABLE_X_SENSOR`, `ENABLE_IG_SECONDARY`) **yalnız o
görevde** açılır — kural tek yerde: `agent_core/capabilities/state.py::with_operator_consent`.
 `.env`'de bir bayrak **açıkça `false`** yazılıysa onay onu ezmez; kasa ve hız
kapıları hiçbir koşulda gevşemez. Onay yoksa sensör `policy:gate_disabled`
der — bunu "bozuk" diye yutturmaz.

---

## 9 · Nasıl çalıştırılır

**Windows'ta** (tek tık): depodaki `baslat.bat`.

**Docker ile** (Windows/Linux/macOS):

```bash
docker compose up --build -d
```

**Elle (geliştirici):**

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.lock

cd frontend
npm ci
npm run build                    # üretilen arayüzü hazırlar
```

**Çalıştır:**

```bash
.venv/bin/python -m uvicorn backend.api:app --host 0.0.0.0 --port 8000
```

Sonra tarayıcıda `http://localhost:8000` (ya da `frontend` klasöründe
`npm run dev` → `http://localhost:1420`).

**İlk yapılacak şey: kasa.** Uygulamadaki kasa mandalına **9Router anahtarını**
gir (adres varsayılan olarak `http://127.0.0.1:20128/v1`). Anahtar girilene kadar
canlı LLM çağrıları kapalıdır ve Aspasia dürüstçe "bağlantı çalışmıyor" der.
Anahtarı `.env` ile de verebilirsin (`NINEROUTER_API_KEY`). Küçük tuzak: 9Router
kipinde kasa anahtarı `sk-pineal` önekiyle başlamalıdır; normal `sk-...` anahtar
kasadan girilirse 9Router yolu seçilmez (ayrıntı: [RUNBOOK.md](RUNBOOK.md) M-3).

Ayrıntılı kurulum, port haritası ve canlıya alma kontrol listesi:
**[GO_LIVE.md](GO_LIVE.md)** · operasyon el kitabı: **[RUNBOOK.md](RUNBOOK.md)**.

---

## 10 · Aspasia'ya neler sorabilirsin

Kokpitin sol altındaki CRT terminali (veya `POST /api/aspasia/chat`) doğal dille
konuşur. Örnekler:

- "Şu an ne oluyor, hangi ajan çalışıyor?"
- "Bu profil ne ilgileniyor, kanıtları ne?"
- "Toplanan bilgi hangi ajandan geldi?"
- "Son LLM çağrısı hangi modele gitti, ne kadara mal oldu?"
- "Hangi kanal çalışmıyor, neden?"
- "Kasa kilitliyken ne yapılabiliyor?"

Cevaplar **canlı veriden** gelir; ölçüm yoksa "bilmiyorum + sebep" der.

Kontrol döngüsünü tek komutta kanıtlamak için:

```bash
python scripts/verify_command_loop.py --url https://instagram.com/KULLANICI/
```

Bu betik canlı komut → görev → ajan → kanıt → çağrı izi zincirini **gerçek API'ye
karşı** koşturur ve ham çıktıyı basar: `0` kanıtlandı · `1` döngü kırık (sebeple) ·
`2` ön koşul sağlanmadı · `Ctrl-C` → "DOĞRULANMADI".

---

## 11 · API yüzeyi (83 HTTP ucu + 1 WebSocket)

> Sayım biçimi: **83 = path+metot çifti**, **81 benzersiz yol**. Fark iki yoldan gelir: `/api/vault/status` hem `GET` (durum) hem `POST` (kilit aç/kapa), `/api/tasks/{task_id}` hem `GET` hem `DELETE` kabul eder. Sayı `backend.api.app.routes` üzerinden ölçülür.

| Alan | Uçlar | Ne yapar |
|---|---|---|
| **Aspasia** | `/api/aspasia/chat` · `/api/aspasia/command` · `/api/aspasia/state` | Konuşma · komut+görev · denetim görünümü (kayıtlı ajanlar, görev durumu, bütçe, kota, anomali, **çağrı izi**) |
| **Komutan & Dağıtım** | `/api/commander/dispatch` · `/api/commander/inject` · `/api/commander/phone-probe` | Herhangi bir ajana serbest görev verme + canlı düşünce zinciri (CoT), ikiz hesap/kanıt mühürleme ve telefon OSINT yoklaması |
| **Görev** | `/api/initiate` · `/api/tasks` · `/api/tasks/{id}` (sil) · `/api/tasks/{id}/…` (cancel, halt, resume, graph, changes, memory, support) · `/api/executor/intervene` | Görevi başlat, durdur, sürdür, gözlemle, müdahale et |
| **Kasa & güvenlik** | `/api/vault` · `/api/vault/status` · `/api/vault/lock` · `/api/vault/unlock` · `/api/minor/case` · `/api/minor/clear` · `/api/minor/state` | Anahtar yönetimi, canlı kapılar, çocuk kilidi |
| **Tarayıcı** | `/api/browser/*` (open, click, type, press, shot, state, save, back, close) | Playwright oturumu üzerinden gerçek sayfa gezinme |
| **Yetenek uçları** | `/api/company/*` · `/api/jury/*` · `/api/language/*` · `/api/media/*` · `/api/report/*` · `/api/mcp/status` · `/api/calibration/*` · `/api/scraper/authorize-alternative` | Kurum taraması, yerel jüri, dil, medya, rapor, MCP, kalibrasyon — her biri durum ucuyla "gerçekten yapılabiliyor mu" bilgisini verir. `authorize-alternative` ayrıca onaya bağlı sensör kapılarını (X/IG/çapraz) **o görev için** açar |
| **Mobil** | `/api/mobile/coach` | Android koç sohbeti: istem **sunucuda** kurulur, yanıt tek ağ geçidinden geçer; cihazda LLM anahtarı durmaz, istemci kendi sistem istemini gönderemez |
| **Tanılama** | `/health` · `/api/telemetry` · `/api/telemetry/taste` · `/api/agents/status` · `/api/memory/…` · `/api/dialogue/sessions` · `/api/experimental/*` | Sağlık, yetenek tablosu, ajan durumu, hafıza, oturumlar, deneysel hatlar |
| **OpenAI uyumlu** | `/v1/models` · `/v1/chat/completions` | OpenAI istemcileriyle birebir konuşma |
| **Canlı akış** | `WS /ws/{client_id}` | `snapshot_update` (her an durum) ve `result` (görev sonu + kanıt zinciri) |

---

## 12 · Bu sürümde ne yeni (P0 → P8)

| Faz | Ne değişti (kısa) |
|---|---|
| **P0** | Güvenlik kapılarının fail-closed düzeltmeleri; "çalışır gibi yapan" kod tespiti |
| **P1** | Profil derinleştirme: bulunan URL'ler artık otomatik olarak doğru yeteneğe gider |
| **P2** | Çapraz profilleme: 4 deterministik sinyal, her eşleşme `EvidenceItem` |
| **P3** | Lilith hat dışı (CLI-only) — kanıt zincirine karışmaz |
| **P4** | Mühür/kanıt kaydı düzeltmeleri; reddedilen taramalar da kayda bağlanır |
| **P5** | Kapanış denetimi: her düzeltmenin testi + revert-doğrulama kırmızıya döner |
| **P6** | Ölü kod dedektörü (`scripts/dead_code_audit.py`, CI'da kapı); 12 ölü arayüz dosyası silindi; 14 kayıtlı ajanın tamamı canlı |
| **P7** | Aspasia komut döngüsü (`/api/aspasia/command`) + **ilk canlı kontrol paneli** + çağrı kimliği bağı |
| **P8** | Panelin "en donanımlı" sürümü (6 blok, filtre, ajan detayı, kanıt zinciri gruplama), çağrı izi **sayfalaması**, `scripts/verify_command_loop.py` doğrulayıcısı, `api.py` satır tavanı 5772 → **5760** |
| **P9** | README baştan yazıldı (15 bölüm, düz dil) + `docs/envanter.html` sisteme bağlandı + `tests/unit/test_readme_claims.py` sayıları koddan ölçer |
| **P10** | Çapraz arama **kablosu**: IG bio ve X gönderi/biyografi adresleri `detected_urls` → derin tarama; operatör onayı X/IG sensörlerini o görev için açar; `holehe` iddiaları `inference` olarak etiketlendi; tek IG gönderi tavanı (`PINEAL_IG_MAX_POSTS`); Android koç sohbeti sunucuya taşındı (`/api/mobile/coach`); noktalı modül yoklaması (`agent_core/utils/optional_deps.py`) |

Ayrıntılı kayıt: **[CHANGELOG.md](CHANGELOG.md)** · denetim raporları:
`docs/reports/` (56 tarihli rapor).

---

## 13 · Durum tablosu: ölçülen çalışma ↔ DOĞRULANMADI

**ÖLÇÜLEBİLDİ (gerçekten koşturuldu, çıktısı görüldü):**

| Ne | Ölçüm |
|---|---|
| API ayakta | `/health` → **200** · `/api/telemetry` → **200** (28 yetenek) |
| Kayıtlı ajanlar | `/api/aspasia/state` → **14** ajan (kayıtlı `executor.agents`; `ENABLE_INTERPRETER=true` ile +1 opsiyonel `interpreter`) |
| Kasa kilidi | Kilitliyken `POST /api/initiate` → **423 VAULT_LOCKED** |
| WebSocket akışı | Yerel istemciyle **63 kare** alındı |
| Test tabanı | CI'ın kendi komutu (`pytest -q --cov=agent_core --cov=backend --cov-fail-under=80`) → **3283 passed, 6 skipped, 2 xfailed**, kapsam **%85.86** |
| Kod kalitesi | `ruff check .` → **All checks passed!** · `npm run check` → **0 hata / 0 uyarı** · `npm test` (vitest sözleşme testleri) → **6/6** · `npm run build` → ✓ |
| Denetim bekçileri | `audit_regression.py` → **✓ BEKÇİ GEÇTİ** · `dead_code_audit.py` → **0/0/0/0/0/0/0** (C1/C1b/C2/C3/C4/C5/C6) |
| Ölçülebilir ilerleme | `backend/api.py` **5493** satır (tavan 5760) |
| Revert-doğrulama | `scripts/revert_verification_p*.py` → **43/43** düzeltme geri alınınca test kırmızıya döndü (p0 7/7 · p1 6/6 · p2 3/3 · p3 4/4 · p4 5/5 · p8 10/10 · p9 8/8; her koşum dosyayı `finally` ile geri yükler) |
| Komut döngüsü | `scripts/verify_command_loop.py` → erişilemeyen API'de `rc=2` + sebep; kırık döngüde `rc=1` + sebep |
| Onay kablosu | Onay yok → `sensor.ig.instagrapi` / `sensor.x.twscrape` **`policy:gate_disabled`**; onay var → kapı **açık**, dürüst sebep `dependency_missing:*` (birim testi, sahte çalıştırıcı) |
| Bio/gönderi adres kablosu | Sahte `twscrape` → `bio` → `x_target_profile_update` → `detected_urls` → `merge_detected_profile_urls` zinciri uçtan uca koşuyor (çevrimdışı) |
| IG gönderi tavanı | Ham HTML yolunda 20 sahte gönderi → **20 post**; `PINEAL_IG_MAX_POSTS=5` → **5 post** (sabit 12 yok) |
| Ajan rotası | `CognitiveRouter` rota seti koşula bağımlıdır (hedef/kullanıcı kanıtı, goal seti, görsel kanıt); kayıtlı 14 ajanın tamamı varsayılan rotada koşmaz — rota **hedef/kullanıcı/görsel-kanıt koşullarına** göre daralır |
| 28 yetenek erişilebilir | `availability()` 28/28 **istisnasız** yanıt verdi (5 açık: socid, dil, handle_probe, phone_probe, rapor metni; 23'ü kapı/bağımlılık sebebiyle kapalı). Her kimliğin adaptör dışı çağrı yeri var; 3 web çıkarıcısı `WEB_EXTRACTION_ORDER` zinciriyle çağrılıyor (`web_research.py`) |
| Çağrı yeri olmayan uçlar | 81 benzersiz HTTP yolu: **25**'i UI/edge worker'dan, **77**'si testlerden çağrılıyor; **2**'sinin çağrı yeri yok (`/api/vault/lock`, `/api/tasks/{task_id}/changes`). Ölçüm `tests/unit/test_http_endpoint_call_sites.py` ile kilitli |
| Panelin görsel doğrulaması | Headless Playwright Chromium (`chrome-win64`) ile 1920×1080 çözünürlükte tam ekran görüntüsü alındı (`cockpit_live_visual.png`), pikselleriyle kanıtlandı |

**DOĞRULANMADI (sebebiyle):**

| Ne | Sebep |
|---|---|
| Canlı 9Router ile tam komut döngüsü (niyet → görev → 9 ajan → **canlı kanıt zinciri**) | Sandbox'tan `127.0.0.1:20128` erişilemiyor (HTTP 000) → komut dürüstçe reddedildi |
| Canlı Instagram / X kazıma | Egress kapalı + Canlı hesap oturumu doğrulanmadı |
| Canlı bio linki → derin tarama | Egress kapalı; zincir yalnız **sahte sensörle** (çevrimdışı birim testi) doğrulandı — canlı hesapta görülmedi |
| Canlı X akışı (`twscrape`) | Hesap havuzu boş → dürüst `no_session_pool`; operatör hesabı eklenmeden X kazıması çalışmaz |
| Canlı `socid`, canlı arama→derin tarama zinciri | Egress kapalı |
| `ENABLE_*` bayraklarının tamamı açık hâli | Kapılar kapalı tutuldu (görev talimatı) |
| Kasa anahtarının diskte şifrelenmesi | **Şifreleme YOK**: `.pineal_vault.json` düz JSON'dur (gitignore'da, uygulama yazmaz; operatör koyar). `repr=False` + log redaksiyonu anahtarı loglara sızdırmaz, `/api/vault/status` yalnız boolean döner. Kasa bir **yetki mandalı**dır, sır kasası değil |
| Atlanan 6 testin kapanması | 4'ü `requirements-retina.txt` paketleri (trafilatura/scrapling/twscrape/instagrapi) CI'da kurulmadığı için, 1'i PIL dolu/None dalı, 1'i open-interpreter opsiyonel katmanı. **2 xfail**: TikTok `tag` rezervi ve `t.me/s` önizlemesi — platform-bazlı rezerv tablosu P10'a devredildi |

---

## 14 · Depo haritası

| Klasör | İçinde ne var |
|---|---|
| `backend/` | HTTP + WS yüzeyi (`api.py` 5493 satır), uç modülleri (`routes/`), servisler (`services/`), güvenlik (`security/`) |
| `agent_core/` | Çekirdek: görev yürütücü, ajanlar, 7 dalga motoru, yetenek omurgası, hafıza, gölge hat |
| `frontend/src/` | Svelte arayüzü: 4 görünüm (Savaş Odası, Kontrol Paneli, SpiderFoot Kokpiti, Atlas Kokpiti) + ajan rafı + destek paneli |
| `rust_core/` | Deneysel, opsiyonel Rust çekirdek (CI'da ayrı derlenir, ürün yoluna bağlı değildir) |
| `android/` | Android istemcisi (CI'da lint + birim testi) |
| `functions/` · `worker.ts` | Cloudflare Pages/Workers `/api` ve `/ws` edge vekilleri |
| `tests/` | 302 test modülü (birim + entegrasyon) |
| `scripts/` | Denetim ve doğrulama araçları: ölü kod denetimi, regresyon bekçisi, envanter üreteci, revert doğrulamaları, 9Router ön kontrolü |
| `docs/` | Tüzük, sözleşmeler, mimari, aktif sözleşmeler ve **tam envanter sayfası** |
| `config/` | Yönlendirme, sağlayıcı kataloğu, karar yapılandırması, RTK politikası |

**Tam ve aranabilir harita:** **[docs/envanter.html](docs/envanter.html)** —
824 dosya, klasör klasör, her dosyanın açıklaması; `python scripts/generate_inventory_page.py`
ile yenilenir, CI `--check` ile bayatlamayı yakalar.

**Ayrıca:** [ARCHITECTURE.md](ARCHITECTURE.md) · [README_TECHNICAL.md](README_TECHNICAL.md) ·
[GO_LIVE.md](GO_LIVE.md) · [RUNBOOK.md](RUNBOOK.md) · [docs/PINEAL_TUZUK.md](docs/PINEAL_TUZUK.md)

---

## 15 · Testler ve kalite kapıları

```bash
.venv/bin/python -m pytest tests -q --cov --cov-fail-under=80   # 3283 passed
.venv/bin/ruff check .                                           # temiz
cd frontend && npm run check && npm run build                    # 0/0 + derleme
.venv/bin/python scripts/dead_code_audit.py                      # ölü kod yok
.venv/bin/python scripts/audit_regression.py                     # 24 denetim bulgusu bekçisi

# Revert-doğrulama: 43/43 (p0 7 · p1 6 · p2 3 · p3 4 · p4 5 · p8 10 · p9 8)
for s in 0 1 2 3 4 8 9; do .venv/bin/python scripts/revert_verification_p$s.py || exit 1; done
```

Revert betikleri **kirli ağaçta koşmayı reddeder** ve dosyayı `finally` ile geri
yükler; `tests/unit/test_revert_verification_contract.py` aradıkları metin
README'den/koddan koptuğunda ya da hedef test silindiğinde kırmızıya döner —
kanıt sessizce çürüyemez.

CI (`.github/workflows/ci.yml`) bunları ve ayrıca envanter tazeliliğini, sağlayıcı
kataloğunu, svelte tip kontrolünü, sözleşme testlerini (`npm test`), smoke testini,
Rust ve Android derlemesini çalıştırır.

**Kanlı ayrıntı — koşmayan kapı yok:** `9Router Preflight Verification` işi
operatörün makinesindeki hub'ı (`127.0.0.1:20128`) doğrular; barındırılan runner
oraya ulaşamaz. Kayıtlı self-hosted runner olmadığı için 2026-10-23'teki üç koşu
`queued` kalıp **hiç çalışmadı**. Bu yüzden zamanlanmış tetik kaldırıldı: kapı
artık elle (`workflow_dispatch`, hub'ın yanındaki runner'dan) ya da doğrudan
`python scripts/preflight_9router.py` ile koşar ve hub erişilemezse **exit 1**
(fail-closed). Sözleşmesi `tests/unit/test_preflight_runner_contract.py` içinde.

**Fiyat bekçisi neden "rejim" konuşuyor:** `deepseek/deepseek-v4-pro` iki günde
$0.2088–$0.95526 aralığında on bir ayrı fiyat okudu (her okumada çıktı = girdi ×2).
Tek bir pini kovalamak yakınsamıyordu; kapı artık (a) bilinen bir ölçülmüş durumu,
(b) ±%2 bandını, (c) **gözlenen rejim içinde ve girdi/çıktı oranı gözlenmiş
oranlarla uyumlu** fiyatı kabul eder; rejim dışı ya da oranı bozuk fiyat yine
`FAIL:` eder. Kalan risk adıyla yazılı: rejim içindeki büyük bir gerçek fiyat
hareketi ayırt edilemez (aynı aralıktaki her değer zaten kotasyon olarak gözlendi);
sınırlar `tests/unit/test_openrouter_catalog_contract.py` ile donduruldu.

# PINEAL EPİFİZ — YILDIZ DEPO KARAR AĞACI
## 325 Depo İçin Tek Parça Entegrasyon Hükmü (v6 Yol Haritası)

**Tarih:** 2026-10-05
**Karar mercii:** Bu belge, 325 yıldızlı depo ile `pineal-epifiz` (HEAD `e724ebd`, sürüm `3.0.0-rc.2`, kod tabanı ~59.600 satır Python) arasındaki entegrasyon kararlarını **tek merkezden** verir.
**Yöntem:**
- Pineal tarafı: `ARCHITECTURE.md`, `README.md`, `docs/reports/EKSIK_YETENEKLER_2026-09-26.md`, `docs/reports/SYSTEM_HEALTH_AND_INTEGRATION_MAP.md`, `agent_core/**`, `backend/api.py`, `config/*`, `requirements*.txt` üzerinde doğrudan kod okuması (iddia değil, kaynak okuması).
- Depo tarafı: kullanıcının sağladığı 325 kayıt + kısa liste için GitHub API'den **lisans / yıldız / son push** doğrulaması (2026-10-05). Kısa listeye girmeyen depolarda karar, depo adı ve verilen açıklamaya dayanır; **lisans sütunu "doğrulanacak" ise entegrasyondan önce G4 kapısı tekrar koşulur.**
- Hiçbir karar "popüler olduğu için" verilmedi. Her satır 8 kapıdan geçti.

**Okuma kuralı:** `E` = çekirdeğe birleşik entegrasyon · `A` = kapı arkası adaptör · `İ` = ilham/desen/veri kümesi (kod alınmaz) · `T` = ertele · `R` = red.

---

## 0. YÖNETİCİ ÖZETİ — HÜKÜM

| Sonuç | Adet | Anlamı |
|---|---|---|
| **E** · E* · E° | **9 + 1 + 7 = 17** | Çekirdeğe entegre. E = gerçek yetenek; E* = yalnız desen/şema; E° = **Agent Skills standardının benimsenmesi** |
| **A** · A* · A† | **39 + 7 + 5 = 51** | Kapı arkası adaptör. Varsayılan **kapalı**; yoksa dürüst `available:false`. A† = yalnız operatörün kendi kimliği / rıza kayıtlı hedef |
| **İ** | **191** | İlham / desen / envanter. **Kod alınmaz.** Mimari, kontrol listesi, veri kümesi |
| **T** | **16** | Ertele — doğru iş, yanlış zaman (Faz 6–9) |
| **MEVCUT** | **7** | Hâlihazırda entegre: maigret, socid-extractor, crawl4ai, 9Router, RTK (desen), CloakBrowser, opencv |
| **R** | **43** (42 kesin + 1 kısmi) | Red — §5'te gerekçeli kırmızı liste |

**Toplam 325 — hepsi karara bağlandı, hiçbiri "sonra bakarız" diye askıda bırakılmadı.**

Gerçek anlamda **kod içeri alınacak** depo sayısı: **17 entegrasyon + 51 adaptör = 68**. Geri kalan 257 kayıt, Pineal'i **desen, standart, veri kümesi ve disiplin** olarak besler. Bu oran bilinçlidir: benzersizlik depo sayısından değil, 68 yeteneğin **tek sözleşmeye bağlanmasından** doğar.

**Tek cümlelik hüküm:** 325 deponun çok küçük bir kısmı **gerçek yetenek**, büyük kısmı **desen/ilham**, bir kısmı ise **Pineal'in varlık sebebine aykırı** (karanlık ağ tarayıcıları, ses/yüz klonlama, jailbreak/sızdırılmış prompt külliyatı, otomatik mesaj gönderimi, filtresiz üretim). Benzersizliği sağlayacak olan şey depo sayısı değil; **hepsini tek sözleşmeye, tek kanıt zincirine, tek telemetriye ve tek güvenlik çekirdeğine bağlayan "Capability Spine" (Yetenek Omurgası)** ve Pineal'in hâlâ kapalı olan 7 yarasının kapatılmasıdır.

**En kritik 5 karar:**
1. **X/Twitter deliği kapatılır** — bugün `XScraperUnsupportedError` → `awaiting_authorization` (B4). `twscrape` (MIT) + `Agent-Reach` (MIT) ile **gerçek X sensörü** açılır; mevcut "alternatif public-web araştırması" yedek yol olarak kalır.
2. **SearXNG (AGPL-3.0) ayrı servis olarak** konumlandırılır — anahtarsız metasearch, Tavily/Exa/SerpAPI maliyetini ve tek sağlayıcı bağımlılığını kırar; AGPL yüzünden **kod gömülmez, HTTP üzerinden çağrılır**.
3. **Medya adli hattı kurulur** (yt-dlp Unlicense + gallery-dl GPL-2.0 harici süreç + opencv kare + PaddleOCR Apache-2.0 + pHash + tersine görsel arama) — bugünün en büyük boşluğu olan "video/ses/görsel kaynağı" kapanır.
4. **7 eksik yeteneğin tamamı kapatılır** (§9): tersine görsel arama, rıza/yaş kapısı, hedef tekrarı takibi, sosyal graf, video/ses, kalibrasyon, dil tespiti/çeviri. Bunların **hiçbiri tek bir depodan hazır gelmez**; her biri "spine + 1-2 adaptör" bileşimidir.
5. **Kırmızı çizgiler yazılır** (§5): karanlık ağ tarama, ihlal/şifre verisi, ses/yüz klonlama, jailbreak & sızdırılmış prompt, filtresiz üretim, otomatik mesaj gönderimi, konum izleme → **ürüne girmez, giriş kapısı kapatılır.**

---

## 1. KARAR AĞACI — 8 KAPI

Bir depo ancak 8 kapının **tamamından** geçerse ürüne girer. Kapılar sırayla uygulanır; ilk "RED" kararı kesindir (sonraki kapılar işletilmez, gerekçe kaydedilir).

```
                     [ 325 ADAY DEPO ]
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K0 · FELSEFE KAPISI                               │
   │ Pineal'in 4 dokunulmaz ilkesine uyuyor mu?        │
   │  1) LLM falcı değildir  2) Kanıt mührü (fail-     │
   │  closed)  3) %100 şeffaf, sıfır sahte simülasyon  │
   │  4) Kasa (vault) mandalı                          │
   └─────────────────────────┬─────────────────────────┘
                             │ geçti
   ┌─────────────────────────▼─────────────────────────┐
   │ K1 · ZARAR KAPISI (en sert kapı)                  │
   │ Yetenek, bir insana gerçek dünyada zarar verebilir│
   │ mi? (takip, kimlik ifşası, konum, taklit,         │
   │ manipülasyon, rızasız özel veri)                  │
   │ → EVET ise: yalnızca operatörün KENDİ verisi için │
   │   ve açık onayla; değilse RED                     │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K2 · KANIT MÜHRÜ KAPISI                           │
   │ Çıktı, EvidenceRecord'a (kaynak URL, alınma zamanı│
   │ hash, çıkarıcı, güven) bağlanabiliyor mu?         │
   │ Bağlanamıyorsa üründe YER YOK (uydurma riski)     │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K3 · RIZA & HUKUK KAPISI                          │
   │ Üçüncü kişi verisi mi? Platform ToS? KVVM/GDPR?   │
   │ Yaş/rıza kapısı gerektiriyor mu?                  │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K4 · LİSANS KAPISI                                │
   │ MIT/BSD/Apache-2.0 → içe alınabilir               │
   │ GPL-2/3 → YALNIZ harici süreç (subprocess/HTTP),  │
   │           kod gömülmez, import edilmez            │
   │ AGPL-3.0 → YALNIZ ayrı servis (konteyner), ağ     │
   │           üzerinden çağrılır, hiç gömülmez        │
   │ NOASSERTION → hukuki inceleme bitmeden AŞILMAZ    │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K5 · AYAK İZİ KAPISI                              │
   │ Çakışan pin var mı? Binary indiriyor mu? Soğuk    │
   │ başlangıç süresi? CI'a giriyor mu?                │
   │ (DERS: open-interpreter'ın starlette pini CVE      │
   │  düzeltmesini rehin almıştı — güvenlik hattı       │
   │  hiçbir aracın pinine rehin olamaz)               │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K6 · BENZERSİZLİK KAPISI                          │
   │ (a) Pineal'de zaten var mı? (maigret/socid/crawl4ai│
   │     /rtk/9Router/CloakBrowser MEVCUT)             │
   │ (b) 50-150 satırda, bağımlılıksız yazılabilir mi? │
   │     → EVET ise depo alma, kendi kodunu yaz (tek   │
   │       parça kalır, sürüm çatışması olmaz)         │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K7 · BİRLEŞME KAPISI (tek parça testi)            │
   │ Capability sözleşmesine, PolicyKernel'e, telemetri│
   │ şemasına ve evidence_chain'e bağlanabiliyor mu?   │
   │ Bağlanamıyorsa = yamalı bohça = RED/İ             │
   └─────────────────────────┬─────────────────────────┘
                             │
   ┌─────────────────────────▼─────────────────────────┐
   │ K8 · BAKIM KAPISI                                 │
   │ Son push < 6 ay? Tek bakımcı? Kırılgan private    │
   │ API mı? (instagrapi/GHunt örnekleri) → A/İ        │
   └─────────────────────────┬─────────────────────────┘
                             ▼
              E  ·  A  ·  İ  ·  T  ·  R
```

### Karar sözlüğü

| Kod | Tanım | Zorunlu koşullar (Definition of Done) |
|---|---|---|
| **E** | Çekirdek entegrasyon — birinci sınıf ürün yeteneği | Capability sözleşmesi + PolicyKernel kapısı + `available:false` yolu + telemetri olayı + evidence kaydı + birim & entegrasyon testi + dokümantasyon + `.env.example` kapısı |
| **A** | Adaptör — opsiyonel, kapı arkası | Varsayılan **kapalı** env anahtarı; bağımlılık yoksa dürüst `available:false`; ürün yolunu bloke etmez; ayrı `requirements-*.txt` (pin çatışması olmamalı) |
| **İ** | İlham / desen / veri kümesi | Kod alma yok. Alınan şey: mimari desen, kontrol listesi, site listesi, prompt disiplini, ürün felsefesi |
| **T** | Ertele | Faz 6+; şimdi alınırsa K5/K6/K7 kırılır |
| **R** | Red | §5'te gerekçeli kırmızı liste; tekrar değerlendirme ancak ilke değişirse |

---

## 2. MEVCUT DURUM RÖNTGENİ (kod okumasıyla doğrulanmış)

### 2.1 Güçlü olan / hazır olan

| Alan | Gerçek durum (kaynak) |
|---|---|
| Deterministik dalga motorları | 7 engine (`agent_core/engines/`) — LLM'siz, saf matematik. **Bu Pineal'in parmak izi; korunacak.** |
| Ajan matrisi | 16 ajan dosyası; router kural tabanlı (`cognitive_router.py`), LLM'siz rota |
| Kanıt disiplini | `evidence_chain`, `quote_guard`, `claim_decision_gate`, `uncertainty_engine` — sahte alıntı ve kanıtsız iddia aktif olarak engelleniyor |
| Platform kararı | `platform_registry.py` **tek kaynak**; kural [009]: ikinci platform katmanı yaratılmaz → yeni sensörler buraya bağlanır |
| LLM omurgası | `llm_gateway.py` (tier/retry/circuit breaker/JSON tamiri/vision) + 9Router yerel omurga + RTK politikası (`config/rtk_policy.json`) |
| Arama | `search_engine.py` — typed `SearchOutcome` (timeout/auth/rate-limit/no-result ayrımı) |
| Bellek | `canonical_memory.py` (JSON) + opsiyonel `hindsight_memory` (semantik) |
| Telemetri | Pydantic şema → FIFO kuyruk → WebSocket; Aspasia köprüsü |
| OSINT zenginleştirme | `maigret_scanner` + `holehe_scanner` + `socid_enricher` (hepsi kapı arkası, dürüst `available:false`) |
| Stealth | `browser_session.py` + `stealth_provider.py` (playwright_stealth / invisible-playwright / CloakBrowser hazır) |
| Test kültürü | 173 test dosyası; adli/forensik denetim raporları; her düzeltme için CONTROL/TREATMENT diff testi |

### 2.2 Kanayan yaralar (kendi denetiminizden + bu röntgenden)

| # | Yara | Kaynak | Kapatacak faz |
|---|---|---|---|
| Y1 | Tersine görsel arama / catfish & görsel kaynağı doğrulaması yok | `EKSIK_YETENEKLER #1` | Faz 3 |
| Y2 | Yaş/rıza kapısı yok | `EKSIK_YETENEKLER #2` | Faz 5 |
| Y3 | Hedef tekrarı / ısrar takibi yok (yalnız genel rate-limit) | `EKSIK_YETENEKLER #3` | Faz 4 |
| Y4 | Sosyal graf yok (yalnız sayısal etkileşim) | `EKSIK_YETENEKLER #4` | Faz 4 |
| Y5 | Video/ses içeriği analiz hattı yok (yalnız metadata) | `EKSIK_YETENEKLER #5` | Faz 3 |
| Y6 | Skor kalibrasyonu ve sonuç geri beslemesi yok (0.70 sabiti) | `EKSIK_YETENEKLER #6` | Faz 1 + 6 |
| Y7 | Dil tespiti / çeviri katmanı yok | `EKSIK_YETENEKLER #7` | Faz 1 |
| Y8 | **X/Twitter doğrudan sensörü yok** — `XScraperUnsupportedError` → `awaiting_authorization` (B4) | `scraper.py`, `backend/api.py:2238` | Faz 2 |
| Y9 | Kalıcı/geçmiş veri deposu yok (kanıt JSON; kalibrasyon için tarihçe gerekli) | `P0_PERSONAL_BASELINE_INFRASTRUCTURE_SCOPE` | Faz 1 |
| Y10 | Yetenekler tek kayıt defterinden yönetilmiyor (env + config + kod dağınık) | bu röntgen | Faz 0 |

> **Uyarı:** Y1–Y7 kullanıcının kendi denetiminde "hiçbiri tam uygulama olarak doğrulanmadı" diye kayda geçmiş. Bu yol haritasının birinci amacı bu 7 yaranın **kapanış kanıtını** üretmektir (§9).

---

## 3. HEDEF MİMARİ: TEK PARÇA = CAPABILITY SPINE

"Entegre edeceğiz, eklemeyeceğiz; bir bütün, birleşik, tek parça gibi olacak" ilkesinin teknik karşılığı şudur: **hiçbir depo doğrudan ürüne bağlanmaz.** Her yetenek — ister kendi kodumuz ister bir depodan gelsin — aynı sözleşmeden geçer.

### 3.1 Sözleşme

```python
# agent_core/capabilities/base.py  (Faz 0'da yazılacak — taslak)
class CapabilityKind(StrEnum):
    SENSOR = "sensor"        # dış dünyadan veri getirir
    EXTRACTOR = "extractor"  # ham veriden yapılandırılmış kanıt çıkarır
    ANALYZER = "analyzer"    # kanıt üzerinde deterministik/LLM analizi
    VERIFIER = "verifier"    # iddiayı çapraz doğrular
    MEMORY = "memory"        # kalıcı/geçmiş veri
    RENDERER = "renderer"    # rapor/görsel ihracatı
    TOOL = "tool"            # MCP/skill köprüsü

@dataclass(frozen=True)
class CapabilityResult:
    records: tuple[EvidenceRecord, ...]   # kanıt mührü: URL, retrieved_at, hash, extractor, confidence
    telemetry: tuple[TelemetryEvent, ...]
    cost_usd: float
    duration_ms: int
    available: bool
    unavailable_reason: str | None        # "paket yok" / "anahtar yok" / "kapı kapalı" — asla uydurma yok

class Capability(Protocol):
    id: str                       # "sensor.x.twscrape"  ·  "extractor.ocr.paddle"
    kind: CapabilityKind
    license: str                  # "MIT" | "GPL-2.0-external" | "AGPL-3.0-service"
    gates: frozenset[str]         # {"vault","consent","budget","rate","ENABLE_X"}
    def availability(self) -> Availability: ...          # çökmez; yoksa available=False
    async def run(self, ctx: CapabilityContext) -> CapabilityResult: ...
```

### 3.2 Akış (her yetenek için zorunlu yol)

```
PolicyKernel (vault → rıza/yaş → lisans → bütçe → hız → hedef-tekrarı)
        │  RED ise: capability ÇALIŞMAZ, sebebi telemetriye yazılır
        ▼
CapabilityRegistry.get("sensor.x.twscrape")   ← tek kayıt defteri
        ▼
CapabilityRunner  (timeout · retry · maliyet · telemetri · ölü-anahtar yok)
        ▼
EvidenceRecord[]  →  evidence_chain  →  ForensicStamp  →  UI / Aspasia / rapor
```

### 3.3 Kurallar (tartışmaya kapalı)

1. **Tek kayıt defteri:** Yetenek `config/capability_registry.json` + `CapabilityRegistry` dışında hiçbir yerde "var/yok" kararı vermez (C8 ölü-anahtar dersi: ikinci kaynak = sapma).
2. **Platform kararı yalnız `platform_registry.py`'dedir** — yeni sensör oraya adaptör olarak eklenir (kural [009]).
3. **Kanıtsız çıktı yok:** bir yetenek `EvidenceRecord` üretemiyorsa sonucu rapora yazılamaz.
4. **Sessiz başarısızlık yok:** bağımlılık/anahtar yoksa `available:false` + gerekçe; asla boş sonuç, asla uydurma.
5. **Güvenlik hattı rehin alınamaz:** hiçbir yeteneğin pin'i `starlette`/`fastapi` sürümünü aşağı çekemez (CVE-2026-48710 dersi). Aday: ayrı `requirements-<capability>.txt` veya harici süreç.
6. **Ölü yapılandırma yaratılmaz:** bir env anahtarı koda bağlanmadan dokümana yazılmaz.
7. **Simülasyon yok:** UI'a giden her değer gerçek telemetridir.

### 3.4 v6 katman haritası (hedef)

```
┌────────────────────────────────────────────────────────────────────┐
│  UI  Atlas Kokpit · Tactical War Room · Mobil/PWA · Rapor Fabrikası│
├────────────────────────────────────────────────────────────────────┤
│  PolicyKernel   vault · rıza/yaş · bütçe · hız · hedef-tekrarı      │
├────────────────────────────────────────────────────────────────────┤
│  CapabilityRegistry + Runner  (TEK SÖZLEŞME)                       │
├──────────┬──────────┬──────────┬──────────┬───────────┬────────────┤
│ Sensör   │ Çıkarıcı │ Analiz   │ Doğrula  │ Bellek    │ İhracat    │
│ Izgarası │ (OCR/ASR/│ (7 dalga │ (3 jüri, │ (kanıt +  │ (PDF/HTML/ │
│ IG·X·TT· │  EXIF/   │  + ajan  │  tersine │  zaman    │  video/    │
│ web·tel· │  pHash/  │  matrisi)│  görsel, │  serisi,  │  diyagram/ │
│ e-posta  │  dil)    │          │  çapraz) │  graf)    │  MCP)      │
├──────────┴──────────┴──────────┴──────────┴───────────┴────────────┤
│  Evidence Chain · Forensic Stamps · Telemetry (WS) · Kalibrasyon    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. YETENEK KÜMELERİ — GEREKÇELİ HÜKÜMLER

Her kümede: **neden** · **hangi depolar** · **nasıl tek parçaya dönüşür** · **Definition of Done**.

---

### K1 · OSINT Kimlik / Ayak İzi Tarama — **KISMEN MEVCUT, GENİŞLETİLECEK**

**Mevcut:** `maigret` (MIT), `socid-extractor` (MIT), `holehe` (GPL-3.0, harici) zaten kapı arkasında ve dürüst `available:false` döndürüyor. **Bu doğru desen — bozulmayacak, genişletilecek.**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E** (veri kümesi) | `75 WhatsMyName` (700+ site veri kümesi) | Kod değil **veri**: maigret'in site DB'sini ve nickname desenlerini tazelemenin en temiz yolu. Lisans NOASSERTION → G4 kapısı: yalnız JSON veri kümesi alınır, kod alınmaz. |
| **E** | `109 python-phonenumbers` (Apache-2.0) | Telefon numarasının **taşıyıcı/ülke/geçerlilik** doğrulaması. Konum izleme DEĞİL (K1 zarar kapısından geçen tek telefon yeteneği budur). |
| **A** | `117 theHarvester` (GPL-2.0 → harici süreç) | Kurumsal/domain hedef sensörü: e-posta, subdomain, isim. Pineal bugün kişi odaklı; kurumsal hedef yüzeyini açar. |
| **A** | `161 open-seo` (MIT) | Domain otoritesi / bağlantı / SEO metrikleri → kurumsal hedef için **sayısal kanıt**. |
| **A-kısıtlı** | `120 MailAccess`, `113 MailFinder`, `168 user-scanner` | E-posta/kullanıcı adı varlık taraması. **Yalnız operatörün kendi kimliği veya açık rıza kaydı olan hedef için**; üçüncü kişi için kapalı (KVVM). `user-scanner`'ın MCP desteği, capability paketleme için örnek. |
| **R** | `118 WhatBreach`, `119 pwnedOrNot`, `122 GHunt`, `15 toutatis`, `125 PhoneNumber-OSINT`, `8 osint-X`, `160 Gokboru_Intel` (konum kısmı) | İhlal/şifre verisi, gizli Google hesap verisi, gizli profillerden e-posta/telefon sökme, telefon **konum** takibi → K1+K3 ihlali. §5 kırmızı liste. |
| **İ** | `5,6,9,10,11,12,13,16,17,71,72,73,89,115,116,121,138,169,236,262(mevcut)` | Katalog/cheat-sheet/CLI koleksiyonları. Değer: **dork kütüphanesi**, site listeleri, sağlayıcı envanteri. Kod alma yok. `sherlock` ve `blackbird` maigret'le örtüşüyor → tekerlek yeniden icat edilmez. |
| **İ** | `7 instatracker` (106★, son push 2024) | Kod bakımsız AMA **desen altın değerinde**: profil değişimlerini zaman içinde loglama. Y3+Y9'un çekirdeği → K13'e taşındı. |

**Tek parça kuralı:** Bu kümenin her üyesi `sensor.identity.*` capability'si olur; çıktısı `EvidenceRecord(kind="identity_presence")`. Rapor doğrudan yazılmaz, `evidence_chain`'e girer.

---

### K2 · Sosyal Platform Sensörleri — **EN BÜYÜK AÇIK: X DELİĞİ**

**Mevcut:** Instagram tek gerçek sensör (Playwright+stealth). X → `XScraperUnsupportedError`. TikTok → yok.

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E** | `70 twscrape` (MIT, 2.8k★, aktif) | **X deliğinin birincil çözümü.** Çoklu hesap rotasyonu + gömülü rate-limit yönetimi. `awaiting_authorization` yolunu yedek bırakırız; birinci sınıf sensör olur. Kapı: `ENABLE_X_SENSOR` (varsayılan kapalı) + hesap havuzu yalnız operatörün kendi hesapları. |
| **A** | `315 Agent-Reach` (MIT, 91k★) | Twitter/Reddit/YouTube/GitHub/Xiaohongshu okuma, ücretsiz, tek CLI. twscrape'in yanına **ikinci kaynak**; Reddit/YouTube yüzeyini bedavaya açar. |
| **A** | `68 Douyin_TikTok_Download_API` (Apache-2.0) + `69 TikTokDownloader` (GPL-3.0 → harici süreç) | TikTok/Douyin sensörü + medya indirme. Lisans farkı yüzünden **68 birincil**, 69 harici süreç yedek. |
| **A** | `131 instagrapi` (NOASSERTION, private API) + `132 instaloader` (MIT) | Mevcut Playwright sensörünün **ikinci kaynak doğrulaması**. Private API kırılgan (K8) → asla birincil yol değil; yalnız çapraz teyit ve "Playwright engellendi" durumunda yedek. Lisans NOASSERTION → G4 incelemesi. |
| **E-desen** | `124 Osintgraph` (GPL-3.0 → desen) | Instagram takipçi/takip edilen **grafını** Neo4j'e yazıyor. Y4'ün (sosyal graf) ilham kaynağı; kod alma yok, **şema deseni** alınır (K13'te yerel graf + opsiyonel Neo4j). |
| **R** | `123 InstagramPrivSniffer` | "Gizli Instagram gönderilerini anonim görüntüleme" → rıza/özel alan ihlali, doğrudan kırmızı liste. |
| **R** | `155, 156, 157` (TikTok imza/kırma/patch) | X-Bogus/X-Gnarly kırma, SDK patch → platform ToS + hukuki risk. Pineal kırarak değil, **açık/self-hosted API** ile çalışır (68 yeter). |
| **İ** | `133 Osintgram`, `154 SoIG` | Komut/envanter referansı; maigret+Playwright kapsıyor. |

**DoD (Faz 2):** `platform_registry`'ye `x`, `tiktok`, `reddit`, `youtube` adaptörleri; her biri için `available:false` yolu; sensör yok → **sahte profil üretilmez** (mevcut B4 disiplini korunur).

---

### K3 · Web Kazıma / İçerik Çıkarma — **MEVCUT + 3 GÜÇLÜ EK**

**Mevcut:** `crawl4ai` (Apache-2.0) kapı arkasında.

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E** | `1 trafilatura` (Apache-2.0, 6.9k★, aktif) | Hafif, hızlı, kanıt için mükemmel: ham HTML → temiz metin + metadata. **crawl4ai ağır olduğunda birincil yol.** Lisans temiz, içe alınabilir. |
| **E** | `159 Scrapling` (BSD-3-Clause, 85k★, aktif) | **Adaptif kazıma:** site yapısı değişince kırılmaz, anti-bot direnci var. Pineal'in en kırılgan noktası (Playwright selector'ları) buradan güçlenir. `stealth_provider`'a üçüncü seçenek olarak eklenir (mevcut: playwright_stealth / invisible / Cloak). |
| **E** | `45 markitdown` (MIT) | Doküman → Markdown. **Office/PDF kanıtının** profile girmesini sağlar, hafif. |
| **A** | `43 marker` (Apache-2.0) · `42 surya` (Apache-2.0) | Ağır PDF/doküman ve 90+ dil OCR. `requirements-heavy.txt` ile ayrı kurulum, kapı arkası. |
| **A** | `44 MinerU` (lisans NOASSERTION → inceleme) | PDF/Office → LLM-ready. Güçlü ama lisans belirsiz → G4 blokajı kalkmadan girmez. |
| **A** | `163 SeleniumBase` (MIT) | CDP mode + captcha yönetimi → stealth yelpazesine 4. seçenek. |
| **İ** | `63 Scrapegraph-ai`, `64 crawlee`, `84 katana`, `114 scrapy`, `170 Photon`, `296 firecrawl`, `20 ai-website-cloner`, `51 stagehand` | Desen/envanter/ücretli servis. `crawlee` Node (yığın dışı), `firecrawl` ücretli → maliyet kapısı. |

**DoD:** `extractor.web.*` capability üçlüsü (trafilatura → crawl4ai → Scrapling) **tek arayüz, sıralı fallback**, hepsi aynı `EvidenceRecord`'u üretir.

---

### K4 · Arama — **MALİYET VE BAĞIMSIZLIK HAMLESİ**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E** | `28 SearXNG` (AGPL-3.0, 38k★, aktif) | Tavily/Exa/SerpAPI bağımlılığını ve maliyetini kırar; anahtar gerekmez, izlemez/profilimez. **Kritik kısıt:** AGPL-3.0 → **kod gömülmez**, ayrı konteyner/servis olarak koşar, Pineal yalnızca HTTP ile çağırır (docker-compose'a eklenir; imaja girmez). Tersine görsel arama (Y1) için de altyapı. |
| **A** | `161 open-seo` | (K1'de de geçiyor) domain metrikleri. |
| **İ** | `260 public-apis` | Sağlayıcı envanteri; ihtiyaç anında tarama. |
| **İ** | `185 last30days-skill` | "Son 30 günü araştır + sentezle" skill deseni → kendi `research.web_timeline` capability'miz için şablon. |

**DoD:** `SearchEngine`'e 4. sağlayıcı olarak `searxng` eklenir; `SearchOutcome` semantiği (timeout/auth/rate-limit/no-result ayrımı) **aynı** kalır; ölü anahtar yok.

---

### K5 · Tarayıcı / Otomasyon / Stealth — **DESEN AL, BAĞIMLILIK ALMA**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **A** | `18 BrowserSkill` (MIT) · `214 ego-lite` (MIT) · `179 actionbook` (Apache-2.0) | **Ortak desen: operatörün kendi oturumlu tarayıcısını paylaşması.** Pineal'in kasa/rıza felsefesiyle tam uyumlu — bot gibi davranmak yerine operatörün kendi kimliğiyle, izlenebilir biçimde erişim. `browser_session`'a "operator-session" modu olarak eklenir. |
| **İ** | `50 nanobrowser`, `52 playwright-mcp`, `135 chrome-devtools-mcp`, `208 agent-browser`, `230 Skyvern`, `285 browser-use`, `249 page-agent`, `87 OmniParser`, `88 Agent-S`, `86 OpenAdapt`, `218 cloudflare/computer` | Ajan-tarayıcı ekosistemi. Hepsi aynı işi yapıyor, hepsi ağır/bağımlılık zinciri getiriyor → **K6 benzersizlik**: Pineal'in kendi `browser_session`'ı var. Yalnız desen (CDP oturum yönetimi, captcha etiği) alınır. |
| **MEVCUT** | `267 CloakBrowser` | `.env.example` içinde `CLOAK_BROWSER_EXECUTABLE` zaten var → bu depo hâlihazırda stealth seçeneği. |
| **İ** | `163 SeleniumBase` → K3'te A | (çakışmayı önlemek için tek yerde) |

**İlke:** Oturum paylaşımı **açık ve kayıtlı** olur; gizli/anonim taklit yok (K1).

---

### K6 · LLM Omurgası / Çıkarım / Yönlendirme / Maliyet — **ÇOĞU ZATEN BİZDE**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **MEVCUT** | `261 9Router` | README'de yerel omurga olarak geçiyor → karar: **korunur**, capability kaydına alınır. |
| **MEVCUT-desen** | `217 rtk` (Apache-2.0) | `config/rtk_policy.json` + `llm_gateway` içinde Python mirror'ı **zaten var**. Depoyu almıyoruz; kendi politikamızı geliştiriyoruz. |
| **A** | `102 ollama` (MIT) · `61 llama.cpp` (MIT) · `60 vllm` (Apache-2.0) | Yerel çıkarım: `USE_LOCAL_LLM` zaten destekli. **Stratejik hedef: 3'lü jüriyi yerelde koşturmak** (maliyet + mahremiyet) → Faz 8. |
| **A** | `193 llmfit` (MIT) · `151 magnitude` (Apache-2.0) · `187 modular` · `300 airllm` | Hangi model donanımda koşar / hızlandırma. Yerel jüri kararının girdisi. |
| **İ** | `198 litellm` · `188 freellmapi` · `291 OmniRoute` · `204 CLIProxyAPI` · `139 OmniCopilot` · `21 django-ninja` · `22 litestar` | Gateway desenleri (maliyet izleme, guardrail, load balance, kota-farkında fallback). `llm_gateway` zaten bu işi yapıyor → **kod alma yok**, yalnız kontrol listesi: "maliyet gözlemlenebilirliği, kota-farkında otomatik düşüş, sağlayıcı sağlık probu". Ücretsiz-katman yönlendiricilerde (188/204/291) **yalnız operatörün kendi hesapları** kuralı; ToS riski notu düşülür. |
| **T** | `58 axolotl` · `59 LlamaFactory` · `215 unsloth` · `276 transformers` | İnce ayar: kendi hakem/jüri modelini eğitmek uzun vadeli ve çok pahalı. Faz 8+. |
| **İ** | `14 grok-1` | 314B ağırlık: pratik değil; yalnız referans. |

**İlke:** LLM omurgasına **yeni bağımlılık eklenmez**; mevcut `llm_gateway` + `provider_manager` + `quota_governor` korunur, yalnız gözlemlenebilirlik ve yerel jüri güçlendirilir.

---

### K7 · Ajan Çerçeveleri & Orkestrasyon — **NEREDEYSE TAMAMI İLHAM (K6/K7)**

Pineal'in kendi deterministik `task_executor` + kural tabanlı `cognitive_router` + kanıt mührü mimarisi varken CrewAI/LangFlow/AutoGPT sınıfı bir çerçeve eklemek, **"tek parça" ilkesini doğrudan ihlal eder** (ikinci orkestrasyon katmanı = kural [009] ihlali).

| Karar | Depolar | Alınan şey |
|---|---|---|
| **İ** (desen) | `55 letta` · `49 mem0` · `206 claude-mem` · `263 agentmemory` · `205 nanobot` · `216 loopx` · `213 prime-agent` · `301 deer-flow` | **Durumlu bellek ve uzun vadeli görev çekirdeği** desenleri. Pineal'in `task_lifecycle` + `canonical_memory`'sini güçlendirmek için. |
| **İ** (desen) | `302 gstack` · `209 agency-agents` · `325 ECC` · `266 financial-services` | **Rol/persona kütüphanesi** ve "ajanlara uzman rolü verme" disiplini → 3'lü jüri ve Aspasia persona'larının sürüm yönetimi. |
| **İ** (desen) | `158 MetaGPT` · `57 crewAI` · `56 agno` · `54 owl` · `274 agent-zero` · `280 OpenHands` · `289 openclaw` · `147 opencode` · `195 cline` · `237 codex` · `239 claude-code` · `277 dify` · `194 n8n` | Çok ajanlı SOP, rol tabanlı işbirliği, iş akışı editörü. **Bağımlılık yok.** İki somut alım: (a) yetenekleri webhook/CLI olarak dışa açma deseni, (b) operatör için görev panosu deseni. |
| **İ** | `34 lobehub` · `35 langflow` · `36 Flowise` · `37 activepieces` · `38 windmill` · `180 vibe-kanban` · `226 orca` · `211 paperclip` · `220 Antigravity-Manager` · `238 awesome-llm-apps` · `162 OpenMAIC` · `219 TradingAgents` · `251 MiroFish-Offline` · `252 BettaFish` · `219` | Görsel akış/orkestrasyon UI desenleri. Pineal'in Muharebe Masası zaten daha iyi bir "gözlemlenebilirlik" yüzeyi sunuyor. |
| **İ-kısıtlı** | `253 duh` (AGPL-3.0, 73★) | Çok-modelli konsensüs motoru: **desen olarak değerli** (3'lü jüri kalibrasyonu, Y6). Lisans AGPL → yalnız desen. |
| **R** | `250 MiroFish` | "Her şeyi tahmin eden sürü zekâsı" → Pineal'in 1. ilkesinin (LLM falcı değildir) **antitezi**. |
| **İ** | `34, 174?` → (174 K1'de) | — |

**Net hüküm:** Bu kümeden **sıfır bağımlılık**. Alınan tek şey desen ve disiplin.

---

### K8 · Bellek / RAG / Bilgi Grafı — **KANIT RAG'I + GRAF (Y4 ve Y9'un cevabı)**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **A** | `48 LightRAG` (MIT) · `273 cognee` (Apache-2.0) · `145 semantica` | Graf-RAG ve bilgi grafı altyapısı. Pineal'in `hindsight_memory`'si (sentence-transformers) basit semantik arama; **kanıt grafiği** (Y4) için graf-RAG deseni gerekli. Önce yerel graf (networkx + DuckDB), başarılı olursa bu desenler. |
| **A** | `313 Understand-Anything` · `177 code-review-graph` · `142 code-graph-rag` | Etkileşimli bilgi grafı **görselleştirme** desenleri → sosyal graf ve kanıt grafiğinin UI'ı (Muharebe Masası'na 5. sekme). |
| **İ** | `49 mem0` · `272 supermemory` · `100 anything-llm` · `271 open-notebook` · `197 private-gpt` · `101 jan` · `46 mcp-toolbox` · `47 ragflow` · `265 codegraph` · `206 claude-mem` · `263 agentmemory` | Bellek/RAG katmanı desenleri. Kritik uyarı: **RAG, kanıt mührünü atlayamaz.** getirilen her parça `EvidenceRecord`'a bağlanır, aksi halde halüsinasyon kaynağı olur. |
| **İ** | `275 js-langgraph-monorepo` | Node yığını, ilgisiz. |

**DoD (Faz 4/6):** `memory.graph` capability'si; yerel graf + opsiyonel Neo4j (Osintgraph şema deseni); graf düğümleri kanıt kimliği taşır; UI'da "İlişki Ağı" sekmesi.

---

### K9 · MCP / Skills / Araç Ekosistemi — **BİRLEŞTİRİCİ STANDART (Faz 7)**

Bu küme Pineal'i **benzersiz** kılacak yerlerden biri: kendi yeteneklerini hem **MCP sunucusu** hem de **Agent Skills** paketi olarak dışa açmak; dış araçları ise kum havuzunda tüketmek.

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E** (standart benimseme) | `322 anthropics/skills` · `318 obra/superpowers` · `136 vercel-labs/skills` · `183 scientific-agent-skills` · `182 garden-skills` · `212 addyosmani/agent-skills` · `299 mattpocock/skills` · `282 clawhub` | **Agent Skills (SKILL.md) standardını benimse.** Her Pineal yeteneği = bir skill + bir MCP aracı. Bu, "tek parça" iddiasını dışa da taşır: yetenek tanımı tek yerde (registry), dışa açılım otomatik. |
| **A** | `228 modelcontextprotocol/servers` · `53 awesome-mcp-servers` · `126 openai/plugins` | Referans sunucular + envanter. Pineal MCP sunucusu yazılırken **sözleşme uyumu** için referans. `openai/plugins`: tarihsel karşılaştırma (neden MCP kazandı) — aynı hataları yapmamak için. |
| **A** | `287 ui-ux-pro-max-skill` · `321 taste-skill` · `225 impeccable` · `146 diagram-design` · `144 archify` | Arayüz ve diyagram kalitesi skill'leri. Pineal'in rapor/UI üretim kalitesini yükseltir (K14). |
| **İ** | `186 i-have-adhd` | Çıktı biçimi disiplini (cevabı gömme) → Aspasia yanıt şablonu. |
| **İ** | `189 book-to-skill` · `152 caveman` · `178 context-mode` · `153 humanizer` · `259 system-prompts-and-models-of-ai-tools` | Skill üretimi, token tasarrufu, bağlam yönetimi, metin tonu. **Başkalarının sistem prompt'u kopyalanmaz** (K1/K3 + kırmızı liste); yalnız yapı incelenir. |
| **İ** | `258 prompts.chat` | Prompt kütüphanesi yönetimi → Pineal için **sürümlenmiş prompt kaydı** fikri (prompt'lar da kanıt gibi sürümlenmeli: hangi ajan, hangi prompt sürümü, hangi model). |
| **İ** | `241 karpathy-skills` · `283 ponytail` | Disiplin: "tek dosya ilke seti" ve "en iyi kod yazmadığın kod" → gereksiz capability yazmama kültürü (K6). |
| **İ** | `201 awesome-dsh-plugin` · `207 deepseek-harness` · `184 claude-plugins-official` | Plugin mimarisi desenleri. |

**DoD (Faz 7):** `capabilities/mcp_server.py` — registry'deki her capability, açık rıza ile MCP aracı olarak yayınlanır; her capability bir `SKILL.md` üretir; dış MCP araçları yalnız kum havuzunda (interpreter kapısı mantığıyla).

---

### K10 · Görsel / Doküman / OCR / Multimodal — **Y1 VE Y5'İN MERKEZİ**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E** | `269 PaddleOCR` (Apache-2.0) · `42 surya` (Apache-2.0) | OCR + layout; video karelerindeki ve belgelerdeki metni **kanıta** çevirir. 100+ dil → Y7 ile birleşir. Ağır → `requirements-heavy.txt`. |
| **E** | `314 opencv` (**zaten bağımlılık**) | Kare çıkarımı + **perceptual hash (pHash/dHash)**. Tersine görsel aramanın yerel yarısı: aynı fotoğrafın başka platformda/awanda kullanımı buradan yakalanır. |
| **A** | `39 ultralytics` | Nesne/sahne tespiti → görsel kanıtın zenginleşmesi (mevcut `VisionAnalyzer` multimodal modele ek olarak **deterministik** katman). |
| **A** | `295 OfficeCLI` (Apache-2.0) | Word/Excel/PPT kanıtlarını okuma; tek binary, Office kurulumu yok. |
| **A** | `43 marker` · `44 MinerU` · `45 markitdown` | (K3'te detaylı) doküman → metin. |
| **İ** | `82 HanLP` · `83 PaddleNLP` | Çince/NLP; Y7 çok dilli katmanı için **yalnız CJK dil desteği** gerektiğinde. |
| **İ** | `137 gods-eye-view` · `246 worldmonitor` | Coğrafi/mekânsal görselleştirme desenleri → konum kanıtı UI'ı (Y1'in coğrafya boyutu). |
| **İ** | `307 ImHex` | Hex editör; **desen:** medya dosyalarında EXIF/metadata/adli iz çıkarma kendi modülümüz olarak yazılır (pillow + opencv + piexif; ~150 satır = K6 kuralı gereği depo alınmaz). |
| **İ** | `270 NVIDIA/cosmos` | Dünya modelleri; video anlama araştırması. Ürüne girmez, izlenir. |
| **R** | `62 facefusion` · `248 deepfakes/faceswap` · `284 Deep-Live-Cam` | Yüz değiştirme/üretme. Pineal **üretmez, tespit eder.** Kırmızı liste. |
| **R** | `278 RuView` | WiFi sinyalinden canlı/yaşamsal izleme → Pineal'in işi değil, gizlilik riski. |
| **İ** | `270` · (yukarıda) | — |

**DoD (Faz 3):** `media` capability ailesi: `media.acquire` (yt-dlp/gallery-dl) → `media.frames` (opencv) → `media.ocr` (PaddleOCR/surya) → `media.asr` (whisper sınıfı, listede yok → kendi seçimimiz) → `media.phash` → `media.reverse_search` (SearXNG/SerpAPI görsel) → `media.metadata` (EXIF). Hepsi `EvidenceRecord` üretir; `AuthenticityAuditor` bu kanıtlarla **gerçek** catfish kontrolü yapar (bugün yalnız görsel-metin tutarlılığı yapabiliyor).

---

### K11 · Ses / Konuşma / Video — **ETİK AYRIM NET**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **R** | `97 fish-speech` · `98 GPT-SoVITS` · `99 RVC` · `164 Real-Time-Voice-Cloning` · `148 VoiceStudio` (klonlama kısmı) | **Ses klonlama.** Pineal sahici iletişim köprüsü kurmayı vaat eder; bir insanın sesini klonlamak bu vaadin ve tüm etik çerçevenin çöküşüdür. Kesin red. |
| **T** | `323 MOSS-TTS` · `324 VoxCPM` · `95 index-tts` · `303 voicebox` (TTS kısmı) | **Erişilebilirlik**: adli raporun seslendirilmesi, görme engelli operatör için Aspasia sesli yanıt. Yalnız bu amaçla, kapı arkası, hedef sesi taklit edilmeden, genel bir sesle. Faz 9. |
| **A** | `96 yt-dlp` (Unlicense) · `94 gallery-dl` (GPL-2.0 → harici süreç) | Video/ses **indirme** (analiz girdisi). Üretim değil, kanıt toplama. |
| **A** | `134 hyperframes` (Apache-2.0) · `304 OpenMontage` (AGPL-3.0 → desen) | HTML→video ve ajanlı video üretim: **adli raporun video dışa aktarımı** için desen (Faz 9). |
| **İ** | `245 speech-to-speech` · `279 AlphaAvatar` · `316 Open-LLM-VTuber` · `247 airi` | Gerçek zamanlı sesli etkileşim desenleri → "Sesli Aspasia" uzak hedef. Ürün kararı ayrı. |
| **İ** | `297 OpenCut` · `93 metube` | Video edit/indirici UI desenleri. |
| **İ** | `231/232` → K15 | — |

**Not — Y5'in son parçası:** listede **konuşma tanıma (ASR)** deposu yok. Bu yetenek dışarıdan seçilecek (faster-whisper/whisperx sınıfı, MIT/Apache). "Listede yok" diye boşluk bırakılmayacak; K6 gereği kendi değerlendirmemizle eklenecek.

---

### K12 · Saldırı / Karanlık Ağ / Jailbreak / Filtresiz — **KIRMIZI LİSTE (bkz. §5)**

`19 T3MP3ST` · `65 TorBot` · `66 darkfox` · `67 darknet-mcp-server` · `127 Darkweb-OSINT` · `128 dark-web-osint-tools` · `129 robin` · `130 deepdarkCTI` · `149 fanqiang` · `150 exploitarium` · `200 L1B3RT4S` · `255 free-claude-code` · `268 heretic` · `292 locally-uncensored` · `298 system_prompts_leaks` · `306 CL4R1T4S` · `308 hackingtool` · `309 PayloadsAllTheThings` · `310 Awesome-Hacking` · `320 G0DM0D3` · `254 Open-Generative-AI` · `281 postiz-app` → **R**.

Gerekçe özeti: Pineal bir **adli gözlem ve doğrulama** istasyonudur; saldırı, ihlal, sansür kırma, gizli erişim ve otomatik gönderim araçları hem hukuki hem de "kanıt mührü + rıza + şeffaflık" ilkeleriyle bağdaşmaz. `281 postiz-app` özelinde: Pineal'in ADR'si **hiçbir platforma otomatik mesaj göndermez**; o ilke korunur.

---

### K13 · Zaman Serisi / Kalıcılık / Kalibrasyon — **Y3, Y6, Y9'UN MERKEZİ**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **E-desen** | `7 instatracker` (MIT, bakımsız) | **Değişim izleme deseni**: profil anlık görüntülerini sakla, farkları çıkar. Y3 (hedef tekrarı), Y4 (ilişki değişimi) ve Y9 (tarihçe) hep bunun üzerine kurulur. Kod alınmaz, desen + şema alınır. |
| **E** | `40 scikit-learn` | Y6'nın kalibrasyon motoru: isotonic/Platt kalibrasyonu, güven-aralığı, backtest. Hafif, BSD, içe alınabilir. **0.70 sabiti, ölçülmüş ve belgelenmiş bir eşiğe dönüşür.** |
| **A** | `25 pocketbase` (MIT) · `165 nocodb` · `23 baserow` · `24 teable` · `167 supabase` | Kalıcı/geçmiş veri deposu. **Kritik ayrım:** kanıt deposu JSON kalır (ADR korunur); bunlar yalnız **kalibrasyon/tarihçe/operatör paneli** için. Birincil öneri: önce **DuckDB + SQLite** (sıfır servis), ihtiyaç büyürse PocketBase (tek dosya, MIT). |
| **A** | `222 authentik` | Ürün içi çok kullanıcılı yetkilendirme gerekirse (kurumsal senaryo). Şimdi değil. |
| **İ** | `103 Wallos` · `104 ghostfolio` · `105 actual` · `106 firefly-iii` | Local-first uygulama desenleri (veri senin cihazında) → Pineal'in "kişisel, yerel, hesap verme" duruşu için ürün referansı. |
| **İ** | `172 awesome-privacy` | Gizlilik alternatifleri envanteri → operatör kılavuzu ve kendi mahremiyet politikamız. |
| **İ** | `251 MiroFish-Offline` | Neo4j + Ollama **tamamen yerel yığın** deseni → Faz 8 yerel jüri için referans. |

**DoD (Faz 1/4/6):** `memory.timeline` (anlık görüntü + fark), `memory.store` (DuckDB), `calibration.engine` (sklearn), `safety.repeat_target` (hedef tekrarı sayacı + ısrar uyarısı).

---

### K14 · Arayüz / Rapor / Dağıtım — **ADLİ RAPOR FABRİKASI**

| Karar | Depolar | Gerekçe |
|---|---|---|
| **A** | `144 archify` (MIT) · `146 diagram-design` (MIT) | Self-contained HTML/SVG diyagram: kanıt akışı, zaman çizelgesi, ilişki ağı şemaları. Rapora gömülür, dış bağımlılık yok. |
| **A** | `134 hyperframes` | HTML → video: raporun sunulabilir video dışa aktarımı. |
| **A** | `257 Pake` (GPL-3.0 → harici süreç/derleme) | Web arayüzünü tek komutla masaüstü uygulamasına çevirme. **Tauri kabuğu ürün dışı** kararı korunur; Pake daha hafif bir yol olarak Faz 9'da değerlendirilir (GPL → dağıtım notu zorunlu). |
| **A** | `225 impeccable` · `287 ui-ux-pro-max-skill` · `321 taste-skill` | Tasarım dili ve UI/UX kalitesi — Pineal'in görselliği iddialı; jüri/UI üretiminde "AI slop"tan kaçınma disiplini. |
| **İ** | `107 vscode` · `108 zed` · `233 LibreChat` · `240 open-webui` · `317 hermes-webui` · `205 nanobot` (WebUI) | Arayüz desenleri; özellikle **mobil/web erişim** (hermes-webui) Pineal'in operatör deneyimi için referans. |
| **İ** | `286 rustdesk` | Uzak erişim; ürünle ilgisiz (operatör aracı). |

**DoD (Faz 9):** `renderer.report` capability ailesi: Markdown → PDF/HTML, kanıt diyagramları, TR/EN i18n, imzalı (hash'li) dışa aktarım.

---

### K15 · Geliştirici Deneyimi / Eğitim / Envanter — **İLHAM, SIFIR BAĞIMLILIK**

`3 blueprint-website` · `4 atom` · `29 wezterm` · `30 kitty` · `31 nushell` · `32 mise` · `33 starship` · `74 delta` · `76 zoxide` · `77 fzf` · `78 fd` · `79 ripgrep` · `80 eza` · `81 chezmoi` · `90 cheat` · `91 navi` · `92 tldr` · `110 LLMs-from-scratch` · `111 nn-zero-to-hero` · `112 micrograd` · `143 OpenLogi` · `191 omarchy` · `196 ghostty` · `203 Win11Debloat` · `224 AI-For-Beginners` · `227 bat` · `229 brew` · `231 dotfiles` · `232 modern-unix` · `234 awesome-cheatsheets` · `235 lazygit` · `242 awesome-python` · `243 free-programming-books` · `244 awesome` · `288 ohmyzsh` · `311 the-book-of-secret-knowledge` · `312 ai-engineering-from-scratch` · `319 build-your-own-x`

**Hüküm:** Hepsi **İ**. Bunlar Pineal'in ürün yeteneği değil; **operatör/geliştirici kültürü** ve eğitim malzemesi. Tek somut alım: `mise`/`chezmoi` benzeri **tekrarlanabilir geliştirici ortamı** (CI ile aynı sürümler) ve `delta/lazygit/ripgrep` ile adli denetim iş akışının hızlanması — bunlar depo değil, **takım alışkanlığı** kararıdır.

---

### K16 · Çeşitli / Tek Tek Değerlendirilenler

| Karar | Depo | Gerekçe |
|---|---|---|
| **A** | `293 open-interpreter` (Apache-2.0) | **Zaten entegre**: `requirements-interpreter.txt`, `ENABLE_INTERPRETER=false`, lazy import. Korunur; Faz 7'de MCP/skill kum havuzu olarak genelleştirilir. |
| **A** | `305 Ciphey` (MIT) | Şifre/kod çözme: **yalnız operatörün kendi verisi** üzerinde kanıt deşifre aracı. Üçüncü kişi verisinde kullanım yasak (K1/K3). |
| **A** | `179 actionbook` · `218 cloudflare/computer` · `192 block/buzz` | (K5'te) oturum/sandbox/iletişim desenleri. |
| **İ** | `223 alibaba/open-code-review` | **Hibrit deterministik + LLM** inceleme mimarisi — Pineal'in felsefesiyle birebir aynı. Kendi kod kalite kapımız için desen. |
| **İ** | `41 OpenBB` · `256 FinceptTerminal` | Veri platformu desenleri. |
| **İ** | `85 hacktricks` · `311` | Güvenlik bilgi tabanı (savunma tarafı, eğitim). Saldırı araçları değil. |
| **İ** | `264 hermes-agent` · `175 warp` · `199 gemini-cli` · `166 fastapi` (zaten kullanılıyor) · `178 context-mode` · `152 caveman` · `153 humanizer` · `266 anthropics/financial-services` · `283 ponytail` · `220 Antigravity-Manager` | Desen/envanter/araç. |
| **İ** | `246 worldmonitor` | (K10'da) |


---

## 5. KIRMIZI LİSTE — 43 DEPO VE GEREKÇELERİ

Bu bölüm "neden almadık" sorusunun kalıcı kaydıdır. Bir daha masaya gelmez.

### 5.1 Üçüncü kişinin rızasız özel verisi / gizli içerik (10)
`15 toutatis` · `118 WhatBreach` · `119 pwnedOrNot` · `122 GHunt` · `123 InstagramPrivSniffer` · `125 PhoneNumber-OSINT` · `171 phoneinfoga` · `8 osint-X` · `160 Gokboru_Intel` (konum kısmı) · `278 RuView`
**Gerekçe:** Pineal bir kişiyi **gözlemlenebilir açık kanıtla** anlamaya çalışır. Gizli hesaptan e-posta/telefon sökmek, ihlal veritabanlarından şifre çekmek, gizli gönderileri "anonim" okumak, telefonun yerini tespit etmek, WiFi sinyalinden canlı/yaşamsal izleme yapmak — bunlar gözlem değil **müdahale/izinsiz erişim**. KVVM/GDPR açısından "meşru menfaat" savunması, sistem tek bir kişiyi hedef aldığı için son derece zayıftır. Ayrıca kanıt mührü ilkesi: bunlardan üretilen çıktının **doğrulanabilir kaynak URL'si yoktur**, yani rapora giremez.

### 5.2 Karanlık ağ ve saldırı arsenali (13)
`19 T3MP3ST` · `65 TorBot` · `66 darkfox` · `67 darknet-mcp-server` · `127 Darkweb-OSINT` · `128 dark-web-osint-tools` · `129 robin` · `130 deepdarkCTI` · `149 fanqiang` · `150 exploitarium` · `308 hackingtool` · `309 PayloadsAllTheThings` · `310 Awesome-Hacking`
**Gerekçe:** Pineal'in ADR'si açık: sistem hiçbir platforma mesaj göndermez, saldırı yürütmez. Bu araçlar ürün felsefesini (adli gözlem) değil, saldırı yüzeyini büyütür; operatörü hukuki riske sokar; toplanan verinin mahkemede/denetimde **kaynağı gösterilemez**. `309/310/85` gibi bilgi tabanlarının yalnız **savunma/eğitim** kısmı okunabilir, ürüne kod girmez.

### 5.3 Jailbreak / sızdırılmış sistem prompt'u / sansür kırma (6)
`200 L1B3RT4S` · `268 heretic` · `292 locally-uncensored` · `298 system_prompts_leaks` · `306 CL4R1T4S` · `320 G0DM0D3`
**Gerekçe:** İki ayrı sebep. (1) **Güvenlik:** Pineal'in 3'lü jüri ve kanıt mührü mekanizması, modelin talimatlara uymasına bağlıdır; güvenlik sınırlarını kaldırmak jüri oylarını anlamsızlaştırır. (2) **Meslek etiği:** başkasının sistem prompt'unu sızdırıp kullanmak fikri mülkiyet ihlalidir ve Pineal'in "kendi sözleşmesini yazan" kimliğine aykırıdır. `259` yalnız **inceleme** amaçlı İ: başkasının prompt'u kopyalanmaz.

### 5.4 Kimlik taklidi — ses ve yüz klonlama (8)
`62 facefusion` · `97 fish-speech` · `98 GPT-SoVITS` · `99 RVC` · `164 Real-Time-Voice-Cloning` · `248 deepfakes/faceswap` · `284 Deep-Live-Cam` · `148 VoiceStudio` (klonlama kısmı)
**Gerekçe:** Pineal'in 12. ajanı *"manipülasyondan arındırılmış, sahici ilk temas köprüsü"* kurar. Bir insanın sesini veya yüzünü klonlayabilen bir araç, bu ürünün **varlık sebebinin inkârıdır**. Ayrıca doruk noktası: Pineal bir gün "bu profil sahte mi?" diye soracaksa (Y1), aynı depoda sahtesini üretebiliyor olamaz. İstisna: hedefin sesini taklit etmeyen, **erişilebilirlik** amaçlı genel TTS (`95/303/323/324`) Faz 9'da değerlendirilir.

### 5.5 Filtresiz üretim ve otomatik gönderim (3)
`254 Open-Generative-AI` · `292 locally-uncensored` · `281 postiz-app`
**Gerekçe:** `281` doğrudan ADR ihlali — Pineal mesaj **taslağı** üretir, göndermez. Otomatik gönderim, "operatör karar verir" ilkesini ve rıza kapısını devre dışı bırakır. Filtresiz üretim ise ürünün itibarını ve hukuki konumunu yakar.

### 5.6 Platform güvenlik mekanizmasını kırma (3)
`155 tiktok-web-reverse-engineering` · `156 tiktok-api` · `157 webmssdk_patch`
**Gerekçe:** X-Bogus/X-Gnarly imzalarını kırmak ve SDK'ya yama yapmak, açık kaynaklı ve self-hosted alternatif varken (`68`) gereksiz hukuki risktir. Pineal, kasa mandalı ve şeffaflık iddiası taşıyan bir araçtır; "gizli aşma" araçları bu iddiayı çürütür.

### 5.7 Hesap/abonelik paylaşımı riski (1 + 3 not)
`255 free-claude-code` → **R** (başkalarının abonelik/token havuzunu kullanmayı ürünleştirir).
`188 freellmapi` · `204 CLIProxyAPI` · `291 OmniRoute` → **İ**: bunlar operatörün **kendi** anahtarlarıyla koşan yönlendiricilerdir; Pineal'in kendi yerel omurgası (`261 9Router`) olduğu için üründe yer almazlar, yalnız "kota-farkında otomatik düşüş" kontrol listesi olarak okunur. Kural: **yalnız kendi hesapların, ilgili servis sözleşmesine uygun.**

### 5.8 Kısıtlı izin verilenler (5) — `A†`
`113 MailFinder` · `120 MailAccess` · `160 Gokboru_Intel` · `168 user-scanner` · `305 Ciphey`
Bunlar **yalnızca** (a) operatörün kendi kimliği veya (b) rıza kaydı oluşturulmuş hedef için çalışır. Üçüncü kişiye karşı otomatik kullanım yasaktır; Faz 5'in rıza defteri hazır olmadan bu kapılar açılmaz.

---

## 6. TAM HÜKÜM TABLOSU — 325 DEPO

Karar kodları: **E** entegre · **A** adaptör (kapı arkası) · **İ** ilham/desen · **T** ertele · **R** red · **MEVCUT** hâlihazırda entegre/desen olarak var · \* yalnız desen/veri kümesi · † yalnız rıza kaydıyla · ° Agent Skills standardının benimsenmesi.

| # | Küme | Depo | Karar | Gerekçe |
|---|---|---|---|---|
| 1 | K3·Web kazıma/çıkarma | `trafilatura` | **E** | HTML→temiz metin+metadata; Apache-2.0; hafif birincil |
| 2 | K1·OSINT kimlik/ayak izi | `007-TheBond` | **İ** | bakımsız bilgi toplama scripti |
| 3 | K15·Geliştirici deneyimi/eğitim | `blueprint-website` | **İ** | dokümantasyon sitesi deseni |
| 4 | K15·Geliştirici deneyimi/eğitim | `atom` | **İ** | editör mimarisi referansı |
| 5 | K1·OSINT kimlik/ayak izi | `OSINT-Toolkit` | **İ** | araç kataloğu; kod alma yok |
| 6 | K1·OSINT kimlik/ayak izi | `DIGI-NETRA` | **İ** | modüler sağlayıcı kayıt deseni |
| 7 | K13·Zaman/kalıcılık/kalibrasyon | `instatracker` | **E*** | değişim izleme DESENİ (kod bakımsız: son push 2024) |
| 8 | K1·OSINT kimlik/ayak izi | `osint-X` | **R** | telefon konum takibi → K1/K3 ihlali |
| 9 | K1·OSINT kimlik/ayak izi | `NotLoBi` | **İ** | OSINT cheat-sheet; dork kaynağı |
| 10 | K1·OSINT kimlik/ayak izi | `Coeus-OSINT-ToolBox` | **İ** | araç kutusu envanteri |
| 11 | K1·OSINT kimlik/ayak izi | `Social-Media-OSINT-Tools-Collection` | **İ** | SOCINT envanteri |
| 12 | K1·OSINT kimlik/ayak izi | `ShadXAlf` | **İ** | çerçeve envanteri |
| 13 | K1·OSINT kimlik/ayak izi | `tookie-osint` | **İ** | maigret ile örtüşüyor (K6) |
| 14 | K6·LLM omurgası/çıkarım/maliyet | `grok-1` | **İ** | 314B ağırlık; pratik değil |
| 15 | K1·OSINT kimlik/ayak izi | `toutatis` | **R** | gizli hesaptan e-posta/telefon sökme (2024'ten beri bakımsız) |
| 16 | K1·OSINT kimlik/ayak izi | `osint-tools` | **İ** | katalog |
| 17 | K1·OSINT kimlik/ayak izi | `X-osint` | **İ** | katalog |
| 18 | K5·Tarayıcı/stealth/otomasyon | `BrowserSkill` | **A** | operatörün oturumlu tarayıcısı; rıza modeline uygun |
| 19 | K12·Saldırı/dark web/jailbreak | `T3MP3ST` | **R** | otonom red-team harness |
| 20 | K3·Web kazıma/çıkarma | `ai-website-cloner-template` | **İ** | klonlama deseni; ürüne girmez |
| 21 | K6·LLM omurgası/çıkarım/maliyet | `django-ninja` | **İ** | API çerçevesi; FastAPI kullanıyoruz |
| 22 | K6·LLM omurgası/çıkarım/maliyet | `litestar` | **İ** | ASGI çerçevesi; kullanılmayacak |
| 23 | K13·Zaman/kalıcılık/kalibrasyon | `baserow` | **T** | kalıcı katman adayı (ağır); önce DuckDB |
| 24 | K13·Zaman/kalıcılık/kalibrasyon | `teable` | **T** | kalıcı katman adayı |
| 25 | K13·Zaman/kalıcılık/kalibrasyon | `pocketbase` | **A** | tek dosya yerel depo (MIT); DuckDB yetmezse |
| 26 | K13·Zaman/kalıcılık/kalibrasyon | `appwrite` | **T** | ağır yığın |
| 27 | K13·Zaman/kalıcılık/kalibrasyon | `immich` | **İ** | medya arşiv deseni |
| 28 | K4·Arama | `searxng` | **E** | anahtarsız metasearch; AGPL-3.0 → AYRI SERVİS, gömülmez |
| 29 | K15·Geliştirici deneyimi/eğitim | `wezterm` | **İ** | operatör terminali |
| 30 | K15·Geliştirici deneyimi/eğitim | `kitty` | **İ** | operatör terminali |
| 31 | K15·Geliştirici deneyimi/eğitim | `nushell` | **İ** | kabuk |
| 32 | K15·Geliştirici deneyimi/eğitim | `mise` | **İ** | tekrarlanabilir dev ortamı (CI ile aynı sürüm) |
| 33 | K15·Geliştirici deneyimi/eğitim | `starship` | **İ** | kabuk istemi |
| 34 | K7·Ajan çerçeveleri/orkestrasyon | `lobehub` | **İ** | ajan orkestrasyon UI deseni |
| 35 | K7·Ajan çerçeveleri/orkestrasyon | `langflow` | **İ** | görsel akış deseni |
| 36 | K7·Ajan çerçeveleri/orkestrasyon | `Flowise` | **İ** | görsel akış deseni |
| 37 | K7·Ajan çerçeveleri/orkestrasyon | `activepieces` | **İ** | entegrasyon tetikleyici deseni |
| 38 | K7·Ajan çerçeveleri/orkestrasyon | `windmill` | **İ** | script→webhook/UI deseni |
| 39 | K10·Görsel/doküman/OCR | `ultralytics` | **A** | deterministik nesne/sahne tespiti (görsel kanıt) |
| 40 | K13·Zaman/kalıcılık/kalibrasyon | `scikit-learn` | **E** | Y6 kalibrasyon: isotonic/Platt + backtest |
| 41 | K16·Çeşitli/tek değerlendirme | `OpenBB` | **İ** | veri platformu deseni |
| 42 | K10·Görsel/doküman/OCR | `surya` | **A** | OCR+layout 90+ dil (Apache-2.0) |
| 43 | K3·Web kazıma/çıkarma | `marker` | **A** | PDF→MD; ağır, ayrı kurulum |
| 44 | K3·Web kazıma/çıkarma | `MinerU` | **T** | lisans NOASSERTION → G4 incelemesi bitmeden girmez |
| 45 | K3·Web kazıma/çıkarma | `markitdown` | **E** | MIT; doküman→MD, hafif |
| 46 | K8·Bellek/RAG/bilgi grafı | `mcp-toolbox` | **İ** | veritabanı MCP deseni |
| 47 | K8·Bellek/RAG/bilgi grafı | `ragflow` | **İ** | RAG motoru deseni |
| 48 | K8·Bellek/RAG/bilgi grafı | `LightRAG` | **A** | MIT graf-RAG; kanıt grafiği adayı |
| 49 | K8·Bellek/RAG/bilgi grafı | `mem0` | **İ** | bellek katmanı deseni (RAG kanıt mührünü atlayamaz) |
| 50 | K5·Tarayıcı/stealth/otomasyon | `nanobrowser` | **İ** | tarayıcı ajanı deseni |
| 51 | K3·Web kazıma/çıkarma | `stagehand` | **İ** | SDK deseni |
| 52 | K5·Tarayıcı/stealth/otomasyon | `playwright-mcp` | **İ** | MCP tarayıcı referansı |
| 53 | K9·MCP/Skills/araç ekosistemi | `awesome-mcp-servers` | **A** | MCP envanteri (tüketim için kum havuzu şart) |
| 54 | K7·Ajan çerçeveleri/orkestrasyon | `owl` | **İ** | çok ajanlı desen |
| 55 | K7·Ajan çerçeveleri/orkestrasyon | `letta` | **İ** | stateful ajan deseni |
| 56 | K7·Ajan çerçeveleri/orkestrasyon | `agno` | **İ** | ajan platformu deseni |
| 57 | K7·Ajan çerçeveleri/orkestrasyon | `crewAI` | **İ** | rol tabanlı ajan işbirliği deseni |
| 58 | K6·LLM omurgası/çıkarım/maliyet | `axolotl` | **T** | ince ayar (Faz 8+) |
| 59 | K6·LLM omurgası/çıkarım/maliyet | `LlamaFactory` | **T** | ince ayar (Faz 8+) |
| 60 | K6·LLM omurgası/çıkarım/maliyet | `vllm` | **A** | yerel jüri çıkarımı (Apache-2.0) |
| 61 | K6·LLM omurgası/çıkarım/maliyet | `llama.cpp` | **A** | yerel LLM (MIT) |
| 62 | K10·Görsel/doküman/OCR | `facefusion` | **R** | yüz manipülasyonu |
| 63 | K3·Web kazıma/çıkarma | `Scrapegraph-ai` | **İ** | AI kazıma deseni |
| 64 | K3·Web kazıma/çıkarma | `crawlee` | **İ** | Node yığını; yığın dışı |
| 65 | K12·Saldırı/dark web/jailbreak | `TorBot` | **R** | dark web tarayıcı |
| 66 | K12·Saldırı/dark web/jailbreak | `darkfox` | **R** | dark web CTI |
| 67 | K12·Saldırı/dark web/jailbreak | `darknet-mcp-server` | **R** | dark web MCP (66 araç) |
| 68 | K2·Sosyal platform sensörleri | `Douyin_TikTok_Download_API` | **A** | Apache-2.0; TikTok/Douyin sensörü (BİRİNCİL) |
| 69 | K2·Sosyal platform sensörleri | `TikTokDownloader` | **A** | GPL-3.0 → harici süreç; yedek sensör |
| 70 | K2·Sosyal platform sensörleri | `twscrape` | **E** | X DELİĞİNİ KAPATIR; MIT, çoklu hesap + rate-limit |
| 71 | K1·OSINT kimlik/ayak izi | `Ominis-OSINT` | **İ** | Google dork arama deseni |
| 72 | K1·OSINT kimlik/ayak izi | `Emora-Project` | **İ** | GUI; maigret örtüşmesi |
| 73 | K1·OSINT kimlik/ayak izi | `enola` | **İ** | Go username tarayıcı; maigret örtüşmesi |
| 74 | K15·Geliştirici deneyimi/eğitim | `delta` | **İ** | git/diff görüntüleyici |
| 75 | K1·OSINT kimlik/ayak izi | `WhatsMyName` | **E** | 700+ site VERİ KÜMESİ (kod değil; lisans NOASSERTION→yalnız veri) |
| 76 | K15·Geliştirici deneyimi/eğitim | `zoxide` | **İ** | dizin atlama |
| 77 | K15·Geliştirici deneyimi/eğitim | `fzf` | **İ** | bulanık bulucu |
| 78 | K15·Geliştirici deneyimi/eğitim | `fd` | **İ** | find alternatifi |
| 79 | K15·Geliştirici deneyimi/eğitim | `ripgrep` | **İ** | hızlı regex arama (adli denetim iş akışı) |
| 80 | K15·Geliştirici deneyimi/eğitim | `eza` | **İ** | ls alternatifi |
| 81 | K15·Geliştirici deneyimi/eğitim | `chezmoi` | **İ** | ortam tekrarlanabilirliği |
| 82 | K10·Görsel/doküman/OCR | `HanLP` | **A** | CJK NLP; Y7 gerektiğinde |
| 83 | K10·Görsel/doküman/OCR | `PaddleNLP` | **İ** | CJK NLP referansı |
| 84 | K3·Web kazıma/çıkarma | `katana` | **İ** | crawler deseni |
| 85 | K16·Çeşitli/tek değerlendirme | `hacktricks` | **İ** | güvenlik bilgi tabanı (savunma/eğitim) |
| 86 | K5·Tarayıcı/stealth/otomasyon | `OpenAdapt` | **İ** | GUI görev derleme deseni |
| 87 | K5·Tarayıcı/stealth/otomasyon | `OmniParser` | **İ** | ekran ayrıştırma deseni |
| 88 | K5·Tarayıcı/stealth/otomasyon | `Agent-S` | **İ** | bilgisayar kullanan ajan deseni |
| 89 | K1·OSINT kimlik/ayak izi | `blackbird` | **İ** | maigret/holehe örtüşmesi |
| 90 | K15·Geliştirici deneyimi/eğitim | `cheat` | **İ** | cheatsheet |
| 91 | K15·Geliştirici deneyimi/eğitim | `navi` | **İ** | cheatsheet |
| 92 | K15·Geliştirici deneyimi/eğitim | `tldr` | **İ** | cheatsheet |
| 93 | K11·Ses/konuşma/video | `metube` | **İ** | indirici UI deseni |
| 94 | K11·Ses/konuşma/video | `gallery-dl` | **A** | GPL-2.0 → harici süreç; medya toplama |
| 95 | K11·Ses/konuşma/video | `index-tts` | **T** | erişilebilirlik TTS (Faz 9) |
| 96 | K11·Ses/konuşma/video | `yt-dlp` | **A** | Unlicense; video/ses indirme (kanıt girdisi) |
| 97 | K11·Ses/konuşma/video | `fish-speech` | **R** | ses klonlama |
| 98 | K11·Ses/konuşma/video | `GPT-SoVITS` | **R** | ses klonlama |
| 99 | K11·Ses/konuşma/video | `RVC` | **R** | ses klonlama/dönüştürme |
| 100 | K8·Bellek/RAG/bilgi grafı | `anything-llm` | **İ** | RAG UI deseni |
| 101 | K8·Bellek/RAG/bilgi grafı | `jan` | **İ** | yerel istemci deseni |
| 102 | K6·LLM omurgası/çıkarım/maliyet | `ollama` | **A** | yerel LLM (MIT) — USE_LOCAL_LLM zaten var |
| 103 | K13·Zaman/kalıcılık/kalibrasyon | `Wallos` | **İ** | local-first ürün deseni |
| 104 | K13·Zaman/kalıcılık/kalibrasyon | `ghostfolio` | **İ** | local-first ürün deseni |
| 105 | K13·Zaman/kalıcılık/kalibrasyon | `actual` | **İ** | local-first ürün deseni (Pineal'in duruşu) |
| 106 | K13·Zaman/kalıcılık/kalibrasyon | `firefly-iii` | **İ** | local-first ürün deseni |
| 107 | K14·Arayüz/rapor/dağıtım | `vscode` | **İ** | editör |
| 108 | K14·Arayüz/rapor/dağıtım | `zed` | **İ** | editör |
| 109 | K1·OSINT kimlik/ayak izi | `python-phonenumbers` | **E** | Apache-2.0; taşıyıcı/ülke/geçerlilik (KONUM YOK) |
| 110 | K15·Geliştirici deneyimi/eğitim | `LLMs-from-scratch` | **İ** | eğitim |
| 111 | K15·Geliştirici deneyimi/eğitim | `nn-zero-to-hero` | **İ** | eğitim |
| 112 | K15·Geliştirici deneyimi/eğitim | `micrograd` | **İ** | eğitim |
| 113 | K1·OSINT kimlik/ayak izi | `MailFinder` | **A†** | isim→e-posta; yalnız rıza kaydı olan hedef |
| 114 | K3·Web kazıma/çıkarma | `scrapy` | **İ** | ağır tarama gerekirse desen |
| 115 | K1·OSINT kimlik/ayak izi | `Social-Media-OSINT` | **İ** | koleksiyon |
| 116 | K1·OSINT kimlik/ayak izi | `awesome-osint-arsenal` | **İ** | koleksiyon |
| 117 | K1·OSINT kimlik/ayak izi | `theHarvester` | **A** | GPL-2.0 → harici süreç; domain/e-posta sensörü |
| 118 | K1·OSINT kimlik/ayak izi | `WhatBreach` | **R** | ihlal verisi (KVVM) |
| 119 | K1·OSINT kimlik/ayak izi | `pwnedOrNot` | **R** | sızmış şifre arama |
| 120 | K1·OSINT kimlik/ayak izi | `MailAccess` | **A†** | 5000+ platform; YALNIZ operatörün kendi adresi |
| 121 | K1·OSINT kimlik/ayak izi | `H4X-Tools` | **İ** | modüler araç seti deseni |
| 122 | K1·OSINT kimlik/ayak izi | `GHunt` | **R** | gizli Google hesap verisi; lisans NOASSERTION |
| 123 | K2·Sosyal platform sensörleri | `InstagramPrivSniffer` | **R** | gizli gönderi görüntüleme → rıza ihlali |
| 124 | K2·Sosyal platform sensörleri | `Osintgraph` | **A*** | GPL-3.0 → yalnız graf ŞEMA deseni (Y4) |
| 125 | K1·OSINT kimlik/ayak izi | `PhoneNumber-OSINT` | **R** | telefon konum takibi |
| 126 | K9·MCP/Skills/araç ekosistemi | `openai/plugins` | **A** | tarihsel plugin sözleşmesi; MCP karşılaştırma |
| 127 | K12·Saldırı/dark web/jailbreak | `Darkweb-OSINT` | **R** | dark web kaynakları |
| 128 | K12·Saldırı/dark web/jailbreak | `dark-web-osint-tools` | **R** | dark web araçları |
| 129 | K12·Saldırı/dark web/jailbreak | `robin` | **R** | AI destekli dark web OSINT |
| 130 | K12·Saldırı/dark web/jailbreak | `deepdarkCTI` | **R** | CTI beslemesi; otomatik hatta girmez |
| 131 | K2·Sosyal platform sensörleri | `instagrapi` | **A** | private API; kırılgan → ikinci kaynak, asla birincil |
| 132 | K2·Sosyal platform sensörleri | `instaloader` | **A** | MIT; ikinci kaynak çapraz teyit |
| 133 | K2·Sosyal platform sensörleri | `Osintgram` | **İ** | komut envanteri |
| 134 | K14·Arayüz/rapor/dağıtım | `hyperframes` | **A** | Apache-2.0; HTML→video rapor ihracı |
| 135 | K5·Tarayıcı/stealth/otomasyon | `chrome-devtools-mcp` | **İ** | MCP tarayıcı referansı |
| 136 | K9·MCP/Skills/araç ekosistemi | `vercel-labs/skills` | **E°** | Agent Skills standardı BENİMSENİR |
| 137 | K10·Görsel/doküman/OCR | `gods-eye-view` | **İ** | mekânsal görselleştirme deseni |
| 138 | K1·OSINT kimlik/ayak izi | `awesome-osint` | **İ** | envanter |
| 139 | K6·LLM omurgası/çıkarım/maliyet | `OmniCopilot` | **İ** | model yönlendirme kontrol listesi |
| 140 | K16·Çeşitli/tek değerlendirme | `x-algorithm` | **İ** | akış algoritması; dikkat ekonomisi referansı |
| 141 | K9·MCP/Skills/araç ekosistemi | `awesome-gpt-image-2` | **İ** | prompt kütüphanesi (üretim yok) |
| 142 | K8·Bellek/RAG/bilgi grafı | `code-graph-rag` | **A*** | graf görselleştirme deseni |
| 143 | K15·Geliştirici deneyimi/eğitim | `OpenLogi` | **İ** | donanım aracı |
| 144 | K14·Arayüz/rapor/dağıtım | `archify` | **A** | MIT; self-contained HTML/SVG kanıt diyagramı |
| 145 | K8·Bellek/RAG/bilgi grafı | `semantica` | **İ** | graf-yerel altyapı deseni |
| 146 | K14·Arayüz/rapor/dağıtım | `diagram-design` | **A** | MIT; editoryal diyagram (Mermaid çöpü yok) |
| 147 | K7·Ajan çerçeveleri/orkestrasyon | `opencode` | **İ** | capability paketleme deseni |
| 148 | K11·Ses/konuşma/video | `VoiceStudio` | **R/T** | klonlama RED; yerel TTS kısmı T |
| 149 | K12·Saldırı/dark web/jailbreak | `fanqiang` | **R** | erişim aşma aracı; ürünle ilgisiz |
| 150 | K12·Saldırı/dark web/jailbreak | `exploitarium` | **R** | exploit arşivi |
| 151 | K6·LLM omurgası/çıkarım/maliyet | `magnitude` | **A** | Apache-2.0; yerel çıkarım hızlandırma |
| 152 | K9·MCP/Skills/araç ekosistemi | `caveman` | **İ** | token tasarrufu deseni (RTK zaten var) |
| 153 | K9·MCP/Skills/araç ekosistemi | `humanizer` | **İ** | rapor dili ton deseni |
| 154 | K2·Sosyal platform sensörleri | `SoIG` | **İ** | IG veri çıkarma envanteri |
| 155 | K2·Sosyal platform sensörleri | `tiktok-web-reverse-engineering` | **R** | imza kırma (X-Bogus/X-Gnarly) |
| 156 | K2·Sosyal platform sensörleri | `tiktok-api` | **R** | güvenlik algoritmalarını kırma |
| 157 | K2·Sosyal platform sensörleri | `webmssdk_patch` | **R** | SDK yaması |
| 158 | K7·Ajan çerçeveleri/orkestrasyon | `MetaGPT` | **İ** | çok ajanlı SOP deseni |
| 159 | K3·Web kazıma/çıkarma | `Scrapling` | **E** | BSD-3-Clause; adaptif kazıma + anti-bot direnci |
| 160 | K1·OSINT kimlik/ayak izi | `Gokboru_Intel` | **A†** | yalnız taşıyıcı/geçerlilik; KONUM kısmı yasak |
| 161 | K4·Arama | `open-seo` | **A** | MIT; domain otoritesi/SEO kanıtı |
| 162 | K7·Ajan çerçeveleri/orkestrasyon | `OpenMAIC` | **İ** | çok ajanlı eğitim deseni |
| 163 | K3·Web kazıma/çıkarma | `SeleniumBase` | **A** | MIT; CDP mode + captcha → 4. stealth seçeneği |
| 164 | K11·Ses/konuşma/video | `Real-Time-Voice-Cloning` | **R** | ses klonlama |
| 165 | K13·Zaman/kalıcılık/kalibrasyon | `nocodb` | **T** | kalibrasyon verisi inceleme arayüzü |
| 166 | K16·Çeşitli/tek değerlendirme | `fastapi` | **İ** | ZATEN kullanılıyor |
| 167 | K13·Zaman/kalıcılık/kalibrasyon | `supabase` | **T** | ağır; DuckDB/PocketBase sonrası |
| 168 | K1·OSINT kimlik/ayak izi | `user-scanner` | **A†** | 2720+ vektör; MCP'li capability paket örneği |
| 169 | K1·OSINT kimlik/ayak izi | `osint_stuff_tool_collection` | **İ** | envanter |
| 170 | K3·Web kazıma/çıkarma | `Photon` | **İ** | hızlı crawler deseni |
| 171 | K1·OSINT kimlik/ayak izi | `phoneinfoga` | **R** | telefon OSINT/konum çerçevesi |
| 172 | K13·Zaman/kalıcılık/kalibrasyon | `awesome-privacy` | **İ** | mahremiyet politikası referansı |
| 173 | K1·OSINT kimlik/ayak izi | `socid-extractor` | **MEVCUT** | zaten entegre (MIT); korunur |
| 174 | K1·OSINT kimlik/ayak izi | `osint-namecheckers-list` | **İ** | site listesi veri kümesi (WhatsMyName ile birleşir) |
| 175 | K16·Çeşitli/tek değerlendirme | `warp` | **İ** | terminal |
| 176 | K7·Ajan çerçeveleri/orkestrasyon | `UI-TARS-desktop` | **İ** | GUI ajan deseni |
| 177 | K8·Bellek/RAG/bilgi grafı | `code-review-graph` | **A*** | graf görselleştirme deseni |
| 178 | K9·MCP/Skills/araç ekosistemi | `context-mode` | **İ** | bağlam/token optimizasyon deseni |
| 179 | K5·Tarayıcı/stealth/otomasyon | `actionbook` | **A** | Apache-2.0; operatör oturumuyla kaynak erişimi |
| 180 | K7·Ajan çerçeveleri/orkestrasyon | `vibe-kanban` | **İ** | operatör görev panosu deseni |
| 181 | K7·Ajan çerçeveleri/orkestrasyon | `Claudable` | **İ** | web üretim ajanı deseni |
| 182 | K9·MCP/Skills/araç ekosistemi | `garden-skills` | **E°** | skill paketleme deseni |
| 183 | K9·MCP/Skills/araç ekosistemi | `scientific-agent-skills` | **E°** | 177 skill; paketleme standardı |
| 184 | K9·MCP/Skills/araç ekosistemi | `claude-plugins-official` | **İ** | plugin dizini deseni |
| 185 | K4·Arama | `last30days-skill` | **A*** | zaman-pencereli araştırma skill deseni |
| 186 | K9·MCP/Skills/araç ekosistemi | `i-have-adhd` | **İ** | çıktı biçimi disiplini (Aspasia yanıtları) |
| 187 | K6·LLM omurgası/çıkarım/maliyet | `modular` | **T** | MAX/Mojo; yerel çıkarım (lisans NOASSERTION) |
| 188 | K6·LLM omurgası/çıkarım/maliyet | `freellmapi` | **İ** | ücretsiz sağlayıcı havuzu; yalnız kendi hesapların (ToS notu) |
| 189 | K9·MCP/Skills/araç ekosistemi | `book-to-skill` | **İ** | skill üretim deseni |
| 190 | K7·Ajan çerçeveleri/orkestrasyon | `openhuman` | **İ** | Rust harness deseni |
| 191 | K15·Geliştirici deneyimi/eğitim | `omarchy` | **İ** | Linux dağıtımı |
| 192 | K16·Çeşitli/tek değerlendirme | `block/buzz` | **İ** | iletişim platformu deseni |
| 193 | K6·LLM omurgası/çıkarım/maliyet | `llmfit` | **A** | MIT; hangi model donanımda koşar (yerel jüri seçimi) |
| 194 | K7·Ajan çerçeveleri/orkestrasyon | `n8n` | **İ** | iş akışı deseni; lisans NOASSERTION → bağımlılık yok |
| 195 | K7·Ajan çerçeveleri/orkestrasyon | `cline` | **İ** | kod ajanı deseni |
| 196 | K15·Geliştirici deneyimi/eğitim | `ghostty` | **İ** | terminal |
| 197 | K8·Bellek/RAG/bilgi grafı | `private-gpt` | **İ** | yerel RAG API katmanı deseni |
| 198 | K6·LLM omurgası/çıkarım/maliyet | `litellm` | **İ** | gateway kontrol listesi: maliyet/guardrail/yük dengeleme |
| 199 | K16·Çeşitli/tek değerlendirme | `gemini-cli` | **İ** | CLI ajan |
| 200 | K12·Saldırı/dark web/jailbreak | `L1B3RT4S` | **R** | jailbreak külliyatı |
| 201 | K9·MCP/Skills/araç ekosistemi | `awesome-dsh-plugin` | **İ** | plugin ekosistemi deseni |
| 202 | K7·Ajan çerçeveleri/orkestrasyon | `OpenManus` | **İ** | ajan deseni |
| 203 | K15·Geliştirici deneyimi/eğitim | `Win11Debloat` | **İ** | operatör terminali sertleştirme |
| 204 | K6·LLM omurgası/çıkarım/maliyet | `CLIProxyAPI` | **İ** | ücretsiz katman yönlendirme; ToS riski → kullanım yok |
| 205 | K7·Ajan çerçeveleri/orkestrasyon | `nanobot` | **İ** | hafif ajan + WebUI deseni |
| 206 | K8·Bellek/RAG/bilgi grafı | `claude-mem` | **İ** | oturumlar arası bellek deseni |
| 207 | K9·MCP/Skills/araç ekosistemi | `deepseek-harness` | **İ** | plugin mimarisi deseni |
| 208 | K5·Tarayıcı/stealth/otomasyon | `agent-browser` | **İ** | CLI tarayıcı deseni |
| 209 | K7·Ajan çerçeveleri/orkestrasyon | `agency-agents` | **İ** | persona/rol kütüphanesi (3'lü jüri için) |
| 210 | K7·Ajan çerçeveleri/orkestrasyon | `pi` | **İ** | ajan araç seti |
| 211 | K7·Ajan çerçeveleri/orkestrasyon | `paperclip` | **İ** | ajan yönetim UI deseni |
| 212 | K9·MCP/Skills/araç ekosistemi | `addyosmani/agent-skills` | **E°** | skill standardı |
| 213 | K7·Ajan çerçeveleri/orkestrasyon | `prime-agent` | **İ** | öz-gelişen ajan; ölçüm disiplini |
| 214 | K5·Tarayıcı/stealth/otomasyon | `ego-lite` | **A** | MIT; oturum paylaşımı (BrowserSkill ile aynı desen) |
| 215 | K6·LLM omurgası/çıkarım/maliyet | `unsloth` | **T** | yerel ince ayar |
| 216 | K7·Ajan çerçeveleri/orkestrasyon | `loopx` | **İ** | uzun vadeli görev durum çekirdeği |
| 217 | K6·LLM omurgası/çıkarım/maliyet | `rtk` | **MEVCUT*** | desen zaten Python mirror'ı (config/rtk_policy.json) |
| 218 | K16·Çeşitli/tek değerlendirme | `cloudflare/computer` | **A*** | izole sandbox deseni |
| 219 | K7·Ajan çerçeveleri/orkestrasyon | `TradingAgents` | **İ** | çok ajanlı finans deseni |
| 220 | K16·Çeşitli/tek değerlendirme | `Antigravity-Manager` | **İ** | operatör hesap aracı |
| 221 | K7·Ajan çerçeveleri/orkestrasyon | `AutoGPT` | **İ** | ajan deseni |
| 222 | K13·Zaman/kalıcılık/kalibrasyon | `authentik` | **A** | çok kullanıcılı yetkilendirme (kurumsal senaryoda) |
| 223 | K16·Çeşitli/tek değerlendirme | `open-code-review` | **İ** | deterministik+LLM hibrit — felsefemizin eşi |
| 224 | K15·Geliştirici deneyimi/eğitim | `AI-For-Beginners` | **İ** | eğitim |
| 225 | K14·Arayüz/rapor/dağıtım | `impeccable` | **A** | tasarım dili; UI kalitesi |
| 226 | K7·Ajan çerçeveleri/orkestrasyon | `orca` | **İ** | paralel ajan yönetimi deseni |
| 227 | K15·Geliştirici deneyimi/eğitim | `bat` | **İ** | cat alternatifi |
| 228 | K9·MCP/Skills/araç ekosistemi | `modelcontextprotocol/servers` | **A** | MCP referans sunucular (sözleşme uyumu) |
| 229 | K15·Geliştirici deneyimi/eğitim | `brew` | **İ** | paket yöneticisi |
| 230 | K5·Tarayıcı/stealth/otomasyon | `Skyvern` | **İ** | tarayıcı iş akışı AI deseni |
| 231 | K15·Geliştirici deneyimi/eğitim | `dotfiles` | **İ** | operatör yapılandırması |
| 232 | K15·Geliştirici deneyimi/eğitim | `modern-unix` | **İ** | araç envanteri |
| 233 | K14·Arayüz/rapor/dağıtım | `LibreChat` | **İ** | çoklu model sohbet UI deseni (Aspasia) |
| 234 | K15·Geliştirici deneyimi/eğitim | `awesome-cheatsheets` | **İ** | envanter |
| 235 | K15·Geliştirici deneyimi/eğitim | `lazygit` | **İ** | git TUI |
| 236 | K1·OSINT kimlik/ayak izi | `sherlock` | **İ** | maigret örtüşmesi; yalnız site listesi alınır |
| 237 | K7·Ajan çerçeveleri/orkestrasyon | `codex` | **İ** | kod ajanı |
| 238 | K7·Ajan çerçeveleri/orkestrasyon | `awesome-llm-apps` | **İ** | envanter |
| 239 | K7·Ajan çerçeveleri/orkestrasyon | `claude-code` | **İ** | kod ajanı |
| 240 | K14·Arayüz/rapor/dağıtım | `open-webui` | **İ** | UI deseni |
| 241 | K9·MCP/Skills/araç ekosistemi | `karpathy-skills` | **İ** | tek dosya ilke seti disiplini (PINEAL.md) |
| 242 | K15·Geliştirici deneyimi/eğitim | `awesome-python` | **İ** | envanter |
| 243 | K15·Geliştirici deneyimi/eğitim | `free-programming-books` | **İ** | eğitim |
| 244 | K15·Geliştirici deneyimi/eğitim | `awesome` | **İ** | envanter |
| 245 | K11·Ses/konuşma/video | `speech-to-speech` | **İ** | sesli arayüz deseni (uzak hedef) |
| 246 | K14·Arayüz/rapor/dağıtım | `worldmonitor` | **İ** | istihbarat panosu görselleştirme deseni |
| 247 | K11·Ses/konuşma/video | `airi` | **İ** | yalnız gerçek zamanlı ses etkileşim deseni |
| 248 | K10·Görsel/doküman/OCR | `deepfakes/faceswap` | **R** | yüz değiştirme |
| 249 | K5·Tarayıcı/stealth/otomasyon | `page-agent` | **İ** | sayfa içi GUI ajanı deseni |
| 250 | K7·Ajan çerçeveleri/orkestrasyon | `MiroFish` | **R** | 'her şeyi tahmin eden sürü' = fal ilkesi ihlali |
| 251 | K7·Ajan çerçeveleri/orkestrasyon | `MiroFish-Offline` | **İ** | Neo4j + Ollama yerel yığın deseni |
| 252 | K7·Ajan çerçeveleri/orkestrasyon | `BettaFish` | **İ** | çok ajanlı duygu analizi deseni |
| 253 | K7·Ajan çerçeveleri/orkestrasyon | `duh` | **A*** | AGPL → yalnız DESEN: çok modelli konsensüs (jüri kalibrasyonu) |
| 254 | K12·Saldırı/dark web/jailbreak | `Open-Generative-AI` | **R** | filtresiz görsel/video üretimi |
| 255 | K12·Saldırı/dark web/jailbreak | `free-claude-code` | **R** | ToS/hesap paylaşımı riski |
| 256 | K16·Çeşitli/tek değerlendirme | `FinceptTerminal` | **İ** | finans terminali deseni |
| 257 | K14·Arayüz/rapor/dağıtım | `Pake` | **A** | GPL-3.0; masaüstü kabuk (Faz 9, dağıtım notu şart) |
| 258 | K9·MCP/Skills/araç ekosistemi | `prompts.chat` | **İ** | sürümlenmiş prompt kaydı fikri |
| 259 | K9·MCP/Skills/araç ekosistemi | `system-prompts-and-models-of-ai-tools` | **İ** | inceleme; BAŞKASININ PROMPT'U KOPYALANMAZ |
| 260 | K4·Arama | `public-apis` | **İ** | sağlayıcı envanteri |
| 261 | K6·LLM omurgası/çıkarım/maliyet | `9router` | **MEVCUT** | yerel omurga; korunur, registry'ye kaydedilir |
| 262 | K1·OSINT kimlik/ayak izi | `maigret` | **MEVCUT** | zaten entegre (MIT); kapı arkası desen korunur |
| 263 | K8·Bellek/RAG/bilgi grafı | `agentmemory` | **İ** | kalıcı bellek + benchmark deseni |
| 264 | K16·Çeşitli/tek değerlendirme | `hermes-agent` | **İ** | ajan deseni |
| 265 | K8·Bellek/RAG/bilgi grafı | `codegraph` | **İ** | kod grafı deseni |
| 266 | K16·Çeşitli/tek değerlendirme | `anthropics/financial-services` | **İ** | alan paketi deseni (Pineal alan şablonları) |
| 267 | K5·Tarayıcı/stealth/otomasyon | `CloakBrowser` | **MEVCUT** | .env'de CLOAK_BROWSER_EXECUTABLE zaten var |
| 268 | K12·Saldırı/dark web/jailbreak | `heretic` | **R** | sansür kaldırma |
| 269 | K10·Görsel/doküman/OCR | `PaddleOCR` | **E** | Apache-2.0; 100+ dil OCR (kare + doküman) |
| 270 | K10·Görsel/doküman/OCR | `NVIDIA/cosmos` | **İ** | dünya modelleri; izlenir, ürüne girmez |
| 271 | K8·Bellek/RAG/bilgi grafı | `open-notebook` | **İ** | kanıt defteri deseni |
| 272 | K8·Bellek/RAG/bilgi grafı | `supermemory` | **İ** | bellek motoru deseni |
| 273 | K8·Bellek/RAG/bilgi grafı | `cognee` | **A** | Apache-2.0; graf bellek platformu (kanıt grafiği) |
| 274 | K7·Ajan çerçeveleri/orkestrasyon | `agent-zero` | **İ** | ajan çerçevesi |
| 275 | K8·Bellek/RAG/bilgi grafı | `js-langgraph-monorepo` | **İ** | Node yığını |
| 276 | K6·LLM omurgası/çıkarım/maliyet | `transformers` | **T** | yerel model/jüri (Faz 8) |
| 277 | K7·Ajan çerçeveleri/orkestrasyon | `dify` | **İ** | akış editörü deseni |
| 278 | K10·Görsel/doküman/OCR | `RuView` | **R** | WiFi ile canlı/yaşamsal izleme |
| 279 | K11·Ses/konuşma/video | `AlphaAvatar` | **İ** | gerçek zamanlı asistan deseni |
| 280 | K7·Ajan çerçeveleri/orkestrasyon | `OpenHands` | **İ** | ajan çerçevesi |
| 281 | K12·Saldırı/dark web/jailbreak | `postiz-app` | **R** | otomatik sosyal medya GÖNDERİMİ (ADR ihlali) |
| 282 | K9·MCP/Skills/araç ekosistemi | `clawhub` | **İ** | skill kayıt defteri deseni |
| 283 | K9·MCP/Skills/araç ekosistemi | `ponytail` | **İ** | 'yazmadığın kod en iyi kod' disiplini (K6) |
| 284 | K10·Görsel/doküman/OCR | `Deep-Live-Cam` | **R** | gerçek zamanlı yüz değiştirme |
| 285 | K5·Tarayıcı/stealth/otomasyon | `browser-use` | **İ** | ajan tarayıcı deseni |
| 286 | K14·Arayüz/rapor/dağıtım | `rustdesk` | **İ** | uzak masaüstü; ürünle ilgisiz |
| 287 | K14·Arayüz/rapor/dağıtım | `ui-ux-pro-max-skill` | **A** | UI/UX tasarım zekâsı skill'i |
| 288 | K15·Geliştirici deneyimi/eğitim | `ohmyzsh` | **İ** | kabuk |
| 289 | K7·Ajan çerçeveleri/orkestrasyon | `openclaw` | **İ** | ajan işletim deseni |
| 290 | K9·MCP/Skills/araç ekosistemi | `awesome-openclaw-skills` | **İ** | skill envanteri |
| 291 | K6·LLM omurgası/çıkarım/maliyet | `OmniRoute` | **İ** | ücretsiz havuz yönlendirme; ToS notu → kullanım yok |
| 292 | K12·Saldırı/dark web/jailbreak | `locally-uncensored` | **R** | filtresiz yerel üretim |
| 293 | K16·Çeşitli/tek değerlendirme | `openinterpreter` | **A** | ZATEN entegre; varsayılan kapalı, kum havuzu |
| 294 | K3·Web kazıma/çıkarma | `crawl4ai` | **MEVCUT** | zaten entegre (Apache-2.0) |
| 295 | K10·Görsel/doküman/OCR | `OfficeCLI` | **A** | Apache-2.0; Word/Excel/PPT kanıtını okur |
| 296 | K3·Web kazıma/çıkarma | `firecrawl` | **İ** | ücretli API; maliyet kapısı |
| 297 | K11·Ses/konuşma/video | `OpenCut` | **İ** | video edit deseni |
| 298 | K12·Saldırı/dark web/jailbreak | `system_prompts_leaks` | **R** | sızdırılmış sistem prompt'ları |
| 299 | K9·MCP/Skills/araç ekosistemi | `mattpocock/skills` | **E°** | skill standardı |
| 300 | K6·LLM omurgası/çıkarım/maliyet | `airllm` | **T** | 70B tek GPU; yerel jüri (Faz 8) |
| 301 | K7·Ajan çerçeveleri/orkestrasyon | `deer-flow` | **İ** | uzun vadeli araştırma ajanı; sandbox/alt-ajan deseni |
| 302 | K7·Ajan çerçeveleri/orkestrasyon | `gstack` | **İ** | ajan rolleri (CEO/QA/Doc) → jüri/persona deseni |
| 303 | K11·Ses/konuşma/video | `voicebox` | **T** | TTS/dikte erişilebilirlik (klonlama değil) |
| 304 | K11·Ses/konuşma/video | `OpenMontage` | **A*** | AGPL → yalnız video ihracı DESENİ |
| 305 | K16·Çeşitli/tek değerlendirme | `Ciphey` | **A†** | MIT; yalnız operatörün kendi verisinde deşifre |
| 306 | K12·Saldırı/dark web/jailbreak | `CL4R1T4S` | **R** | sızdırılmış prompt külliyatı |
| 307 | K10·Görsel/doküman/OCR | `ImHex` | **İ** | GPL-2.0; EXIF/metadata adli inceleme deseni |
| 308 | K12·Saldırı/dark web/jailbreak | `hackingtool` | **R** | çok amaçlı hack aracı |
| 309 | K12·Saldırı/dark web/jailbreak | `PayloadsAllTheThings` | **R** | saldırı payload külliyatı |
| 310 | K12·Saldırı/dark web/jailbreak | `Awesome-Hacking` | **R** | saldırı listeleri |
| 311 | K15·Geliştirici deneyimi/eğitim | `the-book-of-secret-knowledge` | **İ** | envanter |
| 312 | K15·Geliştirici deneyimi/eğitim | `ai-engineering-from-scratch` | **İ** | eğitim |
| 313 | K8·Bellek/RAG/bilgi grafı | `Understand-Anything` | **A** | etkileşimli kanıt grafiği görselleştirme |
| 314 | K10·Görsel/doküman/OCR | `opencv` | **MEVCUT** | zaten bağımlılık; kare + pHash |
| 315 | K2·Sosyal platform sensörleri | `Agent-Reach` | **A** | MIT 91k★; X/Reddit/YouTube/GitHub okuma, ücretsiz |
| 316 | K11·Ses/konuşma/video | `Open-LLM-VTuber` | **İ** | sesli etkileşim deseni |
| 317 | K14·Arayüz/rapor/dağıtım | `hermes-webui` | **İ** | mobil/web operatör arayüzü deseni |
| 318 | K9·MCP/Skills/araç ekosistemi | `obra/superpowers` | **E°** | skill çerçevesi + metodoloji |
| 319 | K15·Geliştirici deneyimi/eğitim | `build-your-own-x` | **İ** | eğitim |
| 320 | K12·Saldırı/dark web/jailbreak | `G0DM0D3` | **R** | jailbreak |
| 321 | K14·Arayüz/rapor/dağıtım | `taste-skill` | **A** | UI üretim kalitesi (AI slop karşıtı) |
| 322 | K9·MCP/Skills/araç ekosistemi | `anthropics/skills` | **E°** | Agent Skills standardı — BENİMSENİR |
| 323 | K11·Ses/konuşma/video | `MOSS-TTS` | **T** | erişilebilirlik TTS (Apache-2.0) |
| 324 | K11·Ses/konuşma/video | `VoxCPM` | **T** | erişilebilirlik TTS (Apache-2.0) |
| 325 | K7·Ajan çerçeveleri/orkestrasyon | `ECC` | **İ** | operasyonel disiplin: beceri/hafıza/güvenlik |

---

## 7. YOL HARİTASI — 10 FAZ

> Her fazın **kabul testi** yazılmadan faz "bitti" sayılmaz. Mevcut test kültürü (173 test dosyası, CONTROL/TREATMENT diff zorunluluğu) korunur.

### Faz 0 · CAPABILITY SPINE (omurga) — her şeyin ön koşulu
**İş:** `agent_core/capabilities/` (base sözleşme + registry + runner) · `PolicyKernel` (vault → rıza → bütçe → hız) · MEVCUT yeteneklerin registry'ye taşınması (maigret, socid, holehe, crawl4ai, vision, osint_investigator, 9router, rtk, interpreter) · UI'a **Yetenek Durumu** paneli (`available` / `available:false` + sebep).
**Kabul:** (1) repoda "yetenek var mı?" kararı veren tek yer registry (grep ile kanıtlanır); (2) her capability için `available:false` birim testi; (3) hiçbir capability doğrudan rapora yazmıyor (statik kontrol); (4) mevcut 173 test paketi düşüş yok.
**Yeni bağımlılık: YOK.**

### Faz 1 · DİL + GEÇMİŞ + KALİBRASYON İSKELETİ (Y6, Y7, Y9)
**İş:** `extractor.lang.detect` (hafif fasttext/lingua sınıfı) · `extractor.translate` (çeviri **kanıt kaybı yaratmaz**: orijinal metin korunur, `quote_guard` orijinalde eşleşir) · DuckDB geçmiş deposu (`memory.store`) · kalibrasyon iskeleti (`calibration.engine`, scikit-learn isotonic + backtest harness) · **0.70 eşiği "ölçülmemiş sabit" olarak işaretlenir** ve kalibrasyon raporuna bağlanır.
**Kabul:** TR/EN/DE/AR + CJK profil metni doğru işlenir; çeviri sonrası `quote_guard` yanlış pozitif üretmez (regresyon testi); geçmiş deposu bozuk dosyadan kurtulur (CanonicalMemory kurtarma testinin aynısı).

### Faz 2 · SENSÖR IZGARASI (Y8 + arama bağımsızlığı)
**İş:** `sensor.x.twscrape` (MIT) · `sensor.reddit/youtube.agent_reach` (MIT) · `sensor.tiktok.*` (`68` birincil, `69` harici yedek) · `extractor.web.trafilatura` (birincil) + `extractor.web.scrapling` (adaptif fallback) + crawl4ai (ağır fallback) · `search.searxng` (**ayrı konteyner**, imaja girmez) · `sensor.identity.phonenumbers` · maigret site DB'si `75/174/236` veri kümeleriyle tazelenir · `sensor.domain.theharvester` + `open-seo` (harici süreç).
**Kabul:** `platform_registry` 6 platformu tanır; her sensörün `available:false` yolu var; **X URL'si sensör açıkken `awaiting_authorization`'a düşmez**, sensör kapalıyken hâlâ sahte profil üretilmez (mevcut B4 testi korunur); SearXNG kapalıyken arama `SearchOutcome(UNAVAILABLE)` döner.
**Not:** `platform_registry` kural [009] gereği tek platform karar mercii olarak kalır — yeni sensörler oraya **adaptör** olarak eklenir.

### Faz 3 · MEDYA ADLİ HATTI (Y1, Y5)
**İş:** `media.acquire` (yt-dlp / gallery-dl harici) → `media.frames` (opencv) → `media.ocr` (PaddleOCR/surya) → `media.asr` (ASR modeli: listede yok, ayrı seçim) → `media.phash` (opencv+pillow) → `media.reverse_search` (SearXNG görsel / SerpAPI) → `media.metadata` (EXIF) · `platform_registry` adaptöründeki **video_url eksikliği** giderilir · `AuthenticityAuditor` tersine görsel arama + pHash ile **gerçek** catfish kontrolüne kavuşur.
**Kabul:** aynı fotoğrafın ikinci bir hesapta kullanımı fixture ile tespit edilir; video gönderiden kare+OCR kanıtı üretilir; OCR/ASR yoksa `UNAVAILABLE` (uydurma transkript yok).

### Faz 4 · GRAF + ZAMAN + KÖTÜYE KULLANIM (Y3, Y4)
**İş:** yerel kanıt/ilişki grafı (networkx + DuckDB; `124` şema deseni, `48/273` desenleri) · yorum/metion/ortak takipçi adaptörleri · `memory.timeline` anlık görüntü + fark (`7` deseni) · `safety.repeat_target`: hedefe özgü tekrar sayacı ve ısrar uyarısı (PolicyKernel içinde) · UI'da "İlişki Ağı" ve "Değişim" sekmeleri.
**Kabul:** aynı hedefe N. sorguda operatöre uyarı gider (test); iki tarama arası fark raporu üretilir; graf düğümleri kanıt kimliği taşır; graf boşsa sekme "kanıt yok" der.

### Faz 5 · RIZA & EMNİYET ÇEKİRDEĞİ (Y2)
**İş:** rıza defteri (hedef, amaç, kapsam, süre, silme) · **yaş kapısı** (reşit olmayan şüphesi → `halted_consent` + gerekçe) · retention ve `DELETE /api/tasks/{id}` kanıtı · denetim izi (kim, ne zaman, hangi yetenek, hangi hedef) · `A†` kapıları yalnız buradan sonra açılır.
**Kabul:** rıza kaydı olmayan hedefte analiz başlamaz (entegrasyon testi); yaş kapısı tetiklenince pipeline durur ve gerekçe rapora yazılır; silme sonrası hiçbir kanıt dosyası kalmaz.

### Faz 6 · KALİBRASYON & GERİ BESLEME (Y6 tamamlanışı)
**İş:** operatör geri bildirimi (sonuç doğrulaması) → isotonic/Platt kalibrasyonu → eşik yönetişimi (0.70 kalibre edilmiş ve **belgelenmiş** değere dönüşür; değişiklik = test + changelog) → yıllık backtest raporu · `253 duh` çok-modelli konsensüs deseniyle jüri ağırlıklandırma.
**Kabul:** her skor yanında güven aralığı; `halted_frequency` kararlarının gerçek sonuçlarla karşılaştırma tablosu; kalibrasyon verisi olmadan eşik değişikliği **reddedilir** (CI kapısı).

### Faz 7 · BİRLİKTE ÇALIŞABİLİRLİK (MCP + Skills)
**İş:** `capabilities/mcp_server.py` — registry'deki her capability açık rıza ile MCP aracı olarak yayınlanır · her capability için `SKILL.md` üretimi (Agent Skills standardı: `322/318/136/183/212/299`) · kum havuzu: dış araçlar `293 open-interpreter` deseninde izole ve kapalı kapı · webhook/CLI ihracı.
**Kabul:** tüm capability'ler MCP araç listesinde görünür; dış araç çağrısı ayrı süreçte ve izole; kapalıyken uç nokta 404.

### Faz 8 · YEREL & MAHREM
**İş:** yerel 3'lü jüri (ollama / llama.cpp / vllm + `193 llmfit` ile donanım seçimi + `151 magnitude` hızlandırma) · maliyet gözlemlenebilirliği (`198 litellm` kontrol listesi) · RTK genişletme.
**Kabul:** kasa kapalı + internet yokken temel analiz hattı çalışır ve maliyet 0; yerel model yoksa dürüst `UNAVAILABLE`.

### Faz 9 · RAPOR FABRİKASI & DAĞITIM
**İş:** kanıt bağlantılı PDF/HTML rapor · diyagramlar (`144 archify`, `146 diagram-design`, gömülü SVG) · video ihracı (`134 hyperframes` / `304` deseni) · tam TR/EN eşliği · masaüstü kabuk (`257 Pake`, GPL dağıtım notuyla) · erişilebilirlik TTS (`323/324/95/303`).
**Kabul:** rapor hash'li ve her iddia kanıt kimliğine bağlı; TR/EN metin eşliği testi; dışa aktarımda gizli anahtar sızmaz (mevcut redaction testleri genişletilir).

### Bağımlılık grafiği
```
Faz 0 ──┬── Faz 1 ──┬── Faz 4 ──┬── Faz 6 ──┐
        │           │           │           │
        ├── Faz 2 ──┴── Faz 3 ──┤           │
        ├── Faz 5 ──────────────┤           │
        ├── Faz 7 (0'a bağlı)   │           │
        ├── Faz 8 (bağımsız)    │           │
        └─────────────────────── Faz 9 ←────┘
```

---

## 8. RİSK, LİSANS VE BAKIM MATRİSİ

### 8.1 Lisans kısıtları (GitHub API ile doğrulandı, 2026-10-05)

| Lisans | Kural | İlgili depolar |
|---|---|---|
| AGPL-3.0 | **Kod gömülmez, import edilmez.** Yalnız ayrı konteyner/servis, HTTP ile çağrılır. | `28 searxng`, `253 duh`, `304 OpenMontage` |
| GPL-3.0 | Yalnız **harici süreç** (subprocess/CLI) veya yalnız **veri/desen**; imaja gömülmez. | `94 gallery-dl`(GPL-2), `69 TikTokDownloader`, `117 theHarvester`(GPL-2), `257 Pake`, `124 Osintgraph` |
| NOASSERTION | Hukuki inceleme bitmeden **AŞILMAZ**. | `44 MinerU`, `75 WhatsMyName`(yalnız veri), `122 GHunt`, `131 instagrapi`, `194 n8n`, `198 litellm`, `277 dify`, `187 modular`, `178 context-mode` |
| MIT / BSD / Apache-2.0 / Unlicense | İçe alınabilir (K5 pin kontrolüyle). | `70 twscrape`, `1 trafilatura`, `159 Scrapling`, `269 PaddleOCR`, `96 yt-dlp`, `45 markitdown`, `315 Agent-Reach`, … |

### 8.2 Teknik riskler

| Risk | Örnek | Karşı önlem |
|---|---|---|
| **Pin rehin alma** | open-interpreter'ın starlette pini CVE-2026-48710 düzeltmesini engellemişti | Her yeni ağır bağımlılık ayrı `requirements-<capability>.txt` + CI çözücü testi; güvenlik yamaları asla bir aracın pinine bağlı kalmaz |
| **Çözücü çatışması** | crawl4ai (psutil≥6.1.1) vs eski araçlar | İki adımlı kurulum deseni korunur; yeni paket önce izole kurulum testinden geçer |
| **Kırılgan özel API** | `131 instagrapi`, `122 GHunt` — platform bir gecede kırar | Asla birincil yol değil; ikinci kaynak + `available:false` + bozulma alarmı |
| **Bakımsız depo** | `7 instatracker` (son push 2024), `15 toutatis` (2024), `119 pwnedOrNot` (2026-03) | Yalnız **desen/veri** alınır, kod alınmaz (K8) |
| **Maliyet patlaması** | Ücretli arama/görsel API'leri | SearXNG varsayılan rota; `quota_governor` + günlük harcama tavanı; cache zorunlu |
| **Halüsinasyon sızıntısı** | Yeni yeteneklerin çıktısı rapora doğrudan yazılırsa | Kural 3: `EvidenceRecord` üretemeyen yetenek rapora yazamaz; `quote_guard` korpusu genişletilir |
| **Kanıt mührünü atlayan RAG** | Graf-RAG/bellek katmanı uydurma bağlam getirirse | Her getirilen parça kanıt kimliği taşır; kimliksiz parça bağlama girmez |
| **Ölü yapılandırma** | C8 denetiminde 4 ölü anahtar bulunmuştu | Env anahtarı = kodda okunmayan anahtar yasak; registry tek kaynak |

### 8.3 Ürün/hukuk riski
Rıza defteri (Faz 5) tamamlanmadan **hiçbir yeni kişi-verisi sensörü** varsayılan açık olamaz. `A†` sınıfı yetenekler yalnız operatörün kendi kimliğiyle çalışır. Platform ToS ihlali gerektiren her şey (imza kırma, gizli içerik, özel API zorlama) reddedilmiştir.

---

## 9. "EKSİK HİÇBİR ŞEY KALMASIN" — BOŞLUK KAPANMA MATRİSİ

Kendi denetiminizde (`EKSIK_YETENEKLER_2026-09-26.md`) "tam uygulama olarak doğrulanmadı" denilen 7 yetenek + bu röntgende bulunan 3 ek yara:

| Yara | Kapatacak yetenek (capability) | Dayanak depolar | Faz | **Kanıt (kabul testi)** |
|---|---|---|---|---|
| **Y1** Tersine görsel arama / catfish | `media.phash` + `media.reverse_search` + `media.metadata` + güçlendirilmiş `AuthenticityAuditor` | `314 opencv`, `28 searxng`, `269 PaddleOCR`, `295 OfficeCLI` | 3 | Aynı görselin ikinci hesapta kullanımı fixture ile yakalanır; tersine arama kapalıyken `UNAVAILABLE`, **asla "orijinal" iddiası yok** |
| **Y2** Yaş/rıza kapısı | `safety.consent` + `safety.age_gate` + denetim izi | (kendi kodumuz — K6 gereği) | 5 | Rıza kaydı yok → analiz başlamaz; reşit olmayan şüphesi → `halted_consent` + gerekçe |
| **Y3** Hedef tekrarı / ısrar takibi | `safety.repeat_target` + `memory.timeline` | `7 instatracker` (desen) | 4 | Aynı hedefe N. sorguda operatöre ısrar uyarısı; uyarı telemetriye yazılır |
| **Y4** Sosyal graf / ilişki ağı | `graph.local` (+ opsiyonel Neo4j) + yorum/metion adaptörleri | `124 Osintgraph` (şema), `48 LightRAG`, `273 cognee`, `313`, `177` | 4 | Graf düğümleri kanıt kimliği taşır; veri yoksa sekme "kanıt yok" der |
| **Y5** Video/ses içeriği analizi | `media.acquire → frames → ocr → asr` + `platform_registry` video_url düzeltmesi | `96 yt-dlp`, `94 gallery-dl`, `314 opencv`, `269 PaddleOCR`, `42 surya` | 3 | Video gönderiden kare + OCR + transkript kanıtı; ASR yoksa uydurma transkript üretilmez |
| **Y6** Skor kalibrasyonu / geri besleme | `calibration.engine` + geri bildirim döngüsü + eşik yönetişimi | `40 scikit-learn`, `253 duh` (desen) | 1 + 6 | Kalibrasyon eğrisi + güven aralığı; kalibrasyon verisiz eşik değişikliği CI'da reddedilir |
| **Y7** Dil tespiti / çeviri | `extractor.lang.detect` + `extractor.translate` (orijinali koruyan) | `82 HanLP`, `83 PaddleNLP`, `42 surya` (CJK) | 1 | TR/EN/DE/AR/CJK doğru işlenir; `quote_guard` çeviri sonrası yanlış pozitif üretmez |
| **Y8** X/Twitter sensörü yok | `sensor.x.twscrape` + `sensor.reddit/youtube.agent_reach` + `sensor.tiktok.*` | `70 twscrape`, `315 Agent-Reach`, `68` | 2 | X URL'si sensör açıkken `awaiting_authorization`'a düşmez; kapalıyken sahte profil üretilmez |
| **Y9** Geçmiş/tarihçe deposu | `memory.store` (DuckDB) + `memory.timeline` | `25 pocketbase`(opsiyonel), `7` (desen) | 1 + 4 | Bozuk dosyadan kurtarma; iki tarama arası fark raporu |
| **Y10** Yetenek yönetimi dağınık | `CapabilityRegistry` + `PolicyKernel` + Yetenek Durumu paneli | `318/322/136` (Skills standardı) | 0 | "Yetenek var mı?" sorusunun tek cevabı registry (grep ile kanıt) |

**Hiçbir yara, tek bir depo eklenerek kapanmaz.** Her satır "spine + 1-2 adaptör + test" üçlüsüdür. Bu yüzden Faz 0 bir lüks değil, **ön koşuldur**.

---

## 10. ONAY BEKLEYEN ÜÇ KARAR (ürün sahibi = sensin)

Karar ağacı teknik hükmü verdi; aşağıdaki üçü **ürün/politika** kararıdır ve kod yazılmadan önce netleşmeli:

1. **Rıza/yaş kapısı (Faz 5) zorunlu mu, uyarı mı?** Önerim: **zorunlu** — rıza kaydı olmayan hedefte analiz başlamasın. Bu, ürünü yavaşlatır ama "benzersiz ve yetkili" iddianın tek savunulabilir yoludur.
2. **Hangi sensörler operatör hesabı gerektiriyor?** X (`70 twscrape`) ve oturum tabanlı erişim (`18/214/179`) için operatörün **kendi** hesabını bağlaması gerekir. Kendi hesabınla mı, hesapsız açık kaynak yollarla mı (daha zayıf sinyal)?
3. **Yerel jüri (Faz 8) için donanım var mı?** Varsa Faz 8'i öne çekeriz (maliyet 0 + mahremiyet), yoksa Faz 8 sona kalır.

---

## 11. DEĞİŞMEZLER (bu belge sonrası da geçerli)

1. LLM'ler falcı değildir — yeni yeteneklerin hiçbiri karakter analizini LLM'e yaptırmaz.
2. Kanıt mührü fail-closed — kanıtsız iddia yok, `InsufficientEvidenceError` kalkmıyor.
3. %100 şeffaf telemetri — UI'a giden her değer gerçek; sahte LED/simülasyon yok.
4. Kasa mandalı — vault kilitliyken dış ağa tek istek çıkmaz (yeni sensörler de buna tabi).
5. Otomatik mesaj gönderimi yok — sistem taslak üretir, göndermez.
6. İkinci platform/orchestration katmanı yok (kural [009]) — her şey `platform_registry` + `CapabilityRegistry`'ye bağlanır.
7. Güvenlik yamaları hiçbir aracın sürüm pinine rehin değildir.

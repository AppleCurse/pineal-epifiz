# Gerçek Tarayıcı Smoke Raporu — 11 Kasım 2026

Bu rapor, önceki oturumun **"Frontend'in gerçek browser'da graph JSON'unu
render etmesi: kanıtlanmadı"** maddesini kapatır. Ölçüm hayali değil: gerçek
Chromium (playwright-core), gerçek Vite dev sunucusu (port 1420) ve gerçek
FastAPI backend (port 8000) üzerinden yapıldı.

## Ortam

| Bileşen | Sürüm / durum |
| --- | --- |
| Node | v22.22.3 |
| Vite | 6.4.3 (`0.0.0.0:1420`, `strictPort`) |
| Backend | uvicorn + FastAPI, `PINEAL_ENV=development`, `PINEAL_REQUIRE_AUTH=false` |
| Sağlık ucu | `/health` → `status: ready`, 12 zorunlu bağımlılık `ready` |
| Tarayıcı | Chromium (headless) |

> Not: Bu konteynerde Chromium'un `libnspr4`/`libnss3` bağımlılıkları ve
> Playwright CDN'i kapalıydı; tarayıcı npm üzerinden temin edilip sistem
> kütüphaneleriyle eşleştirildi. Aynı adımlar `frontend/scripts/README.md`
> içinde tekrarlanabilir hâlde.

## Sonuç: 15/15 adım geçti, 0 sayfa hatası

```
STEP goto                                   ok  200
STEP shell_mounted                          ok  PINEAL-HERETIC v2.0
STEP observatory_rendered                   ok  1934 karakter
STEP surface_tabs                           ok  5 sekme
STEP command_surface                        ok  12 ajan çipi
STEP keyboard_stations                      ok  2 rol=button, tabindex=0
STEP keyboard_enter_works                   ok  aria-pressed=true
STEP chip_click_selected                    ok  aria-pressed=true
STEP evidence_surface                       ok  2079 karakter
STEP live_panel_does_not_cover_tabs         ok  (regresyon kapandı)
STEP live_surface                           ok  1876 karakter
STEP warroom_surface                        ok  1892 karakter
STEP browser_health_via_proxy               ok  200
STEP browser_graph_via_proxy                ok  available=true, 5 düğüm, 4 bağ
STEP browser_websocket                      ok  açıldı
```

Tek "başarısız istek" `fonts.googleapis.com` (kapalı ağ) — ürün hatası değil.

## Tarayıcıdan ölçülen gerçek görev zinciri

Görev `op_20261111091711_6d31bcd4`, tarayıcı origin'inden
`/api/tasks/{id}/graph` (Vite proxy → FastAPI):

```json
{ "available": true, "node_count": 5, "edge_count": 4,
  "nodes": ["evidence_timeline", "life_rupture", "pillar_evidence_adapter",
            "pineal_7pillar", "target"] }
```

Yani backend'de üretilen gerçek kanıt grafı **tarayıcıya kadar** ulaşıyor.
Bu, önceki oturumda yalnız curl ile kanıtlanmış olan zincirin tarayıcı
ayağını da kapatır.

## Smoke'un bulduğu ve bu commit'te kapatılan üç gerçek hata

### 1. CANLI SİSTEM paneli tüm görünümü kaplıyordu

`LiveControlPanel` `position: fixed; inset: 0` ile render ediliyordu ve
`UnifiedPinealCockpit` içine monte edildiği için üst başlığı **ve yüzey sekme
çubuğunu** örtüyordu. Operatör "CANLI SİSTEM"e girdikten sonra başka hiçbir
sekmeye geçemiyordu (kenar çubuğu yok, sekme çubuğu tıklanamaz).

Kanıt: `04-live.png` — sekmeler ve başlık görünür, panel normal akışta.

### 2. Telemetri paneli geliştirmede her zaman "offline"

SPA `apiFetch('/health')` çağırıyor; Vite proxy'sinde yalnız `/api` ve `/ws`
vardı, dolayısıyla istek Vite'a düşüp **404** alıyordu. `/health` proxy'ye
eklendi; tarayıcıdan ölçüm artık **200**.

### 3. ATLAS yüzeyinden başlatılan görevde kanıt grafı boş kalıyordu

`SpiderFootCockpit` görev kimliğini yalnız kendi "GÖREVİ BAŞLAT" düğmesinden
alıyordu. Operatör varsayılan ATLAS yüzeyinden görev başlattığında
`/api/tasks/{id}/graph` **hiç çağrılmıyordu** — backend'de 5 düğüm hazır
olmasına rağmen ekran boştu. WS anlık görüntüsündeki görev kimliği de kimlik
kaynağı yapıldı; görev değişince bayat graf temizleniyor.

Regresyon testi: `spiderfoot-cockpit.contract.test.ts` →
"görev kimliği WS anlık görüntüsünden gelirse grafı kendiliğinden çeker".
Test, düzeltme geçici olarak kaldırıldığında **başarısız**, geri konduğunda
**geçiyor** (ölçtüğü davranışı gerçekten ölçtüğü doğrulandı).

## Ek düzeltmeler

- `svelte-check`: **10 uyarı → 0 uyarı, 0 hata**. Tıklanabilir `div`'lere
  `role="button"`, `tabindex="0"`, `aria-pressed`, `keydown` (Enter/Space) ve
  `focus-visible` çerçevesi; kullanılmayan `telemetryData` prop'u ve ölü
  `.shell-grid` / `.ocular-mark` CSS'i kaldırıldı.
- `.surface-tabs` ızgarası 4 → 5 sütun (beş yüzey var, beşincisi taşıyordu).
- `UnifiedPinealCockpit` içinde çift kodlanmış Türkçe metinler onarıldı:
  "TEK GÃ–REV MERKEZÄ°" → "TEK GÖREV MERKEZİ", "CANLI SÄ°STEM" → "CANLI SİSTEM".

## Hâlâ açık (bu raporun kapatmadığı)

1. ~~**ATLAS OBSERVATORY varsayılan yüzeyi sabit değerler gösteriyor.**~~
   **KAPATILDI** — aşağıdaki "İkinci tur" bölümüne bakın.
2. Varsayılan yüzeyden gerçek görev başlatma akışı kasa kilidi (423) ile
   duruyor — bu **doğru** davranış (fail-closed), ancak operatörün gerçek bir
   tarama başlatıp grafı kendi gözüyle görmesi için kasa anahtarı gerekiyor.
   Smoke bu nedenle grafı API üzerinden ve sözleşme testiyle doğruladı.
3. STT multipart endpoint'i gerçek motorla test edilmedi.
4. Cloudflare edge → backend WebSocket auth senaryosu test edilmedi
   (yalnız yerel proxy WS ölçüldü).
5. LinkedIn extension'daki sabit/mock sonuçlar duruyor.
6. Email dossier zinciri gerçek task/evidence/report factory'ye bağlanmadı.
7. Rust `cargo check/test` MSVC `link.exe` eksikliği nedeniyle hâlâ
   başarılı kabul edilmiyor.

## Dosyalar

- `01-observatory.png` — varsayılan ATLAS yüzeyi (sabit değerler görünür)
- `02-command.png` — KOMUTA: 12 ajan çipi, klavye erişimi
- `03-evidence.png` — KANIT RADARI
- `04-live.png` — CANLI SİSTEM (düzeltme sonrası, sekmeler görünür)
- `05-warroom.png` — MUHAREBE MASASI
- Araç: `frontend/scripts/browser-smoke.mjs`

---

# İkinci tur — ATLAS OBSERVATORY dürüstlüğü (aynı gün)

Varsayılan açılış yüzeyi, "VERİ YOKSA UYDURMAZ" rozeti taşırken tamamen sabit
rakamlarla doluydu. Hepsi gerçek uçlara bağlandı.

## Bulunan dördüncü gerçek hata (P0): ana düğme hiç çalışmıyordu

`AtlasObservatory.triggerDeepScan()` **`POST /api/tasks`** çağırıyordu. Böyle bir
uç backend'de YOK:

```
POST /api/tasks  →  405 Method Not Allowed
```

Yani varsayılan ekrandaki "⚡ GÖREVİ BAŞLAT (DERİN TARAMA)" düğmesi hiçbir
koşulda görev başlatamıyordu; hata `alert("Görev başlatma uyarısı: HTTP 405")`
ile geçiştiriliyordu. Doğru uç `/api/initiate` (diğer üç yüzey bunu kullanıyor).

Tarayıcıda ölçüm (`08` öncesi/sonrası):

| | Önce | Sonra |
| --- | --- | --- |
| Gönderilen istek | `POST /api/tasks` (405) | `POST /api/initiate` |
| Kullanıcının gördüğü | "HTTP 405" | Sunucunun gerçek mesajı (örn. `VAULT KİLİTLİ: …`) |

## Sabitten gerçeğe dönüşen kartlar

| Kart | Önce (sabit) | Sonra (gerçek kaynak) |
| --- | --- | --- |
| KAYNAK ALANI | 127 Aktif / 14 Arşiv / 03 Çelişkili / 07 Karartılmış | `GET /api/tasks` + `/graph`: **12 Kanıt / 3 Görev / 5 Düğüm / 4 Bağ** |
| Sensör ledleri | hepsi sabit yeşil/kırmızı | `GET /api/telemetry` → `scraper`, `x_scraper`, `search_engine`, `core`, `browser_installed` (yok = gri "ölçülmedi") |
| ZAMAN ÇİZELGESİ | "1987 ➔ 2026", 14 olay / 03 anomali | gerçek görev + kanıt sayısı; kayıt yoksa "Zaman serisi yok" |
| GLOBAL İZ | TR 184 / EU 97 / US 66 … ve **448.721 / 97.346 / 61.208** | CORE/GATEWAY/SCRAPER/KASA/AJAN durumu, görev, kanıt, **graf (5 düğüm / 4 bağ)**, LLM harcaması + tavan + fiyatlanmamış çağrı |
| AJAN YUVASI | "AKTİF AJANLAR (14/14)", 14 sabit yeşil led | gerçek `agent_statuses` → "AJAN YUVASI (0/12)", Active=yeşil, Ready=amber, diğer=gri |
| SOSYAL MEDYA İZİ | 1.2M / 842K / 421K / 318K / 275K / 193K | sensör var/yok: X **YOK**, Instagram **YOK**, IG Oturumu **KAPALI**, + `x_scraper_reason` |
| İZ ALANI & RADAR | 842 Sinyal / 61 Korelasyon / 07 / 02 | 5 Düğüm / 4 Bağ / 12 Kanıt / 3 Görev |
| RİSK ANALİZİ | %42 / %37 / %21 + 4 sabit kırmızı tehdit | görev sayısı, ortalama güven (veri yoksa `—`), bellek durumu + KASA/GÖREV UCU/TELEMETRİ gerçek durumu |
| SON RAPOR | "CASE #AT-2025-0918 TAMAMLANDI / 37 Doğrulanmış Kayıt" | gerçek `op_…` kimliği, kanıt sayısı, son güncelleme, bellek durumu — **en yeni görev** |

Ek düzeltme: `GET /api/tasks` listeyi eskiden yeniye döndürüyor; sıralama
olmadan "SON GÖREV" kartı **en eski** görevi gösteriyordu. Artık
`last_updated`'a göre azalan sıralanıyor (tarayıcıda 09:05 → 09:17 doğrulandı).

Veri yokken davranış: rakam uydurulmaz, `—` veya "… yok" basılır; `telemetry` /
`tasks` ucu hata verirse hangi ucun düştüğü kırmızı led + hata metniyle yazılır.

## Regresyon testleri

`frontend/src/__tests__/atlas-observatory-honesty.test.ts` (5 test) bileşeni
gerçekten monte eder, gerçek düğmeye basar:

1. uydurma değerlerin HİÇBİRİ ekranda yok (448.721, 1.2M, AT-2025-0918, %42 …)
2. gerçek telemetri/görev verisi ekrana basılıyor (5 düğüm / 4 bağ, 9 kanıt, $1.2500, 1/2 ajan)
3. SON GÖREV en yeni görevi gösteriyor
4. görev başlatma `/api/initiate` çağırıyor, `POST /api/tasks` **çağırmıyor**
5. 423 kasa kilidi yanıtı AYNEN gösteriliyor, sahte başarı üretilmiyor

Doğrulama: 4 ve 5 numaralı testler, 405 hatası geri konduğunda **başarısız**
oluyor — testin ölçtüğü davranışı gerçekten ölçtüğü kanıtlandı.

Test altyapısı: `src/test-setup.ts` jsdom canvas stub'ına `createRadialGradient`
eklendi (göz çizimi nedeniyle bileşen monte edilemiyordu).

## Durum

| Kontrol | Sonuç |
| --- | --- |
| `svelte-check` | 0 hata, 0 uyarı |
| `vitest` | **39/39** (önce 34) |
| `vite build` | başarılı |
| Tarayıcı smoke | 15/15 adım |
| Varsayılan yüzeyde uydurma sabit | **0** |
| Görev başlatma ucu | `/api/initiate` (405 kapandı) |

Kanıt: `00-observatory-before.png` (sabit değerler) ↔
`06-observatory-real-data.png` (gerçek veri).

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

1. **ATLAS OBSERVATORY varsayılan yüzeyi sabit değerler gösteriyor.**
   Ekran görüntüsünde `TOPLAM VERİ: 448.721`, `İŞLENEN: 97.346`,
   `DOĞRULANAN: 61.208`, `1.2M / 842K / 421K` sosyal erişim, `%42/%37/%21`
   risk dağılımı ve `CASE #AT-2025-0918 — TAMAMLANDI` **kaynakta sabit
   yazılı**. Ürün "VERİ YOKSA UYDURMAZ" rozeti taşırken açılış ekranı
   uydurma rakam gösteriyor; gerçek görev/kanıt verisine bağlanmalı ya da
   "örnek/demo" olarak açıkça işaretlenmeli. **P0 dürüstlük maddesi.**
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

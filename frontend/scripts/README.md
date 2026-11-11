# Tarayıcı smoke testi

`browser-smoke.mjs` Vite dev sunucusunu **gerçek Chromium** ile açar, beş yüzeyi
gezer ve ağ katmanını tarayıcı origin'inden ölçer. `npm run check` ve jsdom
testlerinin göremediği şeyleri yakalar (2026-11-11'de üç gerçek hata buldu:
sekme çubuğunu örten `position: fixed` panel, proxy'de olmayan `/health`,
ATLAS yüzeyinden başlatılan görevde boş kalan kanıt grafı).

## Ön koşullar

```bash
# 1) Backend (geliştirme izolasyonu)
PINEAL_ENV=development PINEAL_REQUIRE_AUTH=false \
  uvicorn backend.api:app --host 0.0.0.0 --port 8000

# 2) Frontend
cd frontend && npm run dev
```

## Çalıştırma

```bash
cd frontend/scripts
npm install            # playwright-core + @sparticuz/chromium (kendi Chromium'u)
node browser-smoke.mjs
```

Ortam değişkenleri:

| Değişken | Anlamı |
| --- | --- |
| `BASE` | Arayüz adresi (varsayılan `http://127.0.0.1:1420`) |
| `TASK_ID` | Gerçek graf ölçümü için görev kimliği (`op_...`) |
| `CHROME_PATH` | Sistemde kurulu bir Chromium/Chrome ikilisi |
| `OUT_DIR` | Ekran görüntüsü + rapor dizini (varsayılan `./.smoke`) |

Çıkış kodu `0` ise tüm adımlar geçti; `1` ise `.smoke/report.json` içindeki
`steps` listesinde `ok: false` olan adıma bakın.

> Not: Bazı minimal konteynerlerde Chromium `libnspr4`/`libnss3` bekler. Bu
> paketler yoksa `LD_LIBRARY_PATH` ile temin edin; aksi halde `CHROME_PATH`
> olarak bağımlılıkları tamam bir tarayıcı verin.

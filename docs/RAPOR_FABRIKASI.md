# RAPOR FABRİKASI — kanıt bağlantılı, mühürlü rapor paketi

> FAZ D · D5 · 2026-10-07
> Bulguları teslim edilebilir hâle getirir: PDF · diyagram · video özet + her
> paketin yanında kanıt listesini ve hash'leri taşıyan **manifest**.

## 1 · Kural: rapor UYDURULMAZ

Paket yalnız **kanonik kanıt zaman çizelgesinden** beslenir
(`services/evidence_timeline.py`): sıra, epistemik tür ve "not independently
verified" gibi epistemik notlar oradan aynen taşınır.

- `strategy` türü çizelgeye girmez (çağrı dışı sayılır, manifest'te sayılır).
- Bozuk/eksik satırlar **reddedilir** ve `rejected_item_count` olarak rapora
  yazılır — sessizce yutulmaz.
- Rapor "özet/çıkarım" satırı üretmez; yalnız kanıtı düzenler.

## 2 · Çıktılar

| Format | Üreten | Yoksa |
|---|---|---|
| `markdown` | dahili (bağımlılık yok) | her koşulda üretilir |
| `pdf` | reportlab (`requirements.lock` 4.5.1) | `dependency_missing:reportlab` |
| `diagram` | Pillow ile deterministik PNG (tür = renk) | `dependency_missing:Pillow` |
| `video` | Pillow kareleri → `ffmpeg` kodlama | `dependency_missing:ffmpeg` |

**Eksik format dürüsttür**: üretilemeyen format `available=False` + sebep alır;
yerine uydurma dosya konmaz. Markdown + manifest yine yazılır, paket teslim
edilir.

## 3 · Mühür (hash + kanıt bağlantısı)

Her eserin `sha256`'sı hesaplanır; `<ad>.manifest.json` şunları taşır:

- `evidence_ids`: pakete giren kanıt kimlikleri (kanıt bağlantısı),
- `artifacts`: eser adı + dosya adı + `sha256` + bayt,
- epistemik sayımlar, reddedilen/çizelge dışı sayıları,
- `manifest_sha256`: gövdenin kendi hash'i.

Doğrulama: `manifest_sha256` alanını çıkar, kalan gövdeyi
`json.dumps(..., sort_keys=True, separators=(",", ":"))` ile serileştir,
sha256'sını hesapla — eşit çıkmalı. (Aynı kontrol testlerde kilitlidir.)

**Bu bir bütünlük mührüdür, kriptografik imza DEĞİLDİR** — anahtar yoktur ve
manifest bunu açıkça yazar.

## 4 · Kullanım

```bash
export ENABLE_REPORT_FACTORY=1
export PINEAL_REPORT_DIR=memory/reports      # varsayılan
python -m uvicorn backend.api:app --port 8000

curl -s -X POST http://127.0.0.1:8000/api/report/build \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"op","title":"Örnek Rapor","subject":"ornek.com",
       "formats":["pdf","diagram"],
       "evidence":[{"evidence_id":"ev_0123456789abcdef0123",
                    "epistemic_type":"observation","source_engine":"twscrape",
                    "content":"Gönderi: ...","provenance_refs":["https://x.com/u/1"]}]}'
```

| Uç | Ne verir |
|---|---|
| `GET /api/report/status` | Hangi format GERÇEKTEN üretilebilir (sebepleriyle), rapor dizini, mühür şeması |
| `POST /api/report/build` | Paket üretir; format başına eser listesi + `manifest_path` + `manifest_sha256` |

Kapılar: `vault` (istisnasız) + `ENABLE_REPORT_FACTORY` (varsayılan **KAPALI**).
HTTP hız kovası: `report` (10 istek/60 sn).

## 5 · Sınama

```bash
pytest tests/unit/test_report_factory.py tests/integration/test_report_capabilities.py -q
```

Testler gerçek PDF/PNG üretir, mühür matematiğini yeniden hesaplar, ffmpeg
yokluğunu (ve POSIX'te sahte ffmpeg ile varlığını) ölçer; hiçbir test dış ağa
çıkmaz, üretilen dosyalar `tmp_path`te kalır.

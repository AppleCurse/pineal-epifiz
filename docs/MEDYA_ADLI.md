# MEDYA ADLİ HATTI — indir · kare kare ölç · yazıya dök · eşleştir

> FAZ D · D3 · 2026-10-07
> Paylaşılan bir video ya da fotoğraf artık ölçülebilir hâle gelir: künye, kare
> kare parlaklık, sahne kesmeleri, transkript ve algısal benzerlik.

## 1 · Dört mod

| Mod | Yetenek | Ne üretir | Araç |
|---|---|---|---|
| `fetch` | `sensor.media.fetch` | dosya + `sha256` mührü; platform linkleri yt-dlp, doğrudan bağlantılar httpx | yt-dlp / httpx |
| `frames` | `analyzer.media.frames` | fps · kare sayısı · süre · çözünürlük · parlaklık (±std) · sahne kesmeleri; fotoğrafta baskın renk + Laplacian keskinliği | OpenCV |
| `transcript` | `extractor.media.transcript` | ses → metin (+ kendi dil tespitimizle dil/güven) | yerel whisper CLI **ya da** yerel uç |
| `similarity` | `analyzer.media.similarity` | pHash (DCT) parmak izi + Hamming mesafesiyle yerel indekste en yakın görseller | OpenCV + dahili pHash |

**Yorum yok, ölçüm var.** Bu katman "videoda ne oluyor?" sorusunu YANITLAMAZ;
ölçüleni yazar. İçerik yorumu jüri (D2) ve rapor (D5) katmanlarının işidir.

## 2 · Yerellik kuralı (transkript)

Ses **ve** metin makineden çıkmaz. Motor sırası:

1. `PINEAL_TRANSCRIBE_URL` — yalnız `127.0.0.1`/`localhost`/`[::1]`; uzak adres
   **sert reddedilir** (`non_local_endpoint`) ve CLI'ye sessizce DÜŞÜLMEZ.
2. `PINEAL_TRANSCRIBE_CMD` — yerel CLI (varsayılan `whisper`).

Video girdide ek olarak `ffmpeg` gerekir (ses kanalını ayırmak için). Yoksa
`dependency_missing:ffmpeg` — uydurma transkript üretilmez.

## 3 · Dürüstlük sözleşmesi

- Platform linki + yt-dlp yok → `dependency_missing:yt-dlp` (indirme uydurulmaz).
- İndirme **özel/yerel adreslere yapılmaz** (`private_address_rejected`);
  istisna yalnız `PINEAL_MEDIA_ALLOW_PRIVATE=1` ile ve bilinçlidir.
- Boyut tavanı `MAX_DOWNLOAD_BYTES` (80 MB) — aşarsa dosya silinir, `too_large`.
- Motor boş çıktı verirse transkript İDDİA EDİLMEZ (`empty_transcript`);
  motor hatası `engine_failed:rcN` olarak ayrılır.
- pHash DC terimini dışarıda bırakır: düz renkli iki fotoğraf "aynı" sayılmaz.
- Kanıt satırı her zaman dosya yoluna/kaynağa bağlanır (`provenance_refs`).

## 4 · Kullanım

```bash
export ENABLE_MEDIA_FORENSICS=1
export PINEAL_MEDIA_DIR=memory/media            # varsayılan
export PINEAL_TRANSCRIBE_CMD="whisper"          # ya da PINEAL_TRANSCRIBE_URL=http://127.0.0.1:9000/stt
python -m uvicorn backend.api:app --port 8000

curl -s -X POST http://127.0.0.1:8000/api/media/analyze \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"op","source":"https://example.com/paylasilan.mp4",
       "modes":["fetch","frames","transcript","similarity"]}'
```

| Uç | Ne verir |
|---|---|
| `GET /api/media/status` | Araç durumu (yt-dlp/ffmpeg/opencv/transkript motoru) + mod başına dürüst `reason` |
| `POST /api/media/analyze` | Mod başına kanıt + notlar (künye, sahne listesi, eşleşmeler) |

Kapılar: `vault` (istisnasız) + `ENABLE_MEDIA_FORENSICS` (varsayılan **KAPALI**);
`fetch` ayrıca `rate`. HTTP hız kovası: `media` (6 istek/60 sn).

## 5 · Sınama

```bash
pytest tests/unit/test_media_forensics.py tests/integration/test_media_api_faz_d.py -q
```

Testler gerçek video/fotoğraf üretir (OpenCV ile siyah→beyaz geçiş → sahne
kesmesi), gerçek pHash hesaplar, sahte whisper CLI ile POSIX'te transkript
üretir; hiçbir test dış ağa çıkmaz.

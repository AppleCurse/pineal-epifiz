# REMEDIYASYON — 9 hâlâ kapalı yeteneği açmak için ne yapmak lazım

Bu dosya `scripts/golge_denetimi.py` tarafından üretilen raporun §7 "Uyanma planı" bölümünün tamamlayıcısıdır. Her kapalı yetenek için **gerçek neden**, **gereken kurulum** ve **doğrulama komutu** yer alır.

Mevcut durum: **18/27 yetenek açık, 9 yetenek kapalı.**

---

## 1 · extractor.media.transcript — `no_engine`

**Neden:** Medya dosyasından metin çıkarmak için yerel bir transkripsiyon motoru yok. Kod `PINEAL_TRANSCRIBE_CMD` (varsayılan `whisper`) CLI'sini arıyor; yoksa `no_engine` döner.

**Gerekenler:**
- `whisper` CLI'sini sistem PATH'ine koyun (`pip install openai-whisper` + ffmpeg gerektirir), veya
- `PINEAL_TRANSCRIBE_CMD` env değişkeni ile başka bir transkripsiyon CLI'sinin yolunu gösterin.

**Kurulum (Windows):**
```powershell
pip install openai-whisper
# ffmpeg de gerekli: https://ffmpeg.org/download.html → PATH'e ekle
```

**Doğrulama:**
```powershell
whisper --help
# veya: $env:PINEAL_TRANSCRIBE_CMD = "C:\yol\whisper.exe"
```

---

## 2 · extractor.text.translate_local — `no_engine`

**Neden:** Yerel çeviri motoru yok. Kod şu sırayla bakar:
1. `PINEAL_TRANSLATE_URL` — yerel HTTP çeviri ucu (http(s) zorunlu)
2. `PINEAL_TRANSLATE_CMD` (varsayılan `trans`) — yerel çeviri CLI'si

Hiçbiri bulunamadı → `no_engine`.

**Gerekenler:**
- `trans` CLI'sini kurun (`pip install translate-cli` veya sistem paketi), veya
- `PINEAL_TRANSLATE_URL=http://127.0.0.1:8080/translate` şeklinde yerel bir uç tanımlayın.

**Kurulum (Windows):**
```powershell
pip install translate-cli
# veya kendi çeviri ucanızı çalıştırıp PINEAL_TRANSLATE_URL'i ayarlayın
```

**Doğrulama:**
```powershell
trans --help
# veya: $env:PINEAL_TRANSLATE_URL = "http://127.0.0.1:8080"
```

---

## 3 · renderer.report.video — `dependency_missing:ffmpeg`

**Neden:** Rapor videosu (mp4) üretmek için ffmpeg sistem binary'si gerekiyor. Pillow zaten kurulu, ffmpeg yok.

**Gerekenler:**
- ffmpeg'i sistem PATH'ine kurun.

**Kurulum (Windows):**
```powershell
# https://ffmpeg.org/download.html'den Windows binary'sini indirin
# Bin klasörünü PATH'e ekleyin
# veya: winget install ffmpeg
winget install ffmpeg
```

**Doğrulama:**
```powershell
ffmpeg -version
```

---

## 4 · sensor.company.harvester — `dependency_missing:theHarvester`

**Neden:** Kurum keşfi (e-posta, alt alan adı, IP, URL) için theHarvester CLI gerekiyor. Kod PATH'te `theHarvester` veya `theharvester` arar.

**DURUM:** PyPI'deki `theHarvester` paketi boş (sadece metadata). GitHub versiyonu Python 3.14+ gerektirir (bizim Python 3.11.2'de çalışmıyor) ve Python 2 sözdizimi hataları içerir.

**Gerekenler:**
- theHarvester'ı Docker ile çalıştırın, veya
- WSL2 / Python 3.14+ ortamında kurup PATH'e ekleyin, veya
- `PINEAL_HARVESTER_CMD` env değişkeni ile kendi theHarvester binary'nizin yolunu gösterin.

**Kurulum (Docker):**
```bash
docker run --rm laramies/theharvester -d example.com -b google
```

**Kurulum (Windows + PINEAL_HARVESTER_CMD):**
```powershell
$env:PINEAL_HARVESTER_CMD = "C:\tools\theHarvester\theHarvester.py"
```

**Doğrulama:**
```powershell
theHarvester --help
```

---

## 5 · sensor.ig.instagrapi — `credentials_missing:IG_USERNAME/IG_PASSWORD`

**Neden:** Instagram ikincil kaynağı için işletimci hesabı gerekiyor. Kod `IG_USERNAME` ve `IG_PASSWORD` env değişkenlerini ister.

**Önemli:** Bu bir **ikincil/çapraz teyit** kaynağıdır. Birincil yol Playwright tabanlıdır. İstagram'a giriş için kendi hesabınızı kullanın.

**Gerekenler:**
- `.env` dosyasına `IG_USERNAME` ve `IG_PASSWORD` ekleyin.

**Kurulum (Windows .env):**
```
IG_USERNAME=kullaniciadiniz
IG_PASSWORD=sifreniz
```

**Doğrulama:**
```powershell
# Denetimi yeniden çalıştırın: credentials_missing kalkmalı
python scripts/golge_denetimi.py
```

---

## 6 · sensor.search.searxng — `config_missing:SEARXNG_BASE_URL`

**Neden:** SearXNG ayrı bir servistir (AGPL-3.0), kod gömülmez, yalnız HTTP ile konuşulur. `SEARXNG_BASE_URL` env değişkeni gerekli.

**Gerekenler:**
- SearXNG'i Docker ile ayağa kaldırın, veya
- Mevcut bir SearXNG örneğinin URL'sini `SEARXNG_BASE_URL` olarak tanımlayın.

**Kurulum (Docker):**
```bash
docker run -d -p 8080:8080 --name searxng searxng/searxng
```
Sonra `.env`':
```
SEARXNG_BASE_URL=http://127.0.0.1:8080
```

**Doğrulama:**
```powershell
curl http://127.0.0.1:8080
# 200 dönmeli
```

---

## 7 · sensor.web.agent_reach — `dependency_missing:agent-reach`

**Nenden:** Twitter/Reddit/YouTube/GitHub/Bilibili okuma için `agent-reach` CLI gerekiyor.

**UYARI:** `npm i -g agent-reach` komutu şu anda **farklı bir projeyi** kuruyor (Nostr ajan ağı, agent-reach@0.3.4). Kör kurulum yanlış aracı "hazır" sayabilir.

**Gerekenler:**
- Gerçek agent-reach CLI'ın yolunu `PINEAL_AGENT_REACH_CMD` ile açıkça gösterin, veya
- Kaynağı sabitlenmiş tarball/commit ile kurun.

**Kurulum:**
```powershell
$env:PINEAL_AGENT_REACH_CMD = "C:\tools\agent-reach\agent-reach"
```

**Doğrulama:**
```powershell
agent-reach --help
```

---

## 8 · voice.stt.local — `no_local_endpoint`

**Nenden:** Yerel konuşma tanıma için `whisper` CLI veya yerel bir STT ucu gerekiyor.

**Gerekenler (sırayla):**
1. `PINEAL_STT_URL` — yerel HTTP STT ucu (yalnız 127.0.0.1), veya
2. `PINEAL_STT_CMD` (varsayılan `whisper`) — yerel whisper CLI'si.

**Kurulum (Windows):**
```powershell
pip install openai-whisper
# ffmpeg gerekli
```

**Doğrulama:**
```powershell
whisper --help
# veya: $env:PINEAL_STT_URL = "http://127.0.0.1:8001/stt"
```

---

## 9 · voice.tts.local — `no_local_endpoint`

**Nenden:** Yerel metin→ses için piper CLI veya yerel TTS ucu gerekiyor.

**Gerekenler (sırayla):**
1. `piper` CLI + `PINEAL_PIPER_MODEL` env değişkeni, veya
2. `PINEAL_TTS_URL` — yerel HTTP TTS ucu (yalnız 127.0.0.1).

**Kurulum (Windows):**
```powershell
# piper: https://github.com/rhasspy/piper/releases
# piper binary'sini PATH'e ekleyin, model dosyasını indirin
$env:PINEAL_PIPER_MODEL = "C:\models\piper\en_US-lessac-medium.onnx"
```

**Doğrulama:**
```powershell
piper --help
```

---

## TOPLAM KURULUM ÖZETI (Windows)

| # | Yeteneik | Komut / İşlem |
|---|----------|--------------|
| 1 | `extractor.media.transcript` | `pip install openai-whisper` + ffmpeg PATH |
| 2 | `extractor.text.translate_local` | `pip install translate-cli` |
| 3 | `renderer.report.video` | `winget install ffmpeg` |
| 4 | `sensor.company.harvester` | Docker theHarvester veya `PINEAL_HARVESTER_CMD` |
| 5 | `sensor.ig.instagrapi` | `.env`'ye `IG_USERNAME`/`IG_PASSWORD` |
| 6 | `sensor.search.searxng` | Docker searxng + `SEARXNG_BASE_URL` |
| 7 | `sensor.web.agent_reach` | `PINEAL_AGENT_REACH_CMD` (dikkat: npm paketi yanlış) |
| 8 | `voice.stt.local` | `pip install openai-whisper` |
| 9 | `voice.tts.local` | piper binary + model |

**Tüm kurulumları yaptıktan sonra:**
```powershell
python scripts/golge_denetimi.py
```
Raporunda "Kullanılabilir: 27/27" görmelisiniz.

---

## NOT: Bu rapor bu makinede ölçülüyor

`dependency_missing`, `no_engine`, `no_local_endpoint` gibi sebepler **makineye bağlıdır**. Senin Windows ortamında bazı paketler zaten kurulu olabilir (scrapling, trafilatura, instagrapi, reportlab, Pillow gibi). Kendi makinende denetimi çalıştırarak gerçek durumu görün:

```powershell
.\scripts\calistir_windows.ps1
# veya
scripts\calistir_windows.bat
```

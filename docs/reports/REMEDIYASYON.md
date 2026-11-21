# REMEDİYASYON — 10 engelin gerçek nedeni, kurulumu ve doğrulaması

Bu belge, `requirements-blocked.txt`'te listelenen 9 kapalı yeteneğin ve LLM
motorunun **neden** kapalı olduğunu, **nasıl** açılacağını ve **nasıl**
doğrulanacağını tek tek yazar. İlke: yetenekler uydurma veri üretmez —
araç yoksa `availability()` dürüstçe `dependency_missing:*` döner.

Pip ile kurulabilenler `requirements-blocked.txt`'tedir; aşağıdaki sistem
araçları (ffmpeg, translate-shell, piper, theHarvester, agent-reach,
SearXNG) **pip paketi değildir** — her biri kendi bölümünde anlatılır.

---

## 1 · `extractor.text.translate_local` — yerel çeviri

**Neden kapalı:** Çeviri motoru translate-shell'in `trans` komutunu çağırır
(`trans -b -no-ansi src:tgt`). `trans` PATH'te yoksa yetenek kapalıdır.
Not: PyPI'deki `translate` / `translate-cli` paketleri bu motorla ilgisizdir;
kurmak işe yaramaz.

**Kurulum:**

```bash
# Debian/Ubuntu
sudo apt install translate-shell
# macOS
brew install translate-shell
# veya kaynaktan: https://github.com/soimort/translate-shell
```

**Env (opsiyonel):** `PINEAL_TRANSLATE_CMD` (varsayılan `trans`); ya da
yerel bir uç için `PINEAL_TRANSLATE_URL` (yalnız localhost kabul edilir).

**Doğrulama:**

```bash
trans -b -no-ansi tr:en "merhaba"
```

## 2 · `extractor.media.transcript` — ses/video yazıya dökme

**Neden kapalı:** Whisper CLI (`whisper`) ve ffmpeg gerekir; ikisi de yoksa
`dependency_missing` döner.

**Kurulum:**

```bash
pip install -r requirements-blocked.txt   # openai-whisper
sudo apt install ffmpeg                    # sistem seviyesinde
```

**Env (opsiyonel):** `PINEAL_STT_CMD` (varsayılan `whisper`).

**Doğrulama:**

```bash
whisper --help && ffmpeg -version
```

## 3 · `voice.stt.local` — yerel konuşma tanıma

**Neden kapalı:** 2. maddeyle aynı araçlar (whisper CLI + ffmpeg).

**Kurulum / doğrulama:** Bölüm 2 ile aynıdır.

## 4 · `renderer.report.video` — video özet (mp4)

**Neden kapalı:** Kareler Pillow ile, kodlama ffmpeg ile yapılır; ffmpeg
yoksa yetenek çökmez, dürüstçe kapalı kalır.

**Kurulum:**

```bash
pip install -r requirements-blocked.txt   # ffmpeg-python
sudo apt install ffmpeg                    # sistem seviyesinde
```

**Doğrulama:**

```bash
ffmpeg -version
```

## 5 · `voice.tts.local` — yerel metin-ses

**Neden kapalı:** Piper Python paketi yoktur; piper bir **binary**'dir ve
ayrıca bir ses modeli gerekir. İkisi de yoksa kapalıdır.

**Kurulum:**

```bash
# https://github.com/rhasspy/piper/releases — binary'yi PATH'e koyun
# Model indirin (örn. tr_TR) ve yolunu gösterin:
export PINEAL_PIPER_MODEL=/yol/piper-voices/tr_TR-dfki-medium.onnx
```

**Doğrulama:**

```bash
piper --help && test -f "$PINEAL_PIPER_MODEL"
```

## 6 · `sensor.company.harvester` — theHarvester

**Neden kapalı:** theHarvester'ın PyPI paketi boştur; araç Docker veya
GitHub kaynağıyla kurulur.

**Kurulum:**

```bash
git clone https://github.com/laramies/theHarvester
# veya Docker imajı; komutu gösterin:
export PINEAL_HARVESTER_CMD=/yol/theHarvester
```

**Doğrulama:**

```bash
theHarvester --help
```

## 7 · `sensor.web.agent_reach` — sosyal/medya okuma

**Neden kapalı:** agent-reach harici bir CLI'dır; PyPI'deki `agent-reach`
paketi ve npm `agent-reach` **başka projelerdir**, kurulmamalıdır.

**Kurulum:** agent-reach CLI'ını kurun ve yolunu gösterin:

```bash
export PINEAL_AGENT_REACH_CMD=/yol/agent-reach
```

**Doğrulama:**

```bash
agent-reach --help
```

## 8 · `sensor.search.searxng` — anahtarsız metasearch

**Neden kapalı:** SearXNG ayrı bir servistir (AGPL-3.0 → gömülemez); URL
tanımlı değilse yetenek `config_missing:SEARXNG_BASE_URL` döner.

**Kurulum:**

```bash
docker run -d --name searxng -p 8080:8080 searxng/searxng
export SEARXNG_BASE_URL=http://127.0.0.1:8080
export ENABLE_SEARXNG=true
```

**Doğrulama:**

```bash
curl "$SEARXNG_BASE_URL/search?q=test&format=json"
```

## 9 · `sensor.ig.instagrapi` — Instagram sensörü

**Neden kapalı:** `instagrapi` kurulu değilse (veya oturum yoksa) kapalıdır.

**Kurulum:**

```bash
pip install -r requirements-retina.txt   # instagrapi>=2.0.0
```

**Doğrulama:**

```bash
python -c "import instagrapi; print(instagrapi.__version__)"
```

## 10 · LLM motoru — canlı uçtan uca

**Neden kapalı:** Canlı LLM çağrısı için sağlayıcı anahtarı gerekir; anahtar
yoksa motor çevrimdışı çalışır ve bunu açıkça söyler.

**Kurulum:** `.env`'e sağlayıcı anahtarını yazın (`.env.example`'a bakın).

**Doğrulama:** `LIVE_LLM_E2E` kapısıyla canlı uçtan uca koşum; anahtar
yoksa koşum atlanır, uydurma yanıt üretilmez.

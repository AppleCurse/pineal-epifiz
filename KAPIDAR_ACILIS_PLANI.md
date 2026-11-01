# KAPIDAR ACILIS PLANI — "Hiçbir şey kapalı kalmayacak"

**Hedef:** Repodaki 17 yönetilen `ENABLE_*` kapısının hepsini `true` yapıp, her yeteneği çalışır hale getirmek.  
**Kaynak:** `agent_core/capabilities/policy.py` (`MANAGED_GATE_FLAGS`), `.env.example`, tüm `adapters_*.py`, `requirements*.txt`.

Bu belge her kapıyı tek tek listeler: şu anki hali, açmak için ne gerekiyor, hangi dosya değişecek, test nasıl yapılır.

---

## 0 · Özet — 17 kapı, 26 yetenek

| Kapı | Şu anki | Açılınca ne olur | Asıl engel |
|---|---|---|---|
| `ENABLE_MAIGRET` | `false` | Kullanıcı adı → 3000+ site tarama | `maigret` paketi (zaten requirements.txt'de) |
| `ENABLE_CROSS_PLATFORM` | `false` | IG/FB/Threads/X/TikTok/GitHub/Reddit/Pinterest/YouTube/Telegram var-yok yoklaması | Native, sadece kasa |
| `ENABLE_HOLEHE` | `false` | E-posta → kayıtlı platform tarama | `holehe` paketi (zaten requirements.txt'de) |
| `ENABLE_CRAWL4AI` | `false` | Sayfa → LLM-dostu metin | `crawl4ai` (requirements-osint.txt) |
| `ENABLE_SCRAPLING` | `false` | Adaptif anti-bot kazıma | `scrapling` + `browserforge` (requirements-retina.txt) |
| `ENABLE_X_SENSOR` | `false` | X/Twitter gönderi akışı (twscrape) | `twscrape` + hesap havuzu + operatör hesabı |
| `ENABLE_IG_SECONDARY` | `false` | Instagram ikinci kaynak (instagrapi) | `instagrapi` + IG kimlik bilgisi |
| `ENABLE_AGENT_REACH` | `false` | Twitter/Reddit/YouTube/GitHub okuma (harici CLI) | `agent-reach` CLI + `PINEAL_AGENT_REACH_CMD` |
| `ENABLE_SEARXNG` | `false` | Anahtarsız metasearch | `SEARXNG_BASE_URL` + ayrı SearXNG servisi |
| `ENABLE_LOCAL_TRANSLATE` | `false` | Yerel çeviri | `trans` CLI veya `PINEAL_TRANSLATE_URL` (localhost) |
| `ENABLE_LOCAL_JURY` | `false` | Yerel 3'lü jüri kararı | Yerel model sunucusu (ollama/llama.cpp/vLLM) |
| `ENABLE_COMPANY_TARGETING` | `false` | Kurum hedefi: theHarvester/SEO/kişi | theHarvester (Python 3.14 uyumu) |
| `ENABLE_REPORT_FACTORY` | `false` | PDF/diyagram/video rapor | `reportlab` (zaten var), video için `ffmpeg` |
| `ENABLE_INTERPRETER` | `false` | Kod görevi ajanı | `open-interpreter` (requirements-interpreter.txt) |
| `ENABLE_MEDIA_FORENSICS` | `false` | Medya indir/kare/transkript/benzerlik | `yt-dlp` + OpenCV (zaten var) + whisper (transkript) |
| `ENABLE_LOCAL_TTS` | `false` | Yerel metin-çon ses | `piper` CLI veya `PINEAL_TTS_URL` (localhost) |
| `ENABLE_LOCAL_STT` | `false` | Yerel ses-çon metin | `whisper` CLI veya `PINEAL_STT_URL` (localhost) |

**Kapı-sıfır yetenekler (zaten açık veya sadece kasa ile):**
- `extractor.identity.socid` — `{vault}` + `socid-extractor` (zaten kurulu)
- `extractor.text.language` — `{vault}` native, bağımlılık yok
- `sensor.identity.handle_probe` — `{vault, ENABLE_CROSS_PLATFORM}` native
- `sensor.identity.phone_probe` — `{vault}` native

---

## 1 · Adım 1: Tüm `ENABLE_*` bayraklarını `true` yap

Dosya: `.env.example` (ve işletmekteyse `.env`)

Şu an hepsi `false`. Tümünü `true` yapın. `CONSENT_GATED_FLAGS` (X, IG, çapraz platform) da `true` olsun — oda onayı zaten görev bazlıdır, env varsayılanını `true` yapmak engel teşkil etmez.

**Değişecek satırlar (`.env.example`'daki `ENABLE_*` blokları):**

```diff
-ENABLE_MAIGRET=false
+ENABLE_MAIGRET=true
-ENABLE_HOLEHE=false
+ENABLE_HOLEHE=true
-ENABLE_CRAWL4AI=false
+ENABLE_CRAWL4AI=true
-ENABLE_SCRAPLING=false
+ENABLE_SCRAPLING=true
-ENABLE_X_SENSOR=false
+ENABLE_X_SENSOR=true
-ENABLE_IG_SECONDARY=false
+ENABLE_IG_SECONDARY=true
-ENABLE_AGENT_REACH=false
+ENABLE_AGENT_REACH=true
-ENABLE_SEARXNG=false
+ENABLE_SEARXNG=true
-ENABLE_LOCAL_TRANSLATE=false
+ENABLE_LOCAL_TRANSLATE=true
-ENABLE_LOCAL_JURY=false
+ENABLE_LOCAL_JURY=true
-ENABLE_COMPANY_TARGETING=false
+ENABLE_COMPANY_TARGETING=true
-ENABLE_REPORT_FACTORY=false
+ENABLE_REPORT_FACTORY=true
-ENABLE_INTERPRETER=false
+ENABLE_INTERPRETER=true
-ENABLE_MEDIA_FORENSICS=false
+ENABLE_MEDIA_FORENSICS=true
-ENABLE_LOCAL_TTS=false
+ENABLE_LOCAL_TTS=true
-ENABLE_LOCAL_STT=false
+ENABLE_LOCAL_STT=true
```

Not: `ENABLE_CROSS_PLATFORM` zaten `false` olarak listelenmiş ama `MANAGED_GATE_FLAGS`'ta var; de TRUE yapın.

---

## 2 · Adım 2: Eksik Python paketlerini kur

`requirements.txt` ve `requirements-lock` zaten şunları içerir (kurulu): `maigret`, `holehe`, `socid-extractor`, `opencv-python-headless`, `reportlab`, `crawl4ai` (lock'ta), `twscrape` (lock'ta), `instagrapi` (lock'ta), `playwright`, `invisible-playwright`.

**Kurulması gereken / eksik olanlar:**

| Paket | Nereye | Not |
|---|---|---|
| `scrapling>=0.4.0` | `requirements-retina.txt` | 3. kademe adaptif kazıma |
| `browserforge>=1.2` | `requirements-retina.txt` | scrapling 0.4.x gizli bağımlılığı |
| `yt-dlp` | media forensics | video indirme (adapters_media.py `media_forensics.fetch_media`) |
| `open-interpreter` | `requirements-interpreter.txt` | ENABLE_INTERPRETER için (opsiyonel adım) |

Komut:
```bash
pip install -r requirements.txt -r requirements-osint.txt -r requirements-retina.txt
pip install scrapling browserforge yt-dlp
```

`open-interpreter` ayrı kurulur (starlette çakışması nedeniyle requirements.txt'ten çıkarıldı):
```bash
pip install -r requirements-interpreter.txt
```

---

## 3 · Adım 3: Harici araç / servis kurulumları (kapı-sıfır değil, yetenek-gereklidir)

Bu araçlar Pineal'e kod olarak girmez; operatör ortamında bulunmalı:

| Yetenek | Gerekli araç | Nasıl sağlanır |
|---|---|---|
| `sensor.web.agent_reach` | `agent-reach` CLI | `PINEAL_AGENT_REACH_CMD=/yol/agent-reach` (NOT: `npm i -g agent-reach` artık farklı bir proje kurar — kaynak sabitlenmeli) |
| `sensor.search.searxng` | SearXNG servisi | `SEARXNG_BASE_URL=http://127.0.0.1:8080` — ayrı AGPL-3.0 servis, Docker ile ayağa kalkar |
| `extractor.text.translate_local` | `trans` (translate-shell) CLI | `PINEAL_TRANSLATE_CMD=trans` veya `PINEAL_TRANSLATE_URL=http://127.0.0.1:9100/translate` |
| `verifier.jury.local` | Yerel model | `ollama` / `llama.cpp` / `vLLM` sunucusu, `PINEAL_LOCAL_JURY_URL` |
| `sensor.company.harvester` | theHarvester CLI | Python ≥ 3.14 istiyor; proje 3.11 → uyumlu sürüm veya ayrı konteyner |
| `renderer.report.video` | `ffmpeg` statik binary | `PATH`'te `ffmpeg` olmalı |
| `extractor.media.transcript` | `whisper` CLI | `PINEAL_STT_CMD=whisper` veya yerel STT ucu |
| `voice.tts.local` | `piper` CLI | `PINEAL_PIPER_MODEL` + piper PATH'te |
| `voice.stt.local` | Yerel STT ucu | `PINEAL_STT_URL=http://127.0.0.1:9000/stt` (yalınız localhost) |
| `sensor.x.twscrape` | Operatör X hesabı | `cache/x_accounts.db` (`.gitignore`'da, repoya düşmez) + `PINEAL_X_ACCOUNTS_DB` |
| `sensor.ig.instagrapi` | Operatör IG hesabı | `IG_USERNAME` / `IG_PASSWORD` veya `IG_SESSIONID` |

---

## 4 · Adım 4: Doğrulama — her kapıyı çalıştırıp test et

Kodda zaten var olan test komutları:

```bash
# Tüm yeteneklerin availability'sini kontrol et
python -c "from agent_core.capabilities.registry import CapabilityRegistry; r=CapabilityRegistry(); [print(c.id, c.availability()) for c in r.all()]"

# Canlı çalışabilirlik probe'u
PINEAL_ENV=development python scripts/canli_calisirlik_probe.py kanit

# Kapasite denetimi
python scripts/kapasite_denetimi_probe.py --out reports/kapasite_denetimi.json

# Testler
pytest tests -q --cov=agent_core --cov=backend --cov-fail-under=80
```

**Başarı kriteri:** Tüm 26 yetenek `available=True` döner veya `dependency_missing:*` / `credentials_missing:*` gibi **makine-okunur ve açıklayıcı** bir sebep verir. Hiçbiri `gate_disabled` veya `unknown_gate` dönmez.

---

## 5 · Adım 5: Kasa (vault) interlock

Tüm yetenekler `vault` kapısına bağlıdır. Kasa kilitliyken dış ağa tek bir istek çıkmaz. Operatör `.env` ile `NINEROUTER_API_KEY` (veya `sk-pineal` önekli anahtar) girerek kasayı açar. Bu, "her şey açık" anlamına gelir ama kasa zırtınağından geçmeden analiz çalışmaz — bu tasarım ile aynı kalır (Tüzük Md.4.1).

---

## 6 · Ne değişmez (kırmızı çizgiler)

Bu plan **kapıları** açar; aşağıdakileri Değil değiştirir:

- **Çocuk kırmızı çizgisi (Madde 4/A):** 18 yaş altı mutlak engel kalır, kapı açılsa bile.
- **Kasa mandalı:** `vault` kilitliyken dış çağrı yok. Kapı açılış = kasa açılış değildir.
- **Hedef rıçası yok:** Tüzük Md.4'de zaten yok; operatör kararı kalır.
- **Yerellik:** TTS/STT/çeviri/jüri uzak uç reddedilir, yalnız `localhost` / `127.0.0.1` kabul edilir.
- **Fail-closed bilinmeyen kapı:** `MANAGED_GATE_FLAGS` listesinde olmayan `ENABLE_*` adı `unknown_gate` ile reddedilir (sessizce kapalı görünmez).

---

## 7 · Önerilen sıralama (kritik yol)

1. **Gün 1:** `.env.example`'da tüm `ENABLE_*` → `true`; `pip install` tüm paketler; `pytest` yeşil.
2. **Gün 2-3:** Harici araçları provision et (SearXNG, theHarvester, ffmpeg, whisper, piper, agent-reach CLI).
3. **Hafta 2:** `scripts/canli_calisirlik_probe.py` ile her yeteneği tek tek canlı doğrula; raporla.

---

Bu plan onaylandıysa, hangi adımdan başlamak istersiniz? Kodda `.env.example` ve `requirements` dosyalarını doğrudan düzenleyebilir, veya önce planı onaylatabilirsiniz.
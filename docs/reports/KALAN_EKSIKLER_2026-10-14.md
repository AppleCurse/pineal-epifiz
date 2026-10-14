# Kalan Eksikler — Mutlak Liste (2026-10-14, ikinci tur)

**Bu belge bir kutlama değildir.** Sistem "tamamı çalışıyor" DEĞİLDİR ve bu
belge o eksiği saklamak yerine tam listeler. Ölçüm: bu ortam, bu kod, bu tur.

---

## 0 · Yöntem ve sınır

- Her satır **çalıştırılarak** ölçüldü (sonda: `scripts/canli_calisirlik_probe.py`;
  kanıt: `reports/canli_calisirlik_*.json`, `reports/kapasite_opsiyonel_kurulu.json`).
- "Kod var" ≠ "çalışıyor" ≠ "ürüne bağlı". Üçü ayrı ayrı işaretlenir.
- Bu ortamda **yok olan** şeyler (API anahtarı, dış ağ, yerel modeller) yüzünden
  kapanamayan kalemler "kapalı" olarak yazılır — "çalışıyor" sayılmaz.

---

## 1 · Bu turda KAPATILANLAR (kanıtla)

| Kalem | Önce | Yapılan | Şimdi (kanıt) |
|---|---|---|---|
| `extractor.web.trafilatura` | `timeout` (kendi bütçesine takılıyordu) | İndirme tavanı (`DOWNLOAD_TIMEOUT`) yeteneğin kendi bütçesinin altına çekildi | Gerçek metin, kanıt=1 |
| `extractor.web.scrapling` | `extract_error` (`browserforge` bildirilmemiş) | `requirements-retina.txt`'e açık beyan | Gerçek metin **19.351 bayt** |
| `sensor.x.twscrape` | `dependency_missing` | Paket kuruldu (beyanlıydı) | Kullanılabilir |
| `sensor.ig.instagrapi` | `dependency_missing` | Paket kuruldu | Artık yalnız **kimlik** bekliyor (`credentials_missing`) |
| `renderer.report.video` | `dependency_missing:ffmpeg` | ffmpeg (statik binary) yol üzerine alındı | **Gerçek video** üretti, kanıt=2 |
| Ses zinciri (TTS+STT) | "motor yok" — zincir kanıtsızdı | Yerel uç taklidiyle uçtan uca koşuldu | **Gerçek WAV** üretildi ve servis edildi (6.444 bayt, RIFF) + dinleme metne çevrildi |
| LLM istek yolu | "anahtar yok, bilinmiyor" | Yerel taklit sağlayıcı ile uçtan uca HTTP | Gövde/başlık doğru, yanıt işlendi; **kapalı portta dürüst hata** |
| Toplam yetenek (tüm kapılar açık) | 13 açık / 13 kapalı | Yukarıdakiler | **17 açık / 9 kapalı** |

Gerçek koşum tablosu (8 yetenek, runner üzerinden): **7/8 çalıştı**; tek
başarısız `holehe` **uydurmadı**: `scan_unavailable:provider_errors`
(bu ortam dış ağa çıkamıyor).

---

## 2 · KAPANMAYANLAR — tam liste (9 yetenek + 2 kanıt kalemi)

| # | Kalem | Bugünkü sebep (ölçüm) | Tam olarak gereken | Kim |
|---|---|---|---|---|
| 1 | `voice.tts.local` | `no_local_endpoint` | Gerçek yerel TTS motoru (piper / VoxCPM / MOSS-TTS) veya yerel uç; `PINEAL_TTS_URL`. Zincirin tamamı kanıtlandı — eksik olan **motorun kendisi** | Operatör kurulumu |
| 2 | `voice.stt.local` | `no_local_endpoint` | Yerel STT servisi (whisper.cpp / faster-whisper sunucusu); `PINEAL_STT_URL` | Operatör kurulumu |
| 3 | `extractor.media.transcript` | `no_engine` | `whisper` CLI veya yerel uç. Model ağır (torch ≈ 2 GB) → bu ortamda kurulmadı | Operatör kurulumu |
| 4 | `extractor.text.translate_local` | `no_engine` | `translate-shell` (`trans`) ikilisi ya da yerel çeviri ucu | Operatör kurulumu |
| 5 | `verifier.jury.local` | `no_local_models` | Yerel model sunucusu (ollama / llama.cpp / vLLM) | Operatör kurulumu |
| 6 | `sensor.search.searxng` | `config_missing:SEARXNG_BASE_URL` | **Gerçek SearXNG servisi.** UYARI: PyPI'deki `searxng` paketi SearXNG'in kendisi DEĞİL (ölçüm: 0.1.2 sürümü bir "MCP shim", yazar D. Danchev) — kör kurulum yanlış izlenim verir | Operatör (servis) |
| 7 | `sensor.web.agent_reach` | `dependency_missing:agent-reach` | Doğru CLI'ın kendisi. UYARI: `npm i -g agent-reach` artık **AYNI ADLI BAŞKA** bir projeyi kuruyor (ölçüm: npm `agent-reach@0.3.4` = Nostr ajan ağı); PyPI'de de ilgisiz bir `agent-reach` var. Kod tarafı hazır: `PINEAL_AGENT_REACH_CMD` ile yol verilir | Operatör (kaynak sabitleme) |
| 8 | `sensor.company.harvester` | `dependency_missing:theHarvester` | theHarvester **Python ≥ 3.14** istiyor (ölçüm), proje 3.11 → uyumlu sürüm ya da ayrı konteyner | Operatör kararı |
| 9 | `sensor.ig.instagrapi` | `credentials_missing:IG_USERNAME/IG_PASSWORD` | Operatörün Instagram hesabı. Kod yolu hazır | Operatör |
| K1 | **Canlı LLM (beyin)** | Bu ortamda hiçbir sağlayıcı anahtarı yok | Tek komut: `/api/vault` ile anahtar girin → `/api/aspasia/chat` gerçek yanıt üretir (komut: `docs/reports/CANLI_KANIT_RAPORU_2026-10-14.md` §3) | Operatör (1 dakika) |
| K2 | **Dış platform taramaları** (holehe/maigret gerçek tarama) | Ortam dış ağa çıkamıyor | Gerçek ağ erişimi olan dağıtımda çalıştırma | Dağıtım ortamı |

**Kod hatası nedeniyle kapalı yetenek: 0.** 9 kalemin tamamı kurulum / kimlik /
servis / ortam bekliyor — bu ayrım ölçümle sabitlendi (availability sebepleri
makine-okunur: `dependency_missing:*`, `no_engine`, `config_missing:*`,
`credentials_missing:*`, `no_local_endpoint`, `no_local_models`).

---

## 3 · "37 uç" meselesinin kesin hâli

- 70 benzersiz `/api/` yolundan **33'ü ön yüzde çağrılıyor, 37'si çağrılmıyor.**
- "Çağrılmıyor" = **arayüzde düğmesi yok**; bozuk DEĞİL. Kanıt: canlı sunucuda
  58 istek → **0×500**; 24 uç anahtarsız gerçek içerik döndü.
- Karar gereken yer burasıdır: hangi 37 uç arayüze taşınacak, hangisi operatör
  ucu olarak kalacak. Bu bir ürün kararıdır; kod tarafı çalışıyor.

---

## 4 · Sıra (kalan iş)

1. **K1** — anahtarı girip canlı LLM'i doğrula (tek komut; bu ortamda imkânsız).
2. **7 + 6** — yanlış paket tuzakları: `PINEAL_AGENT_REACH_CMD` ile gerçek CLI;
   SearXNG'i servis olarak kur (PyPI paketini KURMA).
3. **1 + 2 + 3 + 5** — yerel motorlar (TTS/STT/whisper/jüri): kablo hazır,
   motor kurulumu operatörde. Kurulduğunda bu satırlar `available: true` olur.
4. **4** — `trans` ikilisi.
5. **8** — theHarvester için Python 3.14 uyumu ya da konteyner kararı.
6. **9** — IG kimliği (yalnız operatörde).
7. **§3 kararı** — 37 ucun arayüz/operatör dağılımı.

---

## 5 · Dürüst sınır

Bu ortamda **kanıtlanmayanlar**: canlı bulut LLM çağrısı, gerçek dış platform
taramaları (holehe/maigret), gerçek TTS/STT/whisper/jüri modelleri, gerçek
SearXNG sorgusu, gerçek theHarvester koşusu, gerçek Instagram/X çağrıları.
Bunlar **çalışıyor sayılmaz**; §2'de "kapalı" olarak listelenmiştir.

Kanıtlananlar: istek yolu, üretim hattı, dürüst ret davranışı, 0×500, gerçek
dosya üretimi (PDF/PNG/video/WAV/metin), kimlik bilgisi yokken **uydurmama**.

Tekrar üretim:

```bash
PINEAL_ENV=development python scripts/canli_calisirlik_probe.py kanit
PINEAL_ENV=development python scripts/canli_calisirlik_probe.py taklit
python scripts/kapasite_denetimi_probe.py --out reports/kapasite_opsiyonel_kurulu.json
```

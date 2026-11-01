# Kapı onarımı ve kanıt — 2026-11-01

Bu rapor kod onarımını, ölçülen test sonuçlarını ve açık kalan dış ön koşulları ayırır.
**17 kapının hiçbiri için canlı hedef yürütmesi yapılmadı; bayraklar varsayılan kapalı bırakıldı.**
Dil kuralı: burada “yaptım/açıldı/çalışıyor” değil, **ölçüm + karar** vardır.

## 1. Ölçülen onarımlar

### yt-dlp / `sensor.media.fetch`

- `available=True` artık yalnız paket/komut varlığına dayanmıyor. `MediaFetchCapability.requires_preflight=True`; ön kontrol `yt-dlp --version` çıktısını ağa çıkmadan ölçüyor.
- Geçerli sürüm biçimi doğrulanıyor. Bozuk/okunamaz sürüm çıktısı `ytdlp_version_unreadable`, nonzero exit `ytdlp_probe_failed:rc`, zaman aşımı `ytdlp_probe_timeout` olarak reddediliyor.
- Platform indirmesinde her çağrı yeni bir alt dizine yazıyor. `rc=0` olsa bile yeni dosya yoksa sonuç `download_missing`; eski dosya “indirme başarılı” diye sunulmuyor.
- `/api/media/status` artık `registry.readiness` kullanıyor: kasa/politika reddi, yerel uygunluk ve ön kontrol ayrı alanlarda. `tools.yt-dlp` PATH varsayımı değil, çalıştırılmış sürüm probunun sonucu.
- Bu ortamda ölçülen yt-dlp: `2026.10.26`, exit 0. Bu **yerel araç kanıtıdır**; canlı platform indirmesi kanıtı değildir.

### X / `sensor.x.twscrape`

- `no_session_pool` yalnız ölçülmüş boş/aktif olmayan havuz için kullanılıyor.
- Yol/DB okuma hatası `session_pool_unreadable`; havuz API’si ölçülemiyorsa `session_pool_unmeasurable`. Bunlar `no_session_pool` veya `user_not_found` diye yazılmıyor.
- Preflight, `pool=` parametresini desteklemeyen kurucuda varsayılan DB’ye düşmüyor; durum ölçümü yeni `accounts.db` oluşturmuyor.
- Telemetri `x_session_preflight_reason` alanını taşıyor. MCP/UI yerel ön koşul sebebini etkin politika reddinden ayrı gösteriyor.
- Bu ortamda ölçülen sebep: `no_session_pool`.

### Kalan kapılar

Aynı protokol 17 kapının tamamına uygulandı: paket/import + CLI sürümü + servis ucu + kimlik/model yapılandırması + yerel uygunluk/preflight + depo testi + canlı doğrulama boşluğu.
Servis probları yalnız yapılandırılmış yerel uçlara GET attı; hedef taraması, hesap açma, credential üretimi veya ücretli canlı çağrı yapılmadı.

## 2. Komutlar ve kararlar

| Komut | Ölçülen sonuç | Karar |
|---|---|---|
| `.venv/bin/python scripts/audit_gates.py --run-tests --probe-services` | exit 0; `20261101T042151Z`; 17/17 `YAPILAMADI` | YAPILAMADI (kapılar) |
| `.venv/bin/python -m pytest tests/unit/test_capability_preflight.py tests/unit/test_media_forensics.py tests/integration/test_media_api_faz_d.py tests/unit/test_p0_honest_status.py tests/unit/test_mcp_server.py -q --timeout=120 -p no:cacheprovider --disable-warnings` | `116 passed`; exit 0 | GEÇTİ |
| `.venv/bin/python -m pytest -q -p no:cacheprovider --timeout=300 --cov=agent_core --cov=backend --cov-report=term-missing:skip-covered --cov-fail-under=80` | `3406 passed, 2 skipped, 2 xfailed`; 255.19 s; kapsam `86.59%`; exit 0 | GEÇTİ |
| `.venv/bin/ruff check .` | `All checks passed!`; exit 0 | GEÇTİ |
| `.venv/bin/python scripts/local_smoke.py` | PDF/diyagram/video + kare analizi + `tr` dil tespiti; exit 0 | GEÇTİ (yerel sentetik) |
| `npm run check --prefix frontend` | 0 hata, 9 kullanılmayan CSS uyarısı; exit 0 | GEÇTİ |
| `npm test -- --run` (frontend) | 6 test geçti; exit 0 | GEÇTİ |
| `npm run build --prefix frontend` | 139 modül; exit 0 | GEÇTİ |
| CI bekçileri: `audit_regression`, `dead_code_audit`, routing/inventory/skills, katalog, `pip check` | tümünde `EXIT=0`; katalog canlı anahtar yokken yerel sözleşme | GEÇTİ |

Tam çıktılar: `reports/gate_audit/evidence/*.txt`.
Kapı denetimi: `reports/gate_audit/final_audit.md` ve `final_audit.json`.
Ham kapı logları: `reports/gate_audit/20261101T042151Z/`.

## 3. Kapı kapı ölçüm özeti

Tüm satırlarda ortak politika engeli: `gate_disabled` + `vault_locked`. Bayrak true yapılmadı; kasa aşılmadı.

| Kapı | Paket / CLI | Servis / kimlik | Depo testi | Karar ve gerekçe |
|---|---|---|---|---|
| `ENABLE_MAIGRET` | maigret 0.6.5 | canlı hedef probu yok | GEÇTİ | YAPILAMADI: kapalı/kasa + `live_target_not_verified` |
| `ENABLE_CROSS_PLATFORM` | native/httpx | canlı hedef probu yok | GEÇTİ | YAPILAMADI: kapalı/kasa + `live_target_not_verified` |
| `ENABLE_HOLEHE` | holehe 1.61 | canlı hedef probu yok | GEÇTİ | YAPILAMADI: kapalı/kasa + `live_target_not_verified` |
| `ENABLE_CRAWL4AI` | crawl4ai 0.9.3 | canlı hedef probu yok | GEÇTİ | YAPILAMADI: kapalı/kasa + `live_target_not_verified` |
| `ENABLE_SCRAPLING` | scrapling 0.5, browserforge 1.2.4 | canlı hedef probu yok | GEÇTİ | YAPILAMADI: kapalı/kasa + `live_target_not_verified` |
| `ENABLE_X_SENSOR` | twscrape 0.20.1 | `no_session_pool` | GEÇTİ | YAPILAMADI: aktif oturum havuzu yok + kapalı/kasa |
| `ENABLE_IG_SECONDARY` | instagrapi 3.2.2 | `IG_USERNAME`, `IG_PASSWORD`, `IG_SESSIONID` yok | GEÇTİ | YAPILAMADI: kimlik/oturum yok + kapalı/kasa |
| `ENABLE_AGENT_REACH` | `command_not_found:agent-reach` | canlı hedef probu yok | GEÇTİ | YAPILAMADI: CLI yok + kapalı/kasa |
| `ENABLE_SEARXNG` | ayrı servis | `service_not_configured` | GEÇTİ | YAPILAMADI: uç yapılandırılmadı + kapalı/kasa |
| `ENABLE_LOCAL_TRANSLATE` | `command_not_found:trans` | `service_not_configured` | GEÇTİ | YAPILAMADI: yerel motor yok + kapalı/kasa |
| `ENABLE_LOCAL_JURY` | yerel uç | `/models` probu `ConnectError`; model env yok | GEÇTİ | YAPILAMADI: servis/model yok + kapalı/kasa |
| `ENABLE_COMPANY_TARGETING` | `command_not_found:theHarvester` | canlı hedef probu yok | GEÇTİ | YAPILAMADI: CLI yok + kapalı/kasa |
| `ENABLE_REPORT_FACTORY` | reportlab 4.5.1, Pillow 13.0.0, ffmpeg GEÇTİ | yerel sentetik duman GEÇTİ | GEÇTİ | YAPILAMADI: kapalı/kasa; canlı hedef kanıtı değil |
| `ENABLE_INTERPRETER` | `package_probe_failed` (open-interpreter yok) | kayıtlı capability yok | GEÇTİ | YAPILAMADI: paket/yetenek yok + kapalı/kasa |
| `ENABLE_MEDIA_FORENSICS` | opencv 4.14.0.94, yt-dlp 2026.10.26, ffmpeg GEÇTİ | transkript ucu yok; canlı platform indirmesi doğrulanmadı | GEÇTİ | YAPILAMADI: kapalı/kasa + `live_platform_download_not_verified` |
| `ENABLE_LOCAL_TTS` | `command_not_found:piper` | `PINEAL_PIPER_MODEL` yok, uç yok | GEÇTİ | YAPILAMADI: motor/model yok + kapalı/kasa |
| `ENABLE_LOCAL_STT` | `command_not_found:whisper` | uç yok | GEÇTİ | YAPILAMADI: motor yok + kapalı/kasa |

Her satırın ham kanıtı `final_audit.json` içindeki `packages`, `cli`, `service`, `identity`, `local_diagnostics`, `repository_test`, `blockers`, `verification_gaps` alanlarında ve ilgili `.log` dosyasındadır.

## 4. Yerel sentetik duman testi

`scripts/local_smoke.py` ağ/credential kullanmadan çalıştırıldı. PDF, diyagram ve video üretildi; video kare analizi ve Türkçe dil tespiti ölçüldü. Karar: **GEÇTİ (yerel sentetik; canlı hedef kanıtı değil)**.
Kanıt: `reports/gate_audit/evidence/local-smoke.txt`, `reports/gate_audit/local_smoke.json`.

ffmpeg bu ortamda apt adayı bulunmadığı için izole ortama `imageio-ffmpeg==0.7.0` kuruldu. Sürüm çıktısı: `ffmpeg version 7.0.2-static`, exit 0. Bu, yerel medya/video ön koşulunu sağlar; dış platform indirme veya transkripsiyon başarısı kanıtlamaz.

## 5. Açık kalan dış ön koşullar

- X: aktif hesap havuzu yok (`no_session_pool`).
- Instagram: kimlik/oturum yapılandırması yok.
- SearXNG: uç nokta yapılandırılmadı/doğrulanmadı.
- Yerel jüri: model/uç nokta yok; `/models` bağlantısı `ConnectError`.
- Agent-Reach, translate-shell, theHarvester, Piper, Whisper: komutlar bulunamadı.
- Open Interpreter: paket kurulu değil; kayıtlı capability yok.
- Docker: bu ortamda yok; imaj derlemesi YAPILAMADI.
- Kasa kilitli ve 17 bayrak kapalı olduğu için politika yürütmeyi reddediyor. Bu güvenlik davranışı korundu.

## 6. Yeniden üretim

```bash
python scripts/setup_env.py --dev
.venv/bin/python scripts/audit_gates.py --run-tests --probe-services
.venv/bin/python scripts/local_smoke.py
.venv/bin/python -m pytest -q -p no:cacheprovider --timeout=300 --cov=agent_core --cov=backend --cov-fail-under=80
```

Dış kapıları açmak için gerçek credential/servis/model kurulumu gerekir; bu rapor onları uydurmaz veya açılmış saymaz.

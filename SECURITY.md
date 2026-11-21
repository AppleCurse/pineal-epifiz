# Güvenlik Politikası

## Desteklenen sürümler

| Sürüm | Destek |
|---|---|
| `3.0.0-rc.x` (main) | ✅ aktif geliştirme |
| Daha eski sürümler | ❌ desteklenmiyor |

## Açık bildirme

Güvenlik açığı bulursan **herkese açık issue açma**. Bunun yerine GitHub
üzerinden özel bildirim gönder:

**Security → Report a vulnerability** (repo sayfasında, `github.com/AppleCurse/pineal-epifiz`)

Bildirimine şunları ekle:

- Etkilenen bileşen ve sürüm
- Tekrar üretme adımları (mümkünse)
- Etki değerlendirmesi (kimlik doğrulama atlama, veri sızıntısı vb.)

## Kapsam

- `backend/` (HTTP + WebSocket yüzeyi), `agent_core/`, `frontend/src/`,
  `functions/`, `worker.ts`, `android/`, `extensions/`
- Kapsam dışı: üçüncü taraf servisler (OpenRouter, SearXNG, sağlayıcı
  API'leri), sosyal mühendislik, DoS yük testleri.

## Beklentiler

- 7 gün içinde ilk yanıt, 30 gün içinde düzeltme hedeflenir.
- Düzeltme yayınlanana kadar ayrıntıları herkese açık paylaşma.
- İyi niyetli araştırmacılara kredi verilir (istersen adın CHANGELOG'da
  geçer).

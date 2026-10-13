# PINEAL-HERETIC — tek imajlı paket (multi-stage); release identity comes from VERSION
# 1. Aşama: frontend derlemesi (Svelte -> statik dist)
# 2. Aşama: Python runtime + FastAPI + Playwright/Chromium (scraper için)

# ---------- Stage 1: frontend ----------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
# Vite reads the canonical release identity from the repository root.
COPY VERSION /app/VERSION
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# [AUDIT 2026-09-11 P0] VITE_PINEAL_TOKEN build arg'ı KALDIRILDI.
# Server secret'ı (PINEAL_TOKEN) frontend bundle'ına gömülüyordu; Vite
# VITE_* değerlerini plaintext olarak JS bundle'ına derler -> token'ı
# tarayıcıdan indiren herkes /api/* ve /v1/* çağırabilir hale geliyordu.
# Kimlik artık YALNIZ çalışma zamanında girilir: UI'da Kasa ->
# "API ERİŞİM ANAHTARI (PINEAL_TOKEN)" alanı (localStorage, derleme yok).
RUN npm run build

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PINEAL_ENV=production \
    PINEAL_PORT=8000 \
    DEBIAN_FRONTEND=noninteractive

# Playwright/Chromium için sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Runtime version identity (FastAPI/MCP) uses the same canonical source.
COPY VERSION ./VERSION
# [AUDIT 2026-09-11 P1] Production imaj DETERMİNİSTİK lock'tan kurulur:
# bugün build edilen imaj ile yarınki aynı dependency ağacını alır.
# (requirements.txt/requirements-osint.txt soyut şartnamedir; lock'u
# yeniden üretmek için requirements.lock başlığındaki tarife bakın.)
COPY requirements.lock ./
RUN pip install --default-timeout=300 -r requirements.lock
# Railway/WebSocket kapısı: uvicorn'un WebSocket yolu runtime'da açıkça garanti edilir.
RUN pip install --default-timeout=120 "websockets==17.1"

# Opsiyonel Playwright indirme aynası (bölgesel CDN engeli; build-time).
# Kullanım: .env → PLAYWRIGHT_DOWNLOAD_HOST=... sonra docker compose build pineal
ARG PLAYWRIGHT_DOWNLOAD_HOST=""
ENV PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST}
RUN PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 python -m playwright install --with-deps chromium || \
    (echo "Retrying Playwright download..." && sleep 15 && PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 python -m playwright install --with-deps chromium) || \
    (echo "Retrying Playwright download 2..." && sleep 30 && PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 python -m playwright install --with-deps chromium) || \
    echo "Playwright installation completed with fallback"

COPY backend/ ./backend/
COPY agent_core/ ./agent_core/
COPY config/ ./config/
COPY main.py scraper.py ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Persistent data directories — production'da bunları kalıcı volume'a bağlayın.
# memory/: görev kanıt zinciri (kritik — kayıp geri alınamaz)
# cache/:  SQLite response cache (kaybedilebilir — yeniden doldurulur)
# ⚠ 2+ container aynı volume'u paylaşırsa tutarsızlık oluşur (process-local state).
RUN mkdir -p /app/memory /app/cache
VOLUME ["/app/memory", "/app/cache"]

EXPOSE 8000
# Production startup fails closed unless PINEAL_TOKEN is configured.
# Health: "ready" veya "degraded" → HTTP 200 (servis ayakta);
#         "failed" veya "starting" → HTTP 503 (container unhealthy sayılır).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "\
import urllib.request, json, sys; \
r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4); \
d = json.loads(r.read()); \
sys.exit(0 if d.get('status') in ('ready', 'degraded') else 1)" || exit 1

# İstek gövdesi tavanı uygulama katmanında (BodySizeLimitMiddleware) 1 MiB ile sınırlıdır
# (uvicorn 0.52.4'te --limit-max-request-size bayrağı yoktur; uygulama katmanında enforced).
CMD ["sh", "-c", "uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-${PINEAL_PORT:-8000}}"]

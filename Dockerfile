# PINEAL-HERETIC v2.0 — tek imajlı paket (multi-stage)
# 1. Aşama: frontend derlemesi (Svelte -> statik dist)
# 2. Aşama: Python runtime + FastAPI + Playwright/Chromium (scraper için)

# ---------- Stage 1: frontend ----------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Server secrets must never be embedded in Vite's public VITE_* bundle variables.
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
COPY requirements.lock ./
RUN pip install --default-timeout=300 -r requirements.lock
RUN pip install --default-timeout=120 "websockets==17.1"

ARG PLAYWRIGHT_DOWNLOAD_HOST=""
ENV PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST}
# Browser-backed scraping is a required capability in this image. Retry, then
# fail the build instead of silently shipping an image without Chromium.
RUN PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 python -m playwright install --with-deps chromium || \
    (echo "Retrying Playwright download..." && sleep 15 && PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 python -m playwright install --with-deps chromium) || \
    (echo "Retrying Playwright download 2..." && sleep 30 && PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=300000 python -m playwright install --with-deps chromium)

COPY backend/ ./backend/
COPY agent_core/ ./agent_core/
COPY config/ ./config/
COPY main.py scraper.py ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/memory /app/cache
VOLUME ["/app/memory", "/app/cache"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "\
import urllib.request, json, sys; \
r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4); \
d = json.loads(r.read()); \
sys.exit(0 if d.get('status') in ('ready', 'degraded') else 1)" || exit 1

CMD ["sh", "-c", "uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-${PINEAL_PORT:-8000}}"]

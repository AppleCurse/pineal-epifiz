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
COPY requirements.lock requirements-osint.txt requirements-retina.txt ./
RUN pip install --default-timeout=300 -r requirements.lock
RUN pip install --default-timeout=120 "websockets==17.1"

# ─── Kapı arkasındaki yeteneklerin GERÇEK bağımlılıkları ─────────────────────
# [AUDIT 2026-10-23] requirements.lock yalnız requirements.txt + osint ağacını
# taşıyordu. Retina paketleri (trafilatura, scrapling, browserforge, twscrape,
# instagrapi) imajda HİÇ yoktu; yani operatör `ENABLE_SCRAPLING=true` /
# `ENABLE_X_SENSOR=true` / `ENABLE_IG_SECONDARY=true` yaptığında yetenek
# `dependency_missing:<paket>` dönüyordu — kapı açık, motor yok.
# Artık imaj bu paketleri içerir; kapılar yine varsayılan KAPALI (davranış
# değişmez), ama açıldıklarında çalışırlar.
# `--upgrade-strategy only-if-needed`: psutil gibi ortak bağımlılıklar
# gereksiz yere yükseltilmez (lock'taki pin korunur).
ARG PINEAL_INSTALL_RETINA=1
RUN if [ "$PINEAL_INSTALL_RETINA" = "1" ]; then \
        pip install --default-timeout=300 --upgrade-strategy only-if-needed \
            -r requirements-retina.txt; \
    else \
        echo "PINEAL_INSTALL_RETINA=0 → Retina paketleri kurulmadı (yetenekler dependency_missing döner)"; \
    fi

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

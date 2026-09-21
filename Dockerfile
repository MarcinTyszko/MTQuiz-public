# syntax=docker/dockerfile:1.7

###############################################################################
# Etap 1 — budowa zasobów statycznych (Tailwind CSS + Alpine.js)
###############################################################################
FROM node:20-alpine AS assets

WORKDIR /build

# Instalacja zależności front-endu w osobnej warstwie (lepsze wykorzystanie cache).
# `npm ci` instaluje dokładnie wersje z pliku blokady — build jest powtarzalny.
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --no-audit --no-fund

# Źródła potrzebne do wygenerowania arkusza: szablony i skrypty są skanowane
# przez Tailwind w poszukiwaniu użytych klas.
COPY frontend/ ./frontend/
COPY app/templates/ ./app/templates/
COPY app/static/js/ ./app/static/js/

RUN cd frontend && npm run build


###############################################################################
# Etap 2 — zależności Pythona
###############################################################################
FROM python:3.12-slim AS python-deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /wheels

RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


###############################################################################
# Etap 3 — obraz produkcyjny
###############################################################################
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    QUIZAPP_DATA_DIR=/data

# Konto bez uprawnień administracyjnych — minimalizacja powierzchni ataku.
RUN groupadd --gid 10001 medfiszki \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin medfiszki

COPY --from=python-deps /opt/venv /opt/venv

WORKDIR /srv/app

COPY --chown=10001:10001 app/ ./app/
COPY --from=assets --chown=10001:10001 /build/app/static/css/app.css ./app/static/css/app.css
COPY --from=assets --chown=10001:10001 /build/app/static/vendor/ ./app/static/vendor/

# Katalog danych trwałych montowany jako wolumen.
RUN mkdir -p /data/backups && chown -R 10001:10001 /data /srv/app

USER 10001:10001

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

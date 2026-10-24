# syntax=docker/dockerfile:1

# --- build: install dependencies, compile translations, collect static files
FROM python:3.13.16-slim-trixie AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends gettext \
      build-essential pkg-config default-libmysqlclient-dev \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core poppler-utils \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

WORKDIR /app
COPY . .
RUN SECRET_KEY=build DATABASE_URL=sqlite:////tmp/build.db python manage.py compilemessages --ignore=/venv \
 && SECRET_KEY=build DATABASE_URL=sqlite:////tmp/build.db python manage.py collectstatic --noinput

# --- dev: build stage plus test tools, used by docker-compose.yml and CI
FROM build AS dev
RUN pip install -r /app/requirements-dev.txt

# --- runtime: no compilers; runs as the unprivileged user "app"
FROM python:3.13.16-slim-trixie

ENV PATH=/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/tmp/cache \
    DATA_ROOT=/data
# Pango/HarfBuzz for WeasyPrint (invoice PDFs), poppler for reading archived PDFs,
# libmariadb for MariaDB/MySQL databases.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libmariadb3 \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core poppler-utils \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app app \
 && mkdir -p /data \
 && chown app:app /data

COPY --from=build /venv /venv
COPY --from=build --chown=app:app /app /app

WORKDIR /app
# Starts as root only to give the data folder to "app"; the entrypoint then runs everything as "app".
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "packdesk.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]

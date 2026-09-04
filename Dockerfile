# PZ Control Panel — production image

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PANEL_HOST=0.0.0.0 \
    PANEL_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tar \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.1.1.tgz \
      | tar -xz --strip-components=1 -C /usr/local/bin docker/docker \
    && curl -fsSL -o /usr/local/bin/docker-compose \
      https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 \
    && chmod +x /usr/local/bin/docker /usr/local/bin/docker-compose \
    && rm -rf /var/lib/apt/lists/*

COPY panel/requirements.txt /app/panel/requirements.txt
RUN pip install --no-cache-dir -r panel/requirements.txt

COPY panel/ /app/panel/
COPY tools/ /app/tools/
COPY run_panel.py /app/run_panel.py
COPY packaging/panel_launcher.py /app/packaging/panel_launcher.py

RUN rm -rf /app/panel/data /app/panel/backups \
    && mkdir -p /data/panel/data/servers /data/panel/backups /mirror \
    && ln -sf /data/panel/data /app/panel/data \
    && ln -sf /data/panel/backups /app/panel/backups \
    && ln -sf /mirror /app/.mirror

VOLUME ["/data", "/mirror"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PANEL_PORT}/api/health" || exit 1

CMD ["python", "-m", "uvicorn", "panel.server:app", "--host", "0.0.0.0", "--port", "8000"]

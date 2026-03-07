FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .

RUN chmod +x /app/docker/entrypoint.sh /app/docker/worker-entrypoint.sh /app/docker/migrate-entrypoint.sh

EXPOSE 8000

USER app

CMD ["/app/docker/entrypoint.sh"]

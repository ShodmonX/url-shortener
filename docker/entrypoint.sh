#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
until pg_isready -h "${DATABASE_HOST:-db}" -p "${DATABASE_PORT:-5432}" -U "${POSTGRES_USER:-url_shortener}"; do
  sleep 2
done

echo "Starting API..."
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
  --workers "${UVICORN_WORKERS:-1}"

#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
until pg_isready -h "${DATABASE_HOST:-db}" -p "${DATABASE_PORT:-5432}" -U "${POSTGRES_USER:-url_shortener}"; do
  sleep 2
done

echo "Starting worker..."
exec python -m app.workers.main

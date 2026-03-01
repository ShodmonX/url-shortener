#!/bin/sh

echo "Waiting for database..."

until pg_isready -h db -p 5432 -U "$POSTGRES_USER"
do
  sleep 2
done

echo "Database is ready!"

echo "Running migrations..."
alembic upgrade head

echo "Starting application..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
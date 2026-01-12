#!/usr/bin/env sh
set -eu

echo "[backend] Применяем миграции Alembic..."
alembic -c /app/alembic.ini upgrade head

echo "[backend] Запускаем API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload


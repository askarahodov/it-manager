#!/usr/bin/env bash
set -euo pipefail

# Интеграционные тесты (FastAPI + Postgres) внутри docker-compose.
# Создаёт временную БД, прогоняет миграции, запускает pytest tests_integration, затем удаляет БД.

COMPOSE="docker compose -f deploy/docker-compose.yml"
DB_NAME="${ITMGR_TEST_DB:-it_manager_test}"

cleanup() {
  echo "[it-manager] Cleanup: drop test DB (best-effort): $DB_NAME"
  $COMPOSE exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[it-manager] Собираем backend образ..."
$COMPOSE build backend

echo "[it-manager] Поднимаем db/redis..."
$COMPOSE up -d db redis

echo "[it-manager] Создаём тестовую БД: $DB_NAME"
$COMPOSE exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
$COMPOSE exec -T db psql -U postgres -d postgres -c "CREATE DATABASE ${DB_NAME};"

export DATABASE_URL="postgresql+asyncpg://postgres:password@db:5432/${DB_NAME}"
export MASTER_KEY="test-master-key"
export SECRET_KEY="test-secret-key"

echo "[it-manager] Применяем миграции Alembic..."
$COMPOSE run --rm -e DATABASE_URL="$DATABASE_URL" -e MASTER_KEY="$MASTER_KEY" -e SECRET_KEY="$SECRET_KEY" --entrypoint alembic backend -c /app/alembic.ini upgrade head

echo "[it-manager] Запускаем pytest (integration)..."
$COMPOSE run --rm -e DATABASE_URL="$DATABASE_URL" -e MASTER_KEY="$MASTER_KEY" -e SECRET_KEY="$SECRET_KEY" -e PYTHONPATH=/app --workdir /app --entrypoint pytest backend -c /app/pytest_integration.ini tests_integration

echo "[it-manager] Удаляем тестовую БД: $DB_NAME"
echo "[it-manager] OK"

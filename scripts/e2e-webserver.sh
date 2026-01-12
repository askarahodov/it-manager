#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose.yml"

cleanup() {
  # В локальной разработке иногда удобнее не останавливать сервисы после тестов.
  if [[ "${E2E_COMPOSE_DOWN:-1}" == "1" ]]; then
    echo "[e2e] Останавливаем сервисы docker compose (без удаления volumes)..."
    docker compose -f "$COMPOSE_FILE" down || true
  else
    echo "[e2e] Пропускаем docker compose down (E2E_COMPOSE_DOWN=0)"
  fi
}

trap cleanup EXIT INT TERM

echo "[e2e] Запускаем docker compose stack..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo "[e2e] Stack поднят. Ожидаем завершения Playwright (процесс webServer должен жить)."
while true; do
  sleep 3600
done


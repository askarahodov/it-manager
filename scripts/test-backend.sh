#!/usr/bin/env bash
set -euo pipefail

# Запуск unit-тестов backend внутри docker-compose (без запуска entrypoint.sh).
docker compose -f deploy/docker-compose.yml build backend
docker compose -f deploy/docker-compose.yml run --rm --workdir /app -e PYTHONPATH=/app --entrypoint pytest backend

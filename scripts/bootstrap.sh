#!/usr/bin/env bash
set -euo pipefail

echo "Установите зависимости для backend и frontend через docker-compose при необходимости."
echo "Для backend: docker compose run --rm backend pip install -r requirements.txt"
echo "Для frontend: npm install в каталоге apps/frontend"

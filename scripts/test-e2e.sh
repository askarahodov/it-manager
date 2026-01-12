#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[it-manager] E2E: (best-effort) останавливаем текущий stack чтобы освободить порт 4173"
docker compose -f "$ROOT_DIR/deploy/docker-compose.yml" down || true

echo "[it-manager] E2E: install deps (frontend)"
cd "$ROOT_DIR/apps/frontend"
if [[ "${E2E_NPM_CI:-1}" == "1" ]]; then
  npm ci
else
  npm install
fi

PW_BROWSERS_DIR="$ROOT_DIR/apps/frontend/.pw-browsers"

echo "[it-manager] E2E: install Playwright browsers"
if [[ -d "$PW_BROWSERS_DIR" ]] && ls "$PW_BROWSERS_DIR" | grep -qE '^chromium-' && ls "$PW_BROWSERS_DIR" | grep -qE '^chromium_headless_shell-'; then
  echo "[it-manager] E2E: browsers already present at $PW_BROWSERS_DIR (skip install)"
else
  PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT="120000" \
  PLAYWRIGHT_DOWNLOAD_TIMEOUT="120000" \
  PLAYWRIGHT_BROWSERS_PATH="$PW_BROWSERS_DIR" \
    npx playwright install chromium
fi

echo "[it-manager] E2E: run Playwright tests"
E2E_REUSE_SERVER=0 E2E_COMPOSE_DOWN=1 PLAYWRIGHT_BROWSERS_PATH="$PW_BROWSERS_DIR" npm run test:e2e

echo "[it-manager] OK"

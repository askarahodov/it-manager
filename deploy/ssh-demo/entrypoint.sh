#!/usr/bin/env sh
set -eu

# Генерируем host keys при первом старте (в контейнере ephemeral FS это нормально).
ssh-keygen -A >/dev/null 2>&1 || true

exec /usr/sbin/sshd -D -e


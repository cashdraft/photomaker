#!/usr/bin/env bash
# Пуш текущего состояния репозитория на GitHub. Использует GITHUB_TOKEN из .env.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Файл .env не найден."
  exit 1
fi

GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' | sed 's/^ *//;s/ *$//')

if [ -z "$GITHUB_TOKEN" ] || [ "$GITHUB_TOKEN" = "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН" ]; then
  echo "В .env задайте GITHUB_TOKEN (Personal Access Token с правом repo)."
  exit 1
fi

git remote set-url origin "https://${GITHUB_TOKEN}@github.com/cashdraft/photomaker.git"
git push -u origin main --force

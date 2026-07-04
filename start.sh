#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo ".env is missing. Create it from README.md first." >&2
  exit 1
fi

if [[ -f bot.pid ]] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "Bot is already running: $(cat bot.pid)"
  exit 0
fi

set -a
. ./.env
set +a

export PYTHONUNBUFFERED=1
export BOT_LOG_LEVEL="${BOT_LOG_LEVEL:-INFO}"

./proxy-start.sh || true

mkdir -p logs
nohup .venv/bin/python -u bot.py >> bot.log 2>&1 &
echo "$!" > bot.pid
echo "Started bot: $(cat bot.pid)"
echo "Logs: tail -f bot.log"

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

update_dependencies() {
  if [[ "${BOT_AUTO_UPDATE_DEPS:-1}" == "0" ]]; then
    echo "Dependency auto-update disabled."
    return
  fi

  echo "Updating Python dependencies..."
  .venv/bin/python -m pip install --upgrade --disable-pip-version-check -r requirements.txt \
    || echo "Dependency update failed; starting with installed packages."
}

bash ./cleanup-bot-temp.sh || echo "Bot tmp cleanup failed; continuing startup."
update_dependencies

./proxy-start.sh || true

mkdir -p logs
nohup .venv/bin/python -u bot.py >> bot.log 2>&1 &
echo "$!" > bot.pid
echo "Started bot: $(cat bot.pid)"
echo "Logs: tail -f bot.log"

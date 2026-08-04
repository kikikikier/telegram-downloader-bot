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

cleanup_tmp_downloads() {
  local tmp_parent="${BOT_TMP_DIR:-${TMPDIR:-/tmp}}"
  local tmp_root="${tmp_parent%/}/telegram-downloader-bot"
  local max_age_minutes="${BOT_STARTUP_TMP_MAX_AGE_MINUTES:-30}"

  if [[ ! "$max_age_minutes" =~ ^[0-9]+$ ]]; then
    max_age_minutes=30
  fi

  if [[ -d "$tmp_root" && "$tmp_root" == */telegram-downloader-bot ]]; then
    find "$tmp_root" -mindepth 1 -maxdepth 1 -type d -mmin +"$max_age_minutes" -exec rm -rf -- {} +
  fi
}

update_dependencies() {
  if [[ "${BOT_AUTO_UPDATE_DEPS:-1}" == "0" ]]; then
    echo "Dependency auto-update disabled."
    return
  fi

  echo "Updating Python dependencies..."
  .venv/bin/python -m pip install --upgrade --disable-pip-version-check -r requirements.txt \
    || echo "Dependency update failed; starting with installed packages."
}

cleanup_tmp_downloads
update_dependencies

./proxy-start.sh || true

mkdir -p logs
nohup .venv/bin/python -u bot.py >> bot.log 2>&1 &
echo "$!" > bot.pid
echo "Started bot: $(cat bot.pid)"
echo "Logs: tail -f bot.log"

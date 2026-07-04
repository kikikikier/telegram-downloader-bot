#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  . ./.env
  set +a
fi

echo "== process =="
if [[ -f bot.pid ]] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "bot: RUNNING $(cat bot.pid)"
else
  echo "bot: STOPPED"
fi

echo
echo "== tools =="
command -v ffmpeg || true
command -v ffprobe || true
.venv/bin/python -m yt_dlp --version 2>/dev/null || true
.venv/bin/python - <<'PY'
try:
    import telethon
    print("telethon:", telethon.__version__)
except Exception as exc:
    print("telethon: missing", exc)
PY

echo
echo "== config without secrets =="
echo "BOT_API_BASE=${BOT_API_BASE:-https://api.telegram.org}"
echo "BOT_API_LOCAL=${BOT_API_LOCAL:-0}"
echo "BOT_MAX_MB=${BOT_MAX_MB:-auto}"
echo "BOT_PART_MB=${BOT_PART_MB:-48}"
echo "BOT_DOWNLOAD_MAX_MB=${BOT_DOWNLOAD_MAX_MB:-0}"
echo "BOT_LARGE_UPLOAD_MODE=${BOT_LARGE_UPLOAD_MODE:-document}"
echo "BOT_TELEGRAM_PROXY=$([[ -n "${BOT_TELEGRAM_PROXY:-}" ]] && echo set || echo empty)"
echo "BOT_YTDLP_PROXY=$([[ -n "${BOT_YTDLP_PROXY:-}" ]] && echo set || echo empty)"
echo "BOT_DIRECT_PROXY=$([[ -n "${BOT_DIRECT_PROXY:-}" ]] && echo set || echo empty)"
echo "BOT_MTPROTO_PROXY=$([[ -n "${BOT_MTPROTO_PROXY:-}" ]] && echo set || echo empty)"
echo "TELEGRAM_API_ID=$([[ -n "${TELEGRAM_API_ID:-${APP_ID:-}}" ]] && echo set || echo empty)"
echo "TELEGRAM_API_HASH=$([[ -n "${TELEGRAM_API_HASH:-${APP_HASH:-}}" ]] && echo set || echo empty)"

echo
echo "== network =="
if [[ -n "${BOT_TELEGRAM_PROXY:-}" ]]; then
  curl -fsS --max-time 15 -x "$BOT_TELEGRAM_PROXY" https://api.telegram.org >/dev/null && echo "telegram via proxy: OK" || echo "telegram via proxy: FAIL"
else
  curl -fsS --max-time 15 https://api.telegram.org >/dev/null && echo "telegram direct: OK" || echo "telegram direct: FAIL"
fi

echo
echo "== disk =="
df -h .
df -h "${BOT_TMP_DIR:-/tmp}" 2>/dev/null || true

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f bot.pid ]]; then
  echo "No bot.pid"
  exit 0
fi

pid="$(cat bot.pid)"
if kill "$pid" 2>/dev/null; then
  echo "Stopped bot: $pid"
else
  echo "Bot was not running: $pid"
fi
rm -f bot.pid

./proxy-stop.sh || true

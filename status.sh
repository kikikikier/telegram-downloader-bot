#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f bot.pid ]] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "RUNNING $(cat bot.pid)"
else
  echo "STOPPED"
fi

if ss -lnt 2>/dev/null | grep -q '127.0.0.1:18080'; then
  echo "PROXY RUNNING 127.0.0.1:18080"
else
  echo "PROXY STOPPED"
fi

tail -n 20 bot.log 2>/dev/null || true
echo
echo "Follow logs: ./logs.sh"

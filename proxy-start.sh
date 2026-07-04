#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f sing-box-local.json ]]; then
  echo "No sing-box-local.json, skipping proxy start."
  exit 0
fi

if [[ -f proxy.pid ]] && kill -0 "$(cat proxy.pid)" 2>/dev/null; then
  echo "Proxy is already running: $(cat proxy.pid)"
  exit 0
fi

if ss -lnt 2>/dev/null | grep -q '127.0.0.1:18080'; then
  echo "Proxy port 18080 is already listening."
  exit 0
fi

nohup /usr/bin/sing-box run -c sing-box-local.json >> proxy.log 2>&1 &
echo "$!" > proxy.pid
echo "Started proxy: $(cat proxy.pid)"

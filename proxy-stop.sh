#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f proxy.pid ]]; then
  pid="$(cat proxy.pid)"
  if kill "$pid" 2>/dev/null; then
    echo "Stopped proxy: $pid"
  else
    echo "Proxy was not running by pid: $pid"
  fi
  rm -f proxy.pid
fi

pkill -f '[s]ing-box run -c sing-box-local.json' 2>/dev/null || true

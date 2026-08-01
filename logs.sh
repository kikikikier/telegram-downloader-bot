#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

lines="${1:-200}"
touch bot.log
tail -n "$lines" -f bot.log


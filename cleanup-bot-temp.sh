#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  . ./.env
  set +a
fi

timestamp() {
  date -Is
}

count_workdirs() {
  find "$tmp_root" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' '
}

tmp_parent="${BOT_TMP_DIR:-${TMPDIR:-/tmp}}"
tmp_root="${tmp_parent%/}/telegram-downloader-bot"
max_age_minutes="${BOT_TMP_MAX_AGE_MINUTES:-${BOT_STARTUP_TMP_MAX_AGE_MINUTES:-30}}"

if [[ ! "$max_age_minutes" =~ ^[0-9]+$ ]]; then
  max_age_minutes=30
fi

if [[ "$tmp_root" != */telegram-downloader-bot ]]; then
  echo "Refusing to clean unexpected tmp root: $tmp_root" >&2
  exit 1
fi

mkdir -p "$tmp_root"

echo "[$(timestamp)] bot tmp cleanup start root=$tmp_root max_age_minutes=$max_age_minutes"
echo "disk before:"
df -h "$tmp_parent" || df -h
echo "tmp size before:"
du -sh "$tmp_root" || true

before_count="$(count_workdirs)"
echo "workdirs before=$before_count"

find "$tmp_root" -mindepth 1 -maxdepth 1 -type d -mmin +"$max_age_minutes" -print -exec rm -rf -- {} +

after_count="$(count_workdirs)"
echo "workdirs after=$after_count"
echo "tmp size after:"
du -sh "$tmp_root" || true
echo "disk after:"
df -h "$tmp_parent" || df -h

removed=$((before_count - after_count))
if (( removed < 0 )); then
  removed=0
fi
echo "[$(timestamp)] cleanup complete root=$tmp_root removed=$removed"

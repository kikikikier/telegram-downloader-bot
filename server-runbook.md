# Server Runbook

Server:

```text
95.181.213.67
```

Project path:

```text
/home/codex/telegram-downloader-bot
```

Typical commands from the project folder:

```bash
./status.sh
./start.sh
./stop.sh
./proxy-start.sh
./proxy-stop.sh
./logs.sh
./diagnose.sh
```

Proxy:

```text
127.0.0.1:18080
```

Notes:

- The VPS could not reach `api.telegram.org` directly.
- The bot uses the local mixed proxy route.
- Keep proxy config secrets out of this repository.

## Live Logging

```bash
cd /home/codex/telegram-downloader-bot
./logs.sh
```

To enable verbose logs for one debugging session, put this in `.env`, restart, then tail:

```bash
BOT_LOG_LEVEL=DEBUG
```

```bash
./stop.sh
./start.sh
./logs.sh
```

The log now includes the chosen upload route, downloaded file size, live `yt-dlp` lines, MTProto subprocess output, and ffmpeg split attempts.

Temporary download folders are marked while active, then kept for `BOT_CLEANUP_DELAY_SECONDS=60` seconds after the job ends and removed by the bot cleanup worker. On startup, the worker also removes stale folders left by a killed/restarted process.

## Large Upload Options

Best options in order:

1. Local Bot API server with `--local`: set `BOT_API_BASE=http://127.0.0.1:8081` and `BOT_API_LOCAL=1`.
2. MTProto via Telethon: set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` on the server.
3. ffmpeg segment fallback when the single-file upload route cannot accept the file.

`BOT_PREVIEW_MAX_MB=49` keeps huge files from being uploaded twice as preview plus document. Raise it only if you deliberately want large video previews.

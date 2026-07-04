# Local Bot API Server

This is the cleanest single-file route for large bot uploads.

Official behavior:

- Cloud Bot API: upload about 50 MB, download about 20 MB.
- Local Bot API server with `--local`: upload up to 2000 MB and pass local files by `file://` path.

## Bot `.env`

```env
BOT_API_BASE=http://127.0.0.1:8081
BOT_API_LOCAL=1
BOT_MAX_MB=1990
BOT_UPLOAD_TIMEOUT=7200
```

Before switching an existing bot to the local server, Telegram says to call `logOut` against the cloud API:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/logOut"
```

## Run Server

The local server needs Telegram app credentials from `https://my.telegram.org/apps`.

Example command:

```bash
telegram-bot-api \
  --api-id="$TELEGRAM_API_ID" \
  --api-hash="$TELEGRAM_API_HASH" \
  --local \
  --http-ip-address=127.0.0.1 \
  --http-port=8081 \
  --dir=/var/lib/telegram-bot-api \
  --temp-dir=/tmp/telegram-bot-api \
  --log=/var/log/telegram-bot-api.log \
  --verbosity=2
```

## Check

```bash
curl "http://127.0.0.1:8081/bot$TELEGRAM_BOT_TOKEN/getMe"
tail -f /var/log/telegram-bot-api.log
```

Then restart this bot:

```bash
cd /home/codex/telegram-downloader-bot
./stop.sh
./start.sh
./logs.sh
```


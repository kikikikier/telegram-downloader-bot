# Large File Methods

## 1. Local Bot API Server

Best for a normal Telegram bot that should send large files as the bot.

- Official `telegram-bot-api` server.
- Requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
- Run with `--local`.
- Upload limit becomes 2000 MB.
- Bot can pass `file://` paths instead of reading the whole file into the Python process.

This project supports it with:

```env
BOT_API_BASE=http://127.0.0.1:8081
BOT_API_LOCAL=1
BOT_MAX_MB=1990
```

## 2. MTProto Upload

Best when you do not want to run a local Bot API daemon.

- Uses Telethon.
- Requires `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
- Supports large uploads through Telegram's MTProto layer.
- This bot starts `mtproto_upload.py` for files over `BOT_MAX_MB`.

Config:

```env
TELEGRAM_API_ID=replace_me
TELEGRAM_API_HASH=replace_me
BOT_LARGE_UPLOAD_MODE=document
```

`document` is the safest default for large files. `both` sends a preview plus raw document but uploads the file twice.

## 3. Split Fallback

Last resort when single-file upload cannot be used.

- Uses ffmpeg segment muxer.
- Produces playable parts around `BOT_PART_MB`.
- Sends a concat list for reassembly.

Config:

```env
BOT_PART_MB=48
```

## 4. External File Host

Some public GitHub downloader bots upload files over 50 MB to an external host and return a link. This is simple, but it changes the privacy/security model and depends on a third-party service, so this project does not use it by default.


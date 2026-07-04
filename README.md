# Telegram Downloader Bot

Project id: `telegram-downloader-bot`

Example server path:

```text
/home/codex/telegram-downloader-bot
```

## Purpose

Telegram bot that downloads public media links from YouTube, TikTok, Pinterest, Instagram, VK Video, Rutube, and direct media URLs. It sends back a media preview plus the raw file/document.

Use it only for media you own, are allowed to download, or are otherwise permitted to process.

## Known Files

- `bot.py`
- `mtproto_upload.py`
- `requirements.txt`
- `start.sh`
- `stop.sh`
- `status.sh`
- `proxy-start.sh`
- `proxy-stop.sh`
- `README.md`

## Runtime

- Python venv.
- `yt-dlp`.
- `gallery-dl` for Instagram video first-pass downloads.
- `ffmpeg`.
- Local sing-box proxy on `127.0.0.1:18080`.
- Optional local Telegram Bot API server for files up to 2000 MB.
- Optional MTProto upload through Telethon for files larger than the cloud Bot API limit.

## Video Format

Video downloads prefer already-combined MP4 files with H.264/AAC codecs. This avoids slow server-side FFmpeg merging/transcoding and gives editing apps a more compatible file.

Instagram videos use `gallery-dl` first and fall back to `yt-dlp` if that route fails. This avoids the old Instagram DASH video+audio merge path when possible.

FFmpeg merge is disabled by default. Set `BOT_ENABLE_FFMPEG_MERGE=1` only if you want yt-dlp to fall back to separate video/audio streams and remux them into MP4.

## Last Known Status

- Bot running.
- Proxy running.
- Telegram direct access from VPS required proxy.

## Large Files

Upload route:

1. If the file fits `BOT_MAX_MB`, send through Bot API.
2. If `BOT_API_LOCAL=1` and `BOT_API_BASE` points to a local `telegram-bot-api --local` server, Bot API can upload up to 2000 MB using `file://` local paths.
3. If `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are configured, files over cloud Bot API limits are sent through MTProto/Telethon.
4. If MTProto is unavailable or fails, ffmpeg splits media into playable parts.

Important: cloud `api.telegram.org` still has the classic bot upload limit. For serious large files, use either local Bot API server or MTProto credentials.

## Server Logs

```bash
cd /home/codex/telegram-downloader-bot
./logs.sh
```

For more detail:

```bash
cd /home/codex/telegram-downloader-bot
echo 'BOT_LOG_LEVEL=DEBUG' >> .env
./stop.sh
./start.sh
./logs.sh
```

Quick diagnostics:

```bash
cd /home/codex/telegram-downloader-bot
chmod +x diagnose.sh logs.sh
./diagnose.sh
```

## Vibe Coding Note

This project is a full vibe coding artifact: human-directed, AI-assisted, iteratively debugged and shipped.

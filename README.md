# Telegram Downloader Bot

> Vibe coding note: this project is a full vibe coding artifact: human-directed, AI-assisted, iteratively debugged and shipped.

Telegram bot for downloading public media links, including video and image posts, and sending the result back as a Telegram media preview plus a raw file/document.

Use it only for media you own, are allowed to download, or are otherwise permitted to process.

## Supported Sources

- YouTube
- TikTok
- Pinterest
- Instagram
- VK Video
- Rutube
- Direct media URLs

## How It Works

- Uses `yt-dlp` for most supported platforms.
- Uses `gallery-dl` as the first download route for Instagram and TikTok media posts, with `yt-dlp` as a fallback.
- Sends image-only gallery/carousel posts as Telegram media groups, capped at 10 images per album message.
- Prefers already-combined MP4 video with H.264/AAC codecs when available.
- Keeps FFmpeg merging disabled by default to avoid slow server-side video processing.
- Can use an HTTP/SOCKS proxy for Telegram, yt-dlp, gallery-dl, direct media requests, and MTProto uploads.

## Video Format

Video downloads prefer already-combined MP4 files with H.264/AAC codecs. This avoids slow server-side FFmpeg merging/transcoding and gives editing apps a more compatible file.

Instagram videos use `gallery-dl` first and fall back to `yt-dlp` if that route fails. This avoids the old Instagram DASH video+audio merge path when possible.

FFmpeg merge is disabled by default. Set `BOT_ENABLE_FFMPEG_MERGE=1` only if you want yt-dlp to fall back to separate video/audio streams and remux them into MP4.

## Requirements

- Python 3.10+
- Python packages from `requirements.txt`
- Optional FFmpeg for audio extraction or explicit yt-dlp merge fallback
- Optional local Telegram Bot API server for larger bot uploads
- Optional Telegram API credentials for MTProto uploads through Telethon

## Configuration

Create a local `.env` from `.env.example` and set at least:

```env
TELEGRAM_BOT_TOKEN=replace_me
```

Useful optional settings:

```env
BOT_YTDLP_PROXY=http://127.0.0.1:PORT
BOT_GALLERY_DL_PROXY=http://127.0.0.1:PORT
BOT_TELEGRAM_PROXY=http://127.0.0.1:PORT
BOT_ENABLE_FFMPEG_MERGE=0
BOT_MAX_MB=49
BOT_LARGE_UPLOAD_MODE=document
```

## Large Files

Upload route:

1. If the file fits `BOT_MAX_MB`, send through Bot API.
2. If `BOT_API_LOCAL=1` and `BOT_API_BASE` points to a local `telegram-bot-api --local` server, Bot API can upload up to 2000 MB using `file://` local paths.
3. If `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are configured, files over cloud Bot API limits are sent through MTProto/Telethon with retry attempts controlled by `BOT_MTPROTO_RETRIES`.
4. If no single-file large upload route is configured, the bot fails the job clearly instead of splitting the media into parts.

Cloud `api.telegram.org` still has the classic bot upload limit. For serious large files, use either a local Bot API server or MTProto credentials.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python bot.py
```

The helper scripts `start.sh`, `stop.sh`, `status.sh`, and `logs.sh` are optional convenience wrappers for Unix-like environments.

## Test

```bash
python -m unittest test_bot.py
```

## Related Docs

- `features.md`
- `large-file-methods.md`
- `local-bot-api-server.md`

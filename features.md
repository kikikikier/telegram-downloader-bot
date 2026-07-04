# Features

## Download Sources

- YouTube.
- TikTok.
- Pinterest.
- Instagram.
- Direct media URLs.

## Current Behavior

- `/start` response is intentionally short/weird: `Пришли ссылку на публичное медиа. Ожидайте, не верьте дверным ручкам...`
- Instagram has audio/video buttons.
- YouTube quality options are probed with `yt-dlp --dump-single-json`.
- YouTube buttons may include `144p`, `240p`, `360p`, `480p`, `720p`, `1080p`, `1440p`, `2160p`.
- Audio extraction uses ffmpeg/yt-dlp.
- Default audio bitrate is around `96K`.
- Temp files are deleted after sending.
- Sends media preview and raw file.

## Large Files

Current intended flow:

- Use MTProto upload via Telethon when credentials are configured.
- Fall back to ffmpeg segmenting into playable parts if MTProto is unavailable.

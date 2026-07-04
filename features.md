# Features

## Download Sources

- YouTube.
- TikTok.
- Pinterest.
- Instagram.
- VK Video.
- Rutube.
- Direct media URLs.

## Video Downloads

- The bot prefers already-combined MP4 files when the source provides them.
- The preferred video compatibility target is H.264 video with AAC audio.
- Instagram videos use `gallery-dl` first, then `yt-dlp` as a fallback.
- YouTube quality options are probed with `yt-dlp --dump-single-json`.
- YouTube buttons may include `144p`, `240p`, `360p`, `480p`, `720p`, `1080p`, `1440p`, `2160p`.

## Audio Downloads

- Audio extraction uses `yt-dlp` and FFmpeg when needed.
- Default audio bitrate is around `96K`.

## Sending Results

- Sends a Telegram media preview when practical.
- Sends the raw file/document as the reliable final artifact.
- Temporary files are cleaned up after the job finishes.

## Large Files

Supported routes:

- Use the regular Bot API for files that fit the configured bot limit.
- Use a local Telegram Bot API server when configured.
- Use MTProto upload via Telethon when credentials are configured.
- Fall back to FFmpeg segmenting into playable parts if MTProto is unavailable.

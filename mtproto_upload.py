#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
import time
import urllib.parse
from pathlib import Path

import socks
from telethon import TelegramClient


def main() -> None:
    args = parse_args()
    asyncio.run(upload(args))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chat-id", required=True, type=int)
    parser.add_argument("--path", required=True)
    parser.add_argument("--caption", default="")
    parser.add_argument("--mode", choices=("media", "document", "both"), default="both")
    return parser.parse_args()


async def upload(args: argparse.Namespace) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    api_id = os.environ.get("TELEGRAM_API_ID", "").strip() or os.environ.get("APP_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip() or os.environ.get("APP_HASH", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if not api_id or not api_hash:
        raise SystemExit("TELEGRAM_API_ID and TELEGRAM_API_HASH are required for MTProto uploads")

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"file does not exist: {path}")

    session_path = Path(os.environ.get("BOT_MTPROTO_SESSION", "mtproto_bot")).resolve()
    client = TelegramClient(
        str(session_path),
        int(api_id),
        api_hash,
        proxy=parse_proxy(),
    )
    await client.start(bot_token=token)
    try:
        if args.mode in ("media", "both"):
            print(f"MTProto media upload start: {path.name} ({human_size(path.stat().st_size)})", flush=True)
            await client.send_file(
                args.chat_id,
                str(path),
                caption=args.caption[:1024],
                force_document=False,
                supports_streaming=is_video(path),
                progress_callback=progress_logger("media"),
            )
            print("MTProto media upload done", flush=True)
        if args.mode in ("document", "both"):
            print(f"MTProto document upload start: {path.name} ({human_size(path.stat().st_size)})", flush=True)
            await client.send_file(
                args.chat_id,
                str(path),
                caption=args.caption[:1024],
                force_document=True,
                progress_callback=progress_logger("document"),
            )
            print("MTProto document upload done", flush=True)
    finally:
        await client.disconnect()


def parse_proxy():
    raw = (
        os.environ.get("BOT_MTPROTO_PROXY", "").strip()
        or os.environ.get("BOT_TELEGRAM_PROXY", "").strip()
    )
    if not raw:
        return None

    parsed = urllib.parse.urlparse(raw)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None

    scheme = parsed.scheme.lower()
    if scheme in ("socks", "socks5", "socks5h"):
        proxy_type = socks.SOCKS5
    elif scheme == "socks4":
        proxy_type = socks.SOCKS4
    elif scheme in ("http", "https"):
        proxy_type = socks.HTTP
    else:
        proxy_type = socks.SOCKS5

    username = urllib.parse.unquote(parsed.username) if parsed.username else None
    password = urllib.parse.unquote(parsed.password) if parsed.password else None
    return (proxy_type, host, port, True, username, password)


def is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".m4v", ".mov", ".webm", ".mkv"}


def human_size(value: int) -> str:
    return f"{value / (1024 * 1024):.1f} MB"


def progress_logger(label: str):
    last = {"time": 0.0, "sent": 0}

    def callback(sent: int, total: int) -> None:
        now = time.monotonic()
        if sent < total and now - last["time"] < 10:
            return
        last["time"] = now
        last["sent"] = sent
        percent = (sent / total * 100) if total else 0
        print(f"MTProto {label} progress: {human_size(sent)} / {human_size(total)} ({percent:.1f}%)", flush=True)

    return callback


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise

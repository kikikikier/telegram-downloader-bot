#!/usr/bin/env python3
import collections
import json
import logging
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from replicas import ACCEPT_MESSAGES, DOWNLOADED_MESSAGES, FILE_READY_MESSAGES


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_api_base(token: str) -> str:
    raw = (
        os.environ.get("BOT_API_BASE", "").strip()
        or os.environ.get("TELEGRAM_BOT_API_BASE", "").strip()
    )
    if not raw:
        return f"https://api.telegram.org/bot{token}"

    raw = raw.rstrip("/")
    if "{token}" in raw:
        return raw.format(token=token).rstrip("/")
    if token and raw.endswith(f"/bot{token}"):
        return raw
    if raw.endswith("/bot"):
        return f"{raw}{token}"
    return f"{raw}/bot{token}"


TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API_BASE = build_api_base(TOKEN)
BOT_API_LOCAL = env_bool("BOT_API_LOCAL") or env_bool("BOT_API_LOCAL_MODE")
DEFAULT_MAX_MB = "1990" if BOT_API_LOCAL else "49"
MAX_MB = int(os.environ.get("BOT_MAX_MB", DEFAULT_MAX_MB))
MAX_BYTES = MAX_MB * 1024 * 1024
PREVIEW_MAX_MB = int(os.environ.get("BOT_PREVIEW_MAX_MB", "49"))
PREVIEW_MAX_BYTES = PREVIEW_MAX_MB * 1024 * 1024
DOWNLOAD_MAX_MB = int(os.environ.get("BOT_DOWNLOAD_MAX_MB", "0"))
DOWNLOAD_MAX_BYTES = DOWNLOAD_MAX_MB * 1024 * 1024 if DOWNLOAD_MAX_MB else None
DOWNLOAD_TIMEOUT = int(os.environ.get("BOT_DOWNLOAD_TIMEOUT", "900"))
PROBE_TIMEOUT = int(os.environ.get("BOT_PROBE_TIMEOUT", "90"))
AUDIO_BITRATE = os.environ.get("BOT_AUDIO_BITRATE", "96K").strip() or "96K"
BOT_ENABLE_FFMPEG_MERGE = env_bool("BOT_ENABLE_FFMPEG_MERGE", True)
PROGRESS_MIN_INTERVAL_SECONDS = float(os.environ.get("BOT_PROGRESS_MIN_INTERVAL_SECONDS", "3"))
PROGRESS_BAR_WIDTH = 12
TMP_ROOT = Path(os.environ.get("BOT_TMP_DIR", tempfile.gettempdir())) / "telegram-downloader-bot"
CLEANUP_DELAY_SECONDS = int(os.environ.get("BOT_CLEANUP_DELAY_SECONDS", "60"))
CLEANUP_SWEEP_SECONDS = int(os.environ.get("BOT_CLEANUP_SWEEP_SECONDS", "30"))
TELEGRAM_PROXY = os.environ.get("BOT_TELEGRAM_PROXY", "").strip()
ADMIN_CHAT_ID = os.environ.get("BOT_ADMIN_CHAT_ID", "").strip()
TELEGRAM_API_ID = os.environ.get("TELEGRAM_API_ID", "").strip() or os.environ.get("APP_ID", "").strip()
TELEGRAM_API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip() or os.environ.get("APP_HASH", "").strip()
UPLOAD_TIMEOUT = int(os.environ.get("BOT_UPLOAD_TIMEOUT", "7200"))
MTPROTO_RETRIES = max(1, int(os.environ.get("BOT_MTPROTO_RETRIES", "3")))
MTPROTO_RETRY_DELAY_SECONDS = float(os.environ.get("BOT_MTPROTO_RETRY_DELAY_SECONDS", "5"))
MTPROTO_MAX_MB = int(os.environ.get("BOT_MTPROTO_MAX_MB", "2000"))
MTPROTO_MAX_BYTES = MTPROTO_MAX_MB * 1024 * 1024
LARGE_UPLOAD_MODE = os.environ.get("BOT_LARGE_UPLOAD_MODE", "document").strip().lower()
if LARGE_UPLOAD_MODE not in {"media", "document", "both"}:
    LARGE_UPLOAD_MODE = "document"
LOG_LEVEL = os.environ.get("BOT_LOG_LEVEL", "INFO").strip().upper() or "INFO"
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("telegram-downloader-bot")
URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
YTDLP_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
FFMPEG_OUT_TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
DIRECT_MEDIA_RE = re.compile(
    r"\.(mp4|webm|mov|m4v|jpg|jpeg|png|gif|webp|mp3|m4a|aac|wav|flac|ogg|opus)(?:[?#].*)?$",
    re.IGNORECASE,
)
MEDIA_SUFFIXES = {
    ".mp4",
    ".webm",
    ".mov",
    ".m4v",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",
}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
PHOTO_ALBUM_SUFFIXES = {".jpg", ".jpeg", ".png"}
MEDIA_GROUP_LIMIT = 10

SUPPORTED_HOST_HINTS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "pinterest.com",
    "pin.it",
    "instagram.com",
    "instagr.am",
    "vk.com",
    "vk.ru",
    "vkvideo.ru",
    "rutube.ru",
    "rutube.com",
    "rutube.me",
)

CHOICE_HOST_HINTS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "instagram.com",
    "instagr.am",
)

VIDEO_QUALITIES = ("144", "240", "360", "480", "720", "1080", "1440", "2160", "4320", "best")
PENDING_TTL_SECONDS = 60 * 60
PENDING_DOWNLOADS: dict[str, dict] = {}
CLEANUP_THREAD_STARTED = False

START_TEXT = (
    "Пришли ссылку на публичное медиа. Ожидайте, не верьте дверным ручкам. "
    "Используй свои материалы или то, что тебе разрешено скачивать."
)
NO_URL_MESSAGES = (
    "Пришли ссылку на публичное медиа. Скоро к вам придёт благословение.",
    "Мне нужна ссылка. Дверные ручки без ссылки молчат.",
    "Киньте ссылку, и благодать начнёт шевелиться в коридоре.",
)
UNKNOWN_URL_MESSAGES = (
    "Пока не узнаю эту ссылку. Она постучала не в ту дверь.",
    "Эта ссылка выглядит как странный ключ. Попробуйте другую.",
    "Дверные ручки совещались и не поняли этот адрес.",
)
PROBE_MESSAGES = (
    "Смотрю доступные качества. Не трогайте дверные ручки.",
    "Проверяю, в каком виде благодать согласна прийти.",
    "Ссылка ушла на осмотр. В коридоре тихо, но работа идёт.",
)
PROBE_FAIL_MESSAGES = (
    "Не получилось рассмотреть варианты. Дверные ручки делают вид, что они не при делах.",
    "Качества спрятались в шкафу. Попробуйте ещё раз чуть позже.",
)
OPTIONS_PROMPT_MESSAGES = (
    "Что достать из ссылки? Выберите форму благословения.",
    "В каком виде принести благодать?",
    "Ссылка открылась. Выберите, что вынести из коридора.",
)
_LEGACY_ACCEPT_MESSAGES = (
    "Принял ссылку. Ожидайте. Не верьте дверным ручкам.",
    "Ссылка у меня. Поставил её на тихий огонь благодати.",
    "Забрал ссылку в коридор. Дверные ручки под наблюдением.",
)
SELECTED_MESSAGES = (
    "Выбрано: {label}. Скоро к вам придёт благословение.",
    "{label}: принято. Коридор уже шуршит.",
    "{label}: понёс. Дверные ручки предупреждены.",
)
_LEGACY_DOWNLOADED_MESSAGES = (
    "Файл добрался до прихожей. Отправляю дальше.",
    "Сверток найден. Благодать идёт по коридору.",
    "Добыча у меня. Сейчас передам, пока ручки не передумали.",
)
LARGE_SEND_MESSAGES = (
    "Несу большим коридором. Это может занять немного времени.",
    "Благодать крупная, но дверные ручки уже предупреждены.",
    "Сверток тяжёлый. Иду медленно, но уверенно.",
)
PREVIEW_FAIL_MESSAGES = (
    "Превью спряталось под ковёр. Отправляю как файл.",
    "Картинка для витрины не вышла. Сам сверток цел.",
    "Обложка не захотела показываться. Несу файл напрямую.",
)
NOT_FOUND_MESSAGES = (
    "Ссылка открылась пустой комнатой. Нечего вынести.",
    "Внутри не нашёл сверток. Дверные ручки разводят руками.",
)
TIMEOUT_MESSAGES = (
    "Ожидание растаяло в коридоре. Попробуйте ещё раз позже.",
    "Слишком долго шло. Дверные ручки начали делать вид, что спят.",
)
ERROR_MESSAGES = (
    "Не получилось достать это медиа. Дверные ручки делают вид, что ничего не знают.",
    "Ссылка сопротивлялась сильнее обычного. Попробуйте ещё раз позже.",
    "Благодать застряла по дороге. Я записал следы в журнал.",
)
_LEGACY_DOCUMENT_CAPTIONS = (
    "Вот он. Не верьте дверным ручкам.",
    "Доставлено. Благодать слегка помята, но жива.",
    "Сверток прибыл.",
)
_LEGACY_DOCUMENT_AFTER_PREVIEW_CAPTIONS = (
    "И ещё чистым файлом, чтобы благодать не мялась.",
    "Дубль без витрины. На всякий случай.",
    "Тот же сверток, только без церемоний.",
)


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in the environment.")
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    start_cleanup_worker()
    logger.info(
        "boot config api_base=%s local_bot_api=%s max_mb=%s preview_max_mb=%s mtproto=%s mtproto_max_mb=%s large_mode=%s cleanup_delay=%ss tmp=%s",
        redacted_api_base(),
        BOT_API_LOCAL,
        MAX_MB,
        PREVIEW_MAX_MB,
        mtproto_upload_available(),
        MTPROTO_MAX_MB,
        LARGE_UPLOAD_MODE,
        CLEANUP_DELAY_SECONDS,
        TMP_ROOT,
    )
    send_startup_log()
    offset = None
    while True:
        try:
            updates = api_json("getUpdates", {"timeout": 30, "offset": offset})
            for update in updates.get("result", []):
                offset = update["update_id"] + 1
                handle_update(update)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.exception("poll error: %s", short_error(exc))
            time.sleep(3)


def send_startup_log() -> None:
    try:
        me = api_json("getMe").get("result", {})
        username = me.get("username", "unknown")
        set_bot_commands()
        logger.info("Bot started: @%s", username)
        if ADMIN_CHAT_ID:
            send_message(int(ADMIN_CHAT_ID), f"Бот запущен: @{username}. Можно присылать ссылки.")
    except Exception as exc:
        logger.warning("startup check failed, will keep retrying: %s", short_error(exc))


def set_bot_commands() -> None:
    commands = [
        {"command": "start", "description": "Что умеет бот"},
        {"command": "help", "description": "Помощь"},
    ]
    api_json("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})


def handle_update(update: dict) -> None:
    if "callback_query" in update:
        handle_callback_query(update["callback_query"])
        return

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or message.get("caption") or ""
    if not chat_id:
        return

    if text.startswith("/start") or text.startswith("/help"):
        send_message(chat_id, START_TEXT)
        return

    urls = extract_urls(text)
    if not urls:
        send_message(chat_id, pick(NO_URL_MESSAGES))
        return

    for url in urls[:3]:
        if not is_supported_url(url):
            send_message(chat_id, f"{pick(UNKNOWN_URL_MESSAGES)}\n{url}")
            continue
        if should_offer_download_options(url):
            send_download_options(chat_id, url)
        else:
            handle_url(chat_id, url)


def handle_callback_query(callback: dict) -> None:
    callback_id = callback.get("id")
    if callback_id:
        answer_callback_query(callback_id)

    data = callback.get("data") or ""
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")

    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "dl" or not chat_id:
        return

    prune_pending_downloads()
    token = parts[1]
    entry = PENDING_DOWNLOADS.get(token)
    if not entry:
        send_message(chat_id, "Кнопка устарела. Пришли ссылку ещё раз.")
        return

    if int(entry["chat_id"]) != int(chat_id):
        send_message(chat_id, "Эта кнопка от другой беседы. Не верьте дверным ручкам.")
        return

    if parts[2] == "audio":
        media_mode = "audio"
        quality = None
    elif parts[2] == "video":
        media_mode = "video"
        quality = parts[3] if len(parts) >= 4 else None
    else:
        send_message(chat_id, "Не понял формат выбора. Пришли ссылку ещё раз.")
        return

    choice_key = "audio" if media_mode == "audio" else f"video:{quality or 'default'}"
    choice = entry.get("choices", {}).get(choice_key, {})
    estimated_bytes = choice.get("estimated_bytes")
    label = describe_download_choice(media_mode, quality)
    if message_id:
        edit_message_text(chat_id, message_id, pick(SELECTED_MESSAGES).format(label=label))
    handle_url(chat_id, entry["url"], media_mode=media_mode, quality=quality)


def extract_urls(text: str) -> list[str]:
    urls = []
    for match in URL_RE.findall(text):
        url = match.rstrip(".,;:!?)]}>")
        urls.append(url)
    return urls


def is_supported_url(url: str) -> bool:
    if DIRECT_MEDIA_RE.search(url):
        return True
    return url_host_matches(url, SUPPORTED_HOST_HINTS)


def should_offer_download_options(url: str) -> bool:
    if DIRECT_MEDIA_RE.search(url):
        return False
    return url_host_matches(url, CHOICE_HOST_HINTS)


def url_host_matches(url: str, hints: tuple[str, ...]) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == item or host.endswith("." + item) for item in hints)


def is_youtube_url(url: str) -> bool:
    return url_host_matches(url, ("youtube.com", "youtu.be", "youtube-nocookie.com"))


def is_vk_video_url(url: str) -> bool:
    return url_host_matches(url, ("vk.com", "vkvideo.ru"))


def is_instagram_url(url: str) -> bool:
    return url_host_matches(url, ("instagram.com", "instagr.am"))


def is_instagram_reel_url(url: str) -> bool:
    if not is_instagram_url(url):
        return False
    path = urllib.parse.urlparse(url).path.lower()
    return "/reel/" in path or "/reels/" in path


def is_tiktok_url(url: str) -> bool:
    return url_host_matches(url, ("tiktok.com", "tiktokv.com", "vm.tiktok.com", "vt.tiktok.com"))


def is_gallery_first_url(url: str) -> bool:
    return (is_instagram_url(url) and not is_instagram_reel_url(url)) or is_tiktok_url(url)


def send_download_options(chat_id: int, url: str) -> None:
    prune_pending_downloads()
    token = uuid.uuid4().hex[:12]
    if is_youtube_url(url):
        send_message(chat_id, pick(PROBE_MESSAGES))
        choices = {}
        try:
            options, audio_estimate = get_youtube_download_options(url)
        except Exception as exc:
            logger.exception("quality probe failed url=%s error=%s", safe_log_url(url), short_error(exc))
            send_message(chat_id, pick(PROBE_FAIL_MESSAGES))
            return

        choices["audio"] = {"estimated_bytes": audio_estimate}
        video_buttons = []
        for option in options:
            height = option["height"]
            choices[f"video:{height}"] = {"estimated_bytes": option.get("estimated_bytes")}
            video_buttons.append({
                "text": quality_button_label(height, option.get("estimated_bytes")),
                "callback_data": f"dl:{token}:video:{height}",
            })
        if not video_buttons:
            video_buttons = [{"text": "Видео лучшее", "callback_data": f"dl:{token}:video:best"}]
            choices["video:best"] = {}

        keyboard = {
            "inline_keyboard": [
                [{"text": audio_button_label(audio_estimate), "callback_data": f"dl:{token}:audio"}],
                *chunk_buttons(video_buttons, 2),
            ]
        }
    elif is_instagram_url(url):
        choices = {"audio": {}, "video:default": {}}
        keyboard = {
            "inline_keyboard": [
                [{"text": "Аудио MP3", "callback_data": f"dl:{token}:audio"}],
                [{"text": "Видео", "callback_data": f"dl:{token}:video"}],
            ]
        }
    else:
        choices = {"audio": {}, "video:default": {}}
        keyboard = {
            "inline_keyboard": [
                [{"text": "Аудио MP3", "callback_data": f"dl:{token}:audio"}],
                [{"text": "Видео", "callback_data": f"dl:{token}:video"}],
            ]
        }
    PENDING_DOWNLOADS[token] = {
        "chat_id": chat_id,
        "url": url,
        "created_at": time.time(),
        "choices": choices,
    }
    send_message(
        chat_id,
        pick(OPTIONS_PROMPT_MESSAGES),
        reply_markup=keyboard,
    )


def prune_pending_downloads() -> None:
    expires_before = time.time() - PENDING_TTL_SECONDS
    stale_tokens = [
        token for token, entry in PENDING_DOWNLOADS.items()
        if entry.get("created_at", 0) < expires_before
    ]
    for token in stale_tokens:
        PENDING_DOWNLOADS.pop(token, None)


def describe_download_choice(media_mode: str, quality: str | None) -> str:
    if media_mode == "audio":
        return "аудио MP3"
    if not quality:
        return "видео"
    if quality == "best":
        return "видео в лучшем доступном качестве"
    return f"видео {quality}p"


def get_youtube_download_options(url: str) -> tuple[list[dict], int | None]:
    info = probe_ytdlp_info(url)
    formats = info.get("formats") or []
    duration = info.get("duration")
    audio_estimate = estimate_best_audio_bytes(formats, duration)
    allow_video_only = video_ffmpeg_merge_enabled()

    by_height: dict[int, int | None] = {}
    for fmt in formats:
        if fmt.get("vcodec") in (None, "none"):
            continue
        if not allow_video_only and not is_progressive_mp4_video_format(fmt):
            continue
        height = fmt.get("height")
        if not isinstance(height, int) or height <= 0:
            continue
        estimated = estimate_format_bytes(fmt, duration)
        if fmt.get("acodec") in (None, "none") and audio_estimate:
            estimated = (estimated or 0) + audio_estimate if estimated else None
        current = by_height.get(height)
        by_height[height] = max_optional_size(current, estimated)

    options = [
        {"height": height, "estimated_bytes": by_height[height]}
        for height in sorted(by_height)
    ]
    return options, audio_estimate


def probe_ytdlp_info(url: str) -> dict:
    cmd = build_ytdlp_command([
        "--no-playlist",
        "--dump-single-json",
        "--no-warnings",
        url,
    ], url=url)
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=PROBE_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "yt-dlp probe failed")
    return json.loads(result.stdout)


def estimate_best_audio_bytes(formats: list[dict], duration: int | float | None) -> int | None:
    if duration:
        bitrate = parse_audio_bitrate(AUDIO_BITRATE)
        return int(duration * bitrate * 1000 / 8)
    estimates = [
        estimate_format_bytes(fmt, duration)
        for fmt in formats
        if fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none")
    ]
    estimates = [item for item in estimates if item]
    if estimates:
        return max(estimates)
    return None


def estimate_format_bytes(fmt: dict, duration: int | float | None) -> int | None:
    for key in ("filesize", "filesize_approx"):
        value = fmt.get(key)
        if isinstance(value, int) and value > 0:
            return value
    bitrate = fmt.get("tbr") or fmt.get("vbr") or fmt.get("abr")
    if duration and isinstance(bitrate, (int, float)) and bitrate > 0:
        return int(duration * bitrate * 1000 / 8)
    return None


def is_single_file_video_candidate(fmt: dict) -> bool:
    format_id = fmt.get("format_id")
    if not isinstance(format_id, str) or not format_id:
        return False
    if "+" in format_id:
        return False
    if fmt.get("vcodec") == "none":
        return False
    if fmt.get("acodec") == "none":
        return False
    height = fmt.get("height")
    return isinstance(height, int) and height > 0


def select_upload_safe_video_format_id(
    info: dict,
    quality: str | None,
    max_filesize_bytes: int,
) -> str | None:
    formats = info.get("formats") or []
    duration = info.get("duration")
    max_height = quality_max_height(quality)
    candidates = []

    for fmt in formats:
        if not is_single_file_video_candidate(fmt):
            continue
        height = fmt.get("height")
        if max_height and height > max_height:
            continue
        estimated = estimate_format_bytes(fmt, duration)
        if not estimated or estimated > max_filesize_bytes:
            continue
        tbr = fmt.get("tbr")
        candidates.append((
            height,
            float(tbr) if isinstance(tbr, (int, float)) else 0.0,
            estimated,
            fmt["format_id"],
        ))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][3]


def probe_upload_safe_video_format_id(
    url: str,
    quality: str | None,
    max_filesize_bytes: int,
) -> str | None:
    info = probe_ytdlp_info(url)
    return select_upload_safe_video_format_id(info, quality, max_filesize_bytes)


def parse_audio_bitrate(value: str) -> int:
    match = re.search(r"(\d+)", value)
    if not match:
        return 96
    return max(32, min(320, int(match.group(1))))


def max_optional_size(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def min_optional_size(a: int | None, b: int | None) -> int | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def video_ffmpeg_merge_enabled() -> bool:
    return BOT_ENABLE_FFMPEG_MERGE and bool(shutil.which("ffmpeg"))


def mtproto_upload_available() -> bool:
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH)


def large_upload_route_available() -> bool:
    return BOT_API_LOCAL or mtproto_upload_available()


def effective_download_limit_bytes() -> int | None:
    limit = DOWNLOAD_MAX_BYTES
    if not large_upload_route_available():
        limit = min_optional_size(limit, MAX_BYTES)
    return limit


def cli_size_arg(limit_bytes: int) -> str:
    mb = 1024 * 1024
    if limit_bytes % mb == 0:
        return f"{limit_bytes // mb}M"
    return str(limit_bytes)


def quality_max_height(quality: str | None) -> int | None:
    if not quality or quality == "best":
        return None
    if not str(quality).isdigit():
        return None
    return int(quality)


def height_filter(max_height: int | None) -> str:
    return f"[height<={max_height}]" if max_height else ""


def exact_height_filter(height: int | None) -> str:
    return f"[height={height}]" if height else ""


def progressive_mp4_selectors(max_height: int | None) -> list[str]:
    height = height_filter(max_height)
    return [
        f"b[ext=mp4][vcodec^=avc1][acodec^=mp4a]{height}",
        f"b[ext=mp4][vcodec^=avc1]{height}",
        f"b[ext=mp4][vcodec*=h264][acodec^=mp4a]{height}",
        f"b[ext=mp4][vcodec*=h264]{height}",
        f"b[ext=mp4][acodec^=mp4a]{height}",
        f"b[ext=mp4]{height}",
    ]


def merged_mp4_selectors(max_height: int | None) -> list[str]:
    height = height_filter(max_height)
    selectors = []
    if max_height:
        exact_height = exact_height_filter(max_height)
        selectors.extend([
            f"bv*[ext=mp4]{exact_height}+ba[ext=m4a]",
            f"bv*{exact_height}+ba[ext=m4a]",
            f"bv*{exact_height}+ba",
        ])
    selectors.extend([
        f"bv*[ext=mp4]{height}+ba[ext=m4a]",
        f"bv*{height}+ba[ext=m4a]",
        f"bv*{height}+ba",
        f"bv*[ext=mp4][vcodec^=avc1]{height}+ba[ext=m4a]",
        f"bv*[ext=mp4][vcodec*=h264]{height}+ba[ext=m4a]",
    ])
    return selectors


def filesize_limited_selectors(selectors: list[str], max_filesize_bytes: int) -> list[str]:
    limited = []
    for selector in selectors:
        limited.extend([
            f"{selector}[filesize<={max_filesize_bytes}]",
            f"{selector}[filesize_approx<={max_filesize_bytes}]",
        ])
    return limited


def video_format_selector(
    quality: str | None,
    allow_merge: bool = False,
    max_filesize_bytes: int | None = None,
) -> str:
    max_height = quality_max_height(quality)
    if allow_merge:
        selectors = merged_mp4_selectors(max_height) + progressive_mp4_selectors(max_height)
    else:
        selectors = progressive_mp4_selectors(max_height)
    fallback_selectors = [f"best{height_filter(max_height)}"]
    if max_height:
        fallback_selectors.append("best")
    selectors.extend(fallback_selectors)
    if max_filesize_bytes:
        selectors = filesize_limited_selectors(selectors, max_filesize_bytes) + fallback_selectors
    return "/".join(selectors)


def is_progressive_mp4_video_format(fmt: dict) -> bool:
    if fmt.get("ext") != "mp4":
        return False
    if fmt.get("vcodec") in (None, "none"):
        return False
    return fmt.get("acodec") not in (None, "none")


def quality_button_label(height: int, estimated_bytes: int | None) -> str:
    label = f"{height}p"
    if height >= 2160:
        label += " 4K"
    elif height >= 1440:
        label += " 2K"
    return label


def audio_button_label(estimated_bytes: int | None) -> str:
    return "Аудио MP3"


def chunk_buttons(buttons: list[dict], size: int) -> list[list[dict]]:
    return [buttons[index:index + size] for index in range(0, len(buttons), size)]


def pick(messages: tuple[str, ...]) -> str:
    return random.choice(messages)


def clamp_percent(percent: float) -> float:
    return max(0.0, min(100.0, percent))


def progress_bar(percent: float, width: int = PROGRESS_BAR_WIDTH) -> str:
    percent = clamp_percent(percent)
    filled = int(round(width * percent / 100))
    return "[" + "#" * filled + "-" * (width - filled) + f"] {percent:.0f}%"


def progress_text(label: str, percent: float) -> str:
    return f"{label}\n{progress_bar(percent)}"


def parse_ytdlp_progress_percent(line: str) -> float | None:
    match = YTDLP_PROGRESS_RE.search(line)
    if not match:
        return None
    return clamp_percent(float(match.group(1)))


def parse_ffmpeg_out_time_percent(line: str, duration: float | None) -> float | None:
    if not duration or duration <= 0:
        return None
    if line.strip() == "progress=end":
        return 100.0
    match = FFMPEG_OUT_TIME_RE.search(line)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    elapsed = hours * 3600 + minutes * 60 + seconds
    return clamp_percent(elapsed * 100 / duration)


class DownloadProgressReporter:
    def __init__(
        self,
        chat_id: int,
        message_id: int,
        label: str = "Скачиваю",
        min_interval: float | None = None,
        clock=None,
        edit_func=None,
    ):
        self.chat_id = chat_id
        self.message_id = message_id
        self.label = label
        self.min_interval = PROGRESS_MIN_INTERVAL_SECONDS if min_interval is None else min_interval
        self.clock = clock or time.monotonic
        self.edit_func = edit_func
        self.last_update_at = -self.min_interval
        self.last_rounded: int | None = None
        self.stage_label = label
        self.stage_start = 0.0
        self.stage_end = 100.0

    def update(self, percent: float, label: str | None = None, force: bool = False) -> None:
        percent = clamp_percent(percent)
        rounded = int(round(percent))
        now = self.clock()
        if not force and rounded == self.last_rounded:
            return
        if not force and percent < 100 and now - self.last_update_at < self.min_interval:
            return

        text = progress_text(label or self.label, percent)
        try:
            edit = self.edit_func or edit_message_text
            edit(self.chat_id, self.message_id, text)
            self.last_update_at = now
            self.last_rounded = rounded
        except Exception as exc:
            logger.warning("progress update failed: %s", short_error(exc))

    def update_bytes(self, written: int, total: int | None) -> None:
        if total and total > 0:
            self.update_stage_percent(written * 100 / total)

    def set_stage(self, label: str, start: float, end: float) -> None:
        start = clamp_percent(start)
        end = clamp_percent(end)
        if end < start:
            start, end = end, start
        self.stage_label = label
        self.stage_start = start
        self.stage_end = end
        self.update(start, label=label, force=True)

    def update_stage_percent(self, percent: float, label: str | None = None, force: bool = False) -> None:
        percent = clamp_percent(percent)
        span = self.stage_end - self.stage_start
        self.update(self.stage_start + span * percent / 100, label=label or self.stage_label, force=force)

    def handle_ytdlp_line(self, line: str) -> None:
        percent = parse_ytdlp_progress_percent(line)
        if percent is not None:
            self.update_stage_percent(percent)

    def handle_gallery_line(self, line: str) -> None:
        percent = parse_ytdlp_progress_percent(line)
        if percent is None:
            match = PERCENT_RE.search(line)
            percent = float(match.group(1)) if match else None
        if percent is not None:
            self.update_stage_percent(percent)

    def handle_mtproto_line(self, line: str) -> None:
        match = PERCENT_RE.search(line)
        if match:
            self.update_stage_percent(float(match.group(1)))

    def handle_ffmpeg_line(self, line: str, duration: float | None) -> None:
        percent = parse_ffmpeg_out_time_percent(line, duration)
        if percent is not None:
            self.update(percent, label="Готовлю файл")

    def finish(self) -> None:
        self.update(100, label="Готово", force=True)

    def fail(self) -> None:
        self.update(100, label="Не получилось", force=True)


def start_progress_message(chat_id: int, label: str = "Скачиваю") -> DownloadProgressReporter | None:
    try:
        payload = send_message(chat_id, progress_text(label, 0))
    except Exception as exc:
        logger.warning("could not start progress message: %s", short_error(exc))
        return None
    if not isinstance(payload, dict):
        return None
    message_id = payload.get("result", {}).get("message_id")
    if not isinstance(message_id, int):
        return None
    return DownloadProgressReporter(chat_id, message_id, label=label)



def start_cleanup_worker() -> None:
    global CLEANUP_THREAD_STARTED
    if CLEANUP_THREAD_STARTED:
        return
    CLEANUP_THREAD_STARTED = True
    cleanup_due_workdirs(reason="startup")

    def worker() -> None:
        while True:
            time.sleep(max(5, CLEANUP_SWEEP_SECONDS))
            cleanup_due_workdirs(reason="sweep")

    threading.Thread(target=worker, name="tmp-cleanup", daemon=True).start()


def mark_workdir_active(workdir: Path) -> None:
    payload = {
        "pid": os.getpid(),
        "created_at": time.time(),
    }
    try:
        (workdir / ".active").write_text(json.dumps(payload), encoding="utf-8")
    except Exception as exc:
        logger.warning("could not mark workdir active path=%s error=%s", workdir, short_error(exc))


def schedule_workdir_cleanup(workdir: Path, delay: int | None = None) -> None:
    delay = CLEANUP_DELAY_SECONDS if delay is None else delay
    delete_after = time.time() + max(0, delay)
    try:
        (workdir / ".active").unlink(missing_ok=True)
        (workdir / ".delete_after").write_text(str(delete_after), encoding="utf-8")
        logger.info("scheduled workdir cleanup path=%s delay=%ss", workdir, delay)
    except Exception as exc:
        logger.warning("could not schedule workdir cleanup path=%s error=%s", workdir, short_error(exc))

    threading.Thread(
        target=delayed_workdir_cleanup,
        args=(workdir, max(0, delay)),
        name=f"cleanup-{workdir.name[:8]}",
        daemon=True,
    ).start()


def delayed_workdir_cleanup(workdir: Path, delay: int) -> None:
    time.sleep(delay)
    remove_workdir_if_due(workdir, reason="delayed")


def cleanup_workdir_after_job(workdir: Path, reason: str = "job-finished") -> None:
    try:
        (workdir / ".active").unlink(missing_ok=True)
        (workdir / ".delete_after").unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("could not clear workdir markers path=%s error=%s", workdir, short_error(exc))
    force_remove_workdir(workdir, reason=reason)


def cleanup_due_workdirs(reason: str) -> None:
    try:
        workdirs = [path for path in TMP_ROOT.iterdir() if path.is_dir()]
    except FileNotFoundError:
        return
    except Exception as exc:
        logger.warning("could not scan tmp root path=%s error=%s", TMP_ROOT, short_error(exc))
        return

    for workdir in workdirs:
        remove_workdir_if_due(workdir, reason=reason)


def remove_workdir_if_due(workdir: Path, reason: str) -> None:
    now = time.time()
    delete_after_file = workdir / ".delete_after"
    active_file = workdir / ".active"

    if delete_after_file.exists():
        try:
            delete_after = float(delete_after_file.read_text(encoding="utf-8").strip())
        except Exception:
            delete_after = delete_after_file.stat().st_mtime + CLEANUP_DELAY_SECONDS
        if now < delete_after:
            return
        force_remove_workdir(workdir, reason=reason)
        return

    if active_file.exists():
        active_pid = read_active_pid(active_file)
        if active_pid == os.getpid():
            return
        if active_pid and is_pid_running(active_pid):
            return
        if now < active_file.stat().st_mtime + CLEANUP_DELAY_SECONDS:
            return
        logger.warning("cleaning orphaned active workdir path=%s pid=%s reason=%s", workdir, active_pid, reason)
        force_remove_workdir(workdir, reason=reason)
        return

    try:
        modified_at = workdir.stat().st_mtime
    except FileNotFoundError:
        return
    if now >= modified_at + CLEANUP_DELAY_SECONDS:
        logger.warning("cleaning unmarked workdir path=%s reason=%s", workdir, reason)
        force_remove_workdir(workdir, reason=reason)


def read_active_pid(active_file: Path) -> int | None:
    try:
        payload = json.loads(active_file.read_text(encoding="utf-8"))
        pid = payload.get("pid")
        return int(pid) if pid else None
    except Exception:
        return None


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def force_remove_workdir(workdir: Path, reason: str) -> None:
    for attempt in range(1, 6):
        try:
            shutil.rmtree(workdir)
            logger.info("removed workdir path=%s reason=%s attempt=%s", workdir, reason, attempt)
            return
        except FileNotFoundError:
            return
        except Exception as exc:
            logger.warning(
                "workdir cleanup failed path=%s reason=%s attempt=%s error=%s",
                workdir,
                reason,
                attempt,
                short_error(exc),
            )
            time.sleep(1)
    logger.error("workdir cleanup gave up path=%s reason=%s", workdir, reason)


def handle_url(chat_id: int, url: str, media_mode: str = "video", quality: str | None = "720") -> None:
    workdir = TMP_ROOT / uuid.uuid4().hex
    started_at = time.monotonic()
    progress = None
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        mark_workdir_active(workdir)
        logger.info(
            "job start chat_id=%s mode=%s quality=%s url=%s workdir=%s",
            chat_id,
            media_mode,
            quality,
            safe_log_url(url),
            workdir,
        )
        send_message(chat_id, pick(ACCEPT_MESSAGES))
        progress = start_progress_message(chat_id, label="Готовлю ссылку")
        if progress:
            progress.set_stage("Скачиваю", 5, 70)
        media_paths = download_media_files_for_url(
            url,
            workdir,
            media_mode=media_mode,
            quality=quality,
            progress=progress,
        )
        media_paths = [path for path in media_paths if path and path.exists()]

        if not media_paths:
            if progress:
                progress.fail()
            send_message(chat_id, pick(NOT_FOUND_MESSAGES))
            return

        total_size = sum(path.stat().st_size for path in media_paths)
        if progress:
            progress.update(70, label="Проверяю файл", force=True)
        logger.info(
            "download complete files=%s size=%s",
            ", ".join(path.name for path in media_paths),
            human_size(total_size),
        )
        send_message(chat_id, pick(DOWNLOADED_MESSAGES))
        if is_image_gallery(media_paths):
            if progress:
                send_image_gallery(chat_id, media_paths, progress=progress)
            else:
                send_image_gallery(chat_id, media_paths)
        else:
            total_files = len(media_paths)
            for index, media_path in enumerate(media_paths):
                upload_start = 72 + (26 * index / max(total_files, 1))
                upload_end = 72 + (26 * (index + 1) / max(total_files, 1))
                if progress:
                    send_media_and_document(
                        chat_id,
                        media_path,
                        progress=progress,
                        upload_start=upload_start,
                        upload_end=upload_end,
                    )
                else:
                    send_media_and_document(chat_id, media_path)
        if progress:
            progress.finish()
        logger.info(
            "job done chat_id=%s files=%s elapsed=%.1fs",
            chat_id,
            len(media_paths),
            time.monotonic() - started_at,
        )
    except subprocess.TimeoutExpired:
        logger.exception("job timeout chat_id=%s url=%s", chat_id, safe_log_url(url))
        if progress:
            progress.fail()
        send_message(chat_id, pick(TIMEOUT_MESSAGES))
    except Exception as exc:
        logger.exception("job failed chat_id=%s url=%s error=%s", chat_id, safe_log_url(url), short_error(exc))
        if progress:
            progress.fail()
        send_message(chat_id, pick(ERROR_MESSAGES))
    finally:
        cleanup_workdir_after_job(workdir)


def download_direct(url: str, workdir: Path, progress: DownloadProgressReporter | None = None) -> Path:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name or "media"
    path = safe_target(workdir, name)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    size_limit = effective_download_limit_bytes()
    logger.info("direct download start url=%s target=%s", safe_log_url(url), path.name)
    with media_urlopen(req, timeout=DOWNLOAD_TIMEOUT) as response:
        length = response.headers.get("content-length")
        total = int(length) if length and length.isdigit() else None
        if size_limit and total and total > size_limit:
            raise RuntimeError(f"remote file is {human_size(total)}, over current upload limit {human_size(size_limit)}")
        written = 0
        if progress:
            progress.update_bytes(written, total)
        with path.open("wb") as out:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                written += len(chunk)
                if size_limit and written > size_limit:
                    raise RuntimeError(f"file grew over current upload limit {human_size(size_limit)}")
                out.write(chunk)
                if progress:
                    progress.update_bytes(written, total)
    if progress:
        progress.update(100, force=True)
    logger.info("direct download complete file=%s size=%s", path.name, human_size(path.stat().st_size))
    return path


def download_media_for_url(
    url: str,
    workdir: Path,
    media_mode: str = "video",
    quality: str | None = "720",
    progress: DownloadProgressReporter | None = None,
) -> Path:
    if DIRECT_MEDIA_RE.search(url):
        return download_direct(url, workdir, progress=progress)

    if is_instagram_url(url) and not is_instagram_reel_url(url) and media_mode == "video":
        try:
            return download_instagram_with_gallery_dl(url, workdir, progress=progress)
        except Exception as exc:
            logger.exception(
                "instagram gallery-dl failed, falling back to yt-dlp url=%s error=%s",
                safe_log_url(url),
                short_error(exc),
            )

    if progress:
        return download_with_ytdlp(url, workdir, media_mode=media_mode, quality=quality, progress=progress)
    return download_with_ytdlp(url, workdir, media_mode=media_mode, quality=quality)


def download_media_files_for_url(
    url: str,
    workdir: Path,
    media_mode: str = "video",
    quality: str | None = "720",
    progress: DownloadProgressReporter | None = None,
) -> list[Path]:
    if DIRECT_MEDIA_RE.search(url):
        return [download_direct(url, workdir, progress=progress)]

    if is_gallery_first_url(url) and media_mode == "video":
        try:
            gallery_files = download_with_gallery_dl(url, workdir, progress=progress)
            if should_retry_gallery_result_with_ytdlp(url, media_mode, gallery_files):
                logger.warning(
                    "gallery-dl returned no video for instagram reel, falling back to yt-dlp url=%s files=%s",
                    safe_log_url(url),
                    ", ".join(path.name for path in gallery_files),
                )
            else:
                return gallery_files
        except Exception as exc:
            logger.exception(
                "gallery-dl failed, falling back to yt-dlp url=%s error=%s",
                safe_log_url(url),
                short_error(exc),
            )

    if progress:
        return download_files_with_ytdlp(url, workdir, media_mode=media_mode, quality=quality, progress=progress)
    return download_files_with_ytdlp(url, workdir, media_mode=media_mode, quality=quality)


def download_instagram_with_gallery_dl(
    url: str,
    workdir: Path,
    progress: DownloadProgressReporter | None = None,
) -> Path:
    files = download_with_gallery_dl(url, workdir, progress=progress)
    if should_retry_gallery_result_with_ytdlp(url, "video", files):
        raise RuntimeError("gallery-dl returned no video for instagram reel")
    return files[0]


def download_with_gallery_dl(
    url: str,
    workdir: Path,
    progress: DownloadProgressReporter | None = None,
) -> list[Path]:
    size_limit = effective_download_limit_bytes()
    gallery_args = [
        "--config-ignore",
        "--no-part",
        "--no-mtime",
        "--windows-filenames",
        "-D",
        str(workdir),
        url,
    ]
    if size_limit:
        gallery_args[1:1] = ["--filesize-max", cli_size_arg(size_limit)]
    cmd = build_gallery_dl_command(gallery_args)

    run_kwargs = {
        "cwd": workdir,
        "timeout": DOWNLOAD_TIMEOUT,
        "label": "gallery-dl",
    }
    if progress:
        run_kwargs["on_output_line"] = progress.handle_gallery_line
    returncode, output = run_logged_command(cmd, **run_kwargs)
    if returncode != 0:
        raise RuntimeError(output or "gallery-dl failed")

    return select_downloaded_media_files(workdir)


def download_with_ytdlp(
    url: str,
    workdir: Path,
    media_mode: str = "video",
    quality: str | None = "720",
    progress: DownloadProgressReporter | None = None,
) -> Path:
    if progress:
        return download_files_with_ytdlp(url, workdir, media_mode=media_mode, quality=quality, progress=progress)[0]
    return download_files_with_ytdlp(url, workdir, media_mode=media_mode, quality=quality)[0]


def download_files_with_ytdlp(
    url: str,
    workdir: Path,
    media_mode: str = "video",
    quality: str | None = "720",
    progress: DownloadProgressReporter | None = None,
) -> list[Path]:
    output_template = str(workdir / "%(title).80s-%(id)s.%(ext)s")
    size_limit = effective_download_limit_bytes()

    if media_mode == "audio":
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Audio extraction needs ffmpeg.")
        media_args = [
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            AUDIO_BITRATE,
            "-f",
            "bestaudio/best",
        ]
    else:
        if not quality:
            quality = "best"
        if quality != "best" and not str(quality).isdigit():
            quality = "best"

        allow_merge = is_youtube_url(url) and video_ffmpeg_merge_enabled() and large_upload_route_available()
        format_selector = None
        if size_limit and is_vk_video_url(url) and not allow_merge:
            try:
                format_selector = probe_upload_safe_video_format_id(url, quality, size_limit)
                if format_selector:
                    logger.info("selected upload-safe format url=%s format=%s", safe_log_url(url), format_selector)
            except Exception as exc:
                logger.warning("upload-safe format probe failed url=%s error=%s", safe_log_url(url), short_error(exc))
        if not format_selector:
            format_selector = video_format_selector(
                quality,
                allow_merge=allow_merge,
                max_filesize_bytes=size_limit,
            )
        merge_args = ["--merge-output-format", "mp4"] if allow_merge else []
        media_args = [*merge_args, "-f", format_selector]

    ytdlp_args = [
        "--no-playlist",
        "--newline",
        "--no-colors",
        "--windows-filenames",
        "--restrict-filenames",
        *media_args,
        "-o",
        output_template,
        url,
    ]
    if size_limit:
        ytdlp_args[1:1] = ["--max-filesize", cli_size_arg(size_limit)]
    cmd = build_ytdlp_command(ytdlp_args, url=url)

    run_kwargs = {
        "cwd": workdir,
        "timeout": DOWNLOAD_TIMEOUT,
        "label": "yt-dlp",
    }
    if progress:
        run_kwargs["on_output_line"] = progress.handle_ytdlp_line
    returncode, output = run_logged_command(cmd, **run_kwargs)
    if returncode != 0:
        raise RuntimeError(output or "yt-dlp failed")

    files = [
        path for path in workdir.rglob("*")
        if path.is_file()
        and not path.name.endswith(".part")
        and path.suffix.lower() in MEDIA_SUFFIXES
    ]
    if not files:
        if size_limit and ("max-filesize" in output.lower() or "larger than" in output.lower()):
            raise RuntimeError(
                f"Selected media is over the current upload limit {human_size(size_limit)}."
            )
        if "max-filesize" in output.lower() or "larger than" in output.lower():
            raise RuntimeError(
                f"Выбранный файл больше защитного лимита скачивания {DOWNLOAD_MAX_MB} MB."
            )
        raise RuntimeError(output or "yt-dlp did not create a media file")
    selected = select_preferred_media_files(files)
    if size_limit:
        oversized = [path for path in selected if path.stat().st_size > size_limit]
        if oversized:
            names = ", ".join(f"{path.name} ({human_size(path.stat().st_size)})" for path in oversized)
            raise RuntimeError(
                f"Downloaded media is over the current upload limit {human_size(size_limit)}: {names}"
            )
    return selected


def select_downloaded_media_file(workdir: Path) -> Path:
    return select_downloaded_media_files(workdir)[0]


def select_downloaded_media_files(workdir: Path) -> list[Path]:
    files = [
        path for path in workdir.rglob("*")
        if path.is_file()
        and not path.name.endswith(".part")
        and path.suffix.lower() in MEDIA_SUFFIXES
    ]
    if not files:
        raise RuntimeError("downloader did not create a media file")
    return select_preferred_media_files(files)


def select_preferred_media_file(files: list[Path]) -> Path:
    return select_preferred_media_files(files)[0]


def select_preferred_media_files(files: list[Path]) -> list[Path]:
    video_files = [path for path in files if path.suffix.lower() in VIDEO_SUFFIXES]
    candidates = video_files or [path for path in files if path.suffix.lower() in IMAGE_SUFFIXES] or files
    candidates.sort(key=lambda path: (path.stat().st_size, path.stat().st_mtime), reverse=True)
    if video_files:
        return [candidates[0]]
    return candidates


def has_video_file(paths: list[Path]) -> bool:
    return any(path.suffix.lower() in VIDEO_SUFFIXES for path in paths)


def should_retry_gallery_result_with_ytdlp(url: str, media_mode: str, paths: list[Path]) -> bool:
    return media_mode == "video" and is_instagram_reel_url(url) and not has_video_file(paths)


def cookies_file_for_url(url: str | None) -> str:
    if url and is_instagram_url(url):
        instagram_cookies = os.environ.get("BOT_INSTAGRAM_COOKIES_FILE", "").strip()
        if instagram_cookies:
            return instagram_cookies
    return os.environ.get("BOT_COOKIES_FILE", "").strip()


def build_ytdlp_command(args: list[str], url: str | None = None) -> list[str]:
    cmd = [sys.executable, "-m", "yt_dlp"]
    proxy = os.environ.get("BOT_YTDLP_PROXY", "").strip()
    cookies = cookies_file_for_url(url)
    if proxy:
        cmd.extend(["--proxy", proxy])
    if cookies:
        cmd.extend(["--cookies", cookies])
    cmd.extend(args)
    return cmd


def build_gallery_dl_command(args: list[str]) -> list[str]:
    cmd = [sys.executable, "-m", "gallery_dl"]
    proxy = (
        os.environ.get("BOT_GALLERY_DL_PROXY", "").strip()
        or os.environ.get("BOT_INSTAGRAM_PROXY", "").strip()
        or os.environ.get("BOT_YTDLP_PROXY", "").strip()
    )
    cookies = (
        os.environ.get("BOT_INSTAGRAM_COOKIES_FILE", "").strip()
        or os.environ.get("BOT_COOKIES_FILE", "").strip()
    )
    if proxy:
        cmd.extend(["--proxy", proxy])
    if cookies:
        cmd.extend(["--cookies", cookies])
    cmd.extend(args)
    return cmd


def run_logged_command(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int | None = None,
    label: str = "cmd",
    on_output_line=None,
) -> tuple[int, str]:
    logger.info("%s start: %s", label, redacted_command(cmd))
    started_at = time.monotonic()
    output_tail: collections.deque[str] = collections.deque(maxlen=120)
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    def read_output() -> None:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            line = redact_secret_text(line)
            output_tail.append(line)
            logger.info("%s | %s", label, line)
            if on_output_line:
                try:
                    on_output_line(line)
                except Exception as exc:
                    logger.warning("%s progress callback failed: %s", label, short_error(exc))

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    while process.poll() is None:
        if timeout and time.monotonic() - started_at > timeout:
            process.kill()
            reader.join(timeout=2)
            raise subprocess.TimeoutExpired(cmd, timeout)
        time.sleep(0.5)

    reader.join(timeout=2)
    elapsed = time.monotonic() - started_at
    logger.info("%s exit=%s elapsed=%.1fs", label, process.returncode, elapsed)
    return process.returncode or 0, "\n".join(output_tail)


def redacted_command(cmd: list[str]) -> str:
    redacted = []
    skip_next = False
    for index, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg in {"--proxy"} and index + 1 < len(cmd):
            redacted.extend([arg, "[proxy]"])
            skip_next = True
            continue
        redacted.append(redact_secret_text(arg))
    return " ".join(redacted)


def redact_secret_text(text: str) -> str:
    value = text
    if TOKEN:
        value = value.replace(TOKEN, "[token]")
    for raw in (
        os.environ.get("BOT_TELEGRAM_PROXY", ""),
        os.environ.get("BOT_MTPROTO_PROXY", ""),
        os.environ.get("BOT_YTDLP_PROXY", ""),
        TELEGRAM_API_HASH,
    ):
        if raw:
            value = value.replace(raw, "[secret]")
    return value


def redacted_api_base() -> str:
    return redact_secret_text(API_BASE)


def safe_log_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if len(path) > 80:
            path = path[:77] + "..."
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    except Exception:
        return "[url]"


def safe_target(workdir: Path, name: str) -> Path:
    clean = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "media"
    return workdir / clean[:120]


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    params = {
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": True,
    }
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    return api_json("sendMessage", params)


def edit_message_text(chat_id: int, message_id: int, text: str) -> None:
    try:
        api_json(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text[:3900],
                "disable_web_page_preview": True,
            },
        )
    except Exception as exc:
        logger.warning("edit message failed: %s", short_error(exc))


def answer_callback_query(callback_id: str) -> None:
    try:
        api_json("answerCallbackQuery", {"callback_query_id": callback_id})
    except Exception as exc:
        logger.warning("answer callback failed: %s", short_error(exc))


def send_document(
    chat_id: int,
    path: Path,
    caption: str = "",
    progress: DownloadProgressReporter | None = None,
) -> None:
    fields = {
        "chat_id": str(chat_id),
        "caption": caption[:1024],
        "disable_content_type_detection": "true",
    }
    upload_file(
        "sendDocument",
        fields,
        "document",
        path,
        mime_override="application/octet-stream",
        progress=progress,
    )


def send_media_and_document(
    chat_id: int,
    path: Path,
    progress: DownloadProgressReporter | None = None,
    upload_start: float = 72,
    upload_end: float = 98,
) -> None:
    size = path.stat().st_size
    logger.info(
        "upload route file=%s size=%s limit=%s local_bot_api=%s mtproto=%s",
        path.name,
        human_size(size),
        human_size(MAX_BYTES),
        BOT_API_LOCAL,
        mtproto_upload_available(),
    )
    if size <= MAX_BYTES:
        send_small_media_and_document(
            chat_id,
            path,
            progress=progress,
            upload_start=upload_start,
            upload_end=upload_end,
        )
        return

    if mtproto_upload_available() and size <= MTPROTO_MAX_BYTES:
        try:
            send_large_media_via_mtproto(
                chat_id,
                path,
                progress=progress,
                upload_start=upload_start,
                upload_end=upload_end,
            )
            return
        except Exception as exc:
            logger.exception("MTProto upload failed, no split fallback: %s", short_error(exc))
            raise RuntimeError(f"MTProto upload failed: {short_error(exc)}") from exc

    if size > MTPROTO_MAX_BYTES and mtproto_upload_available():
        raise RuntimeError(
            "Large file exceeds configured MTProto limit: "
            f"{human_size(size)} > {human_size(MTPROTO_MAX_BYTES)}"
        )

    raise RuntimeError(
        "Large file upload is not configured: "
        f"{path.name} is {human_size(size)}, cloud Bot API limit is {human_size(MAX_BYTES)}. "
        "Configure BOT_API_LOCAL=1 with a local Bot API server or TELEGRAM_API_ID/TELEGRAM_API_HASH for MTProto."
    )


def is_image_gallery(paths: list[Path]) -> bool:
    return len(paths) > 1 and all(path.suffix.lower() in IMAGE_SUFFIXES for path in paths)


def send_image_gallery(
    chat_id: int,
    paths: list[Path],
    progress: DownloadProgressReporter | None = None,
) -> None:
    capped = paths[:MEDIA_GROUP_LIMIT]
    if not capped:
        return
    if len(paths) > MEDIA_GROUP_LIMIT:
        logger.info("image gallery capped files=%s limit=%s", len(paths), MEDIA_GROUP_LIMIT)

    send_message(chat_id, pick(FILE_READY_MESSAGES))
    photo_paths = [path for path in capped if path.suffix.lower() in PHOTO_ALBUM_SUFFIXES]
    if len(photo_paths) >= 2:
        if progress:
            progress.set_stage("Отправляю альбом", 72, 84)
            send_media_group(chat_id, "photo", photo_paths, progress=progress)
        else:
            send_media_group(chat_id, "photo", photo_paths)
    elif len(photo_paths) == 1:
        if progress:
            progress.set_stage("Отправляю превью", 72, 84)
            send_media_preview(chat_id, photo_paths[0], "", progress=progress)
        else:
            send_media_preview(chat_id, photo_paths[0], "")

    if progress:
        progress.set_stage("Отправляю файлы", 84, 98)
        send_media_group(chat_id, "document", capped, progress=progress)
    else:
        send_media_group(chat_id, "document", capped)


def send_large_media_via_mtproto(
    chat_id: int,
    path: Path,
    progress: DownloadProgressReporter | None = None,
    upload_start: float = 72,
    upload_end: float = 98,
) -> None:
    send_message(chat_id, pick(LARGE_SEND_MESSAGES))
    send_message(chat_id, pick(FILE_READY_MESSAGES))
    if progress:
        progress.set_stage("Отправляю большой файл", upload_start, upload_end)
    run_mtproto_upload(chat_id, path, caption="", mode=LARGE_UPLOAD_MODE, progress=progress)


def run_mtproto_upload(
    chat_id: int,
    path: Path,
    caption: str,
    mode: str,
    progress: DownloadProgressReporter | None = None,
) -> None:
    script = Path(__file__).with_name("mtproto_upload.py")
    cmd = [
        sys.executable,
        str(script),
        "--chat-id",
        str(chat_id),
        "--path",
        str(path),
        "--caption",
        caption[:1024],
        "--mode",
        mode,
    ]
    run_kwargs = {
        "cwd": Path(__file__).parent,
        "timeout": UPLOAD_TIMEOUT,
        "label": "mtproto",
    }
    if progress:
        run_kwargs["on_output_line"] = progress.handle_mtproto_line
    last_output = ""
    for attempt in range(1, MTPROTO_RETRIES + 1):
        if progress and attempt > 1:
            progress.set_stage(f"Повторяю отправку {attempt}/{MTPROTO_RETRIES}", 72, 98)
        try:
            returncode, output = run_logged_command(cmd, **run_kwargs)
        except Exception as exc:
            returncode = 1
            output = short_error(exc)
        if returncode == 0:
            return

        last_output = output or "MTProto upload failed"
        if attempt < MTPROTO_RETRIES:
            logger.warning(
                "MTProto upload attempt failed attempt=%s/%s error=%s",
                attempt,
                MTPROTO_RETRIES,
                redact_secret_text(last_output[-500:]),
            )
            time.sleep(MTPROTO_RETRY_DELAY_SECONDS * attempt)

    raise RuntimeError(last_output or "MTProto upload failed")


def send_small_media_and_document(
    chat_id: int,
    path: Path,
    caption_prefix: str = "",
    progress: DownloadProgressReporter | None = None,
    upload_start: float = 72,
    upload_end: float = 98,
) -> None:
    if caption_prefix:
        send_message(chat_id, caption_prefix)
    else:
        send_message(chat_id, pick(FILE_READY_MESSAGES))
    caption = ""
    if path.stat().st_size > PREVIEW_MAX_BYTES:
        logger.info(
            "skip preview over preview limit file=%s size=%s preview_limit=%s",
            path.name,
            human_size(path.stat().st_size),
            human_size(PREVIEW_MAX_BYTES),
        )
        if progress:
            progress.set_stage("Отправляю файл", upload_start, upload_end)
            send_document(chat_id, path, caption=caption, progress=progress)
        else:
            send_document(chat_id, path, caption=caption)
        return
    preview_end = upload_start + (upload_end - upload_start) * 0.45
    if progress:
        progress.set_stage("Отправляю превью", upload_start, preview_end)
        preview_sent = send_media_preview(chat_id, path, caption, progress=progress)
    else:
        preview_sent = send_media_preview(chat_id, path, caption)
    if preview_sent:
        if progress:
            progress.set_stage("Отправляю файл", preview_end, upload_end)
            send_document(chat_id, path, caption="", progress=progress)
        else:
            send_document(chat_id, path, caption="")
    else:
        if progress:
            progress.set_stage("Отправляю файл", preview_end, upload_end)
            send_document(chat_id, path, caption=caption, progress=progress)
        else:
            send_document(chat_id, path, caption=caption)


def send_media_preview(
    chat_id: int,
    path: Path,
    caption: str,
    progress: DownloadProgressReporter | None = None,
) -> bool:
    method, field = media_method_for_path(path)
    if not method:
        return False
    try:
        fields = {
            "chat_id": str(chat_id),
            "caption": caption[:1024],
        }
        if method == "sendVideo":
            fields["supports_streaming"] = "true"
        upload_file(method, fields, field, path, progress=progress)
        return True
    except Exception as exc:
        logger.warning("media preview failed file=%s error=%s", path.name, short_error(exc))
        send_message(chat_id, pick(PREVIEW_FAIL_MESSAGES))
        return False


def media_method_for_path(path: Path) -> tuple[str | None, str | None]:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png"} and path.stat().st_size <= 10 * 1024 * 1024:
        return "sendPhoto", "photo"
    if suffix == ".gif":
        return "sendAnimation", "animation"
    if suffix in {".mp4", ".m4v", ".mov"}:
        return "sendVideo", "video"
    if suffix in {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}:
        return "sendAudio", "audio"
    return None, None


def send_media_group(
    chat_id: int,
    media_kind: str,
    paths: list[Path],
    progress: DownloadProgressReporter | None = None,
) -> None:
    if not 2 <= len(paths) <= MEDIA_GROUP_LIMIT:
        raise ValueError("sendMediaGroup requires 2-10 media items")
    if media_kind not in {"photo", "document"}:
        raise ValueError(f"unsupported media group type: {media_kind}")

    media_type = "photo" if media_kind == "photo" else "document"
    if BOT_API_LOCAL:
        media = [
            {
                "type": media_type,
                "media": path.resolve().as_uri(),
            }
            for path in paths
        ]
        logger.info("bot api local media group type=%s files=%s", media_type, len(paths))
        result = api_json(
            "sendMediaGroup",
            {
                "chat_id": str(chat_id),
                "media": json.dumps(media, ensure_ascii=False),
            },
            timeout=UPLOAD_TIMEOUT,
        )
        if progress:
            progress.update_stage_percent(100, force=True)
        return result

    media = [
        {
            "type": media_type,
            "media": f"attach://file{index}",
        }
        for index, _path in enumerate(paths)
    ]
    upload_files(
        "sendMediaGroup",
        {
            "chat_id": str(chat_id),
            "media": json.dumps(media, ensure_ascii=False),
        },
        {f"file{index}": path for index, path in enumerate(paths)},
        progress=progress,
    )


def api_json(method: str, params: dict | None = None, timeout: int = 60) -> dict:
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(f"{API_BASE}/{method}", data=data)
    logger.debug("bot api request method=%s timeout=%s", method, timeout)
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload


def upload_file(
    method: str,
    fields: dict,
    file_field: str,
    path: Path,
    mime_override: str | None = None,
    progress: DownloadProgressReporter | None = None,
) -> dict:
    if BOT_API_LOCAL:
        params = dict(fields)
        params[file_field] = path.resolve().as_uri()
        logger.info(
            "bot api local file ref method=%s field=%s file=%s size=%s",
            method,
            file_field,
            path.name,
            human_size(path.stat().st_size),
        )
        if progress:
            progress.update_stage_percent(10, force=True)
        payload = api_json(method, params, timeout=UPLOAD_TIMEOUT)
        if progress:
            progress.update_stage_percent(100, force=True)
        return payload

    boundary = "----boardbot" + uuid.uuid4().hex
    mime = mime_override or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = bytearray()

    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode()
    )
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{API_BASE}/{method}",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    logger.info(
        "bot api multipart upload method=%s field=%s file=%s size=%s",
        method,
        file_field,
        path.name,
        human_size(path.stat().st_size),
    )
    if progress:
        progress.update_stage_percent(10, force=True)
    with urlopen(req, timeout=UPLOAD_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload)
    if progress:
        progress.update_stage_percent(100, force=True)
    return payload


def upload_files(
    method: str,
    fields: dict,
    files: dict[str, Path],
    progress: DownloadProgressReporter | None = None,
) -> dict:
    boundary = "----boardbot" + uuid.uuid4().hex
    body = bytearray()

    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    for field, path in files.items():
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode()
        )
        body.extend(path.read_bytes())
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{API_BASE}/{method}",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    logger.info("bot api multipart upload method=%s files=%s", method, len(files))
    if progress:
        progress.update_stage_percent(10, force=True)
    with urlopen(req, timeout=UPLOAD_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload)
    if progress:
        progress.update_stage_percent(100, force=True)
    return payload


def human_size(value: int) -> str:
    mb = value / (1024 * 1024)
    return f"{mb:.1f} MB"


def short_error(exc: Exception) -> str:
    text = str(exc).strip().replace(TOKEN, "[token]")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-4:])[:1000] or exc.__class__.__name__


def urlopen(req, timeout: int):
    if not TELEGRAM_PROXY:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({
            "http": TELEGRAM_PROXY,
            "https": TELEGRAM_PROXY,
        })
    )
    return opener.open(req, timeout=timeout)


def media_urlopen(req, timeout: int):
    proxy = (
        os.environ.get("BOT_DIRECT_PROXY", "").strip()
        or os.environ.get("BOT_YTDLP_PROXY", "").strip()
    )
    if not proxy:
        return urllib.request.urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({
            "http": proxy,
            "https": proxy,
        })
    )
    return opener.open(req, timeout=timeout)


if __name__ == "__main__":
    main()

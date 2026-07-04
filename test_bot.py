import unittest
from pathlib import Path
from unittest.mock import patch

import bot


class FakeStat:
    def __init__(self, size=1, mtime=1):
        self.st_size = size
        self.st_mtime = mtime


class FakeFile:
    def __init__(self, name, size=1, mtime=1):
        self.name = name
        self.suffix = Path(name).suffix
        self._stat = FakeStat(size=size, mtime=mtime)

    def is_file(self):
        return True

    def stat(self):
        return self._stat


class FakeWorkdir:
    def __init__(self, files=None):
        self.files = files or []

    def __str__(self):
        return "fake-workdir"

    def __truediv__(self, name):
        return Path("fake-workdir") / name

    def iterdir(self):
        return self.files

    def rglob(self, pattern):
        return self.files


class UrlSupportTests(unittest.TestCase):
    def test_supports_vk_and_rutube_video_urls(self):
        urls = [
            "https://vk.com/video-123_456",
            "https://m.vk.com/video-123_456",
            "https://vkvideo.ru/video-123_456",
            "https://rutube.ru/video/0123456789abcdef/",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(bot.is_supported_url(url))


class YtdlpFormatTests(unittest.TestCase):
    def test_instagram_video_download_uses_gallery_dl_and_returns_video_file(self):
        captured = {}
        workdir = FakeWorkdir([
            FakeFile("preview.jpg", size=10_000, mtime=2),
            FakeFile("reel.mp4", size=5_000_000, mtime=1),
        ])

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd"):
            captured["cmd"] = cmd
            captured["label"] = label
            return 0, ""

        with patch.object(bot, "run_logged_command", side_effect=fake_run_logged_command):
            path = bot.download_instagram_with_gallery_dl(
                "https://www.instagram.com/reel/ABC123/",
                workdir,
            )

        self.assertEqual("reel.mp4", path.name)
        self.assertEqual("gallery-dl", captured["label"])
        self.assertIn("-m", captured["cmd"])
        self.assertIn("gallery_dl", captured["cmd"])
        self.assertNotIn("yt_dlp", captured["cmd"])
        self.assertNotIn("--merge-output-format", captured["cmd"])

    def test_download_media_routes_instagram_video_to_gallery_dl(self):
        expected = FakeFile("reel.mp4")
        workdir = FakeWorkdir([expected])

        with patch.object(bot, "download_instagram_with_gallery_dl", create=True, return_value=expected) as gallery:
            with patch.object(bot, "download_with_ytdlp") as ytdlp:
                result = bot.download_media_for_url(
                    "https://www.instagram.com/reel/ABC123/",
                    workdir,
                    media_mode="video",
                    quality=None,
                )

        self.assertIs(result, expected)
        gallery.assert_called_once()
        ytdlp.assert_not_called()

    def test_youtube_options_skip_video_only_formats_without_ffmpeg_merge(self):
        fake_info = {
            "duration": 10,
            "formats": [
                {
                    "height": 1080,
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "filesize": 10_000_000,
                },
                {
                    "height": 720,
                    "ext": "mp4",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "filesize": 5_000_000,
                },
                {
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "filesize": 1_000_000,
                },
            ],
        }

        with patch.object(bot, "probe_ytdlp_info", return_value=fake_info):
            options, _ = bot.get_youtube_download_options("https://www.youtube.com/watch?v=videoid")

        self.assertEqual([{"height": 720, "estimated_bytes": 5_000_000}], options)

    def test_video_download_prefers_progressive_h264_mp4_without_ffmpeg_merge(self):
        captured = {}

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd"):
            captured["cmd"] = cmd
            return 0, ""

        with patch.object(bot.shutil, "which", return_value="/usr/bin/ffmpeg"):
            with patch.object(bot, "run_logged_command", side_effect=fake_run_logged_command):
                bot.download_with_ytdlp(
                    "https://www.youtube.com/watch?v=videoid",
                    FakeWorkdir([FakeFile("download.mp4")]),
                    media_mode="video",
                    quality="720",
                )

        cmd = captured["cmd"]
        self.assertNotIn("--merge-output-format", cmd)
        selector = cmd[cmd.index("-f") + 1]
        self.assertIn("b[ext=mp4][vcodec^=avc1][acodec^=mp4a][height<=720]", selector)
        self.assertNotIn("+ba", selector)


if __name__ == "__main__":
    unittest.main()

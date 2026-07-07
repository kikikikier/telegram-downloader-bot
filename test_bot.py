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

    def exists(self):
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

    def mkdir(self, parents=False, exist_ok=False):
        return None

    def iterdir(self):
        return self.files

    def rglob(self, pattern):
        return self.files


class FakeTmpRoot:
    def __init__(self, workdir):
        self.workdir = workdir

    def __truediv__(self, name):
        return self.workdir

    def mkdir(self, parents=False, exist_ok=False):
        return None


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

    def test_download_media_files_routes_tiktok_posts_to_gallery_dl_first(self):
        expected = [FakeFile("photo.jpg")]
        workdir = FakeWorkdir(expected)

        with patch.object(bot, "download_with_gallery_dl", create=True, return_value=expected) as gallery:
            with patch.object(bot, "download_files_with_ytdlp", create=True) as ytdlp:
                result = bot.download_media_files_for_url(
                    "https://www.tiktok.com/@user/photo/1234567890",
                    workdir,
                    media_mode="video",
                    quality=None,
                )

        self.assertEqual(expected, result)
        gallery.assert_called_once()
        ytdlp.assert_not_called()

    def test_gallery_dl_image_post_returns_all_downloaded_images(self):
        workdir = FakeWorkdir([
            FakeFile("photo-1.jpg", size=1_000_000, mtime=1),
            FakeFile("photo-2.jpg", size=2_000_000, mtime=2),
            FakeFile("photo-3.png", size=1_500_000, mtime=3),
        ])

        with patch.object(bot, "run_logged_command", return_value=(0, "")):
            paths = bot.download_with_gallery_dl(
                "https://www.instagram.com/p/ABC123/",
                workdir,
            )

        self.assertEqual(["photo-2.jpg", "photo-3.png", "photo-1.jpg"], [path.name for path in paths])

    def test_handle_url_sends_downloaded_images_as_one_gallery_album(self):
        paths = [
            FakeFile("photo-1.jpg", size=1_000_000, mtime=1),
            FakeFile("photo-2.jpg", size=2_000_000, mtime=2),
        ]
        workdir = FakeWorkdir(paths)

        with patch.object(bot, "TMP_ROOT", FakeTmpRoot(workdir)):
            with patch.object(bot, "mark_workdir_active"):
                with patch.object(bot, "schedule_workdir_cleanup"):
                    with patch.object(bot, "download_media_files_for_url", create=True, return_value=paths):
                        with patch.object(bot, "download_media_for_url", return_value=paths[0]):
                            with patch.object(bot, "send_message"):
                                with patch.object(bot, "send_image_gallery") as send_gallery:
                                    with patch.object(bot, "send_media_and_document") as send_media:
                                        bot.handle_url(123, "https://www.instagram.com/p/ABC123/")

        send_gallery.assert_called_once_with(123, paths)
        send_media.assert_not_called()

    def test_image_gallery_uses_media_groups_and_caps_at_telegram_limit(self):
        paths = [
            FakeFile(f"photo-{index}.jpg", size=1_000_000 + index, mtime=index)
            for index in range(12)
        ]

        with patch.object(bot, "send_message") as send_message:
            with patch.object(bot, "send_media_group") as send_group:
                bot.send_image_gallery(123, paths)

        send_message.assert_called_once()
        self.assertIn(send_message.call_args.args[1], bot.FILE_READY_MESSAGES)
        self.assertEqual(2, send_group.call_count)
        self.assertEqual(("photo", paths[:10]), send_group.call_args_list[0].args[1:])
        self.assertEqual(("document", paths[:10]), send_group.call_args_list[1].args[1:])

    def test_single_image_still_uses_existing_single_file_route(self):
        path = FakeFile("photo-1.jpg", size=1_000_000, mtime=1)
        workdir = FakeWorkdir([path])

        with patch.object(bot, "TMP_ROOT", FakeTmpRoot(workdir)):
            with patch.object(bot, "mark_workdir_active"):
                with patch.object(bot, "schedule_workdir_cleanup"):
                    with patch.object(bot, "download_media_files_for_url", create=True, return_value=[path]):
                        with patch.object(bot, "send_message"):
                            with patch.object(bot, "send_image_gallery") as send_gallery:
                                with patch.object(bot, "send_media_and_document") as send_media:
                                    bot.handle_url(123, "https://www.instagram.com/p/ABC123/")

        send_gallery.assert_not_called()
        send_media.assert_called_once_with(123, path)

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


class UserReplicaTests(unittest.TestCase):
    def test_main_user_replica_sets_have_200_unique_messages_each(self):
        replica_sets = (
            bot.ACCEPT_MESSAGES,
            bot.DOWNLOADED_MESSAGES,
            bot.FILE_READY_MESSAGES,
        )

        for messages in replica_sets:
            with self.subTest(first_message=messages[0]):
                self.assertEqual(200, len(messages))
                self.assertEqual(200, len(set(messages)))

    def test_small_upload_announces_ready_separately_and_uses_empty_captions(self):
        media = FakeFile("download.mp4", size=1024)

        with patch.object(bot, "send_message") as send_message:
            with patch.object(bot, "send_media_preview", return_value=True) as send_preview:
                with patch.object(bot, "send_document") as send_document:
                    bot.send_small_media_and_document(123, media)

        send_message.assert_called_once()
        self.assertIn(send_message.call_args.args[1], bot.FILE_READY_MESSAGES)
        send_preview.assert_called_once_with(123, media, "")
        send_document.assert_called_once_with(123, media, caption="")

    def test_mtproto_upload_announces_ready_separately_and_uses_empty_caption(self):
        media = FakeFile("large.mp4", size=1024)

        with patch.object(bot, "send_message") as send_message:
            with patch.object(bot, "run_mtproto_upload") as upload:
                bot.send_large_media_via_mtproto(123, media)

        self.assertEqual(2, send_message.call_count)
        self.assertIn(send_message.call_args_list[1].args[1], bot.FILE_READY_MESSAGES)
        upload.assert_called_once_with(123, media, caption="", mode=bot.LARGE_UPLOAD_MODE)


if __name__ == "__main__":
    unittest.main()

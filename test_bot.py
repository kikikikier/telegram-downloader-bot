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

    def test_download_media_routes_instagram_reels_to_ytdlp_first(self):
        expected = FakeFile("reel.mp4")
        workdir = FakeWorkdir([expected])

        with patch.object(bot, "download_instagram_with_gallery_dl", create=True) as gallery:
            with patch.object(bot, "download_with_ytdlp", create=True, return_value=expected) as ytdlp:
                result = bot.download_media_for_url(
                    "https://www.instagram.com/reel/ABC123/",
                    workdir,
                    media_mode="video",
                    quality=None,
                )

        self.assertIs(result, expected)
        gallery.assert_not_called()
        ytdlp.assert_called_once_with(
            "https://www.instagram.com/reel/ABC123/",
            workdir,
            media_mode="video",
            quality=None,
        )

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

    def test_download_media_files_routes_instagram_reels_to_ytdlp_first(self):
        expected = [FakeFile("reel.mp4")]
        workdir = FakeWorkdir(expected)

        with patch.object(bot, "download_with_gallery_dl", create=True) as gallery:
            with patch.object(bot, "download_files_with_ytdlp", create=True, return_value=expected) as ytdlp:
                result = bot.download_media_files_for_url(
                    "https://www.instagram.com/reel/ABC123/",
                    workdir,
                    media_mode="video",
                    quality=None,
                )

        self.assertEqual(expected, result)
        gallery.assert_not_called()
        ytdlp.assert_called_once_with(
            "https://www.instagram.com/reel/ABC123/",
            workdir,
            media_mode="video",
            quality=None,
        )

    def test_gallery_dl_reel_image_only_is_not_accepted_as_video(self):
        workdir = FakeWorkdir([FakeFile("preview.jpg")])

        with patch.object(bot, "run_logged_command", return_value=(0, "")):
            with self.assertRaisesRegex(RuntimeError, "no video"):
                bot.download_instagram_with_gallery_dl(
                    "https://www.instagram.com/reel/ABC123/",
                    workdir,
                )

    def test_instagram_image_post_keeps_gallery_images_without_ytdlp_fallback(self):
        expected = [
            FakeFile("photo-1.jpg", size=1_000_000, mtime=1),
            FakeFile("photo-2.jpg", size=2_000_000, mtime=2),
        ]
        workdir = FakeWorkdir(expected)

        with patch.object(bot, "download_with_gallery_dl", create=True, return_value=expected) as gallery:
            with patch.object(bot, "download_files_with_ytdlp", create=True) as ytdlp:
                result = bot.download_media_files_for_url(
                    "https://www.instagram.com/p/ABC123/",
                    workdir,
                    media_mode="video",
                    quality=None,
                )

        self.assertEqual(expected, result)
        gallery.assert_called_once()
        ytdlp.assert_not_called()

    def test_instagram_ytdlp_download_uses_instagram_cookies_file(self):
        captured = {}
        workdir = FakeWorkdir([FakeFile("reel.mp4")])

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd"):
            captured["cmd"] = cmd
            return 0, ""

        with patch.dict(bot.os.environ, {"BOT_INSTAGRAM_COOKIES_FILE": "instagram-cookies.txt"}, clear=True):
            with patch.object(bot, "run_logged_command", side_effect=fake_run_logged_command):
                bot.download_files_with_ytdlp(
                    "https://www.instagram.com/reel/ABC123/",
                    workdir,
                    media_mode="video",
                    quality=None,
                )

        self.assertIn("--cookies", captured["cmd"])
        self.assertIn("instagram-cookies.txt", captured["cmd"])

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
            with patch.object(bot, "video_ffmpeg_merge_enabled", return_value=False):
                options, _ = bot.get_youtube_download_options("https://www.youtube.com/watch?v=videoid")

        self.assertEqual([{"height": 720, "estimated_bytes": 5_000_000}], options)

    def test_video_download_prefers_progressive_h264_mp4_without_ffmpeg_merge(self):
        captured = {}

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd", on_output_line=None):
            captured["cmd"] = cmd
            captured["on_output_line"] = on_output_line
            return 0, ""

        with patch.object(bot, "video_ffmpeg_merge_enabled", return_value=False):
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

    def test_video_download_without_large_route_uses_upload_safe_format_limit(self):
        captured = {}

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd", on_output_line=None):
            captured["cmd"] = cmd
            return 0, ""

        with patch.object(bot, "large_upload_route_available", return_value=False):
            with patch.object(bot, "probe_upload_safe_video_format_id", return_value=None):
                with patch.object(bot, "run_logged_command", side_effect=fake_run_logged_command):
                    bot.download_files_with_ytdlp(
                        "https://vkvideo.ru/video-94_456240146",
                        FakeWorkdir([FakeFile("download.mp4", size=bot.MAX_BYTES - 1024)]),
                        media_mode="video",
                        quality="720",
                    )

        cmd = captured["cmd"]
        selector = cmd[cmd.index("-f") + 1]
        self.assertIn(f"[filesize_approx<={bot.MAX_BYTES}]", selector)
        self.assertIn("--max-filesize", cmd)
        self.assertEqual(bot.cli_size_arg(bot.MAX_BYTES), cmd[cmd.index("--max-filesize") + 1])

    def test_vk_upload_safe_format_uses_bitrate_estimate_and_skips_video_only(self):
        info = {
            "duration": 1028,
            "formats": [
                {"format_id": "url720", "height": 720, "ext": "mp4", "vcodec": None, "acodec": None},
                {"format_id": "hls-516", "height": 360, "ext": "mp4", "tbr": 516.821, "vcodec": None, "acodec": None},
                {
                    "format_id": "hls_fmp4-399",
                    "height": 360,
                    "ext": "mp4",
                    "tbr": 399.509,
                    "vcodec": "avc1.4D401E",
                    "acodec": "none",
                },
                {"format_id": "hls-306", "height": 240, "ext": "mp4", "tbr": 306.274, "vcodec": None, "acodec": None},
                {"format_id": "hls-218", "height": 144, "ext": "mp4", "tbr": 218.203, "vcodec": None, "acodec": None},
            ],
        }

        selected = bot.select_upload_safe_video_format_id(info, "720", bot.MAX_BYTES)

        self.assertEqual("hls-306", selected)

    def test_vk_download_uses_probed_upload_safe_format_id(self):
        captured = {}

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd", on_output_line=None):
            captured["cmd"] = cmd
            return 0, ""

        with patch.object(bot, "large_upload_route_available", return_value=False):
            with patch.object(bot, "probe_upload_safe_video_format_id", return_value="hls-306"):
                with patch.object(bot, "run_logged_command", side_effect=fake_run_logged_command):
                    bot.download_files_with_ytdlp(
                        "https://vkvideo.ru/video-94_456240146",
                        FakeWorkdir([FakeFile("download.mp4", size=bot.MAX_BYTES - 1024)]),
                        media_mode="video",
                        quality="720",
                    )

        cmd = captured["cmd"]
        self.assertEqual("hls-306", cmd[cmd.index("-f") + 1])
        self.assertIn("--max-filesize", cmd)

    def test_video_download_without_large_route_rejects_oversized_result(self):
        with patch.object(bot, "large_upload_route_available", return_value=False):
            with patch.object(bot, "probe_upload_safe_video_format_id", return_value=None):
                with patch.object(bot, "run_logged_command", return_value=(0, "")):
                    with self.assertRaisesRegex(RuntimeError, "over the current upload limit"):
                        bot.download_files_with_ytdlp(
                            "https://vkvideo.ru/video-94_456240146",
                            FakeWorkdir([FakeFile("download.mp4", size=bot.MAX_BYTES + 1)]),
                            media_mode="video",
                            quality="720",
                        )

    def test_video_download_merge_selector_prefers_requested_4k_before_progressive_fallback(self):
        selector = bot.video_format_selector("2160", allow_merge=True)
        choices = selector.split("/")

        self.assertIn("+ba", choices[0])
        self.assertIn("[height=2160]", choices[0])
        self.assertGreater(
            choices.index("b[ext=mp4][vcodec^=avc1][acodec^=mp4a][height<=2160]"),
            0,
        )

    def test_youtube_options_include_video_only_4k_when_ffmpeg_merge_enabled(self):
        fake_info = {
            "duration": None,
            "formats": [
                {
                    "height": 360,
                    "ext": "mp4",
                    "vcodec": "avc1.42001E",
                    "acodec": "mp4a.40.2",
                    "filesize": 25_000_000,
                },
                {
                    "height": 2160,
                    "ext": "mp4",
                    "vcodec": "av01.0.12M.08",
                    "acodec": "none",
                    "filesize": 350_000_000,
                },
                {
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "filesize": 8_000_000,
                },
            ],
        }

        with patch.object(bot, "probe_ytdlp_info", return_value=fake_info):
            with patch.object(bot, "video_ffmpeg_merge_enabled", return_value=True):
                options, _ = bot.get_youtube_download_options("https://www.youtube.com/watch?v=videoid")

        self.assertEqual(
            [
                {"height": 360, "estimated_bytes": 25_000_000},
                {"height": 2160, "estimated_bytes": 358_000_000},
            ],
            options,
        )

    def test_ytdlp_download_updates_progress_from_output_lines(self):
        edits = []
        progress = bot.DownloadProgressReporter(
            123,
            456,
            min_interval=0,
            edit_func=lambda chat_id, message_id, text: edits.append((chat_id, message_id, text)),
        )

        def fake_run_logged_command(cmd, cwd=None, timeout=None, label="cmd", on_output_line=None):
            self.assertIsNotNone(on_output_line)
            on_output_line("[download]  36.6% of    5.46MiB at    6.50MiB/s ETA 00:00")
            return 0, ""

        with patch.object(bot, "run_logged_command", side_effect=fake_run_logged_command):
            bot.download_files_with_ytdlp(
                "https://www.youtube.com/watch?v=videoid",
                FakeWorkdir([FakeFile("download.mp4")]),
                media_mode="video",
                quality="720",
                progress=progress,
            )

        self.assertEqual(123, edits[-1][0])
        self.assertEqual(456, edits[-1][1])
        self.assertIn("37%", edits[-1][2])

    def test_ytdlp_progress_maps_to_active_stage_range(self):
        edits = []
        progress = bot.DownloadProgressReporter(
            123,
            456,
            min_interval=0,
            edit_func=lambda chat_id, message_id, text: edits.append(text),
        )

        progress.set_stage("Скачиваю", 5, 70)
        progress.handle_ytdlp_line("[download]  50.0% of   20.00MiB at    6.50MiB/s ETA 00:01")

        self.assertIn("38%", edits[-1])

    def test_ffmpeg_progress_line_updates_progress_by_duration(self):
        edits = []
        progress = bot.DownloadProgressReporter(
            123,
            456,
            min_interval=0,
            edit_func=lambda chat_id, message_id, text: edits.append(text),
        )

        progress.handle_ffmpeg_line("out_time=00:00:05.000000", duration=10)

        self.assertIn("50%", edits[-1])

    def test_send_message_returns_bot_api_payload(self):
        payload = {"ok": True, "result": {"message_id": 456}}

        with patch.object(bot, "api_json", return_value=payload):
            result = bot.send_message(123, "hello")

        self.assertIs(result, payload)


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

    def test_small_upload_reports_preview_and_document_stages(self):
        media = FakeFile("download.mp4", size=1024)
        edits = []
        progress = bot.DownloadProgressReporter(
            123,
            456,
            min_interval=0,
            edit_func=lambda chat_id, message_id, text: edits.append(text),
        )

        with patch.object(bot, "send_message"):
            with patch.object(bot, "send_media_preview", return_value=True):
                with patch.object(bot, "send_document"):
                    bot.send_small_media_and_document(123, media, progress=progress)

        text = "\n".join(edits)
        self.assertIn("Отправляю превью", text)
        self.assertIn("Отправляю файл", text)

    def test_handle_url_finishes_progress_after_upload_route(self):
        media = FakeFile("download.mp4", size=1024)
        workdir = FakeWorkdir([media])
        events = []

        class FakeProgress:
            def set_stage(self, label, start, end):
                events.append(("stage", label, start, end))

            def update(self, percent, label=None, force=False):
                events.append(("update", label, int(percent)))

            def finish(self):
                events.append("finish")

            def fail(self):
                events.append("fail")

        progress = FakeProgress()

        def fake_send_media(chat_id, path, progress=None, **kwargs):
            events.append(("send", progress is progress_obj))

        progress_obj = progress
        with patch.object(bot, "TMP_ROOT", FakeTmpRoot(workdir)):
            with patch.object(bot, "mark_workdir_active"):
                with patch.object(bot, "schedule_workdir_cleanup"):
                    with patch.object(bot, "start_progress_message", return_value=progress):
                        with patch.object(bot, "download_media_files_for_url", return_value=[media]):
                            with patch.object(bot, "send_message"):
                                with patch.object(bot, "send_media_and_document", side_effect=fake_send_media):
                                    bot.handle_url(123, "https://www.youtube.com/watch?v=videoid")

        self.assertLess(events.index(("send", True)), events.index("finish"))

    def test_mtproto_upload_announces_ready_separately_and_uses_empty_caption(self):
        media = FakeFile("large.mp4", size=1024)

        with patch.object(bot, "send_message") as send_message:
            with patch.object(bot, "run_mtproto_upload") as upload:
                bot.send_large_media_via_mtproto(123, media)

        self.assertEqual(2, send_message.call_count)
        self.assertIn(send_message.call_args_list[1].args[1], bot.FILE_READY_MESSAGES)
        upload.assert_called_once_with(123, media, caption="", mode=bot.LARGE_UPLOAD_MODE, progress=None)

    def test_mtproto_upload_retries_transient_command_failure(self):
        media = FakeFile("large.mp4", size=1024)

        with patch.object(bot, "run_logged_command", side_effect=[(1, "temporary"), (0, "ok")]) as run_command:
            with patch.object(bot.time, "sleep") as sleep:
                bot.run_mtproto_upload(123, media, caption="", mode="document")

        self.assertEqual(2, run_command.call_count)
        sleep.assert_called_once()

    def test_mtproto_upload_raises_after_retry_attempts_are_exhausted(self):
        media = FakeFile("large.mp4", size=1024)

        with patch.object(bot, "run_logged_command", return_value=(1, "still down")) as run_command:
            with patch.object(bot.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "still down"):
                    bot.run_mtproto_upload(123, media, caption="", mode="document")

        self.assertEqual(bot.MTPROTO_RETRIES, run_command.call_count)

    def test_large_upload_without_large_file_route_fails_instead_of_splitting(self):
        media = FakeFile("large.mp4", size=bot.MAX_BYTES + 1)

        with patch.object(bot, "mtproto_upload_available", return_value=False):
            with patch.object(bot, "send_message"):
                with patch.object(bot, "send_small_media_and_document") as send_small:
                    with self.assertRaisesRegex(RuntimeError, "Large file upload is not configured"):
                        bot.send_media_and_document(123, media)

        send_small.assert_not_called()

    def test_mtproto_upload_failure_does_not_fall_back_to_splitting(self):
        media = FakeFile("large.mp4", size=bot.MAX_BYTES + 1)

        with patch.object(bot, "mtproto_upload_available", return_value=True):
            with patch.object(bot, "MTPROTO_MAX_BYTES", media.stat().st_size + 1024):
                with patch.object(bot, "send_large_media_via_mtproto", side_effect=RuntimeError("boom")):
                    with patch.object(bot, "send_message"):
                        with self.assertRaisesRegex(RuntimeError, "MTProto upload failed"):
                            bot.send_media_and_document(123, media)


if __name__ == "__main__":
    unittest.main()

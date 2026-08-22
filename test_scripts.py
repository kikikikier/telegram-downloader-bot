import unittest
from pathlib import Path


class StartupScriptTests(unittest.TestCase):
    def test_start_script_updates_dependencies_before_launch(self):
        script = Path(__file__).with_name("start.sh").read_text(encoding="utf-8")

        update_index = script.index("pip install")
        launch_index = script.index("nohup .venv/bin/python -u bot.py")

        self.assertLess(update_index, launch_index)
        self.assertIn("--upgrade", script)
        self.assertIn("-r requirements.txt", script)
        self.assertIn("BOT_AUTO_UPDATE_DEPS", script)

    def test_start_script_prunes_stale_temp_downloads_before_launch(self):
        script = Path(__file__).with_name("start.sh").read_text(encoding="utf-8")
        cleanup_script = Path(__file__).with_name("cleanup-bot-temp.sh").read_text(encoding="utf-8")

        cleanup_index = script.index("./cleanup-bot-temp.sh")
        launch_index = script.index("nohup .venv/bin/python -u bot.py")

        self.assertLess(cleanup_index, launch_index)
        self.assertIn("telegram-downloader-bot", cleanup_script)
        self.assertIn("BOT_STARTUP_TMP_MAX_AGE_MINUTES", cleanup_script)

    def test_cleanup_script_is_observable_and_scoped_to_bot_tmp(self):
        script = Path(__file__).with_name("cleanup-bot-temp.sh").read_text(encoding="utf-8")

        self.assertIn("df -h", script)
        self.assertIn("du -sh", script)
        self.assertIn("find \"$tmp_root\"", script)
        self.assertIn("*/telegram-downloader-bot", script)
        self.assertIn("cleanup complete", script)

    def test_generated_monitor_logs_are_ignored(self):
        gitignore = Path(__file__).with_name(".gitignore").read_text(encoding="utf-8")

        self.assertIn("logs/", gitignore)


if __name__ == "__main__":
    unittest.main()

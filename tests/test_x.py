"""X (Twitter) MP4 下载命令的离线单元测试。"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from opc_cli import cli, x


class XDownloadTests(unittest.TestCase):
    def test_download_video_returns_printed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            downloaded = output_dir / "tweet.mp4"
            downloaded.write_bytes(b"fake-video")
            version = subprocess.CompletedProcess(["yt-dlp", "--version"], 0)
            result = subprocess.CompletedProcess(
                ["yt-dlp"], 0, stdout=f"{downloaded}\n", stderr=""
            )

            with patch("opc_cli._video.subprocess.run", side_effect=[version, result]) as run, patch(
                "opc_cli._video.write_finder_comment", return_value=False
            ):
                path = x.download_video(
                    "https://x.com/i/status/123",
                    str(output_dir),
                    cookies="cookies.txt",
                )

        self.assertEqual(path, str(downloaded))
        command = run.call_args_list[1].args[0]
        self.assertIn("--merge-output-format", command)
        self.assertIn("--cookies", command)
        self.assertIn("cookies.txt", command)
        self.assertEqual(command[-1], "https://x.com/i/status/123")

    def test_download_video_error_includes_cookies_hint(self):
        version = subprocess.CompletedProcess(["yt-dlp", "--version"], 0)
        failed = subprocess.CompletedProcess(
            ["yt-dlp"], 1, stdout="", stderr="No video could be found in this tweet"
        )
        with tempfile.TemporaryDirectory() as temporary:
            with patch("opc_cli._video.subprocess.run", side_effect=[version, failed]):
                with self.assertRaises(x.XDownloadError) as caught:
                    x.download_video("https://x.com/i/status/123", temporary)

        message = str(caught.exception)
        self.assertIn("No video could be found", message)
        self.assertIn("--cookies", message)

    def test_cli_uses_default_folder_and_shared_cookie_setting(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            output_file = output_dir / "video.mp4"
            with patch.dict(
                os.environ,
                {"X_FOLDER": str(output_dir), "YT_DLP_COOKIES": "cookies.txt"},
                clear=False,
            ), patch("opc_cli.media.download_x_video", return_value=str(output_file)) as download:
                result = runner.invoke(cli.app, ["media", "download", "https://x.com/i/status/123"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(str(output_file), result.output)
        self.assertEqual(
            download.call_args.args,
            ("https://x.com/i/status/123", str(output_dir), "cookies.txt"),
        )


if __name__ == "__main__":
    unittest.main()

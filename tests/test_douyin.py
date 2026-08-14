"""抖音 MP4 下载命令的离线单元测试。

下载逻辑已抽取到 ``opc_cli._video``，因此涉及 subprocess / Finder 评注的桩
都打在 ``opc_cli._video`` 上；这里验证抖音入口经由共享实现端到端可用。
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from opc_cli import cli, douyin


class DouyinDownloadTests(unittest.TestCase):
    def test_download_video_requests_mp4_and_returns_printed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            downloaded = output_dir / "测试视频.mp4"
            downloaded.write_bytes(b"fake-video")
            version = subprocess.CompletedProcess(["yt-dlp", "--version"], 0)
            result = subprocess.CompletedProcess(
                ["yt-dlp"], 0, stdout=f"{downloaded}\n", stderr=""
            )

            with patch("opc_cli._video.subprocess.run", side_effect=[version, result]) as run, patch(
                "opc_cli._video.write_finder_comment", return_value=False
            ):
                path = douyin.download_video(
                    "https://www.douyin.com/video/123",
                    str(output_dir),
                    cookies="cookies.txt",
                )

        self.assertEqual(path, str(downloaded))
        command = run.call_args_list[1].args[0]
        self.assertIn("--merge-output-format", command)
        self.assertIn("--remux-video", command)
        self.assertIn("mp4", command)
        self.assertIn("--cookies", command)
        self.assertIn("cookies.txt", command)
        # 原链接 / 作者 / 发布信息应被写入 MP4 元数据。
        self.assertIn("--embed-metadata", command)
        self.assertIn("--parse-metadata", command)
        parse_index = command.index("--parse-metadata")
        comment_arg = command[parse_index + 1]
        self.assertIn("%(webpage_url)s", comment_arg)
        self.assertIn("%(uploader)s", comment_arg)
        self.assertIn("%(upload_date", comment_arg)
        self.assertTrue(comment_arg.endswith(":%(meta_comment)s"))
        self.assertEqual(command[-1], "https://www.douyin.com/video/123")

    def test_download_video_surfaces_ytdlp_error(self):
        version = subprocess.CompletedProcess(["yt-dlp", "--version"], 0)
        failed = subprocess.CompletedProcess(["yt-dlp"], 1, stdout="", stderr="access denied")
        with tempfile.TemporaryDirectory() as temporary:
            with patch("opc_cli._video.subprocess.run", side_effect=[version, failed]):
                with self.assertRaisesRegex(douyin.DouyinDownloadError, "access denied"):
                    douyin.download_video("https://www.douyin.com/video/123", temporary)

    def test_cli_uses_default_folder_and_shared_cookie_setting(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            output_file = output_dir / "video.mp4"
            with patch.dict(
                os.environ,
                {"DOUYIN_FOLDER": str(output_dir), "YT_DLP_COOKIES": "cookies.txt"},
                clear=False,
            ), patch("opc_cli.media.download_douyin_video", return_value=str(output_file)) as download:
                result = runner.invoke(cli.app, ["media", "download", "https://www.douyin.com/video/123"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(str(output_file), result.output)
        self.assertEqual(
            download.call_args.args,
            ("https://www.douyin.com/video/123", str(output_dir), "cookies.txt"),
        )

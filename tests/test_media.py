"""统一媒体下载（opc media download）的离线单元测试。"""

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from opc_cli import cli, media
from opc_cli.media import MediaError, detect_platform


class DetectPlatformTests(unittest.TestCase):
    def test_detects_supported_platforms(self):
        cases = {
            "https://www.bilibili.com/video/BV1xx": "bilibili",
            "https://b23.tv/abc123": "bilibili",
            "https://www.douyin.com/video/123": "douyin",
            "https://x.com/i/status/123": "x",
            "https://twitter.com/i/status/123": "x",
            "https://music.163.com/song?id=123": "netease",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(detect_platform(url), expected)

    def test_unknown_platform_raises_with_supported_list(self):
        with self.assertRaises(MediaError) as caught:
            detect_platform("https://example.com/video/123")
        self.assertIn("bilibili", str(caught.exception))
        self.assertIn("netease", str(caught.exception))


class MediaDownloadCliTests(unittest.TestCase):
    def test_netease_with_summarize_is_rejected(self):
        result = CliRunner().invoke(
            cli.app,
            ["media", "download", "https://music.163.com/song?id=1", "--summarize"],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("不支持 --summarize", result.output)

    def test_pipeline_flags_require_summarize(self):
        result = CliRunner().invoke(
            cli.app,
            ["media", "download", "https://www.bilibili.com/video/BV1xx", "--skip-download"],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("--summarize", result.output)

    def test_unknown_platform_is_rejected(self):
        result = CliRunner().invoke(
            cli.app,
            ["media", "download", "https://example.com/video/123"],
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("无法识别", result.output)

    def test_bilibili_summarize_delegates_to_bili_pipeline(self):
        with patch("opc_cli.media.bili.run_bili") as run_bili:
            result = CliRunner().invoke(
                cli.app,
                ["media", "download", "https://www.bilibili.com/video/BV1xx", "--summarize"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            run_bili.call_args.kwargs["url"], "https://www.bilibili.com/video/BV1xx"
        )

    def test_douyin_summarize_delegates_to_bili_pipeline(self):
        with patch("opc_cli.media.bili.run_bili") as run_bili:
            result = CliRunner().invoke(
                cli.app,
                ["media", "download", "https://www.douyin.com/video/123", "--summarize"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            run_bili.call_args.kwargs["url"], "https://www.douyin.com/video/123"
        )

    def test_bilibili_audio_only_delegates_to_bili_mp3(self):
        with patch("opc_cli.media.bili.run_bili") as run_bili:
            result = CliRunner().invoke(
                cli.app,
                [
                    "media",
                    "download",
                    "https://www.bilibili.com/video/BV1xx",
                    "--audio-only",
                    "--bitrate",
                    "320",
                ],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(run_bili.call_args.kwargs["audio_only"])
        self.assertEqual(run_bili.call_args.kwargs["bitrate"], 320)

    def test_netease_download_delegates_to_run_music(self):
        with patch("opc_cli.media.run_music") as run_music:
            result = CliRunner().invoke(
                cli.app,
                ["media", "download", "https://music.163.com/song?id=123"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            run_music.call_args.kwargs["url"], "https://music.163.com/song?id=123"
        )

    def test_douyin_download_delegates_to_mp4_downloader(self):
        with patch("opc_cli.media.download_douyin_video", return_value="/tmp/out.mp4"):
            result = CliRunner().invoke(
                cli.app,
                ["media", "download", "https://www.douyin.com/video/123"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("已保存 MP4", result.output)


if __name__ == "__main__":
    unittest.main()

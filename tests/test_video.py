"""Qwen3-VL 视频理解命令的离线单元测试。"""

import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from opc_cli import cli
from opc_cli import _video
from opc_cli.config import get_video_config
from opc_cli.video import VideoUnderstandingError, encode_video, understand_video


class WriteFinderCommentTests(unittest.TestCase):
    def test_write_finder_comment_skips_off_macos(self):
        with patch("opc_cli._video.sys.platform", "linux"), patch(
            "opc_cli._video.subprocess.run"
        ) as run:
            self.assertFalse(_video.write_finder_comment("/tmp/video.mp4"))
        run.assert_not_called()

    def test_write_finder_comment_copies_embedded_comment_on_macos(self):
        ffprobe = subprocess.CompletedProcess(
            ["ffprobe"], 0, stdout="来源：url ｜ 作者：a ｜ 发布：2024-12-02\n", stderr=""
        )
        osascript = subprocess.CompletedProcess(["osascript"], 0, stdout="", stderr="")
        with patch("opc_cli._video.sys.platform", "darwin"), patch(
            "opc_cli._video.subprocess.run", side_effect=[ffprobe, osascript]
        ) as run:
            self.assertTrue(_video.write_finder_comment("/tmp/video.mp4"))

        osascript_call = run.call_args_list[1].args[0]
        self.assertEqual(osascript_call[0], "osascript")
        self.assertEqual(osascript_call[-2], "/tmp/video.mp4")
        self.assertEqual(osascript_call[-1], "来源：url ｜ 作者：a ｜ 发布：2024-12-02")


class VideoUnderstandingTests(unittest.TestCase):
    def test_video_config_uses_aliyun_and_qwen_defaults(self):
        with patch.dict(os.environ, {"ALIYUN_API_KEY": "test-key"}, clear=True):
            self.assertEqual(
                get_video_config(),
                (
                    "test-key",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "qwen3-vl-235b-a22b-instruct",
                ),
            )

    def test_local_video_is_sent_as_video_data_uri(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="分析结果"))]
        )
        client = Mock()
        client.chat.completions.create.return_value = response

        with tempfile.NamedTemporaryFile(suffix=".mp4") as video_file, patch.dict(
            os.environ, {"ALIYUN_API_KEY": "test-key"}, clear=True
        ), patch("openai.OpenAI", return_value=client):
            video_file.write(b"fake-video")
            video_file.flush()
            result = understand_video(video_file.name, prompt="分析运镜")

        self.assertEqual(result, "分析结果")
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "qwen3-vl-235b-a22b-instruct")
        self.assertEqual(request["messages"][0]["content"][1]["text"], "分析运镜")
        video_url = request["messages"][0]["content"][0]["video_url"]["url"]
        self.assertTrue(video_url.startswith("data:video/mp4;base64,"))
        self.assertEqual(
            base64.b64decode(video_url.split(",", 1)[1]),
            b"fake-video",
        )

    def test_remote_video_url_is_forwarded_without_local_file_access(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="远程结果"))]
        )
        client = Mock()
        client.chat.completions.create.return_value = response
        url = "https://example.com/video.mp4"

        with patch.dict(os.environ, {"ALIYUN_API_KEY": "test-key"}, clear=True), patch(
            "openai.OpenAI", return_value=client
        ):
            result = understand_video(url)

        self.assertEqual(result, "远程结果")
        request_url = client.chat.completions.create.call_args.kwargs["messages"][0][
            "content"
        ][0]["video_url"]["url"]
        self.assertEqual(request_url, url)

    def test_unsupported_video_format_has_clear_error(self):
        with tempfile.NamedTemporaryFile(suffix=".txt") as video_file:
            with self.assertRaisesRegex(VideoUnderstandingError, "不支持的视频格式"):
                encode_video(video_file.name)

    def test_cli_writes_analysis_to_output_file(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = os.path.join(temp_dir, "analysis.txt")
            with patch("opc_cli.cli.load_env"), patch(
                "opc_cli.cli.understand_video", return_value="镜头从低角度向上推进"
            ) as understand:
                result = runner.invoke(
                    cli.app,
                    [
                        "video",
                        "input.mp4",
                        "-p",
                        "分析镜头运动",
                        "-o",
                        output,
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(
                Path(output).read_text(encoding="utf-8"), "镜头从低角度向上推进\n"
            )
            understand.assert_called_once_with(
                video="input.mp4",
                prompt="分析镜头运动",
                model="",
                max_tokens=4096,
                temperature=0.7,
            )


if __name__ == "__main__":
    unittest.main()

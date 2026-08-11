"""音乐理解命令的离线单元测试。"""

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from opc_cli import audio, cli


class _FakeResponse:
    status_code = 200

    class output:
        class choices:
            class _Choice:
                class message:
                    content = [{"text": "这是一首电子音乐。"}]

            _Choice = _Choice

            @classmethod
            def __class_getitem__(cls, index):
                return cls._Choice()


class AudioUnderstandingTests(unittest.TestCase):
    def test_analyze_audio_uses_base64_audio_only_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "song.m4a"
            audio_path.write_bytes(b"audio-bytes")

            with patch.dict(
                os.environ,
                {"ALIYUN_API_KEY": "test-key", "AUDIO_MODEL": audio.DEFAULT_AUDIO_MODEL},
                clear=False,
            ), patch.object(
                audio.dashscope.MultiModalConversation,
                "call",
                return_value=_FakeResponse(),
            ) as call:
                result = audio.analyze_audio(str(audio_path))

        self.assertEqual(result, "这是一首电子音乐。")
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "test-key")
        self.assertEqual(kwargs["model"], audio.DEFAULT_AUDIO_MODEL)
        message = kwargs["messages"][0]
        self.assertEqual(message["role"], "user")
        self.assertEqual(
            message["content"][0]["audio"],
            "data:;base64," + base64.b64encode(b"audio-bytes").decode("ascii"),
        )

    def test_cli_prints_and_saves_analysis(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "song.mp3"
            output_path = Path(temporary) / "nested" / "analysis.txt"
            audio_path.write_bytes(b"audio")

            with patch("opc_cli.cli.analyze_audio", return_value="音乐分析结果") as analyze:
                result = runner.invoke(
                    cli.app,
                    ["audio", str(audio_path), "-o", str(output_path)],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("音乐分析结果", result.output)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "音乐分析结果\n")
            analyze.assert_called_once_with(str(audio_path), model="")


if __name__ == "__main__":
    unittest.main()

"""OPC 两级命令层级（模态 + 动词）与引擎分发的离线单元测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from opc_cli import cli

_MODALITY_GROUPS = ("media", "music", "image", "video", "speech")
_TOOL_COMMANDS = ("local-tts", "check-api", "comfyui", "aigate", "news")


class CliHierarchyTests(unittest.TestCase):
    def test_root_help_lists_groups_and_tool_commands(self):
        result = CliRunner().invoke(cli.app, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        for name in _MODALITY_GROUPS + _TOOL_COMMANDS:
            self.assertIn(name, result.output)
        # 旧的平铺一级命令不再出现在帮助中
        for removed in ("bili", "douyin", "music-gen", "asr", "audio", "tts",
                        "read-img", "gpt-img", "x"):
            self.assertNotIn(f" {removed} ", result.output)

    def test_bare_modality_commands_show_subcommand_help(self):
        for group in _MODALITY_GROUPS:
            with self.subTest(group=group):
                result = CliRunner().invoke(cli.app, [group])
                # no_args_is_help：无参数时展示子命令帮助（typer 可能以 0 或 2 退出）
                self.assertIn(result.exit_code, (0, 2), result.output)
                self.assertIn("--help", result.output)

    def test_speech_tts_lists_subcommands(self):
        result = CliRunner().invoke(cli.app, ["speech", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("tts", result.output)
        self.assertIn("asr", result.output)

    def test_music_group_lists_verbs(self):
        result = CliRunner().invoke(cli.app, ["music", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        for verb in ("understand", "beats", "generate"):
            self.assertIn(verb, result.output)


class EngineDispatchTests(unittest.TestCase):
    def test_speech_tts_rejects_unknown_engine(self):
        result = CliRunner().invoke(
            cli.app, ["speech", "tts", "你好", "--engine", "local"]
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("qwen-tts", result.output)

    def test_speech_tts_defaults_to_qwen_engine(self):
        with patch("opc_cli.cli.load_env"), patch(
            "opc_cli.cli.text_to_speech"
        ) as text_to_speech:
            result = CliRunner().invoke(cli.app, ["speech", "tts", "hello"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(text_to_speech.call_args.kwargs["engine"], "qwen-tts")

    def test_image_generate_rejects_unknown_engine(self):
        result = CliRunner().invoke(
            cli.app, ["image", "generate", "猫", "--engine", "foo"]
        )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("qwen / gpt-image", result.output)

    def test_image_generate_defaults_to_qwen_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_file = Path(temporary) / "out.png"
            output_file.write_bytes(b"png")
            with patch("opc_cli.cli.load_env"), patch(
                "opc_cli.cli.get_image_config",
                return_value=("key", "qwen-image-3.0"),
            ), patch(
                "opc_cli.cli.generate_image",
                return_value={"image_urls": ["https://example.com/a.png"]},
            ) as generate, patch(
                "opc_cli.cli.download_image", return_value=str(output_file)
            ):
                result = CliRunner().invoke(
                    cli.app, ["image", "generate", "一只猫", "-o", str(output_file)]
                )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(generate.call_args.kwargs["model"], "qwen-image-3.0")

    def test_image_generate_gpt_engine_via_codex(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_file = Path(temporary) / "gpt.png"
            output_file.write_bytes(b"png")
            with patch("opc_cli.cli.load_env"), patch(
                "opc_cli.cli._codex_generate", return_value=[str(output_file)]
            ) as generate:
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "image",
                        "generate",
                        "海报",
                        "--engine",
                        "gpt-image",
                        "--no-enhance",
                        "-o",
                        str(output_file),
                    ],
                )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(str(output_file), result.output)
            self.assertEqual(
                generate.call_args.kwargs,
                {
                    "prompt": "海报",
                    "output": str(output_file),
                    "size": "2:3",
                    "n": 1,
                    "enhance": False,
                    "ref": None,
                    "timeout": 600,
                },
            )

    def test_image_generate_ignores_qwen_only_flags_with_gpt_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_file = Path(temporary) / "gpt.png"
            output_file.write_bytes(b"png")
            with patch("opc_cli.cli.load_env"), patch(
                "opc_cli.cli._codex_generate", return_value=[str(output_file)]
            ):
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "image",
                        "generate",
                        "海报",
                        "--engine",
                        "gpt-image",
                        "--no-enhance",
                        "--no-download",
                        "--seed",
                        "42",
                        "-o",
                        str(output_file),
                    ],
                )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("仅 qwen 引擎生效", result.output)

    def test_image_generate_gpt_engine_failure_raises(self):
        with patch("opc_cli.cli.load_env"), patch(
            "opc_cli.cli._codex_generate",
            side_effect=cli._CodexImageError("codex exec 超时"),
        ):
            result = CliRunner().invoke(
                cli.app,
                ["image", "generate", "海报", "--engine", "gpt-image", "--no-enhance"],
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("codex exec 超时", result.output)


if __name__ == "__main__":
    unittest.main()

"""codex CLI 图像生成（opc image generate --engine gpt-image）的离线单元测试。"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opc_cli.codex_image import (
    CodexImageError,
    _output_paths,
    _parse_version,
    _size_hint,
    codex_available,
    generate_with_codex,
)


class SizeHintTests(unittest.TestCase):
    def test_aspect_ratios(self):
        self.assertEqual(_size_hint("16:9"), "横版构图（16:9）")
        self.assertEqual(_size_hint("2:3"), "竖版构图（2:3）")
        self.assertEqual(_size_hint("1:1"), "方形构图（1:1）")
        self.assertEqual(_size_hint(""), "方形构图（1:1）")

    def test_pixel_sizes(self):
        self.assertEqual(_size_hint("1024*1536"), "竖版，分辨率约 1024×1536")
        self.assertEqual(_size_hint("2048*1152"), "横版，分辨率约 2048×1152")

    def test_unparsable_size_passes_through(self):
        self.assertEqual(_size_hint("weird"), "画面比例 weird")


class VersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(_parse_version("codex-cli 0.147.0"), (0, 147, 0))
        self.assertEqual(_parse_version("codex-cli 0.146"), (0, 146))
        self.assertEqual(_parse_version("no version"), (0, 0, 0))

    def test_codex_available_missing_binary(self):
        with patch("opc_cli.codex_image.shutil.which", return_value=None):
            self.assertFalse(codex_available())

    def test_codex_available_with_sufficient_version(self):
        version = subprocess.CompletedProcess(["codex", "--version"], 0, stdout="codex-cli 0.147.0\n")
        with patch("opc_cli.codex_image.shutil.which", return_value="/usr/bin/codex"), patch(
            "opc_cli.codex_image.subprocess.run", return_value=version
        ):
            self.assertTrue(codex_available())

    def test_codex_available_rejects_old_version(self):
        version = subprocess.CompletedProcess(["codex", "--version"], 0, stdout="codex-cli 0.120.0\n")
        with patch("opc_cli.codex_image.shutil.which", return_value="/usr/bin/codex"), patch(
            "opc_cli.codex_image.subprocess.run", return_value=version
        ):
            self.assertFalse(codex_available())


class OutputPathTests(unittest.TestCase):
    def test_single_keeps_path(self):
        self.assertEqual(_output_paths("out/a.png", 1), ["out/a.png"])

    def test_multiple_appends_index(self):
        self.assertEqual(
            _output_paths("out/a.png", 3),
            ["out/a_1.png", "out/a_2.png", "out/a_3.png"],
        )


class GenerateWithCodexTests(unittest.TestCase):
    def test_missing_codex_raises(self):
        with patch("opc_cli.codex_image.shutil.which", return_value=None):
            with self.assertRaises(CodexImageError) as caught:
                generate_with_codex("一只猫", "/tmp/out.png")
        self.assertIn("codex CLI", str(caught.exception))

    def test_successful_single_generation(self):
        version = subprocess.CompletedProcess(
            ["codex", "--version"], 0, stdout="codex-cli 0.147.0\n"
        )

        with tempfile.TemporaryDirectory() as temporary:
            output = str(Path(temporary) / "out.png")
            Path(output).write_bytes(b"png")

            def fake_run(cmd, **kwargs):
                # 第一次是版本检查；exec 调用时把最终回复写入 -o 指定的文件
                if "-o" in cmd:
                    last_path = cmd[cmd.index("-o") + 1]
                    Path(last_path).write_text(
                        json.dumps({"image_path": output}), encoding="utf-8"
                    )
                    return subprocess.CompletedProcess(cmd, 0)
                return version

            with patch("opc_cli.codex_image.shutil.which", return_value="/usr/bin/codex"), patch(
                "opc_cli.codex_image.subprocess.run", side_effect=fake_run
            ) as run:
                paths = generate_with_codex(
                    "一只猫", output, size="16:9", enhance=False, timeout=60
                )
            self.assertEqual(paths, [output])
            self.assertEqual(run.call_args.kwargs["timeout"], 60)
            # 提示词应包含工具名与保存指令
            prompt = run.call_args.args[0][-1]
            self.assertIn("image_gen__imagegen", prompt)
            self.assertIn("横版构图（16:9）", prompt)
            self.assertIn(output, prompt)
            self.assertIn('{"image_path"', prompt)

    def test_timeout_raises(self):
        version = subprocess.CompletedProcess(
            ["codex", "--version"], 0, stdout="codex-cli 0.147.0\n"
        )
        with patch("opc_cli.codex_image.shutil.which", return_value="/usr/bin/codex"), patch(
            "opc_cli.codex_image.subprocess.run",
            side_effect=[version, subprocess.TimeoutExpired("codex", 60)],
        ):
            with self.assertRaises(CodexImageError) as caught:
                generate_with_codex("一只猫", "/tmp/out.png", timeout=60)
        self.assertIn("超时", str(caught.exception))

    def test_missing_result_path_raises(self):
        version = subprocess.CompletedProcess(
            ["codex", "--version"], 0, stdout="codex-cli 0.147.0\n"
        )
        with patch("opc_cli.codex_image.shutil.which", return_value="/usr/bin/codex"), patch(
            "opc_cli.codex_image.subprocess.run",
            side_effect=[version, subprocess.CompletedProcess(["codex"], 0)],
        ):
            with self.assertRaises(CodexImageError) as caught:
                generate_with_codex("一只猫", "/tmp/out.png")
        self.assertIn("未返回结构化结果", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

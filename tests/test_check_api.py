import os
import unittest
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from opc_cli import cli
from opc_cli.check_api import (
    CHECK_MAP,
    CheckResult,
    CommandAvailability,
    get_command_availability,
)
from opc_cli.config import (
    get_asr_config,
    get_image_config,
    get_llm_config,
    get_music_gen_config,
    get_qwen_tts_config,
)


class CheckApiTests(unittest.TestCase):
    def test_empty_environment_marks_keyed_commands_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            availability = {
                item.command: item for item in get_command_availability()
            }

        self.assertEqual(availability["speech asr"].status, "不可用")
        self.assertEqual(availability["music understand"].status, "不可用")
        self.assertEqual(availability["speech tts"].status, "不可用")
        self.assertEqual(availability["local-tts"].status, "可用")
        self.assertEqual(availability["music beats"].status, "可用")
        self.assertEqual(availability["media download"].status, "部分可用")

    def test_provider_keys_enable_the_expected_commands(self):
        env = {
            "ALIYUN_API_KEY": "aliyun-test-key",
            "DEEPSEEK_API_KEY": "deepseek-test-key",
            "GPT_IMAGE_API_KEY": "gpt-image-test-key",
            "AIGATE_TOKEN": "aigate-test-token",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "opc_cli.check_api._codex_available", return_value=True
        ):
            availability = {
                item.command: item for item in get_command_availability()
            }

        self.assertEqual(availability["speech asr"].status, "可用")
        self.assertEqual(availability["image generate"].status, "可用")
        self.assertEqual(availability["media download"].status, "可用")
        self.assertEqual(availability["aigate"].status, "可用")
        self.assertEqual(availability["music understand"].status, "可用")
        self.assertEqual(availability["music generate"].status, "可用")

    def test_minimax_key_alone_enables_music_generation(self):
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "minimax-test-key"},
            clear=True,
        ):
            availability = {
                item.command: item for item in get_command_availability()
            }

        self.assertEqual(availability["music generate"].status, "可用")
        self.assertIn("MiniMax Music", availability["music generate"].detail)

    def test_check_map_includes_all_dashscope_audio_checks(self):
        self.assertIn("deepseek", CHECK_MAP)
        self.assertIn("audio", CHECK_MAP)
        self.assertIn("qwen-tts", CHECK_MAP)

    def test_check_api_does_not_run_deepseek_twice_for_compatibility_alias(self):
        from opc_cli.check_api import run_check_api

        check = Mock(
            return_value=CheckResult("DeepSeek (LLM)", False, "missing")
        )
        with patch("opc_cli.check_api.load_env"), patch(
            "opc_cli.check_api.CHECK_MAP",
            {"llm": check, "deepseek": check},
        ):
            run_check_api()

        self.assertEqual(check.call_count, 1)

    def test_check_api_prints_command_availability(self):
        runner = CliRunner()
        availability = [
            CommandAvailability("asr", "可用", "ALIYUN_API_KEY", "使用 ALIYUN_API_KEY"),
            CommandAvailability("audio", "不可用", "ALIYUN_API_KEY", "缺少 ALIYUN_API_KEY"),
        ]
        with patch("opc_cli.cli.load_env") as load_env, patch(
            "opc_cli.cli.get_command_availability", return_value=availability
        ), patch(
            "opc_cli.cli.run_check_api",
            return_value=[CheckResult("LLM", True, "test", 1)],
        ):
            result = runner.invoke(cli.app, ["check-api", "--only", "llm"])

        self.assertEqual(result.exit_code, 0, result.output)
        load_env.assert_called_once_with(None)
        self.assertIn("opc asr", result.output)
        self.assertIn("可用命令: 1/2", result.output)
        self.assertIn("API 连通性检查", result.output)

    def test_aliyun_key_is_shared_by_asr_image_and_qwen_tts(self):
        env = {
            "ALIYUN_API_KEY": "aliyun-test-key",
            "ASR_MODEL": "asr-test-model",
            "IMAGE_MODEL": "image-test-model",
            "QWEN_TTS_MODEL": "tts-test-model",
        }
        with patch.dict(os.environ, env, clear=True):
            asr_key, asr_model = get_asr_config()
            image_key, image_model = get_image_config()
            tts_key, tts_model = get_qwen_tts_config()

        self.assertEqual((asr_key, asr_model), ("aliyun-test-key", "asr-test-model"))
        self.assertEqual((image_key, image_model), ("aliyun-test-key", "image-test-model"))
        self.assertEqual((tts_key, tts_model), ("aliyun-test-key", "tts-test-model"))

    def test_music_gen_uses_beijing_workspace_endpoint(self):
        env = {
            "ALIYUN_API_KEY": "aliyun-test-key",
            "MUSIC_GEN_WORKSPACE_ID": "workspace123",
            "MUSIC_GEN_MODEL": "fun-music-v1",
        }
        with patch.dict(os.environ, env, clear=True):
            key, base_url, model = get_music_gen_config()

        self.assertEqual(key, "aliyun-test-key")
        self.assertEqual(
            base_url,
            "https://workspace123.cn-beijing.maas.aliyuncs.com/api/v1",
        )
        self.assertEqual(model, "fun-music-v1")

    def test_music_gen_uses_minimax_free_defaults(self):
        with patch.dict(
            os.environ,
            {"MINIMAX_API_KEY": "minimax-test-key"},
            clear=True,
        ):
            key, base_url, model = get_music_gen_config("minimax")

        self.assertEqual(key, "minimax-test-key")
        self.assertEqual(base_url, "https://api.minimaxi.com")
        self.assertEqual(model, "music-3.0-free")

    def test_music_gen_provider_environment_selects_minimax(self):
        with patch.dict(
            os.environ,
            {
                "MUSIC_GEN_PROVIDER": "minimax",
                "MINIMAX_API_KEY": "minimax-test-key",
            },
            clear=True,
        ):
            key, base_url, model = get_music_gen_config()

        self.assertEqual(key, "minimax-test-key")
        self.assertEqual(base_url, "https://api.minimaxi.com")
        self.assertEqual(model, "music-3.0-free")

    def test_default_tts_does_not_require_zhipu_key(self):
        runner = CliRunner()
        with patch("opc_cli.cli.load_env"), patch(
            "opc_cli.cli.get_api_config",
            side_effect=AssertionError("default Qwen TTS should not load Zhipu config"),
        ), patch("opc_cli.cli.text_to_speech") as text_to_speech:
            result = runner.invoke(cli.app, ["speech", "tts", "hello"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(text_to_speech.call_args.kwargs["engine"], "qwen-tts")

    def test_deepseek_key_replaces_llm_api_key(self):
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "deepseek-test-key"},
            clear=True,
        ):
            api_key, base_url, model = get_llm_config()

        self.assertEqual(api_key, "deepseek-test-key")
        self.assertEqual(base_url, "https://api.deepseek.com")
        self.assertEqual(model, "deepseek-v4-flash")

    def test_removed_function_keys_are_not_used_as_fallbacks(self):
        env = {
            "LLM_API_KEY": "old-llm-key",
            "VISION_API_KEY": "old-vision-key",
            "ASR_API_KEY": "old-asr-key",
            "IMAGE_API_KEY": "old-image-key",
            "QWEN_TTS_API_KEY": "old-tts-key",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "opc_cli.check_api._codex_available", return_value=False
        ):
            availability = {
                item.command: item for item in get_command_availability()
            }

        self.assertEqual(availability["news"].status, "不可用")
        self.assertEqual(availability["speech asr"].status, "不可用")
        self.assertEqual(availability["image generate"].status, "不可用")
        self.assertEqual(availability["music generate"].status, "不可用")
        self.assertEqual(availability["speech tts"].status, "不可用")

    def test_codex_cli_alone_enables_gpt_image_engine(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "opc_cli.check_api._codex_available", return_value=True
        ):
            availability = {
                item.command: item for item in get_command_availability()
            }

        self.assertEqual(availability["image generate"].status, "部分可用")
        self.assertIn("codex CLI", availability["image generate"].detail)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from opc_cli import cli
from opc_cli.music_gen import download_music, generate_music


def _music_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "output": {
            "audio": {"url": "https://example.com/song.wav"},
            "extra_info": {"lyrics": "[verse]\nhello"},
        },
        "usage": {"duration": 42},
        "request_id": "music-request",
    }
    return response


def _minimax_music_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "data": {
            "audio": "https://example.com/minimax-song.mp3",
            "status": 2,
        },
        "extra_info": {"music_duration": 42000},
        "trace_id": "minimax-request",
        "base_resp": {"status_code": 0, "status_msg": "success"},
    }
    return response


class MusicGenerationTests(unittest.TestCase):
    @patch("opc_cli.cli.download_music", return_value="/tmp/minimax.mp3")
    @patch(
        "opc_cli.cli.generate_music",
        return_value={"audio_url": "https://example.com/song.mp3"},
    )
    @patch(
        "opc_cli.cli.get_music_gen_config",
        return_value=("minimax-test-key", "https://api.minimaxi.com", "music-3.0"),
    )
    @patch("opc_cli.cli.load_env")
    def test_cli_selects_minimax_provider(
        self, load_env, get_config, generate, download
    ):
        result = CliRunner().invoke(
            cli.app,
            [
                "music",
                "generate",
                "梦幻电子流行",
                "--provider",
                "minimax",
                "-o",
                "/tmp/minimax.mp3",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        get_config.assert_called_once_with("minimax")
        self.assertEqual(generate.call_args.kwargs["provider"], "minimax")
        self.assertIsNone(generate.call_args.kwargs["lyrics_optimizer"])
        download.assert_called_once_with(
            "https://example.com/song.mp3", "/tmp/minimax.mp3"
        )

    @patch("opc_cli.music_gen.requests.post")
    def test_generates_minimax_music_with_prompt_only(self, post):
        post.return_value = _minimax_music_response()

        result = generate_music(
            provider="minimax",
            prompt="梦幻电子流行，明亮女声，适合夜晚城市漫步",
            api_key="minimax-test-key",
            base_url="https://api.minimaxi.com",
            model="music-3.0",
            format="mp3",
        )

        self.assertEqual(
            post.call_args.args[0],
            "https://api.minimaxi.com/v1/music_generation",
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer minimax-test-key",
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "music-3.0")
        self.assertEqual(body["prompt"], "梦幻电子流行，明亮女声，适合夜晚城市漫步")
        self.assertTrue(body["lyrics_optimizer"])
        self.assertEqual(body["output_format"], "url")
        self.assertEqual(
            body["audio_setting"],
            {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"},
        )
        self.assertTrue(body["is_instrumental"] is False)
        self.assertEqual(result["audio_url"], "https://example.com/minimax-song.mp3")
        self.assertEqual(result["duration"], 42)
        self.assertEqual(result["request_id"], "minimax-request")

    @patch("opc_cli.music_gen.requests.post")
    def test_minimax_instrumental_does_not_send_lyrics_optimizer_or_gender(self, post):
        post.return_value = _minimax_music_response()

        generate_music(
            provider="minimax",
            prompt="电影感钢琴与弦乐，温暖收束",
            is_instrumental=True,
            gender="male",
            api_key="minimax-test-key",
            model="music-3.0",
        )

        body = post.call_args.kwargs["json"]
        self.assertTrue(body["is_instrumental"])
        self.assertNotIn("lyrics_optimizer", body)
        self.assertNotIn("gender", body)

    @patch("opc_cli.music_gen.requests.post")
    def test_minimax_base_url_with_v1_is_not_duplicated(self, post):
        post.return_value = _minimax_music_response()

        generate_music(
            provider="minimax",
            prompt="短歌",
            api_key="minimax-test-key",
            base_url="https://api.minimaxi.com/v1",
            model="music-3.0",
        )

        self.assertEqual(
            post.call_args.args[0],
            "https://api.minimaxi.com/v1/music_generation",
        )

    def test_minimax_validates_prompt_and_lyrics_limits(self):
        with self.assertRaisesRegex(ValueError, "prompt 最多 2000"):
            generate_music(
                provider="minimax",
                prompt="x" * 2001,
                api_key="minimax-test-key",
                model="music-3.0",
            )

        with self.assertRaisesRegex(ValueError, "lyrics 最多 3500"):
            generate_music(
                provider="minimax",
                lyrics="x" * 3501,
                api_key="minimax-test-key",
                model="music-3.0",
            )

    @patch("opc_cli.music_gen.requests.post")
    def test_generates_song_with_prompt_and_voice_gender(self, post):
        post.return_value = _music_response()

        result = generate_music(
            prompt="夏日清新民谣，木吉他伴奏",
            api_key="aliyun-test-key",
            base_url="https://example.com/api/v1",
            model="fun-music-v1",
            gender="male",
            format="wav",
        )

        self.assertEqual(
            post.call_args.args[0],
            "https://example.com/api/v1/services/audio/music/generation",
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer aliyun-test-key",
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "fun-music-v1")
        self.assertEqual(body["input"]["prompt"], "夏日清新民谣，木吉他伴奏")
        self.assertEqual(body["input"]["gender"], "male")
        self.assertEqual(body["input"]["format"], "wav")
        self.assertFalse(body["input"]["is_instrumental"])
        self.assertEqual(result["audio_url"], "https://example.com/song.wav")
        self.assertEqual(result["duration"], 42)

    @patch("opc_cli.music_gen.requests.post")
    def test_instrumental_mode_omits_gender(self, post):
        post.return_value = _music_response()

        generate_music(
            prompt="宁静的钢琴曲",
            api_key="aliyun-test-key",
            is_instrumental=True,
            gender="male",
        )

        body = post.call_args.kwargs["json"]["input"]
        self.assertTrue(body["is_instrumental"])
        self.assertNotIn("gender", body)

    def test_validates_model_input_requirements(self):
        with self.assertRaises(ValueError):
            generate_music(api_key="aliyun-test-key")

        with self.assertRaises(ValueError):
            generate_music(
                lyrics="歌词",
                api_key="aliyun-test-key",
                model="fun-music-preview",
            )

    @patch("opc_cli.music_gen.requests.get")
    def test_downloads_audio_to_parent_directory(self, get):
        response = Mock()
        response.iter_content.return_value = [b"audio", b"data"]
        get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "nested" / "song.mp3"
            saved = download_music("https://example.com/song.mp3", str(destination))

            self.assertEqual(saved, str(destination))
            self.assertEqual(destination.read_bytes(), b"audiodata")
            get.assert_called_once_with(
                "https://example.com/song.mp3", timeout=120, stream=True
            )


if __name__ == "__main__":
    unittest.main()

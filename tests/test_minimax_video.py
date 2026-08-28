"""MiniMax H3 视频生成的离线单元测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from opc_cli import cli
from opc_cli.config import get_minimax_video_config
from opc_cli.minimax_video import (
    MiniMaxVideoError,
    build_video_payload,
    generate_video,
)


class MiniMaxVideoPayloadTests(unittest.TestCase):
    def test_text_to_video_payload_uses_h3_v2_content_shape(self):
        payload = build_video_payload(
            prompt="A cinematic sunrise over the sea",
            duration=5,
            resolution="2K",
            ratio="16:9",
        )

        self.assertEqual(payload["duration"], 5)
        self.assertEqual(payload["resolution"], "2K")
        self.assertEqual(payload["ratio"], "16:9")
        self.assertEqual(payload["content"], [
            {"type": "text", "text": "A cinematic sunrise over the sea"},
        ])

    def test_reference_payload_uses_roles_and_adaptive_ratio(self):
        payload = build_video_payload(
            prompt="Animate the character naturally",
            duration=6,
            resolution="768P",
            ratio="adaptive",
            first_frame="https://example.com/first.png",
            last_frame="https://example.com/last.png",
            reference_images=["https://example.com/style.png"],
            reference_videos=["https://example.com/motion.mp4"],
            reference_audios=["https://example.com/voice.wav"],
        )

        self.assertEqual(payload["content"][1]["role"], "first_frame")
        self.assertEqual(payload["content"][2]["role"], "last_frame")
        self.assertEqual(payload["content"][3]["role"], "reference_image")
        self.assertEqual(payload["content"][4]["role"], "reference_video")
        self.assertEqual(payload["content"][5]["role"], "reference_audio")
        self.assertNotIn("ratio", payload)

    def test_local_reference_is_rejected_instead_of_sending_unreachable_path(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            with self.assertRaisesRegex(MiniMaxVideoError, "本地文件"):
                build_video_payload(
                    prompt="Animate this",
                    duration=5,
                    resolution="2K",
                    ratio="adaptive",
                    first_frame=image_file.name,
                )


class MiniMaxVideoClientTests(unittest.TestCase):
    def test_config_uses_shared_minimax_key_and_h3_defaults(self):
        with patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}, clear=True):
            self.assertEqual(
                get_minimax_video_config(),
                ("test-key", "https://api.minimaxi.com", "MiniMax-H3"),
            )

    def test_create_poll_and_download_video(self):
        create_response = Mock()
        create_response.json.return_value = {"task_id": "task-123"}
        query_response = Mock()
        query_response.json.return_value = {
            "task": {
                "status": "succeeded",
                "content": {"url": "https://example.com/result.mp4"},
            }
        }
        download_response = Mock()
        download_response.iter_content.return_value = [b"fake", b"-video"]

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "opc_cli.minimax_video.requests.post", return_value=create_response
        ) as post, patch(
            "opc_cli.minimax_video.requests.get",
            side_effect=[query_response, download_response],
        ) as get:
            result = generate_video(
                prompt="A quiet ocean at dawn",
                api_key="test-key",
                base_url="https://api.minimaxi.com/",
                output=str(Path(temp_dir) / "result.mp4"),
                sleep_fn=lambda _seconds: None,
            )
            output_bytes = Path(result["output"]).read_bytes()

        self.assertEqual(result["task_id"], "task-123")
        self.assertEqual(output_bytes, b"fake-video")
        self.assertEqual(
            post.call_args.args[0],
            "https://api.minimaxi.com/v2/video_generation",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["model"],
            "MiniMax-H3",
        )
        self.assertEqual(
            get.call_args_list[0].args[0],
            "https://api.minimaxi.com/v2/query/video_generation/task-123",
        )
        self.assertEqual(get.call_args_list[1].args[0], "https://example.com/result.mp4")

    def test_cli_passes_minimax_video_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = str(Path(temp_dir) / "h3.mp4")
            with patch("opc_cli.cli.load_env"), patch(
                "opc_cli.cli.get_minimax_video_config",
                return_value=("test-key", "https://api.minimaxi.com", "MiniMax-H3"),
            ), patch(
                "opc_cli.cli.generate_video",
                return_value={
                    "task_id": "task-123",
                    "output": output,
                    "duration": 6,
                    "resolution": "768P",
                    "ratio": "16:9",
                },
            ) as generate:
                Path(output).write_bytes(b"video")
                result = CliRunner().invoke(
                    cli.app,
                    [
                        "video",
                        "generate",
                        "海边日出",
                        "--duration",
                        "6",
                        "--resolution",
                        "768P",
                        "--ratio",
                        "16:9",
                        "-o",
                        output,
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(generate.call_args.kwargs["duration"], 6)
            self.assertEqual(generate.call_args.kwargs["resolution"], "768P")
            self.assertEqual(generate.call_args.kwargs["ratio"], "16:9")
            self.assertEqual(generate.call_args.kwargs["output"], output)


if __name__ == "__main__":
    unittest.main()

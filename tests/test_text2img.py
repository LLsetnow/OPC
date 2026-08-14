import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from opc_cli.text2img import encode_image_reference, generate_image


def _response(*images):
    response = Mock()
    response.json.return_value = {
        "output": {
            "choices": [
                {
                    "message": {
                        "content": [{"image": image} for image in images],
                    }
                }
            ]
        },
        "usage": {"width": 1024, "height": 1536, "image_count": len(images)},
        "request_id": "test-request",
    }
    return response


class QwenImageTests(unittest.TestCase):
    @patch("opc_cli.text2img.requests.post")
    def test_text_to_image_uses_qwen_image_model(self, post):
        post.return_value = _response("https://example.com/generated.png")

        result = generate_image(
            prompt="a cat",
            api_key="aliyun-test-key",
            model="qwen-image-3.0",
            size="1:1",
        )

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "qwen-image-3.0")
        self.assertEqual(body["input"]["messages"][0]["content"], [{"text": "a cat"}])
        self.assertEqual(result["image_urls"], ["https://example.com/generated.png"])

    @patch("opc_cli.text2img.requests.post")
    def test_image_editing_sends_image_before_instruction(self, post):
        post.return_value = _response("https://example.com/edited.png")

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "input.png"
            image_path.write_bytes(b"test-image")
            generate_image(
                prompt="change the sky to sunset",
                api_key="aliyun-test-key",
                images=[str(image_path)],
            )

        content = post.call_args.kwargs["json"]["input"]["messages"][0]["content"]
        self.assertEqual(content[-1], {"text": "change the sky to sunset"})
        self.assertEqual(content[0]["image"].split(",", 1)[0], "data:image/png;base64")
        self.assertEqual(
            base64.b64decode(content[0]["image"].split(",", 1)[1]),
            b"test-image",
        )

    def test_local_image_reference_rejects_missing_file(self):
        with self.assertRaises(ValueError):
            encode_image_reference("missing-image.png")

    def test_cli_exposes_image_group_without_ui2vue_or_z_image(self):
        from typer.testing import CliRunner
        from opc_cli.cli import app

        result = CliRunner().invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("image", result.output)
        self.assertNotIn("ui2vue", result.output)
        self.assertNotIn("Z-image", result.output)

        image_help = CliRunner().invoke(app, ["image", "--help"])
        self.assertEqual(image_help.exit_code, 0, image_help.output)
        self.assertIn("understand", image_help.output)
        self.assertIn("generate", image_help.output)
        self.assertNotIn("--enhance", image_help.output)

        generate_help = CliRunner().invoke(app, ["image", "generate", "--help"])
        self.assertEqual(generate_help.exit_code, 0, generate_help.output)
        self.assertIn("--engine", generate_help.output)
        self.assertIn("--enhance", generate_help.output)


if __name__ == "__main__":
    unittest.main()

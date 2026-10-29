"""无影灵构工作站 API 客户端与 CLI 的离线测试。"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from opc_cli import cli
from opc_cli.wuying import WuyingClient, WuyingError, parse_json_body


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self.payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self.payload


class WuyingClientTests(unittest.TestCase):
    def test_request_puts_apikey_in_body_by_default(self):
        session = MagicMock()
        session.post.return_value = FakeResponse({"Success": True, "Data": []})
        client = WuyingClient("secret", session=session)

        result = client.request("DescribeDesktops", {"DisplayType": "Linggou"})

        self.assertEqual(result["Success"], True)
        args = session.post.call_args
        self.assertEqual(args.args[0], "https://wuying-personal-pc.cn-hangzhou.aliyuncs.com")
        self.assertEqual(
            args.kwargs["params"],
            {
                "Action": "DescribeDesktops",
                "Format": "JSON",
                "Version": "2025-11-11",
                "SignatureVersion": "1.0",
            },
        )
        self.assertEqual(args.kwargs["json"], {"DisplayType": "Linggou", "ApiKey": "secret"})
        self.assertEqual(args.kwargs["timeout"], 30)

    def test_request_can_put_apikey_in_query(self):
        session = MagicMock()
        session.post.return_value = FakeResponse({"Code": "Success"})
        client = WuyingClient("secret", api_key_placement="query", session=session)

        client.request("StartDesktop", {"DesktopId": "ws-1"})

        args = session.post.call_args.kwargs
        self.assertEqual(args["params"]["ApiKey"], "secret")
        self.assertEqual(args["json"], {"DesktopId": "ws-1"})

    def test_business_error_does_not_leak_key(self):
        session = MagicMock()
        session.post.return_value = FakeResponse(
            {"Code": "InvalidApiKey", "Message": "secret is invalid"}
        )
        client = WuyingClient("secret", session=session)

        with self.assertRaises(WuyingError) as caught:
            client.request("DescribeDesktops")

        self.assertIn("无影灵构 API 返回失败", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_parse_json_body(self):
        self.assertEqual(parse_json_body('{"DesktopId":"ws-1"}'), {"DesktopId": "ws-1"})
        with self.assertRaises(WuyingError):
            parse_json_body("[]")


class WuyingCliTests(unittest.TestCase):
    def test_request_command_passes_body_and_does_not_print_key(self):
        fake_client = MagicMock()
        fake_client.request.return_value = {"Success": True, "DesktopId": "ws-1"}
        with patch.dict(os.environ, {}, clear=True), patch("opc_cli.cli.load_env"), patch(
            "opc_cli.cli.WuyingClient", return_value=fake_client
        ):
            result = CliRunner().invoke(
                cli.app,
                [
                    "wuying",
                    "--api-key",
                    "secret",
                    "request",
                    "DescribeDesktops",
                    "--body",
                    '{"DisplayType":"Linggou"}',
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn('"DesktopId": "ws-1"', result.output)
        self.assertNotIn("secret", result.output)
        fake_client.request.assert_called_once_with("DescribeDesktops", {"DisplayType": "Linggou"})

    def test_missing_api_key_fails_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("opc_cli.cli.load_env"):
            result = CliRunner().invoke(cli.app, ["wuying", "workstations"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("WUYING_API_KEY", result.output)

    def test_create_requires_explicit_confirmation(self):
        with patch.dict(os.environ, {"WUYING_API_KEY": "secret"}), patch("opc_cli.cli.load_env"), patch(
            "opc_cli.cli.WuyingClient"
        ) as client:
            result = CliRunner().invoke(
                cli.app,
                [
                    "wuying",
                    "create",
                    "--image-id",
                    "img-1",
                    "--product-code",
                    "prm.test",
                ],
            )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("--yes", result.output)
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()

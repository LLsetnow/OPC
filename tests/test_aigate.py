"""云扉 CLI 适配层的离线单元测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opc_cli import aigate


class AigateTests(unittest.TestCase):
    def test_normalize_bearer_token(self):
        self.assertEqual(aigate.normalize_bearer_token("Bearer secret"), "secret")
        self.assertEqual(aigate.normalize_bearer_token(" secret "), "secret")
        with self.assertRaises(aigate.AigateError):
            aigate.normalize_bearer_token("")
        with self.assertRaises(aigate.AigateError):
            aigate.make_comfyui_base_url("comfy.example/path")

    @patch("opc_cli.aigate._aigate_json")
    def test_list_instances_reads_all_pages_before_creation_safety_check(self, request):
        request.side_effect = [
            {"records": [{"instanceId": "one"}] * 20, "total": 21},
            {"records": [{"instanceId": "two"}], "total": 21},
        ]

        records = aigate.list_instances("token")

        self.assertEqual(len(records), 21)
        self.assertEqual(records[-1]["instanceId"], "two")
        self.assertEqual(request.call_count, 2)

    @patch("opc_cli.aigate._aigate_json")
    def test_create_instance_uses_expected_openapi_payload(self, request):
        request.return_value = {"instanceId": "instance-1"}

        created = aigate.create_instance(
            "token", "A100-80GB", "cn-hz", "42", "2"
        )

        self.assertEqual(created["instanceId"], "instance-1")
        self.assertEqual(request.call_args.args[0:2], ("POST", "/instance/start"))
        self.assertEqual(
            request.call_args.args[3],
            {
                "skuName": "A100-80GB",
                "areaName": "cn-hz",
                "count": 1,
                "imageId": 42,
                "imageType": "2",
            },
        )

    def test_prepare_workflow_uploads_and_updates_detected_nodes(self):
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
            "2": {
                "class_type": "KSampler",
                "inputs": {"seed": 1, "steps": 20, "cfg": 1.0, "denoise": 1.0},
            },
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "old prompt"}},
            "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow_path = root / "workflow.json"
            image_path = root / "input.png"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            image_path.write_bytes(b"fake-image")

            with patch("opc_cli.aigate._upload_image", return_value="remote.png"):
                prepared, prefix = aigate._prepare_workflow(
                    str(workflow_path),
                    "https://comfy.example",
                    str(image_path),
                    "new prompt",
                    123,
                    None,
                    None,
                    None,
                    None,
                    None,
                    8,
                    2.5,
                    0.7,
                    "result",
                )

        self.assertEqual(prepared["1"]["inputs"]["image"], "remote.png")
        self.assertEqual(prepared["2"]["inputs"], {"seed": 123, "steps": 8, "cfg": 2.5, "denoise": 0.7})
        self.assertEqual(prepared["3"]["inputs"]["text"], "new prompt")
        self.assertEqual(prepared["4"]["inputs"]["filename_prefix"], "result")
        self.assertEqual(prefix, "result")

    @patch("opc_cli.aigate.get_instance_detail")
    @patch("opc_cli.aigate.list_instances")
    def test_discover_running_comfyui_never_starts_instance(self, list_instances, detail):
        list_instances.return_value = [
            {"instanceId": "stopped", "operationStatus": "3"},
            {"instanceId": "running", "operationStatus": "2"},
        ]
        detail.return_value = {
            "instanceId": "running",
            "instanceName": "ComfyUI",
            "operationStatus": "2",
            "instanceUtilList": [{"name": "ComfyUI", "host": "comfy.example"}],
        }

        found = aigate.discover_running_comfyui("token")

        self.assertEqual(found["instance_id"], "running")
        self.assertEqual(found["base_url"], "https://comfy.example")
        self.assertEqual(detail.call_count, 1)

    @patch("opc_cli.aigate.wait_for_comfyui")
    @patch("opc_cli.aigate.control_instance")
    @patch("opc_cli.aigate._select_comfyui_instance")
    def test_start_waits_for_pending_creation_without_opening_again(
        self, select, control, wait
    ):
        select.return_value = {
            "instanceId": "creating",
            "operationStatus": "1",
            "instanceUtilList": [{"name": "ComfyUI", "host": "comfy.example"}],
        }
        wait.return_value = {"instance_id": "creating", "base_url": "https://comfy.example"}

        aigate.start_comfyui("token", "creating")

        control.assert_not_called()
        wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()

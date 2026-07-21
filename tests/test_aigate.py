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

    def test_list_workflow_files_recurses_and_only_returns_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "nested"
            nested.mkdir()
            (root / "first.json").write_text("{}", encoding="utf-8")
            (nested / "second.json").write_text("{}", encoding="utf-8")
            (root / "notes.txt").write_text("not a workflow", encoding="utf-8")

            workflows = aigate.list_workflow_files(str(root))

        self.assertEqual(
            [path.relative_to(root).as_posix() for path in workflows],
            ["first.json", "nested/second.json"],
        )

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
    def test_list_skus_uses_area_filter(self, request):
        request.return_value = [{"skuName": "4090-24GB-DDR5"}]

        skus = aigate.list_skus("token", "华东一区")

        self.assertEqual(skus, [{"skuName": "4090-24GB-DDR5"}])
        self.assertEqual(request.call_args.args[0:2], ("GET", "/instance/skuList?areaName=%E5%8D%8E%E4%B8%9C%E4%B8%80%E5%8C%BA"))

    @patch("opc_cli.aigate._aigate_json")
    def test_list_skus_queries_all_supported_areas_by_default(self, request):
        request.side_effect = [
            [{"areaName": "华东一区", "skuName": "4090-24GB-DDR5"}],
            [{"areaName": "华东二区", "skuName": "A100-80GB"}],
        ]

        skus = aigate.list_skus("token")

        self.assertEqual(len(skus), 2)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            request.call_args_list[0].args[0:2],
            ("GET", "/instance/skuList?areaName=%E5%8D%8E%E4%B8%9C%E4%B8%80%E5%8C%BA"),
        )
        self.assertEqual(
            request.call_args_list[1].args[0:2],
            ("GET", "/instance/skuList?areaName=%E5%8D%8E%E4%B8%9C%E4%BA%8C%E5%8C%BA"),
        )

    @patch("opc_cli.aigate._aigate_json")
    def test_list_personal_images_reads_all_pages(self, request):
        request.side_effect = [
            {"records": [{"worksId": "one"}] * 20, "total": 21},
            {"records": [{"worksId": "two"}], "total": 21},
        ]

        images = aigate.list_personal_images("token")

        self.assertEqual(len(images), 21)
        self.assertEqual(images[-1]["worksId"], "two")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            request.call_args_list[0].args[0:4],
            ("POST", "/image/page", "token", {"current": 1, "pageSize": 20, "imageType": "3"}),
        )

    @patch("opc_cli.aigate._aigate_json")
    def test_list_community_images_uses_sku_and_area(self, request):
        request.return_value = {"records": [{"worksId": "42"}], "total": 1}

        images = aigate.list_community_images("token", "华东一区", "4090D-48G")

        self.assertEqual(images, [{"worksId": "42"}])
        self.assertEqual(
            request.call_args.args[0:4],
            (
                "POST",
                "/image/page",
                "token",
                {
                    "current": 1,
                    "pageSize": 20,
                    "imageType": "2",
                    "areaName": "华东一区",
                    "skuName": "4090D-48G",
                    "imageName": "",
                    "imageVersion": "",
                },
            ),
        )

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

    def test_prepare_workflow_uploads_video_and_reference_image(self):
        workflow = {
            "30": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
            "33": {"class_type": "VHS_LoadVideo", "inputs": {"video": "old.mp4"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow_path = root / "workflow.json"
            video_path = root / "input.mp4"
            reference_path = root / "reference.png"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            video_path.write_bytes(b"fake-video")
            reference_path.write_bytes(b"fake-image")

            with patch(
                "opc_cli.aigate._upload_input_file",
                side_effect=["remote-reference.png", "remote-video.mp4"],
            ):
                prepared, _ = aigate._prepare_workflow(
                    str(workflow_path),
                    "https://comfy.example",
                    None,
                    None,
                    123,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    video=str(video_path),
                    reference_image=str(reference_path),
                )

        self.assertEqual(prepared["30"]["inputs"]["image"], "remote-reference.png")
        self.assertEqual(prepared["33"]["inputs"]["video"], "remote-video.mp4")

    def test_output_files_collects_images_and_videos(self):
        history = {
            "outputs": {
                "1": {"images": [{"filename": "image.png"}]},
                "2": {"gifs": [{"filename": "video.mp4"}]},
            }
        }

        outputs = aigate._output_files(history)

        self.assertEqual([item["filename"] for item in outputs], ["image.png", "video.mp4"])

    def test_replace_with_vhs_video_combine_preserves_image_audio_and_fps(self):
        workflow = {
            "305": {
                "class_type": "1hew_SaveVideoByImage",
                "inputs": {
                    "fps": ["156", 5],
                    "filename": "video/ComfyUI",
                    "image": ["262", 0],
                    "audio": ["33", 2],
                },
            }
        }

        aigate._replace_with_vhs_video_combine(workflow, "305")

        self.assertEqual(workflow["305"]["class_type"], "VHS_VideoCombine")
        self.assertEqual(workflow["305"]["inputs"]["images"], ["262", 0])
        self.assertEqual(workflow["305"]["inputs"]["frame_rate"], ["156", 5])
        self.assertEqual(workflow["305"]["inputs"]["audio"], ["33", 2])

    def test_safe_error_message_does_not_return_full_error_payload(self):
        message = aigate._safe_error_message(
            {"error": {"type": "prompt_invalid", "message": "Prompt is invalid", "details": "secret"}}
        )

        self.assertEqual(message, "Prompt is invalid")

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

"""云扉 CLI 适配层的离线单元测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from opc_cli import aigate
from opc_cli.scail import build_scail_workflow, unresolved_references


class AigateTests(unittest.TestCase):
    def test_build_scail_workflows_for_two_and_four_clips(self):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "SCAIL2-3clips.json"
        )
        template = json.loads(template_path.read_text(encoding="utf-8"))

        two_clips = build_scail_workflow(template, 2)
        four_clips = build_scail_workflow(template, 4)

        self.assertEqual(
            len([node for node in two_clips.values() if node["class_type"] == "WanSCAILToVideo"]),
            2,
        )
        self.assertEqual(two_clips["217"]["inputs"]["value"], 2)
        self.assertEqual(two_clips["305"]["class_type"], "VHS_VideoCombine")
        self.assertEqual(two_clips["305"]["inputs"]["images"], ["70", 0])
        self.assertNotIn("88", two_clips)
        self.assertEqual(unresolved_references(two_clips), set())

        self.assertEqual(
            len([node for node in four_clips.values() if node["class_type"] == "WanSCAILToVideo"]),
            4,
        )
        self.assertEqual(four_clips["217"]["inputs"]["value"], 4)
        self.assertEqual(four_clips["305"]["inputs"]["images"], ["312", 0])
        self.assertEqual(four_clips["306"]["inputs"]["previous_frames"], ["264", 0])
        self.assertEqual(four_clips["312"]["inputs"]["images.image0"], ["262", 0])
        self.assertEqual(unresolved_references(four_clips), set())

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
    def test_list_instances_reads_all_pages(self, request):
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

    def test_make_comfyui_base_url_strips_query_and_accepts_port(self):
        # 云扉会把 ?token=... 塞进 host（JupyterLab 那条就是）。
        self.assertEqual(
            aigate.make_comfyui_base_url("comfy.example?token=secret"),
            "https://comfy.example",
        )
        self.assertEqual(
            aigate.make_comfyui_base_url("comfy.example:8188"),
            "https://comfy.example:8188",
        )
        self.assertEqual(
            aigate.make_comfyui_base_url("https://comfy.example/"),
            "https://comfy.example",
        )
        with self.assertRaises(aigate.AigateError):
            aigate.make_comfyui_base_url("comfy.example/path")

    def test_describe_instance_status_keeps_unknown_codes_visible(self):
        self.assertEqual(aigate.describe_instance_status("2"), "运行中(2)")
        self.assertEqual(aigate.describe_instance_status("22"), "停止中/网关不可用(22)")
        self.assertEqual(aigate.describe_instance_status("99"), "未知状态(99)")
        self.assertEqual(aigate.describe_instance_status(""), "未知")

    @patch("opc_cli.aigate._select_comfyui_instance")
    def test_discover_reports_actual_status_for_stopped_instance(self, select):
        # 停机实例仍带着 host 返回，必须靠 operationStatus 判定而不是 host。
        select.return_value = {
            "instanceId": "gone",
            "operationStatus": "22",
            "instanceUtilList": [{"name": "ComfyUI", "host": "comfy.example"}],
        }

        with self.assertRaises(aigate.AigateError) as caught:
            aigate.discover_running_comfyui("token", "gone")

        self.assertIn("停止中/网关不可用(22)", str(caught.exception))

    @patch("opc_cli.aigate.get_instance_detail")
    @patch("opc_cli.aigate.list_instances")
    def test_select_prefers_running_instance_over_stopped_one(self, listed, detail):
        listed.return_value = [{"instanceId": "stopped"}, {"instanceId": "running"}]
        detail.side_effect = [
            {
                "instanceId": "stopped",
                "operationStatus": "22",
                "instanceUtilList": [{"name": "ComfyUI", "host": "stopped.example"}],
            },
            {
                "instanceId": "running",
                "operationStatus": "2",
                "instanceUtilList": [{"name": "ComfyUI", "host": "running.example"}],
            },
        ]

        selected = aigate._select_comfyui_instance("token", None)

        self.assertEqual(selected["instanceId"], "running")

    @patch("opc_cli.aigate.probe_comfyui")
    @patch("opc_cli.aigate.get_instance_detail")
    def test_wait_skips_probe_until_running_and_reports_last_status(
        self, detail, probe
    ):
        detail.return_value = {
            "instanceId": "pending",
            "operationStatus": "22",
            "instanceUtilList": [{"name": "ComfyUI", "host": "comfy.example"}],
        }

        with self.assertRaises(aigate.AigateError) as caught:
            aigate.wait_for_comfyui("token", "pending", timeout=1, poll_interval=1)

        # 实例没跑起来时不该浪费探活请求，超时消息要带上最后已知状态。
        probe.assert_not_called()
        self.assertIn("停止中/网关不可用(22)", str(caught.exception))

    @patch("opc_cli.aigate._comfyui_json")
    def test_wait_for_history_survives_transient_poll_failures(self, request):
        request.side_effect = [
            aigate.AigateError("云扉 ComfyUI 连接失败：连接被对端重置"),
            aigate.AigateError("云扉 ComfyUI 请求失败（HTTP 502）"),
            {"p1": {"status": {"completed": True}, "outputs": {"9": {"images": [{"filename": "a.png"}]}}}},
        ]

        with patch("opc_cli.aigate.time.sleep"):
            task = aigate._wait_for_history("https://comfy.example", "p1", 600)

        self.assertEqual(task["outputs"]["9"]["images"][0]["filename"], "a.png")
        self.assertEqual(request.call_count, 3)

    @patch("opc_cli.aigate._comfyui_json")
    def test_wait_for_history_gives_up_after_sustained_failure(self, request):
        request.side_effect = aigate.AigateError("云扉 ComfyUI 连接失败：无法建立连接")
        clock = iter([0.0] + [float(i) for i in range(0, 4000, 10)])

        with patch("opc_cli.aigate.time.sleep"), patch(
            "opc_cli.aigate.time.monotonic", lambda: next(clock)
        ):
            with self.assertRaises(aigate.AigateError) as caught:
                aigate._wait_for_history("https://comfy.example", "p1", 3600)

        self.assertIn("任务可能仍在云端运行", str(caught.exception))

    @patch("opc_cli.aigate._comfyui_json")
    def test_wait_for_history_surfaces_execution_error_detail(self, request):
        request.return_value = {
            "p1": {
                "status": {
                    "status_str": "error",
                    "completed": False,
                    "messages": [
                        [
                            "execution_error",
                            {
                                "node_type": "WanSCAILToVideo",
                                "exception_type": "torch.OutOfMemoryError",
                                "exception_message": "CUDA out of memory",
                            },
                        ]
                    ],
                }
            }
        }

        with patch("opc_cli.aigate.time.sleep"):
            with self.assertRaises(aigate.AigateError) as caught:
                aigate._wait_for_history("https://comfy.example", "p1", 60)

        message = str(caught.exception)
        self.assertIn("WanSCAILToVideo", message)
        self.assertIn("CUDA out of memory", message)

    @patch("opc_cli.aigate._comfyui_json")
    def test_wait_for_history_rejects_completed_run_without_outputs(self, request):
        request.return_value = {"p1": {"status": {"completed": True}, "outputs": {}}}

        with patch("opc_cli.aigate.time.sleep"):
            with self.assertRaises(aigate.AigateError) as caught:
                aigate._wait_for_history("https://comfy.example", "p1", 60)

        self.assertIn("没有产生任何输出", str(caught.exception))

    @patch("opc_cli.aigate._comfyui_json")
    def test_upload_retries_then_succeeds(self, request):
        request.side_effect = [
            aigate.AigateError("云扉 ComfyUI 连接失败：等待响应超时"),
            {"name": "remote (1).png"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "input.png"
            image.write_bytes(b"fake-image")
            with patch("opc_cli.aigate.time.sleep"):
                name = aigate._upload_input_file("https://comfy.example", image)

        self.assertEqual(name, "remote (1).png")
        self.assertEqual(request.call_count, 2)

    def test_upload_timeout_scales_with_file_size(self):
        # 原来固定 60s，250MB 的输入视频必然超时。
        self.assertEqual(aigate._upload_timeout(0), (15, 120))
        self.assertGreater(aigate._upload_timeout(250 * 1024 * 1024)[1], 300)

    @patch("opc_cli.aigate._comfyui_json")
    def test_queue_position_reports_tasks_ahead(self, request):
        request.return_value = {
            "queue_running": [[0, "other-running", {}]],
            "queue_pending": [[1, "ahead", {}], [2, "mine", {}]],
        }

        self.assertEqual(
            aigate._queue_position("https://comfy.example", "mine"),
            "排队中，前面还有 2 个任务",
        )
        self.assertEqual(
            aigate._queue_position("https://comfy.example", "other-running"),
            "正在执行",
        )
        self.assertEqual(aigate._queue_position("https://comfy.example", "gone"), "")

    @patch("opc_cli.aigate._comfyui_json")
    def test_queue_position_is_diagnostic_only(self, request):
        # 队列查询失败不能影响主流程。
        request.side_effect = aigate.AigateError("云扉 ComfyUI 连接失败：无法建立连接")
        self.assertEqual(aigate._queue_position("https://comfy.example", "p1"), "")

    @patch("opc_cli.aigate._send")
    def test_download_rejects_oversize_before_writing(self, send):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.is_redirect = False
        response.is_permanent_redirect = False
        response.ok = True
        response.headers = {"Content-Length": str(200 * 1024 * 1024)}
        send.return_value = response

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            with self.assertRaises(aigate.AigateError) as caught:
                aigate._download_output(
                    "https://comfy.example",
                    {"filename": "huge.mp4"},
                    destination,
                    max_download_mb=100,
                )
            # 超限必须在写盘之前拒绝，不留半个文件。
            self.assertEqual(list(destination.iterdir()), [])

        response.iter_content.assert_not_called()
        self.assertIn("--max-download-mb", str(caught.exception))

    @patch("opc_cli.aigate._send")
    def test_download_streams_to_disk(self, send):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.is_redirect = False
        response.is_permanent_redirect = False
        response.ok = True
        response.headers = {"Content-Length": "10"}
        response.iter_content.return_value = [b"hello", b"world"]
        send.return_value = response

        with tempfile.TemporaryDirectory() as temporary:
            saved = aigate._download_output(
                "https://comfy.example", {"filename": "out.png"}, Path(temporary)
            )
            self.assertEqual(saved.read_bytes(), b"helloworld")

    def test_safe_error_message_reads_apisix_gateway_field(self):
        self.assertEqual(
            aigate._safe_error_message({"error_msg": "404 Route Not Found"}),
            "404 Route Not Found",
        )

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

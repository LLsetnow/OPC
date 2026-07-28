"""构建不同视频切片数量的 SCAIL2 ComfyUI API 工作流。"""

from copy import deepcopy
from typing import Any


class ScailWorkflowError(ValueError):
    """SCAIL2 工作流模板不符合预期结构。"""


def _node(workflow: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = workflow.get(node_id)
    if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
        raise ScailWorkflowError(f"SCAIL2 模板缺少节点 {node_id}。")
    return node


def _remove_nodes(workflow: dict[str, Any], node_ids: set[str]) -> None:
    for node_id in node_ids:
        workflow.pop(node_id, None)


def _set_video_output(workflow: dict[str, Any], images: list[Any]) -> None:
    """使用个人镜像内置的 VideoHelperSuite 保存最终视频。"""
    original_inputs = _node(workflow, "305")["inputs"]
    frame_rate = original_inputs.get("fps") or original_inputs.get("frame_rate")
    audio = original_inputs.get("audio")
    if frame_rate is None:
        raise ScailWorkflowError("节点 305 缺少视频帧率输入。")

    inputs: dict[str, Any] = {
        "frame_rate": frame_rate,
        "loop_count": 0,
        "filename_prefix": "Wan21_SCAIL2",
        "format": "video/h264-mp4",
        "pix_fmt": "yuv420p",
        "crf": 19,
        "save_output": True,
        "save_metadata": True,
        "trim_to_audio": False,
        "pingpong": False,
        "no_preview": False,
        "images": images,
    }
    if audio is not None:
        inputs["audio"] = audio
    workflow["305"] = {
        "inputs": inputs,
        "class_type": "VHS_VideoCombine",
        "_meta": {"title": "Video Combine (SCAIL2)"},
    }


def _clone_clip_chain(
    workflow: dict[str, Any],
    next_node_id: int,
    previous_wan: str,
    previous_decode: str,
    previous_batch: str,
    clip_number: int,
) -> tuple[int, str, str, str]:
    """复制第三段的推理、解码、色彩衔接与批次合并链路。"""
    node_ids = [str(next_node_id + offset) for offset in range(7)]
    wan_id, sampler_id, decode_id, range_id, last_frame_id, color_id, batch_id = node_ids

    wan = deepcopy(_node(workflow, "261"))
    wan["inputs"]["video_frame_offset"] = [previous_wan, 3]
    wan["inputs"]["previous_frames"] = [previous_decode, 0]
    wan["_meta"] = {"title": f"WanSCAILToVideo (clip {clip_number})"}
    workflow[wan_id] = wan

    sampler = deepcopy(_node(workflow, "243"))
    sampler["inputs"]["positive"] = [wan_id, 0]
    sampler["inputs"]["negative"] = [wan_id, 1]
    sampler["inputs"]["latent_image"] = [wan_id, 2]
    sampler["_meta"] = {"title": f"SamplerCustom (clip {clip_number})"}
    workflow[sampler_id] = sampler

    decode = deepcopy(_node(workflow, "264"))
    decode["inputs"]["samples"] = [sampler_id, 0]
    decode["_meta"] = {"title": f"VAE Decode (clip {clip_number})"}
    workflow[decode_id] = decode

    image_range = deepcopy(_node(workflow, "265"))
    image_range["inputs"]["images"] = [decode_id, 0]
    image_range["_meta"] = {"title": f"Get image range (clip {clip_number})"}
    workflow[range_id] = image_range

    last_frame = deepcopy(_node(workflow, "263"))
    last_frame["inputs"]["images"] = [previous_decode, 0]
    last_frame["_meta"] = {"title": f"Get last frame (clip {clip_number - 1})"}
    workflow[last_frame_id] = last_frame

    color = deepcopy(_node(workflow, "260"))
    color["inputs"]["image_target"] = [range_id, 0]
    color["inputs"]["image_ref"] = [last_frame_id, 0]
    color["_meta"] = {"title": f"Transfer color (clip {clip_number})"}
    workflow[color_id] = color

    batch = deepcopy(_node(workflow, "262"))
    batch["inputs"]["images.image0"] = [previous_batch, 0]
    batch["inputs"]["images.image1"] = [color_id, 0]
    batch["_meta"] = {"title": f"Batch images (through clip {clip_number})"}
    workflow[batch_id] = batch
    return next_node_id + 7, wan_id, decode_id, batch_id


def build_scail_workflow(template: dict[str, Any], clips: int) -> dict[str, Any]:
    """从 3clip 模板生成 1 个或多个连续 SCAIL2 分段。"""
    if clips < 1:
        raise ScailWorkflowError("clips 必须至少为 1。")

    workflow = deepcopy(template)
    for node_id in ("114", "115", "261", "305", "217"):
        _node(workflow, node_id)

    # 模板中的节点 88 仅用来预览蒙版视频；移除后避免产生额外的视频文件。
    _remove_nodes(workflow, {"88"})

    if clips == 1:
        _remove_nodes(
            workflow,
            {
                "63", "66", "70", "73", "78", "79", "115", "211", "217",
                "243", "260", "261", "262", "263", "264", "265",
            },
        )
        _node(workflow, "114")["inputs"].update(
            {
                "length": ["156", 6],
                "video_frame_offset": 0,
                # 该值是模型所需的条件帧数，不能设为 0。
                "previous_frame_count": 5,
            }
        )
        _set_video_output(workflow, ["6", 0])
        return workflow

    _node(workflow, "217")["inputs"]["value"] = clips

    if clips == 2:
        _remove_nodes(workflow, {"243", "260", "261", "262", "263", "264", "265"})
        _set_video_output(workflow, ["70", 0])
        return workflow

    previous_wan, previous_decode, previous_batch = "261", "264", "262"
    next_node_id = max(int(node_id) for node_id in workflow if node_id.isdigit()) + 1
    for clip_number in range(4, clips + 1):
        next_node_id, previous_wan, previous_decode, previous_batch = _clone_clip_chain(
            workflow,
            next_node_id,
            previous_wan,
            previous_decode,
            previous_batch,
            clip_number,
        )
    _set_video_output(workflow, [previous_batch, 0])
    return workflow


def unresolved_references(workflow: dict[str, Any]) -> set[str]:
    """返回 API 工作流中不存在的上游节点 ID。"""
    references: set[str] = set()
    for node in workflow.values():
        inputs = node.get("inputs", {}) if isinstance(node, dict) else {}
        for value in inputs.values():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
            ):
                references.add(value[0])
    return references - set(workflow)

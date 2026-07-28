# Qwen 单图编辑（OPC AIGate）

将一张图片提交到 `Qwen+单图编辑-api.json`，并下载生成的 PNG。该工作流的输出可直接作为 SCAIL-2 动作迁移的参考图；不需要鸭鸭图解码流程。

---

## 前置条件

- 已安装 `opc`，并在仓库 `.env` 中配置 `AIGATE_TOKEN`。
- 已启动带 Qwen Image Edit 模型的云扉 ComfyUI 实例。
- 在仓库根目录执行命令；或为工作流和输入文件使用绝对路径。

---

## 提交工作流

提交时**无需读取、解析或修改** `Qwen+单图编辑-api.json` 的完整内容。`opc aigate` 会自动识别工作流中的图片输入节点；只需设置：

- `--image`：输入图片路径。
- `--output`：本地输出**目录**，而不是固定输出文件路径。
- `--timeout`：最大等待时间（秒）。

```bash
opc aigate --run --instance INSTANCE_ID \
  --workflow "workflows/Qwen+单图编辑-api.json" \
  --image "input/firstFrame/<首帧文件名>.png" \
  --output "output/aigate-qwen" \
  --timeout 900
```

完成后，命令会打印下载的 PNG 路径，例如：

```text
output/aigate-qwen/ComfyUI_00042_.png
```

图像生成完成后，直接使用命令返回的 PNG 路径；**无需执行、等待或检查 “Viewed Image”**。只有用户明确要求人工审核图片内容时，才打开图片进行视觉检查。

将该文件直接作为后续 SCAIL-2 工作流的 `--reference-image`：

```bash
opc aigate --run --instance INSTANCE_ID \
  --workflow "workflows/SCAIL2-3clips.json" \
  --video "input/videos/<视频文件名>.mp4" \
  --reference-image "output/aigate-qwen/ComfyUI_00042_.png" \
  --video-output-node 305 \
  --output "output/aigate-scail" \
  --timeout 1800
```

---

## 监视执行日志

从 `opc aigate --start` 的输出中取得 ComfyUI 地址后，可读取当前个人镜像公开的日志：

```bash
COMFYUI_URL="https://<实例地址>"
curl -sS "$COMFYUI_URL/internal/logs" | jq -r . | tail -n 50
```

正常完成时会出现 `Prompt executed in ... seconds`。若出现 `[ERROR]`、`CUDA out of memory` 或 `invalid prompt`，应根据日志中的节点名修复后重新提交。

---

## 注意事项

- `--output` 只指定目录；不要预先假定具体文件名。
- 工作流会将图片最长边缩放到 1280 像素。
- 只有用户明确要求时才审核人物外观、背景与构图；否则直接将输出 PNG 用作视频动作迁移的参考图。

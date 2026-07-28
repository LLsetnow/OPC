# OPC Agent 工作规范

## AIGate / 云扉 ComfyUI

### 资源生命周期

- 凭证只从仓库根目录 `.env` 的 `AIGATE_TOKEN` 读取，绝不在命令输出、文档或提交中回显。
- 创建计费实例前，先查询 `opc aigate --gpus` 与 `opc aigate --images`；只有用户明确要求时才使用 `--start --create`。
- 仅启动已有实例：`opc aigate --start --instance INSTANCE_ID`。
- 执行前用 `opc aigate --status` 确认状态为 `2`（运行中）。除非用户明确要求，不停止或释放实例。
- 任务需要中止时，使用 ComfyUI 原生接口并验证队列：

  ```bash
  curl -sS -X POST "$COMFYUI_URL/interrupt"
  curl -sS "$COMFYUI_URL/queue"
  ```

  `queue_running` 与 `queue_pending` 都为空才表示没有遗留任务。

### Qwen 单图编辑

提交 `workflows/Qwen+单图编辑-api.json` 时，**不需要读取或修改完整工作流 JSON**。只需提供工作流路径及：

- `--image`：输入图片路径；
- `--output`：本地输出目录；
- `--timeout`：最大等待秒数。

```bash
opc aigate --run --instance INSTANCE_ID \
  --workflow "workflows/Qwen+单图编辑-api.json" \
  --image "input/firstFrame/<首帧>.png" \
  --output "output/aigate-qwen" \
  --timeout 900
```

`--output` 是目录，实际 `ComfyUI_*.png` 文件名由服务端生成并由 CLI 打印。除非用户明确要求人工审核，否则直接使用该路径作为 SCAIL-2 的 `--reference-image`，不需要执行 “Viewed Image”。不要使用或提交会对真实人物产生裸体化、性化等不安全编辑的默认或自定义提示词；如需自定义编辑提示词，应先确认该工作流的提示词节点与 CLI 覆盖方式兼容。

### SCAIL-2 视频动作迁移

处理顺序：提取视频首帧 → Qwen 编辑 →（仅在用户要求时审核）→ 以 Qwen 输出为参考图提交 SCAIL-2。输入视频固定按 16 fps 处理。

| 视频时长 | 工作流 |
|---|---|
| ≤ 3 秒 | `workflows/SCAIL2-1clip.json` |
| 3–6 秒 | `workflows/SCAIL2-2clips.json` |
| 6–9 秒 | `workflows/SCAIL2-3clips.json` |
| 9–12 秒 | `workflows/SCAIL2-4clips.json` |
| > 12 秒 | 运行 `.venv/bin/python scripts/generate_scail_workflow.py N` 生成 Nclip |

节点 217 只计算已有分段的长度，修改它不会创建或删除推理分支。速度优先时可估算：`N = max(1, ceil((16 × 视频秒数 - 5) / 45))`。

1/2/4clip 工作流已使用 `VHS_VideoCombine`，可直接提交；重命名后的原始 3clip 工作流保留旧视频输出节点，须附加 `--video-output-node 305`：

```bash
opc aigate --run --instance INSTANCE_ID \
  --workflow "workflows/SCAIL2-3clips.json" \
  --video "input/videos/<视频>.mp4" \
  --reference-image "output/aigate-qwen/<参考图>.png" \
  --video-output-node 305 \
  --output "output/aigate-scail" \
  --timeout 1800
```

### 监控、报错与结果

从 `opc aigate --start` 输出中取得 `COMFYUI_URL`。提交后持续监控日志与队列：

```bash
curl -sS "$COMFYUI_URL/internal/logs" | jq -r . | tail -n 50
curl -sS "$COMFYUI_URL/queue"
```

- 正常进度：`got prompt`、SAM3 `tracking`、采样进度（如 `3/6`）、`Prompt executed in ... seconds`。
- 失败信号：`[ERROR]`、`CUDA out of memory`、`invalid prompt`、缺失自定义节点。
- 遇到可修复错误，先读取节点级错误与日志，修复工作流后再重试；不要盲目重复提交。
- 交付带音轨的 `ComfyUI_*-audio.mp4`。原始 3clip 额外生成的 `Wan21_SCAIL2_*.mp4` 是预览 / mask 视频，不是最终成片。

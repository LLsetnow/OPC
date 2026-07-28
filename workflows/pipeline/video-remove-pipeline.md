# 动作迁移流水线（OPC AIGate）

将输入视频依次经过「提取首帧 → Qwen 图片处理 →（可选人工审核）→ SCAIL-2 动作迁移」，输出带音频的 MP4 视频。Qwen 的处理结果直接作为 SCAIL-2 的参考图，不需要额外的图像或视频解码步骤。

---

## 前置条件

- 已安装 `opc`，并在 `.env` 中配置 `AIGATE_TOKEN`。
- 已启动一个带所需模型和自定义节点的云扉 ComfyUI 实例；SCAIL-2 建议使用 48GB 显存实例。
- 工作流文件位于仓库的 `workflows/` 目录。
- 输入视频位于 `input/videos/` 目录。

---

## 批量处理多个视频（分阶段提交）

当一次要处理多个视频时，**先对所有视频的首帧统一执行 Step 2（Qwen 图片处理），全部完成后再统一执行 Step 3（SCAIL-2 视频生成）**；不要逐个视频地在图像与视频工作流之间来回切换。

原因：Qwen 图像模型与 SCAIL-2 视频模型体积都很大，ComfyUI 在两类工作流之间切换时会反复加载 / 卸载模型。分阶段提交可让每类模型只加载一次，显著减少切换开销：

1. **图像阶段**：遍历所有首帧，逐个提交 `Qwen+单图编辑-api.json`，输出统一放到同一个 Qwen 目录；记录每个首帧（及其对应视频）得到的输出 PNG。
2. **视频阶段**：图像阶段全部完成后，再遍历所有视频，用各自时长对应的 SCAIL-2 工作流提交，参考图使用第 1 步得到的 PNG，输出统一放到同一个 SCAIL 目录。

同一实例上 ComfyUI 按队列串行执行，因此每个阶段内部逐个提交即可；关键是**不要交替**提交图像与视频任务。输出目录名建议以日期开头（如 `output/2026-07-23-aigate-qwen`、`output/2026-07-23-aigate-scail`）便于归档。

---

## Step 0：获取输入视频（可选）

若 `input/videos/` 中已有本地视频文件，直接进入 Step 1。若只有抖音视频链接，先下载到该目录：

```bash
opc douyin \
  "https://www.douyin.com/video/7663055524247118822?modeFrom=userPost&secUid=MS4wLjABAAAAubBZMv-N8jz9cHpD5u5yagiQN9kisi48b_IE7mYwNG8" \
  --cookies "www.douyin.com_cookies.txt" \
  --output-dir "input/videos"
```

将链接替换为目标视频链接，并确保 cookies 文件有效。下载完成后，以 `input/videos/` 中生成的 MP4 文件作为后续步骤的 `<视频文件名>`。

---

## Step 1：提取视频首帧

从 `input/videos/` 选取一个视频，提取首帧到 `input/firstFrame/`：

```bash
ffmpeg -i "input/videos/<视频文件名>.mp4" \
  -frames:v 1 "input/firstFrame/<视频名>_first_frame.png"
```

---

## Step 2：提交 Qwen 图片处理工作流

将首帧提交给 Qwen 单图编辑工作流。输出 PNG 直接用于下一步的参考图。

> 处理多个视频时，见「批量处理多个视频（分阶段提交）」：**先把所有视频的首帧都跑完 Step 2，再统一进入 Step 3**，避免图像 / 视频模型反复切换。

提交时**无需读取、解析或修改** `Qwen+单图编辑-api.json` 的完整内容。`opc aigate` 会自动识别图片输入节点；只需提供以下参数：

- `--image`（或 `-i`）：首帧图片路径。
- `--output`（或 `-o`）：本地输出**目录**；实际 PNG 文件名由 ComfyUI 生成。
- `--timeout`（或 `-t`）：最大等待秒数。

```bash
opc aigate --run --instance INSTANCE_ID \
  -w "workflows/Qwen+单图编辑-api.json" \
  -i "input/firstFrame/<首帧文件名>.png" \
  -o "output/aigate-qwen" \
  -t 900
```

记录输出的 `output/aigate-qwen/ComfyUI_*.png` 路径；下文记为 `<处理后参考图>.png`。

图像生成完成后，直接使用 CLI 打印的 PNG 路径进入下一步；**无需执行、等待或检查 “Viewed Image”**。只有用户明确要求人工审核图片内容时，才打开图片进行视觉检查。

---

## 可选审核断点

只有用户明确要求审核时，才打开并展示 Qwen 的处理结果，确认人物外观、背景与构图是否满足预期。否则直接使用已生成 PNG 的路径执行 SCAIL-2。

若用户要求修改，重新执行 Step 2；无需生成额外的中间参考图文件。

---

## Step 3：提交 SCAIL-2 动作迁移工作流

以**原视频**为驱动源，以 Step 2 的**处理后 PNG**为参考角色图。

### 按视频时长选择工作流

以下建议以当前工作流固定的 **16 fps** 输入、4090D-48G 实测为基准，优先平衡速度和段间一致性。切片不是并行执行：每一段会顺序推理，但短时间序列的注意力计算更快。

| 视频时长 | 推荐工作流 | 说明 |
|---|---|---|
| ≤ 3 秒 | `SCAIL2-1clip.json` | 不切片，避免不必要的段间衔接。 |
| 3–6 秒 | `SCAIL2-2clips.json` | 两段连续推理，使用 5 帧重叠衔接。 |
| 6–9 秒 | `SCAIL2-3clips.json` | 默认选择；8.2 秒 / 129 帧实测比 1clip 快约 30%。 |
| 9–12 秒 | `SCAIL2-4clips.json` | 将每段控制在约 45–55 帧。 |
| > 12 秒 | 按需生成 | 每增加约 3 秒增加一个 clip，或将视频拆成多个独立任务。 |

节点 217 仅用于计算**已有分段**的长度，不能只改它的数值来增加或减少推理次数。需要 5clip 及以上时，从仓库根目录运行：

```bash
.venv/bin/python scripts/generate_scail_workflow.py 5
```

该命令生成 `workflows/SCAIL2-5clips.json`；将 `5` 改为所需数量即可。速度优先时，可用下面的公式估算分段数，其中 `T` 为视频秒数：

```text
clips = max(1, ceil((16 × T - 5) / 45))
```

质量优先时，尽量使单段不超过约 81 帧（模型的训练片段长度）；可使用 `ceil((16 × T - 5) / 76)` 作为最少分段数。分段越多，首尾重叠、色彩转移与人物状态的累积误差也越明显。

```bash
opc aigate --run --instance INSTANCE_ID \
  -w "workflows/<选择的 SCAIL2 工作流>.json" \
  --video "input/videos/<视频文件名>.mp4" \
  --reference-image "output/aigate-qwen/<处理后参考图>.png" \
  -o "output/aigate-scail"
```

`SCAIL2-1clip.json`、`SCAIL2-2clips.json` 与 `SCAIL2-4clips.json` 已使用 `VHS_VideoCombine`，可直接提交。重命名后的原始 `SCAIL2-3clips.json` 仍保留其原始保存节点（节点 305，`1hew_SaveVideoByImage`），提交时额外添加 `--video-output-node 305`，即可在本次提交时替换为镜像可用的 `VHS_VideoCombine`；不会修改仓库内的工作流 JSON。

### 重命名输出为原视频文件名

SCAIL-2 的输出由 ComfyUI 自动编号（如 `Wan21_SCAIL2_00004-audio.mp4`、`ComfyUI_00007-audio.mp4`），不便于与原视频对应。**每个任务下载完成后，将其最终视频重命名为与原输入视频相同的文件名**（保留 `.mp4` 扩展名，放在同一 SCAIL 输出目录）：

```bash
mv "output/<日期>-aigate-scail/<ComfyUI 自动命名>-audio.mp4" \
   "output/<日期>-aigate-scail/<原视频文件名>.mp4"
```

由于已移除保存 mask 视频的节点 88（见下文「关键节点」与「输出与验证」），每个任务只产生**一个**视频输出，重命名不存在歧义。批量处理时按「视频 → 参考图 → 输出文件」的对应记录逐个重命名即可。

### 提交后监视 ComfyUI 日志

`opc aigate --start` 的输出会显示 ComfyUI 地址。将其保存为变量，并查询当前个人镜像公开的运行日志：

```bash
COMFYUI_URL="https://<实例地址>"
curl -sS "$COMFYUI_URL/internal/logs" | jq -r . | tail -n 50
```

持续监控时，每 15 秒刷新一次：

```bash
while true; do
  clear
  curl -sS "$COMFYUI_URL/internal/logs" | jq -r . | tail -n 50
  sleep 15
done
```

正常日志会依次出现 `got prompt`、SAM3 `tracking`、采样进度（如 `3/6`）以及 `Prompt executed in ... seconds`。若出现 `[ERROR]`、`CUDA out of memory`、`invalid prompt` 或视频保存节点缺失，应停止继续提交，先根据对应节点修复工作流后再重试。

### 工作流说明

SCAIL-2 是端到端角色动画模型，不需要骨骼或 ControlNet，通过 SAM3 自动分割人物并生成彩色控制 mask。

模式由节点 199（`replacement_mode`）控制：

- `false`：动画模式，将参考图人物外观迁移到驱动视频动作上。
- `true`：替换模式，将驱动视频人物替换为参考图人物。

### 关键节点

| 节点 | 类型 | 说明 |
|------|------|------|
| 30 | `LoadImage` | 参考角色图，由 `--reference-image` 替换 |
| 33 | `VHS_LoadVideo` | 驱动视频，由 `--video` 替换 |
| 74 | `DiffusionModelLoaderKJ` | SCAIL-2 FP8 模型 |
| 85 / 91 | `SAM3_VideoTrack` | 分别跟踪驱动视频与参考图人物 |
| 104 | `SCAIL2ColoredMask` | 生成彩色控制 mask |
| 114 / 115 / 261 | `WanSCAILToVideo` | 原始 3clip 的分段生成节点；其他变体按 clip 数量裁剪或扩展 |
| 179 | `PrimitiveStringMultiline` | 动作提示词 |
| 199 | `PrimitiveBoolean` | 动画 / 替换模式开关 |
| 210 | `PrimitiveInt` | 分辨率上限 |
| 217 | `PrimitiveInt` | 已有分段的长度计算参数；不会自动创建或删除推理分支 |
| 305 | 视频保存节点 | 最终带音频 MP4 输出；原始 3clip 提交时由命令行替换 |

> **节点 88 已移除**：早期工作流中的节点 88（`VHS_VideoCombine`，`filename_prefix=Wan21_SCAIL2`）专门用于保存彩色控制 mask / 预览视频。因不再需要 mask 视频，已从**所有** clip 工作流中删除该节点；它是终端汇点（输入取自节点 104 / 156，且不被任何其他节点引用），删除不影响最终视频。`scripts/generate_scail_workflow.py` 生成的工作流本就不含该节点，无需改动。彩色 mask 生成节点 104 仍保留，因为它仍为采样器提供控制输入——移除的只是**保存** mask 视频的汇点。

---

## 输出与验证

每个任务只输出**一个**带音频的最终视频。由于所有工作流均已移除保存 mask 视频的节点 88，不再产生 `Wan21_SCAIL2_*.mp4` 这类 mask / 预览视频。

ComfyUI 自动命名的最终视频通常形如：

```text
output/<日期>-aigate-scail/Wan21_SCAIL2_00004-audio.mp4   # 1/2/4/5/6clip（VHS_VideoCombine）
output/<日期>-aigate-scail/ComfyUI_00007-audio.mp4        # 3clip（--video-output-node 305 替换后）
```

按上文「重命名输出为原视频文件名」，将其重命名为对应的原视频文件名后即为最终交付文件，例如 `output/2026-07-23-aigate-scail/<原视频文件名>.mp4`。

---

## 注意事项

- SCAIL-2 使用约 17.7GB 的 FP8 模型；建议使用 48GB 显存以获得稳定余量。
- 视频会按节点 210 的上限缩放；长视频应使用上方生成器创建对应 clip 数量的工作流，而不是只修改节点 217。
- 同一实例可以提交多个任务；ComfyUI 会按队列串行执行。建议为每个任务记录视频、参考图和输出文件的对应关系。
- 任务完成后及时下载最终 MP4；实例关机或释放后，云端临时下载地址可能失效。
- 处理多个视频时，先跑完全部图像任务（Qwen）再跑全部视频任务（SCAIL-2），避免图像 / 视频模型反复切换；详见「批量处理多个视频（分阶段提交）」。
- 每个最终视频重命名为对应的原视频文件名，便于与输入一一对应；已移除节点 88，任务只输出一个视频，重命名无歧义。

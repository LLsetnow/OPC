# 动作迁移流水线（OPC AIGate）

将输入视频依次经过「提取首帧 → Qwen 图片处理 → 人工审核 → SCAIL-2 动作迁移」，输出带音频的 MP4 视频。Qwen 的处理结果直接作为 SCAIL-2 的参考图，不需要额外的图像或视频解码步骤。

---

## 前置条件

- 已安装 `opc`，并在 `.env` 中配置 `AIGATE_TOKEN`。
- 已启动一个带所需模型和自定义节点的云扉 ComfyUI 实例；SCAIL-2 建议使用 48GB 显存实例。
- 工作流文件位于仓库的 `workflows/` 目录。
- 输入视频位于 `input/videos/` 目录。

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

```bash
opc aigate --run --instance INSTANCE_ID \
  -w "workflows/Qwen+单图编辑-api.json" \
  -i "input/firstFrame/<首帧文件名>.png" \
  -o "output/aigate-qwen"
```

记录输出的 `output/aigate-qwen/ComfyUI_*.png` 路径；下文记为 `<处理后参考图>.png`。

---

## 审核断点

将 Qwen 的处理结果直接展示给用户，确认人物外观、背景与构图满足预期后，再执行 SCAIL-2。

若用户要求修改，重新执行 Step 2；无需生成额外的中间参考图文件。

---

## Step 3：提交 SCAIL-2 动作迁移工作流

以**原视频**为驱动源，以 Step 2 的**处理后 PNG**为参考角色图。

```bash
opc aigate --run --instance INSTANCE_ID \
  -w "workflows/SCAIL2+Animation+&+Replacement+动作迁移&角色替换_api.json" \
  --video "input/videos/<视频文件名>.mp4" \
  --reference-image "output/aigate-qwen/<处理后参考图>.png" \
  --video-output-node 305 \
  -o "output/aigate-scail"
```

`--video-output-node 305` 会在本次提交时将工作流中的视频保存节点替换为当前镜像可用的 `VHS_VideoCombine`，直接生成 H.264 MP4；不会修改仓库内的原始工作流 JSON。

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
| 114 / 115 / 261 | `WanSCAILToVideo` | 分段生成视频 |
| 179 | `PrimitiveStringMultiline` | 动作提示词 |
| 199 | `PrimitiveBoolean` | 动画 / 替换模式开关 |
| 210 | `PrimitiveInt` | 分辨率上限 |
| 217 | `PrimitiveInt` | 视频分段数 |
| 305 | `VHS_VideoCombine`（运行时替换） | 最终带音频 MP4 输出 |

---

## 输出与验证

最终成片是节点 305 生成的带音频文件，通常命名为：

```text
output/aigate-scail/ComfyUI_00001-audio.mp4
```

工作流也可能产生 `Wan21_SCAIL2_*.mp4`：这是节点 88 的临时控制 / mask 视频，文件较小且不带音频，不是最终成片。应保留和交付 `ComfyUI_*-audio.mp4`。

---

## 注意事项

- SCAIL-2 使用约 17.7GB 的 FP8 模型；建议使用 48GB 显存以获得稳定余量。
- 视频会按节点 210 的上限缩放；长视频可通过节点 217 增加分段数，以降低显存占用。
- 同一实例可以提交多个任务；ComfyUI 会按队列串行执行。建议为每个任务记录视频、参考图和输出文件的对应关系。
- 任务完成后及时下载最终 MP4；实例关机或释放后，云端临时下载地址可能失效。

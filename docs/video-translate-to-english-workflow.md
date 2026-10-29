# 中文视频翻译为英文视频：OPC 工作流案例

本文记录一套将中文旁白视频制作成英文版视频的可复用流程。目标是：

1. 从中文视频提取旁白并生成带时间戳的中文字幕。
2. 将中文字幕翻译成英文，同时保留原有字幕编号和时间轴。
3. 使用阿里云 DashScope CosyVoice 生成英文配音。
4. 删除原视频音轨，将英文配音重新封装回视频。
5. 为一批视频保留中间产物、处理状态和质量检查结果，支持失败重跑。

当前 OPC 已直接提供 `speech asr` 和 `speech tts`；“字幕翻译、逐条配音、按时间轴拼接、批处理续跑”仍属于外层工作流编排，不能把下面的流程理解为现成的一条 `opc` 子命令。

## 一、总体流程

```text
中文视频
   │
   ├─ ffprobe：检查时长、帧率、音轨
   ├─ ffmpeg：提取并规范化音频（16 kHz、单声道 WAV）
   ├─ opc speech asr：中文 ASR → zh.srt + asr.json
   ├─ LLM 翻译：中文文本 → 英文文本，保留 cue ID 和时间码
   ├─ opc speech tts：逐条英文文本 → 英文语音片段
   ├─ 时间轴拼接：按原中文字幕时间码放置英文语音
   └─ ffmpeg：视频流 + 英文音轨 → 英文版视频
```

推荐先处理单个视频的短片段，确认音色、翻译风格、语速和时间轴，再批量运行。

## 二、前提条件

### 1. 在 OPC checkout 中运行

```bash
cd /Users/apple/Documents/github/OPC
source .venv/bin/activate
```

检查 CLI 是否可用：

```bash
opc --help
ffmpeg -version
ffprobe -version
```

### 2. API 配置

在 OPC 的 `.env` 中配置凭证，或通过安全的环境变量注入：

```dotenv
ALIYUN_API_KEY=<阿里云 DashScope API Key>
ASR_MODEL=fun-asr-realtime
QWEN_TTS_MODEL=cosyvoice-v3-flash

# 只有使用 opc speech asr --llm-fix 或外部 LLM 翻译时才需要
DEEPSEEK_API_KEY=<LLM API Key>
LLM_BASE_URL=<兼容 OpenAI API 的地址>
LLM_MODEL=<翻译使用的模型>
```

不要将真实 API Key、访问令牌或带鉴权参数的 URL 写入本文档、脚本、字幕或 Git。

## 三、推荐的中间目录

以一个视频为单位保存中间文件，避免多个视频共用临时文件名：

```text
work/<video-name>/
├── source.mp4          # 可选：源文件副本或软链接，不覆盖原视频
├── source.audio.wav    # ASR 输入音频
├── source.zh.srt       # 中文字幕，来自 ASR
├── source.asr.json     # ASR 原始 JSON
├── source.zh.txt       # 待翻译的中文文本，可选
├── source.translation.json
├── tts/
│   ├── 0001.wav        # 每个英文字幕 cue 一个语音片段
│   ├── 0002.wav
│   └── ...
├── source.en.srt       # 英文字幕，时间码与中文版本一致
├── source.en.timeline.wav
├── source.en.mp4       # 最终视频
└── manifest.json       # 处理状态、参数和路径，不包含密钥
```

批处理的最终输出可按源视频分目录保存：

```text
<output-dir>/<video-name>/
├── <video-name>.en.mp4
├── <video-name>.en.srt
└── manifest.json
```

原始视频不应被覆盖；重跑时使用新的工作目录或版本目录。

## 四、步骤 1：检查源视频并提取音频

先确认源视频是否存在音轨、视频时长和帧率：

```bash
VIDEO_IN="<输入视频路径>"
WORK_DIR="<工作目录>/<video-name>"
mkdir -p "$WORK_DIR"

ffprobe -v error \
  -show_entries format=duration:stream=index,codec_type,codec_name,sample_rate,channels,r_frame_rate \
  -of json "$VIDEO_IN"
```

提取原视频音频。为提高 ASR 稳定性，统一转换为 16 kHz、单声道 WAV：

```bash
ffmpeg -y -i "$VIDEO_IN" -vn \
  -ac 1 -ar 16000 -c:a pcm_s16le \
  "$WORK_DIR/source.audio.wav"
```

如果源视频没有音轨，流程无法从旁白自动生成字幕；应先提供旁白音频或改用人工脚本。

注意：如果原音轨同时包含背景音乐、环境声和人声，完整替换音轨会一并删除这些声音。若需要保留音乐或环境声，应先做语音分离，再对背景声和英文旁白进行混音。

## 五、步骤 2：使用 OPC 生成中文字幕

```bash
opc speech asr "$WORK_DIR/source.audio.wav" \
  --output-dir "$WORK_DIR" \
  --llm-fix
```

当前命令会生成：

- `source.audio.srt`：带时间戳的字幕文件。
- `source.audio.asr.json`：ASR 原始结果，包含更详细的识别信息。

如果希望最终文件名更清楚，可以在工作流编排层将它们规范化为 `source.zh.srt` 和 `source.asr.json`；不要直接丢弃原始 JSON。

`--llm-fix` 用于修复断词和标点，不能替代人工校对。专有名词、人名、数字、品牌名和中英文混杂内容应重点检查。

只测试前 30 秒时，可以使用：

```bash
opc speech asr "$WORK_DIR/source.audio.wav" \
  --output-dir "$WORK_DIR" \
  --trim 30 \
  --llm-fix
```

### ASR 单条请求与长视频策略

当前 `opc speech asr` 使用阿里云 `fun-asr-realtime`，通过 DashScope SDK 的实时识别接口处理本地文件，并在 CLI 内转换为 16 kHz WAV。上游文档对不同接入方式的限制不同：

| 接入方式 | 文档中的单次限制/特点 | 工作流建议 |
| --- | --- | --- |
| `opc speech asr` 当前实现 | 使用实时 WebSocket 文件识别；客户端没有按秒截断，除非使用 `--trim` | 短视频可直接调用；生产批处理仍建议按视频独立执行 |
| 阿里云 HTTP 非实时文件识别 | `fun-asr-realtime` 文件/URL 方式：不超过 5 分钟、2 GB | 适合短音频；超时或超过时长时切片 |
| 阿里云异步文件转写 | 支持的模型可到 12 小时、2 GB，结果链接有有效期 | 长视频或长音频优先评估异步接口 |

因此，“ASR 单条请求上线是多少”不能只看模型名，必须看具体接入方式。当前 OPC CLI 走的是实时 WebSocket 路径；对于长视频，推荐切成 3–5 分钟片段分别识别，再按片段起始偏移合并 SRT，并保留原始片段 JSON 以便追溯。

## 六、步骤 3：翻译中文字幕

当前 OPC 没有专门的 `speech translate` 子命令。翻译层可以使用外部 LLM 或已有翻译服务，但必须遵守以下数据契约：

1. 保留 cue 的 `id`、`start`、`end` 和原始顺序。
2. 只翻译文本，不修改时间码。
3. 每一个中文 cue 对应一个英文 cue；不要擅自合并或拆分。
4. 只返回结构化结果，不要混入解释、Markdown 围栏或额外段落。
5. 英文应适合口语配音，避免逐字直译；人名、数字和专有名词应保持一致。

推荐的中间 JSON 结构：

```json
[
  {
    "id": 1,
    "start": "00:00:00,000",
    "end": "00:00:02,400",
    "zh": "这是一个示例。",
    "en": "This is an example."
  }
]
```

翻译提示词应明确要求“保留 JSON 数组结构、ID 和时间码，只填写 `en` 字段”。翻译完成后，自动检查：

```text
中文 cue 数量 == 英文 cue 数量
英文 ID 集合 == 中文 ID 集合
英文时间码逐条等于中文时间码
每个英文文本非空
```

英文 SRT 直接使用中文 SRT 的时间码，仅替换字幕文本。这样字幕和配音共用同一时间基准，后续才能进行时长检查。

## 七、步骤 4：使用阿里云 CosyVoice 生成英文配音

### 1. 正确的语言和音色选择

当前命令默认使用阿里云 CosyVoice：

```bash
opc speech tts \
  "Today is a wonderful day to build something people love." \
  --engine qwen-tts \
  --voice loongandy_v3 \
  --speed 1.0 \
  --format wav \
  --output "$WORK_DIR/tts/0001.wav"
```

当前 OPC CLI 没有 `--language English` 参数。英文配音的关键是：

- 文本本身使用英文。
- `--engine qwen-tts` 选择阿里云 CosyVoice 路径。
- `--voice` 使用支持英文的 CosyVoice 音色。

可优先选择以下官方英文音色：

| 音色 | 风格 |
| --- | --- |
| `loongandy_v3` | 美式英语男声 |
| `loongabby_v3` | 美式英语女声 |
| `loongeric_v3` | 英式英语男声 |
| `loongemily_v3` | 英式英语女声 |

这些英文音色 ID 应以阿里云官方 CosyVoice 音色列表为准。当前 OPC 的本地音色字典未必列出所有新版 `loong...` 音色，但 Qwen TTS 路径会将 `--voice` ID 传给阿里云接口；如果返回音色不存在，应先检查模型与音色是否匹配。

不要用 `--engine glm-tts` 来测试阿里云英文配音；该选项是智谱 GLM-TTS 引擎。`--clone` 在当前 CLI 中也是 GLM-TTS 的克隆路径，不是阿里云 CosyVoice 的英文音色选择方式。

### 2. 按 cue 逐条合成

为每个英文字幕 cue 单独调用一次 TTS：

```bash
mkdir -p "$WORK_DIR/tts"

opc speech tts "<第 1 条英文字幕>" \
  --engine qwen-tts \
  --voice loongandy_v3 \
  --speed 1.0 \
  --format wav \
  --output "$WORK_DIR/tts/0001.wav"
```

批处理编排器应按 `id` 生成固定文件名，并将以下参数纳入缓存键：

```text
hash(英文文本 + 模型 + 音色 + 语速 + 输出格式 + 采样率)
```

这样翻译未变时可以复用已生成的语音，避免重复计费和重复等待。先采用串行或低并发；确认账户限流、失败重试和费用可接受后再提高并发。

当前 OPC 的云端 CosyVoice TTS 使用非流式请求，默认输出 24 kHz 音频。单条文本过长时 CLI 会按长度分段合成并拼接；字幕配音场景仍建议按 cue 调用，以便精确控制时间轴。

## 八、步骤 5：锁定英文配音时间轴

英文翻译后，句子长度通常会变化，不能直接把整段英文一次合成后覆盖整条视频，否则会逐渐产生音画漂移。

推荐的“时间轴锁定”算法如下：

1. 读取英文 SRT 的每条 cue：`start_i`、`end_i`、`slot_i = end_i - start_i`。
2. 对英文文本逐条生成 `tts_i.wav`。
3. 用 `ffprobe` 测量 `duration_i`。
4. 将 `tts_i.wav` 放置在全长静音轨的 `start_i` 位置。
5. 如果 `duration_i <= slot_i`，尾部补静音，等待下一条 cue。
6. 如果 `duration_i > slot_i`，按以下顺序处理：
   - 先改写英文，使其更简洁、更适合口播。
   - 再适度提高 TTS `--speed`，避免不自然的过快语速。
   - 仍超时时标记为人工复核，不要无提示地截断音频。
7. cue 之间保留原 SRT 的空隙；不要把后一条语音提前到上一条 cue 的结束时间之前。

可将每条 cue 的状态记录为：

```json
{
  "id": 1,
  "slot_seconds": 2.4,
  "tts_seconds": 2.1,
  "speed": 1.0,
  "status": "ok"
}
```

如果更看重英文表达的自然度，可以使用“整段合成”模式，但必须接受英文音频与原视频时间线逐渐漂移，并在视频编辑阶段重新确定切点。旁白翻译视频通常优先使用逐 cue 锁定模式。

## 九、步骤 6：移除原音频并封装英文视频

完成时间轴音轨 `source.en.timeline.wav` 后，将它与源视频的视频流重新封装：

```bash
ffmpeg -y -i "$VIDEO_IN" -i "$WORK_DIR/source.en.timeline.wav" \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 192k \
  -shortest \
  "$WORK_DIR/source.en.mp4"
```

这里的 `-map 0:v:0 -map 1:a:0` 明确保留源视频流、只使用新英文音轨，因此不会把原中文音轨带入输出。若英文时间轴音频需要覆盖到视频末尾，应确保时间轴音频长度至少覆盖视频时长，再决定是否使用 `-shortest`。

如果源视频使用的编码或封装不适合直接复制视频流，可将 `-c:v copy` 改成项目规定的重新编码参数；这会增加耗时，也可能改变文件大小和编码质量，应在 manifest 中记录。

## 十、批处理编排建议

对目录中的每个视频独立执行以下状态机：

```text
discovered
  → inspected
  → audio_extracted
  → asr_done
  → translation_done
  → tts_done
  → timeline_done
  → muxed
  → qa_passed
```

每个状态完成后立即写入 `manifest.json`。重跑时先检查已有文件和状态，只执行缺失或失败的阶段。单个视频失败不应让整批任务丢失其他已完成结果。

建议 manifest 至少记录：

```json
{
  "source": {
    "path": "<源视频路径>",
    "sha256": "<源文件哈希>",
    "duration_seconds": 0
  },
  "asr": {
    "provider": "aliyun-dashscope",
    "model": "fun-asr-realtime",
    "status": "done"
  },
  "translation": {
    "source_language": "zh",
    "target_language": "en",
    "cue_count": 0,
    "status": "done"
  },
  "tts": {
    "provider": "aliyun-dashscope",
    "model": "cosyvoice-v3-flash",
    "voice": "loongandy_v3",
    "speed": 1.0,
    "status": "done"
  },
  "outputs": {
    "zh_srt": "source.zh.srt",
    "en_srt": "source.en.srt",
    "audio": "source.en.timeline.wav",
    "video": "source.en.mp4"
  }
}
```

路径可以是相对当前视频工作目录的路径；不要记录 API Key、请求头、完整鉴权 URL 或其他凭证。

## 十一、验收清单

### 字幕

- 中文和英文 cue 数量相同。
- cue ID 连续且顺序一致。
- 英文时间码逐条等于中文时间码。
- `start < end`，没有负数、重叠或超出视频时长的 cue。
- 人名、品牌、数字、专有名词已抽样复核。

### 配音

- 每条英文 cue 都有对应的 TTS 音频，且可播放。
- `duration_i` 与对应时间槽的差异已检查。
- 没有因为超时而静默截断句尾。
- 英文发音、口音、语速和音量符合成片要求。

### 视频

```bash
ffprobe -v error \
  -show_entries format=duration:stream=index,codec_type,codec_name,codec_time_base,r_frame_rate,sample_rate,channels \
  -of json "$WORK_DIR/source.en.mp4"
```

重点确认：

- 视频时长和帧率与源视频一致或在预期误差内。
- 输出只有一个视频流和一个英文音频流。
- 输出不再包含原中文音轨。
- 文件可以从头播放到尾，最后一句没有被截断。
- 输出路径、字幕路径和 manifest 中的路径实际存在。

## 十二、已知限制与改进方向

### 当前限制

- 当前 OPC 没有把“ASR → 翻译 → 逐 cue TTS → 时间轴合成 → mux”封装为一条正式命令。
- `speech asr --llm-fix` 只负责 ASR 文本的断词和标点修复，不负责可靠的中译英。
- 完整替换原音轨会同时去掉原背景音乐和环境声。
- 当前流程没有说话人分离、角色级音色分配或口型同步。
- 自动翻译和英文 TTS 仍可能误读专有名词、数字、缩写和单位。
- 阿里云不同模型、区域和接入方式的限制可能变化；上线前应以控制台和官方文档的当前配额为准。

### 建议的 OPC 产品化方向

未来可以增加一个正式的编排命令，例如：

```bash
opc video dub-en <input-dir> \
  --output-dir <output-dir> \
  --voice loongandy_v3 \
  --timing locked \
  --llm-fix \
  --resume
```

这只是目标接口示例，当前 OPC 尚未提供该命令。实现时应优先加入：任务 manifest、断点续跑、TTS 缓存、单视频失败隔离、cue 时长报告和最终 `ffprobe` 验收。

## 十三、官方参考

- [阿里云 CosyVoice 音色列表](https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list)
- [阿里云非实时语音合成](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)
- [阿里云 ASR 模型与文件限制](https://help.aliyun.com/zh/model-studio/asr-model)
- [阿里云非实时语音识别](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)
- [阿里云实时语音识别](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition-user-guide)

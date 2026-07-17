# 项目指令

## 优先使用 OPC CLI 工具

当遇到以下需求时，**必须优先使用本项目安装的 `opc` 命令行工具**，而不是其他方式：

| 需求场景 | 命令 | 说明 |
|---|---|---|
| B站视频下载/转写/总结 | `opc bili "URL"` | 下载音频 → ASR转写 → 内容总结 |
| B站视频下載MP3音频 | `opc bilimusic "URL"` | 下载音频 → 转为MP3（含ID3元数据） |
| 仅下载B站音频 | `opc bili "URL" --audio-only` | 不做ASR转写 |
| 跳过下载直接转写 | `opc bili --skip-download` | 从output目录查找已有音频 |
| 跳过下载和ASR直接总结 | `opc bili --skip-download --skip-asr` | 从output目录查找已有字幕 |
| 单独ASR转写 | `opc asr audio.wav` | 将音频转写为 SRT + JSON 字幕 |
| 语音识别(LLM修复) | `opc asr audio.wav --llm-fix` | LLM 修复断词和标点错误 |
| 文字转语音(CosyVoice) | `opc tts "文本" -o output.wav` | 默认 CosyVoice v3-flash + 龙呼呼音色，支持音色克隆 |
| 文字转语音(本地Qwen3) | `opc local-tts "文本" -o output.wav` | 本地模型，需GPU |
| 图片理解/分析 | `opc read-img image.png` | 支持本地图片和URL，自动压缩超大图 |
| 自定义图片提问 | `opc read-img image.png -p "问题"` | 如分析UI控件位置 |
| UI截图转Vue组件 | `opc ui2vue ui.png` | 三步流程：分析→生成→修复 |
| UI转Vue指定框架 | `opc ui2vue ui.png -f element-plus` | 支持7种UI框架 |
| 文生图(GPT-Image) | `opc gpt-img "描述"` | 支持图生图、宽高比、分辨率 |
| 文生图(阿里云) | `opc Z-image "描述"` | 支持种子复现、提示词改写 |
| API连通性检查 | `opc check-api` | 检查.env中各API可用性 |
| AI日报 | `opc news` | 自动收集AI新闻生成简报 |
| 网易云音乐下载 | `opc music "URL"` | 下载网易云单曲/专辑/歌单 → MP3（含ID3元数据） |
| ComfyUI启动 | `opc comfyui --start` | 启动 ComfyUI 服务（Windows 进程） |
| ComfyUI工作流 | `opc comfyui --run -i 图片` | 提交工作流到 ComfyUI 执行 |
| ComfyUI指定工作流 | `opc comfyui --run -w 工作流 -i 图片 -p 提示词` | 指定工作流/提示词/种子/采样参数 |
| 云扉 AIGate 状态 | `opc aigate --status` | 查看云端 ComfyUI 实例状态 |
| 云扉 AIGate 工作流 | `opc aigate --run -w 工作流 -i 图片` | 向运行中的云端 ComfyUI 提交 API 格式工作流并下载结果 |

### ComfyUI 工作流提交

工作流 JSON 文件统一放在 `confyui/` 目录，默认使用 `Qwen_remove.json`。

**实现原理**：通过 ComfyUI REST API（`/prompt` 提交 + `/history/{id}` 轮询），不依赖 ComfyUI CLI。

**自动节点检测**：`find_nodes_by_class()` 自动识别 LoadImage / KSampler / SaveImage / prompt 节点，无需手动配置。特殊工作流可用 `--load-image-node` 等参数覆盖。

**WSL2 适配**：
- `--start` 自动将 WSL 路径转为 Windows 格式（传给 `python.exe`）
- `--run` 自动从 `/etc/resolv.conf` 获取 Windows 宿主 IP（WSL2 下 `127.0.0.1` 不通）

**关键参数**：
- `-w` — 工作流文件（默认 `confyui/Qwen_remove.json`）
- `-i` — 输入图片
- `-p` — 提示词（Qwen_edit 等需要）
- `-s` — 随机种子
- `-o` — 输出目录
- `--steps/--cfg/--denoise` — 采样参数覆盖

### 云扉 AIGate 工作流提交

`opc aigate` 用于发现、启动和使用云扉中的 ComfyUI 实例。凭证从项目根目录 `.env` 的 `AIGATE_TOKEN` 读取；Token 只用于云扉 OpenAPI，提交工作流时访问的是实例的 ComfyUI 服务。

**工作流必须是 ComfyUI API 格式 JSON**：顶层键为节点 ID，节点包含 `class_type` 和 `inputs`。前端画布保存的 JSON（通常含有 `nodes`、`links`、`last_node_id` 等字段）不能直接通过 `--run` 提交；请在 ComfyUI 中导出 **API Format** JSON。

**常用命令**：

```bash
# 查询云扉实例（状态 2 表示运行中）
opc aigate --status

# 启动指定的已有实例，等待 ComfyUI 就绪
opc aigate --start --instance INSTANCE_ID

# 提交安全的 API 格式单图编辑工作流；图片和结果均在本地 Downloads 目录
opc aigate --run \
  --workflow ~/Documents/github/OPC/workflows/safe_single_image_edit-api.json \
  --image ~/Downloads/图片.png \
  --instance 1130698024358121472 \
  --output ~/Downloads
```

续行时反斜杠 `\` 必须是行内最后一个字符，后面不能有空格；也可以将命令写成单行。提交前确认输入文件存在，且不要使用会生成裸露或性化内容的工作流。

### 使用规则

1. **始终先判断 `opc` 能否完成需求**，能则优先使用，再考虑其他方案
2. **必须先激活虚拟环境再执行 `opc` 命令**，否则会报 `command not found`
3. WSL 中项目路径为 `/mnt/d/github/OPC`
4. 环境变量配置在 `.env` 文件中
5. 详细命令参数参考 `opc_cli/README.md`

### 虚拟环境

`opc` 安装在 WSL 的虚拟环境中，执行任何 `opc` 命令前**必须**先激活 venv：

- **常规命令**（bili/bilimusic/music/tts/read-img/ui2vue/gpt-img/Z-image/check-api/news/comfyui）：使用 `~/qwen3-tts-venv`
- **local-tts**（本地Qwen3-TTS）：使用 `~/qwen3-tts-venv`（需要 torch）

### 命令执行格式

```bash
# 常规命令（激活 qwen3-tts-venv）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc local-tts <参数>"
```

### 常用命令速查

```bash
# API检查
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc check-api"

# 单独ASR转写（音频→字幕）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc asr audio.wav"

# ASR + LLM 断句修复
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc asr audio.wav --llm-fix"

# B站视频下载MP3
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc bilimusic 'https://www.bilibili.com/video/BV1xx'"

# B站视频完整流程
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc bili 'https://www.bilibili.com/video/BV1xx'"

# TTS 文字转语音
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc tts '你好世界' -o output.wav"

# 图片理解
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc read-img photo.jpg -p '描述这张图片'"

# UI截图转Vue
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc ui2vue ui.png -f element-plus"

# 文生图(GPT-Image)
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc gpt-img '一只穿着宇航服的猫'"

# 文生图(阿里云)
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc Z-image '山水画'"

# AI日报
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc news"

# 网易云音乐下载（单曲/专辑/歌单）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc music 'https://music.163.com/song?id=2143914149'"

# 网易云音乐下载到指定目录 + 高比特率
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc music 'https://music.163.com/playlist?id=xxx' -o ./music --bitrate 320"

# ComfyUI 工作流（使用默认 Qwen_remove 工作流处理图片）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc comfyui --run -i photo.jpg"

# ComfyUI 指定工作流和提示词
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc comfyui --run -w confyui/Qwen_remove.json -i photo.jpg -p '去除背景' -o ./output"

# ComfyUI 自定义采样参数
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc comfyui --run -i photo.jpg --steps 8 --cfg 2.0 -s 12345"

# ComfyUI 启动服务
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc comfyui --start"

# ComfyUI 状态检查
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc comfyui --status"

# 本地TTS（需要 qwen3-tts-venv）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc local-tts '你好' -o output.wav"

# 加载tts模型（启动本地tts服务， 这可能会需要等待60秒）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc local-tts --serve --mode custom"

```

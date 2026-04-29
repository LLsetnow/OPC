# 项目指令

## 优先使用 OPC CLI 工具

当遇到以下需求时，**必须优先使用本项目安装的 `opc` 命令行工具**，而不是其他方式：

| 需求场景 | 命令 | 说明 |
|---|---|---|
| B站视频下载/转写/总结 | `opc bili "URL"` | 下载音频 → ASR转写 → 内容总结 |
| 仅下载B站音频 | `opc bili "URL" --audio-only` | 不做ASR转写 |
| 跳过下载直接转写 | `opc bili --skip-download` | 从output目录查找已有音频 |
| 跳过下载和ASR直接总结 | `opc bili --skip-download --skip-asr` | 从output目录查找已有字幕 |
| 文字转语音(智谱) | `opc tts "文本" -o output.wav` | 支持7种预设音色+音色克隆 |
| 文字转语音(本地Qwen3) | `opc local-tts "文本" -o output.wav` | 本地模型，需GPU |
| 图片理解/分析 | `opc read-img image.png` | 支持本地图片和URL，自动压缩超大图 |
| 自定义图片提问 | `opc read-img image.png -p "问题"` | 如分析UI控件位置 |
| UI截图转Vue组件 | `opc ui2vue ui.png` | 三步流程：分析→生成→修复 |
| UI转Vue指定框架 | `opc ui2vue ui.png -f element-plus` | 支持7种UI框架 |
| 文生图(GPT-Image) | `opc gpt-img "描述"` | 支持图生图、宽高比、分辨率 |
| 文生图(阿里云) | `opc Z-image "描述"` | 支持种子复现、提示词改写 |
| API连通性检查 | `opc check-api` | 检查.env中各API可用性 |
| AI日报 | `opc news` | 自动收集AI新闻生成简报 |

### 使用规则

1. **始终先判断 `opc` 能否完成需求**，能则优先使用，再考虑其他方案
2. **必须先激活虚拟环境再执行 `opc` 命令**，否则会报 `command not found`
3. WSL 中项目路径为 `/mnt/d/github/OPC`
4. 环境变量配置在 `.env` 文件中
5. 详细命令参数参考 `opc_cli/README.md`

### 虚拟环境

`opc` 安装在 WSL 的虚拟环境中，执行任何 `opc` 命令前**必须**先激活 venv：

- **常规命令**（bili/tts/read-img/ui2vue/gpt-img/Z-image/check-api/news）：使用 `~/qwen3-tts-venv`
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

# 本地TTS（需要 qwen3-tts-venv）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC && opc local-tts '你好' -o output.wav"
```

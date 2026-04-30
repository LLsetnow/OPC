# Real-time-voice 开发总结

## 项目概述

实时语音对话 Web 应用：**麦克风/文字输入 → Fun-ASR 流式识别 → LLM 流式回复 → CosyVoice-v3 流式合成 → 浏览器播放**。前端采用二次元角色 Yuki 风格。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 (Composition API) + Vite |
| 通信 | WebSocket 全双工 |
| 后端 | Python `websockets` 16.0 + `httpx` |
| ASR | 阿里云 Fun-ASR Realtime (DashScope WS) |
| LLM | DeepSeek API (SSE streaming) |
| TTS | 阿里云 CosyVoice-v3 (SSE streaming) |

## 已完成功能

### 2026-04-30 — 初始版本 (v0.1.0)

#### 后端模块

| 文件 | 功能 | 状态 |
|---|---|---|
| `server.py` | WebSocket 服务主入口 + HTTP API + 静态文件 serve | ✅ |
| `asr_client.py` | Fun-ASR Realtime WS 封装（双工流式识别+VAD断句） | ✅ |
| `llm_client.py` | DeepSeek SSE 流式对话 + Yuki 角色 Prompt + 会话上下文 | ✅ |
| `tts_client.py` | CosyVoice SSE 流式合成 + 音色列表查询 | ✅ |
| `logger.py` | 按日期写入 `logs/YYYY-MM-DD.log` + 终端双输出 | ✅ |

#### 前端模块

| 文件 | 功能 | 状态 |
|---|---|---|
| `App.vue` | 主组件：状态机 + WS 消息路由 + 麦克风/文字输入协调 | ✅ |
| `ParticleBg.vue` | 星空粒子漂浮背景 | ✅ |
| `CharacterPanel.vue` | Yuki 角色 SVG 立绘 + 好感度/信任度条 + 状态指示灯 | ✅ |
| `ChatBubbles.vue` | 毛玻璃对话气泡（识别中/流式/打断标记） | ✅ |
| `VoiceWaveform.vue` | 实时音量柱状波形（蓝=聆听/粉=AI说话） | ✅ |
| `ControlBar.vue` | 底部文字输入框 + 麦克风按钮 + 发送/设置按钮 | ✅ |
| `SettingsPanel.vue` | 两分页抽屉：语音设置 + 模型与密钥 | ✅ |
| `useWebSocket.js` | WebSocket 连接管理 + 消息收发 + binary/text 分发 | ✅ |
| `useMicrophone.js` | AudioWorklet 麦克风采集 + 设备枚举 + 音量检测 | ✅ |
| `useAudioPlayer.js` | Web Audio API Float32 PCM 排队播放 | ✅ |
| `useSettings.js` | 设置状态管理 + localStorage 持久化 | ✅ |

#### 核心特性

- [x] 语音输入：AudioWorklet 16kHz 采集 → WebSocket → Fun-ASR → 实时 partial 文本显示
- [x] 文字输入：跳过 ASR，直接送入 LLM
- [x] LLM 流式：SSE token 级别增量返回 → 前端实时打字效果
- [x] TTS 流式：LLM 积累 ~30 字触发 CosyVoice 分块合成 → 流式 PCM 播放
- [x] 打断 (Barge-in)：THINKING 阶段新输入 → 取消 LLM/TTS → 清空播放队列 → 重新处理
- [x] 状态机：IDLE → LISTENING → THINKING → SPEAKING 四态流转
- [x] 角色好感度：解析 `<好感变化:+X><信任变化:+X>` 标签动态更新
- [x] 设置面板：音色选择 + 语气提示词 + 麦克风设备 + 开关 + 模型密钥配置
- [x] 日志系统：按日期写入 `logs/` 目录

#### 已修复 Bug

- [x] websockets 16.0 `process_request` 签名兼容：`_http_handler(connection, request)` 替代旧的 `(path, request_headers)`
- [x] `full_text` 变量初始化，避免 `async for` 未执行时未定义
- [x] 终端报错写入日志：`sys.excepthook` + asyncio 异常处理器 + `sys.stderr` tee 三路捕获

## 启动方式

```bash
# 后端（WSL + venv）
wsl -e zsh -c "source ~/qwen3-tts-venv/bin/activate && cd /mnt/d/github/OPC/Real-time-voice && python server.py --port 9902"

# 前端开发模式
wsl -e zsh -c "cd /mnt/d/github/OPC/Real-time-voice/frontend && npx vite"

# 前端构建
wsl -e zsh -c "cd /mnt/d/github/OPC/Real-time-voice/frontend && npx vite build"
```

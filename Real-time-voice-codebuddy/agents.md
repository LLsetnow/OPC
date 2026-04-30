# Real-time-voice-codebuddy 项目进度

## 项目概述

实时语音对话 Web 应用，实现：**麦克风/文字输入 → Fun-ASR 流式识别 → LLM 流式回复 → CosyVoice-v3 流式合成 → 浏览器播放**。前端采用二次元角色风格，以虚拟角色 Yuki 为主题。

---

## 功能模块进度

### 后端模块

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 日志系统 | `logger.py` | ✅ 完成 | 按日期轮转日志文件 + 终端双输出 |
| ASR 识别 | `asr_client.py` | ✅ 完成 | DashScope Fun-ASR Realtime WebSocket，流式识别 + VAD 断句 |
| LLM 对话 | `llm_client.py` | ✅ 完成 | DeepSeek SSE 流式生成 + 会话上下文 + 好感/信任提取 + TTS 分块触发 |
| TTS 合成 | `tts_client.py` | ✅ 完成 | CosyVoice SSE 流式合成 + 音色查询（系统 + 复刻）+ WAV→Float32 PCM |
| 主服务 | `server.py` | ✅ 完成 | WebSocket 主循环 + HTTP API + 静态文件 + 打断逻辑 + 配置更新 |
| 依赖声明 | `requirements.txt` | ✅ 完成 | websockets, httpx, python-dotenv, numpy, requests |

### 前端模块

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 项目配置 | `package.json` / `vite.config.js` / `index.html` | ✅ 完成 | Vite + Vue 3，dev proxy 转发 /ws 和 /api |
| 入口 | `main.js` / `App.vue` | ✅ 完成 | 主布局 + 状态机编排 + 消息路由 + 打断处理 |

#### Composables（逻辑层）

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| WebSocket 管理 | `useWebSocket.js` | ✅ 完成 | 连接管理 + 消息收发 + 自动重连 + 二进制帧解析 |
| 麦克风采集 | `useMicrophone.js` | ✅ 完成 | AudioWorklet PCM 采集 + 设备枚举 + 音量分析 |
| 音频播放 | `useAudioPlayer.js` | ✅ 完成 | Web Audio API 排队播放 Float32 PCM + 清空队列（打断） |
| 设置状态 | `useSettings.js` | ✅ 完成 | localStorage 持久化 + 语音设置/模型密钥双分页 + 配置同步消息 |

#### Components（UI 层）

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 粒子背景 | `ParticleBg.vue` | ✅ 完成 | CSS 飘浮粒子动画 |
| 角色面板 | `CharacterPanel.vue` | ✅ 完成 | SVG 角色立绘 + 状态光晕 + 好感度/信任度条 + 状态指示灯 |
| 对话气泡 | `ChatBubbles.vue` | ✅ 完成 | 毛玻璃气泡列表 + ASR 实时预览 + LLM 打字效果 + 打断标记 |
| 语音波形 | `VoiceWaveform.vue` | ✅ 完成 | CSS 柱状波形动画，随音量跳动 |
| 控制栏 | `ControlBar.vue` | ✅ 完成 | 文字输入框 + 麦克风按钮 + 发送按钮 + 设置按钮 |
| 设置面板 | `SettingsPanel.vue` | ✅ 完成 | 右侧滑出抽屉，双 Tab（语音设置 + 模型密钥） |

---

## 关键协议

### 上行（Browser → Server）

| type | 格式 | 说明 |
|------|------|------|
| `start_voice` | JSON | 开始语音输入 |
| `stop_voice` | JSON | 结束语音输入 |
| `audio` | binary: `[0x01] + PCM16` | 麦克风音频块 |
| `text_input` | JSON | 文字输入 |
| `interrupt` | JSON | 打断当前 AI 回复 |
| `update_config` | JSON | 更新语音/模型/密钥配置 |

### 下行（Server → Browser）

| type | 格式 | 说明 |
|------|------|------|
| `asr_partial` / `asr_final` | JSON | ASR 中间/最终结果 |
| `llm_delta` / `llm_done` | JSON | LLM 增量文本/完成 |
| `tts_start` / `tts_audio` / `tts_end` | JSON + binary | TTS 音频流 |
| `status` | JSON | 状态变更 (idle/listening/thinking/speaking) |
| `emotion` | JSON | 好感/信任变化 |

---

## 待完成 / 后续优化

- [ ] 端到端联调测试
- [ ] 语音输入实际测试（ASR → LLM → TTS 全链路）
- [ ] 文字输入测试
- [ ] 打断功能测试
- [ ] 设置面板实际测试（音色切换、密钥更新）
- [ ] 麦克风设备切换测试
- [ ] 延迟优化（ASR 首包 < 500ms, LLM 首 token < 1s, TTS 首包 < 2s）
- [ ] 移动端适配优化

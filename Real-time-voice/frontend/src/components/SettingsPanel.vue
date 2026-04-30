<template>
  <Teleport to="body">
    <Transition name="panel">
      <div v-if="visible" class="settings-overlay" @click.self="$emit('close')">
        <div class="settings-panel">
          <div class="panel-header">
            <h3>设置</h3>
            <button class="close-btn" @click="$emit('close')">&times;</button>
          </div>

          <div class="tabs">
            <button class="tab" :class="{ active: activeTab === 'voice' }"
              @click="activeTab = 'voice'">语音设置</button>
            <button class="tab" :class="{ active: activeTab === 'model' }"
              @click="activeTab = 'model'">模型与密钥</button>
          </div>

          <div class="tab-content" v-if="activeTab === 'voice'">
            <div class="form-group">
              <label>TTS 音色</label>
              <select :value="currentVoice" @change="$emit('update:voice', $event.target.value)">
                <option v-for="v in voices" :key="v.value" :value="v.value">{{ v.label }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>语气提示词</label>
              <textarea :value="currentInstruction" placeholder="如：用温柔撒娇的语气说"
                @input="$emit('update:instruction', $event.target.value)" rows="2" />
            </div>
            <div class="form-group">
              <label>麦克风设备</label>
              <select :value="currentDeviceId" @change="$emit('update:device', $event.target.value)">
                <option value="">默认设备</option>
                <option v-for="d in audioDevices" :key="d.deviceId" :value="d.deviceId">{{ d.label }}</option>
              </select>
            </div>
            <div class="form-group toggle-group">
              <label>麦克风开关</label>
              <button class="toggle" :class="{ on: micEnabled }"
                @click="$emit('update:mic-enabled', !micEnabled)">
                <span class="toggle-knob" />
              </button>
            </div>
          </div>

          <div class="tab-content" v-if="activeTab === 'model'">
            <div class="form-section">
              <h4>ASR 语音识别</h4>
              <div class="form-group">
                <label>模型</label>
                <select :value="modelConfig.asr_model"
                  @change="emitModel('asr_model', $event.target.value)">
                  <option value="fun-asr-realtime">Fun-ASR Realtime</option>
                </select>
              </div>
              <div class="form-group">
                <label>API Key</label>
                <input type="password" :value="modelConfig.asr_api_key" placeholder="默认使用 .env 配置"
                  @input="emitModel('asr_api_key', $event.target.value)" />
              </div>
            </div>

            <div class="form-section">
              <h4>LLM 对话模型</h4>
              <div class="form-group">
                <label>模型</label>
                <select :value="modelConfig.llm_model"
                  @change="emitModel('llm_model', $event.target.value)">
                  <option value="deepseek-v4-flash">DeepSeek v4 Flash</option>
                  <option value="deepseek-chat">DeepSeek Chat</option>
                  <option value="glm-5.1">GLM 5.1</option>
                </select>
              </div>
              <div class="form-group">
                <label>API Key</label>
                <input type="password" :value="modelConfig.llm_api_key" placeholder="默认使用 .env 配置"
                  @input="emitModel('llm_api_key', $event.target.value)" />
              </div>
              <div class="form-group">
                <label>Base URL</label>
                <input type="text" :value="modelConfig.llm_base_url" placeholder="https://api.deepseek.com"
                  @input="emitModel('llm_base_url', $event.target.value)" />
              </div>
            </div>

            <div class="form-section">
              <h4>TTS 语音合成</h4>
              <div class="form-group">
                <label>模型</label>
                <select :value="modelConfig.tts_model"
                  @change="emitModel('tts_model', $event.target.value)">
                  <option value="cosyvoice-v3.5-flash">CosyVoice v3.5 Flash（推荐，仅复刻音色）</option>
                  <option value="cosyvoice-v3-flash">CosyVoice v3 Flash（系统音色+复刻）</option>
                  <option value="cosyvoice-v3-plus">CosyVoice v3 Plus</option>
                  <option value="cosyvoice-v3.5-plus">CosyVoice v3.5 Plus</option>
                </select>
              </div>
              <div class="form-group">
                <label>API Key</label>
                <input type="password" :value="modelConfig.tts_api_key" placeholder="默认使用 .env 配置"
                  @input="emitModel('tts_api_key', $event.target.value)" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  visible: Boolean,
  voices: { type: Array, default: () => [] },
  currentVoice: String,
  currentInstruction: String,
  currentDeviceId: String,
  micEnabled: Boolean,
  audioDevices: { type: Array, default: () => [] },
  modelConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits([
  'close', 'update:voice', 'update:instruction', 'update:device',
  'update:mic-enabled', 'update:model-config',
])

const activeTab = ref('voice')

function emitModel(key, value) {
  emit('update:model-config', { key, value })
}
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}
.settings-panel {
  width: 360px;
  max-width: 90vw;
  height: 100%;
  background: rgba(15,15,30,0.95);
  backdrop-filter: blur(20px);
  border-left: 1px solid rgba(255,255,255,0.06);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.panel-header h3 {
  font-size: 18px;
  color: #e0d0f0;
  font-weight: 600;
}
.close-btn {
  background: none;
  border: none;
  color: rgba(200,180,220,0.6);
  font-size: 24px;
  cursor: pointer;
  padding: 0;
}
.close-btn:hover { color: #e0d0f0; }
.tabs {
  display: flex;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.tab {
  flex: 1;
  padding: 14px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: rgba(200,180,220,0.5);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.tab:hover { color: rgba(200,180,220,0.8); }
.tab.active {
  color: #e0d0f0;
  border-bottom-color: rgba(160,120,220,0.6);
}
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}
.form-section { margin-bottom: 24px; }
.form-section h4 {
  font-size: 13px;
  color: rgba(200,180,220,0.5);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 12px;
}
.form-group { margin-bottom: 16px; }
.form-group label {
  display: block;
  font-size: 12px;
  color: rgba(200,180,220,0.6);
  margin-bottom: 6px;
}
.form-group select, .form-group input, .form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.04);
  color: #e0d0f0;
  font-size: 13px;
  outline: none;
  font-family: inherit;
  resize: vertical;
}
.form-group select:focus, .form-group input:focus, .form-group textarea:focus {
  border-color: rgba(160,120,220,0.4);
}
.form-group input::placeholder, .form-group textarea::placeholder {
  color: rgba(200,180,220,0.2);
}
.toggle-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.toggle {
  width: 48px; height: 26px;
  border-radius: 13px;
  border: none;
  background: rgba(255,255,255,0.08);
  cursor: pointer;
  position: relative;
  transition: background 0.3s;
  padding: 0;
}
.toggle.on { background: rgba(160,120,220,0.5); }
.toggle-knob {
  position: absolute;
  top: 3px; left: 3px;
  width: 20px; height: 20px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.3s;
}
.toggle.on .toggle-knob { transform: translateX(22px); }

.panel-enter-active { transition: all 0.3s ease; }
.panel-leave-active { transition: all 0.2s ease; }
.panel-enter-from .settings-panel { transform: translateX(100%); }
.panel-enter-from { background: transparent; }
.panel-leave-to .settings-panel { transform: translateX(100%); }
.panel-leave-to { background: transparent; }
</style>

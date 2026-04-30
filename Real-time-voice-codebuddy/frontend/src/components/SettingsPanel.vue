<template>
  <Teleport to="body">
    <transition name="slide">
      <div v-if="visible" class="settings-overlay" @click.self="$emit('close')">
        <div class="settings-panel">
          <div class="panel-header">
            <h3>设置</h3>
            <button class="close-btn" @click="$emit('close')">&times;</button>
          </div>

          <div class="tab-bar">
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'voice' }"
              @click="activeTab = 'voice'"
            >语音设置</button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'model' }"
              @click="activeTab = 'model'"
            >模型与密钥</button>
          </div>

          <div class="panel-body">
            <!-- 语音设置 -->
            <div v-show="activeTab === 'voice'" class="tab-content">
              <div class="form-group">
                <label>TTS 音色</label>
                <select :value="currentVoice" @change="$emit('update:voice', $event.target.value)">
                  <option value="">加载中...</option>
                  <optgroup v-if="systemVoices.length" label="系统音色">
                    <option v-for="v in systemVoices" :key="v.value" :value="v.value">{{ v.label }}</option>
                  </optgroup>
                  <optgroup v-if="cloneVoices.length" label="复刻音色">
                    <option v-for="v in cloneVoices" :key="v.value" :value="v.value">{{ v.label }}</option>
                  </optgroup>
                </select>
              </div>

              <div class="form-group">
                <label>语气提示词</label>
                <textarea
                  :value="currentInstruction"
                  @input="$emit('update:instruction', $event.target.value)"
                  placeholder="如：用温柔撒娇的语气说"
                  rows="2"
                />
              </div>

              <div class="form-group">
                <label>麦克风设备</label>
                <select :value="currentDeviceId" @change="$emit('update:device', $event.target.value)">
                  <option v-for="d in audioDevices" :key="d.deviceId" :value="d.deviceId">{{ d.label }}</option>
                </select>
              </div>

              <div class="form-group toggle-group">
                <label>麦克风开关</label>
                <label class="toggle">
                  <input
                    type="checkbox"
                    :checked="micEnabled"
                    @change="$emit('update:mic-enabled', $event.target.checked)"
                  />
                  <span class="toggle-slider" />
                </label>
              </div>
            </div>

            <!-- 模型与密钥 -->
            <div v-show="activeTab === 'model'" class="tab-content">
              <div class="form-group">
                <label>ASR 模型</label>
                <select :value="modelConfig.asr_model" @change="updateModelConfig('asr_model', $event.target.value)">
                  <option value="fun-asr-realtime">Fun-ASR (fun-asr-realtime)</option>
                </select>
              </div>

              <div class="form-group">
                <label>ASR API Key</label>
                <input
                  type="password"
                  :value="modelConfig.asr_api_key"
                  @input="updateModelConfig('asr_api_key', $event.target.value)"
                  placeholder="DashScope API Key"
                />
              </div>

              <div class="form-group">
                <label>LLM 模型</label>
                <select :value="modelConfig.llm_model" @change="updateModelConfig('llm_model', $event.target.value)">
                  <option value="deepseek-v4-flash">DeepSeek (deepseek-v4-flash)</option>
                </select>
              </div>

              <div class="form-group">
                <label>LLM API Key</label>
                <input
                  type="password"
                  :value="modelConfig.llm_api_key"
                  @input="updateModelConfig('llm_api_key', $event.target.value)"
                  placeholder="LLM API Key"
                />
              </div>

              <div class="form-group">
                <label>LLM Base URL</label>
                <input
                  type="text"
                  :value="modelConfig.llm_base_url"
                  @input="updateModelConfig('llm_base_url', $event.target.value)"
                  placeholder="https://api.deepseek.com"
                />
              </div>

              <div class="form-group">
                <label>TTS 模型</label>
                <select :value="modelConfig.tts_model" @change="updateModelConfig('tts_model', $event.target.value)">
                  <option value="cosyvoice-v3.5-flash">CosyVoice v3.5 Flash</option>
                  <option value="cosyvoice-v3-flash">CosyVoice v3 Flash</option>
                  <option value="cosyvoice-v3-plus">CosyVoice v3 Plus</option>
                </select>
              </div>

              <div class="form-group">
                <label>TTS API Key</label>
                <input
                  type="password"
                  :value="modelConfig.tts_api_key"
                  @input="updateModelConfig('tts_api_key', $event.target.value)"
                  placeholder="DashScope API Key"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  voices: { type: Array, default: () => [] },
  currentVoice: { type: String, default: '' },
  currentInstruction: { type: String, default: '' },
  currentDeviceId: { type: String, default: '' },
  micEnabled: { type: Boolean, default: true },
  audioDevices: { type: Array, default: () => [] },
  modelConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits([
  'close',
  'update:voice',
  'update:instruction',
  'update:device',
  'update:mic-enabled',
  'update:model-config',
])

const activeTab = ref('voice')

const systemVoices = computed(() => props.voices.filter((v) => v.type === 'system'))
const cloneVoices = computed(() => props.voices.filter((v) => v.type === 'clone'))

function updateModelConfig(key, value) {
  emit('update:model-config', { key, value })
}
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: flex-end;
}

.settings-panel {
  width: 360px;
  max-width: 90vw;
  height: 100%;
  background: rgba(20, 15, 40, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.panel-header h3 {
  color: rgba(255, 255, 255, 0.9);
  font-size: 16px;
  font-weight: 500;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.6);
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: white;
}

.tab-bar {
  display: flex;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.tab-btn {
  flex: 1;
  padding: 12px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
}

.tab-btn.active {
  color: #ff7eb3;
  border-bottom-color: #ff7eb3;
}

.tab-content {
  padding: 16px 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 6px;
}

.form-group select,
.form-group input,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  color: #e0e0f0;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}

.form-group select:focus,
.form-group input:focus,
.form-group textarea:focus {
  border-color: rgba(255, 120, 180, 0.4);
}

.form-group textarea {
  resize: vertical;
  font-family: inherit;
}

.form-group select option {
  background: #1a1040;
  color: #e0e0f0;
}

.toggle-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toggle-group label:first-child {
  margin-bottom: 0;
}

.toggle {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.12);
  transition: 0.3s;
  cursor: pointer;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  border-radius: 50%;
  background: white;
  transition: 0.3s;
}

.toggle input:checked + .toggle-slider {
  background: rgba(255, 120, 180, 0.5);
}

.toggle input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* Slide transition */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

.slide-enter-to,
.slide-leave-from {
  transform: translateX(0);
}
</style>

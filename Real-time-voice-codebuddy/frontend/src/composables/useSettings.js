/**
 * 设置状态管理 + localStorage 持久化
 * 双分页：语音设置 + 模型与密钥
 */
import { ref, reactive, watch } from 'vue'

const STORAGE_KEY = 'yuki-voice-settings'

function _loadDefaults() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved) {
    try {
      return JSON.parse(saved)
    } catch (e) {
      // ignore
    }
  }
  return null
}

const defaults = _loadDefaults()

// 语音设置
const voice = ref(defaults?.voice || 'longxiaochun_v3')
const instruction = ref(defaults?.instruction || '')
const micEnabled = ref(defaults?.micEnabled !== undefined ? defaults.micEnabled : true)
const selectedDeviceId = ref(defaults?.selectedDeviceId || '')

// 模型与密钥
const modelConfig = reactive({
  asr_model: defaults?.asr_model || 'fun-asr-realtime',
  asr_api_key: defaults?.asr_api_key || '',
  llm_model: defaults?.llm_model || 'deepseek-v4-flash',
  llm_api_key: defaults?.llm_api_key || '',
  llm_base_url: defaults?.llm_base_url || 'https://api.deepseek.com',
  tts_model: defaults?.tts_model || 'cosyvoice-v3.5-flash',
  tts_api_key: defaults?.tts_api_key || '',
})

function _save() {
  const data = {
    voice: voice.value,
    instruction: instruction.value,
    micEnabled: micEnabled.value,
    selectedDeviceId: selectedDeviceId.value,
    ...modelConfig,
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
}

// 自动保存
watch([voice, instruction, micEnabled, selectedDeviceId], _save)
watch(modelConfig, _save, { deep: true })

export function useSettings() {
  function getUpdateConfigMsg() {
    const msg = { type: 'update_config' }
    if (voice.value) msg.voice = voice.value
    if (instruction.value) msg.instruction = instruction.value
    msg.asr_model = modelConfig.asr_model
    if (modelConfig.asr_api_key) msg.asr_api_key = modelConfig.asr_api_key
    msg.llm_model = modelConfig.llm_model
    if (modelConfig.llm_api_key) msg.llm_api_key = modelConfig.llm_api_key
    msg.llm_base_url = modelConfig.llm_base_url
    msg.tts_model = modelConfig.tts_model
    if (modelConfig.tts_api_key) msg.tts_api_key = modelConfig.tts_api_key
    return msg
  }

  return {
    voice,
    instruction,
    micEnabled,
    selectedDeviceId,
    modelConfig,
    getUpdateConfigMsg,
  }
}

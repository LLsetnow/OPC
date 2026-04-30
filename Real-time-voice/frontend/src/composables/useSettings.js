import { reactive, watch } from 'vue'

const STORAGE_KEY = 'real-time-voice-settings'

const defaults = {
  voice: 'longxiaochun_v3',
  instruction: '',
  deviceId: '',
  micEnabled: true,
  asr_model: 'fun-asr-realtime',
  asr_api_key: '',
  llm_model: 'deepseek-v4-flash',
  llm_api_key: '',
  llm_base_url: 'https://api.deepseek.com',
  tts_model: 'cosyvoice-v3.5-flash',
  tts_api_key: '',
}

function loadSettings() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? { ...defaults, ...JSON.parse(saved) } : { ...defaults }
  } catch {
    return { ...defaults }
  }
}

export function useSettings() {
  const settings = reactive(loadSettings())

  watch(settings, (val) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(val))
  }, { deep: true })

  function updateSetting(key, value) {
    if (key in settings) {
      settings[key] = value
    }
  }

  function getWebSocketConfig() {
    return {
      type: 'update_config',
      voice: settings.voice,
      instruction: settings.instruction,
      asr_model: settings.asr_model,
      asr_api_key: settings.asr_api_key,
      llm_model: settings.llm_model,
      llm_api_key: settings.llm_api_key,
      llm_base_url: settings.llm_base_url,
      tts_model: settings.tts_model,
      tts_api_key: settings.tts_api_key,
    }
  }

  return { settings, updateSetting, getWebSocketConfig }
}

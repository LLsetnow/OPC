"""Qwen3-TTS 常驻服务：模型加载一次，通过 HTTP API 提供推理服务

启动服务:
    opc tts-serve [--mode custom] [--port 9900] [--device cuda:0]

关闭服务:
    opc tts-serve --stop

释放模型（保持服务）:
    opc tts-unload

客户端调用:
    opc local-tts "你好" -s Vivian   # 自动检测本地服务，优先走服务端
"""

import io
import json
import os
import sys
import time
import threading
import signal
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

from .local_tts import (
    load_model,
    generate_custom_voice,
    generate_voice_design,
    generate_voice_clone,
    MODEL_PATHS,
    TOKENIZER_PATH,
    PRESET_SPEAKERS,
    SUPPORTED_LANGUAGES,
)

# ── 全局模型缓存 ──────────────────────────────────────────────────

_model_cache = {}       # mode -> model
_model_lock = threading.Lock()
_server_instance = None  # HTTPServer reference

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9900

# PID 文件，用于跨进程管理
_PID_DIR = Path(os.environ.get("TEMP", "/tmp")) / "opc_tts_server"
_PID_FILE = _PID_DIR / "server.json"


def _write_pid_info(port: int, mode: str, device: str):
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    info = {
        "pid": os.getpid(),
        "port": port,
        "mode": mode,
        "device": device,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(_PID_FILE, "w") as f:
        json.dump(info, f, indent=2)


def _read_pid_info() -> dict:
    if _PID_FILE.exists():
        try:
            return json.loads(_PID_FILE.read_text())
        except Exception:
            pass
    return {}


def _remove_pid_info():
    if _PID_FILE.exists():
        _PID_FILE.unlink()


def _is_server_running() -> bool:
    """Check if the TTS server is alive by hitting /health."""
    info = _read_pid_info()
    if not info:
        return False
    try:
        import urllib.request
        url = f"http://{DEFAULT_HOST}:{info['port']}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── HTTP Handler ──────────────────────────────────────────────────

class TTSHandler(BaseHTTPRequestHandler):
    """HTTP handler for TTS inference requests."""

    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_wav(self, wav_bytes, filename="output.wav"):
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav_bytes)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(wav_bytes)

    def do_GET(self):
        if self.path == "/health":
            modes_loaded = list(_model_cache.keys())
            self._send_json(200, {
                "status": "ok",
                "models_loaded": modes_loaded,
                "pid": os.getpid(),
            })
        elif self.path == "/speakers":
            self._send_json(200, PRESET_SPEAKERS)
        elif self.path == "/languages":
            self._send_json(200, SUPPORTED_LANGUAGES)
        elif self.path == "/status":
            info = _read_pid_info()
            modes_loaded = list(_model_cache.keys())
            self._send_json(200, {
                **info,
                "models_loaded": modes_loaded,
                "pid": os.getpid(),
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            params = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON"})
            return

        path = self.path

        # /generate - unified generation endpoint
        if path == "/generate":
            self._handle_generate(params)
        # /load - load a model into cache
        elif path == "/load":
            self._handle_load(params)
        # /unload - unload model from cache
        elif path == "/unload":
            self._handle_unload(params)
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_load(self, params):
        mode = params.get("mode", "custom")
        device = params.get("device", "cuda:0")
        attn = params.get("attn", "sdpa")

        if mode in _model_cache:
            self._send_json(200, {"status": "already_loaded", "mode": mode})
            return

        try:
            print(f"[tts-serve] 加载模型: {mode} (device={device}, attn={attn})")
            t0 = time.time()
            model = load_model(mode, device=device, attn=attn)
            elapsed = time.time() - t0
            with _model_lock:
                _model_cache[mode] = model
            print(f"[tts-serve] 模型 {mode} 已加载 (耗时: {elapsed:.1f}s)")
            self._send_json(200, {"status": "loaded", "mode": mode, "elapsed": round(elapsed, 1)})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_unload(self, params):
        mode = params.get("mode")
        if not mode:
            # Unload all
            with _model_lock:
                unloaded = list(_model_cache.keys())
                _model_cache.clear()
            if unloaded:
                import gc
                import torch
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print(f"[tts-serve] 已释放所有模型: {unloaded}")
            self._send_json(200, {"status": "unloaded", "modes": unloaded})
        else:
            with _model_lock:
                if mode in _model_cache:
                    del _model_cache[mode]
                    import gc
                    import torch
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    print(f"[tts-serve] 已释放模型: {mode}")
                    self._send_json(200, {"status": "unloaded", "mode": mode})
                else:
                    self._send_json(404, {"error": f"model '{mode}' not loaded"})

    def _handle_generate(self, params):
        mode = params.get("mode", "custom")
        text = params.get("text", "")
        output_path = params.get("output_path", "")  # server-side save
        return_wav = params.get("return_wav", True)  # return wav bytes

        if not text:
            self._send_json(400, {"error": "text is required"})
            return

        # Auto-load if not cached
        if mode not in _model_cache:
            device = params.get("device", "cuda:0")
            attn = params.get("attn", "sdpa")
            try:
                print(f"[tts-serve] 自动加载模型: {mode}")
                t0 = time.time()
                model = load_model(mode, device=device, attn=attn)
                elapsed = time.time() - t0
                with _model_lock:
                    _model_cache[mode] = model
                print(f"[tts-serve] 模型 {mode} 已加载 (耗时: {elapsed:.1f}s)")
            except Exception as e:
                self._send_json(500, {"error": f"failed to load model: {e}"})
                return

        model = _model_cache[mode]

        # Generate to buffer
        buf = io.BytesIO()

        try:
            t0 = time.time()
            if mode == "custom":
                speaker = params.get("speaker", "Vivian")
                language = params.get("language", "Chinese")
                instruct = params.get("instruct", "")
                kwargs = dict(text=text, language=language, speaker=speaker)
                if instruct:
                    kwargs["instruct"] = instruct
                wavs, sr = model.generate_custom_voice(**kwargs)
            elif mode == "design":
                instruct = params.get("instruct", "")
                language = params.get("language", "Chinese")
                if not instruct:
                    self._send_json(400, {"error": "instruct is required for design mode"})
                    return
                wavs, sr = model.generate_voice_design(
                    text=text, language=language, instruct=instruct,
                )
            elif mode == "base":
                ref_audio = params.get("ref_audio", "")
                if not ref_audio:
                    self._send_json(400, {"error": "ref_audio is required for base mode"})
                    return
                language = params.get("language", "Chinese")
                ref_text = params.get("ref_text", "")
                kwargs = dict(text=text, language=language, ref_audio=ref_audio)
                if ref_text:
                    kwargs["ref_text"] = ref_text
                wavs, sr = model.generate_voice_clone(**kwargs)
            else:
                self._send_json(400, {"error": f"unknown mode: {mode}"})
                return

            gen_time = time.time() - t0
            duration = len(wavs[0]) / sr

            # Write WAV to buffer
            import soundfile as sf
            sf.write(buf, wavs[0], sr, format="WAV")
            wav_bytes = buf.getvalue()

            # Optionally save to file on server side
            if output_path:
                out_dir = os.path.dirname(output_path)
                if out_dir:
                    os.makedirs(out_dir, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(wav_bytes)
                print(f"[tts-serve] 保存: {output_path} ({len(wav_bytes)/1024:.1f} KB, "
                      f"音频: {duration:.1f}s, 生成: {gen_time:.1f}s, RTF: {gen_time/duration:.2f})")

            if return_wav:
                self._send_wav(wav_bytes, os.path.basename(output_path) if output_path else "output.wav")
            else:
                self._send_json(200, {
                    "status": "ok",
                    "output_path": output_path,
                    "duration": round(duration, 2),
                    "gen_time": round(gen_time, 2),
                    "rtf": round(gen_time / duration, 2),
                    "file_size_kb": round(len(wav_bytes) / 1024, 1),
                })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})


# ── 服务启动/停止 ────────────────────────────────────────────────

def start_server(mode: str = "custom", device: str = "cuda:0", attn: str = "sdpa",
                 host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Start the TTS server, loading model on startup."""
    global _server_instance

    # Check if already running
    if _is_server_running():
        info = _read_pid_info()
        print(f"TTS 服务已在运行 (port={info.get('port')}, pid={info.get('pid')})")
        print(f"  模式: {info.get('mode')}, 设备: {info.get('device')}")
        return

    # Load initial model
    print(f"[tts-serve] 启动 TTS 服务 ({host}:{port})")
    print(f"[tts-serve] 预加载模型: {mode} (device={device}, attn={attn})")
    t0 = time.time()
    model = load_model(mode, device=device, attn=attn)
    elapsed = time.time() - t0
    with _model_lock:
        _model_cache[mode] = model
    print(f"[tts-serve] 模型 {mode} 加载完成 (耗时: {elapsed:.1f}s)")

    # Start HTTP server
    server = HTTPServer((host, port), TTSHandler)
    _server_instance = server
    _write_pid_info(port, mode, device)

    # Graceful shutdown
    def _shutdown(signum, frame):
        print(f"\n[tts-serve] 正在关闭服务...")
        with _model_lock:
            _model_cache.clear()
        _remove_pid_info()
        server.shutdown()
        print("[tts-serve] 服务已停止")

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print(f"[tts-serve] 服务就绪 → http://{host}:{port}")
    print(f"[tts-serve] API:")
    print(f"  GET  /health      - 健康检查")
    print(f"  GET  /speakers    - 预设音色列表")
    print(f"  GET  /status      - 服务状态")
    print(f"  POST /generate    - 生成语音")
    print(f"  POST /load        - 加载模型到缓存")
    print(f"  POST /unload      - 释放模型缓存")
    print(f"[tts-serve] 按 Ctrl+C 停止服务")

    server.serve_forever()


def stop_server():
    """Stop the running TTS server."""
    info = _read_pid_info()
    if not info:
        print("未发现运行中的 TTS 服务")
        return

    pid = info.get("pid")
    port = info.get("port")

    # Try HTTP shutdown first (gentle)
    try:
        import urllib.request
        url = f"http://{DEFAULT_HOST}:{port}/health"
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass

    # Try to kill the process
    if pid:
        try:
            import psutil
            p = psutil.Process(pid)
            p.terminate()
            p.wait(timeout=5)
            print(f"TTS 服务已停止 (pid={pid})")
        except ImportError:
            # Fallback: use os.kill on Linux/Mac, taskkill on Windows
            try:
                if sys.platform == "win32":
                    os.system(f"taskkill /PID {pid} /F")
                else:
                    os.kill(pid, signal.SIGTERM)
                print(f"TTS 服务已停止 (pid={pid})")
            except ProcessLookupError:
                print(f"进程 {pid} 不存在")
        except psutil.NoSuchProcess:
            print(f"进程 {pid} 不存在")
        except Exception as e:
            print(f"停止服务失败: {e}")
    else:
        print("PID 信息缺失，请手动关闭")

    _remove_pid_info()


def get_server_url() -> str:
    """Get the URL of the running TTS server, or empty string if not running."""
    if _is_server_running():
        info = _read_pid_info()
        return f"http://{DEFAULT_HOST}:{info.get('port', DEFAULT_PORT)}"
    return ""


def call_server_generate(server_url: str, params: dict, output_path: str) -> dict:
    """Call the TTS server to generate audio and save to file."""
    import urllib.request

    params["return_wav"] = True
    if output_path:
        params["output_path"] = ""

    body = json.dumps(params, ensure_ascii=False).encode("utf-8")
    url = f"{server_url}/generate"

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
    req_time = time.time() - t0

    if "audio/wav" in content_type:
        # Save wav
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)

        import soundfile as sf
        info = sf.info(output_path)
        duration = info.duration
        return {
            "status": "ok",
            "output_path": output_path,
            "duration": round(duration, 2),
            "gen_time": round(req_time, 2),
            "rtf": round(req_time / duration, 2) if duration > 0 else 0,
            "file_size_kb": round(len(data) / 1024, 1),
            "via_server": True,
        }
    else:
        # JSON response (error)
        result = json.loads(data)
        return result


def call_server_load(server_url: str, mode: str, device: str = "cuda:0", attn: str = "sdpa") -> dict:
    """Ask the server to load a model."""
    import urllib.request

    body = json.dumps({"mode": mode, "device": device, "attn": attn}).encode("utf-8")
    url = f"{server_url}/load"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def call_server_unload(server_url: str, mode: str = "") -> dict:
    """Ask the server to unload model(s)."""
    import urllib.request

    body = json.dumps({"mode": mode}).encode("utf-8") if mode else b"{}"
    url = f"{server_url}/unload"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

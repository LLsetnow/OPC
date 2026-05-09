"""ComfyUI 进程管理 + 工作流提交"""

import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# PID 文件，用于跨进程管理
_PID_DIR = Path(os.environ.get("TEMP", "/tmp")) / "opc_comfyui"
_PID_FILE = _PID_DIR / "server.json"


def _write_pid_info(pid: int, comfyui_root: str, listen: str, port: int):
    _PID_DIR.mkdir(parents=True, exist_ok=True)
    info = {
        "pid": pid,
        "comfyui_root": comfyui_root,
        "listen": listen,
        "port": port,
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


def is_comfyui_running() -> bool:
    """检查 ComfyUI 进程是否存活"""
    info = _read_pid_info()
    if not info:
        return False
    pid = info.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        _remove_pid_info()
        return False


def _is_wsl() -> bool:
    """检测是否在 WSL 中运行"""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _to_windows_path(wsl_path: str) -> str:
    """将 WSL 路径转为 Windows 路径（如 /mnt/d/foo -> D:\\foo）"""
    p = Path(wsl_path)
    parts = p.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt":
        drive = parts[2].upper()
        rest = "\\".join(parts[3:])
        return f"{drive}:\\{rest}"
    return wsl_path


def start_comfyui(comfyui_root: str, listen: str = "0.0.0.0", port: int = 8188):
    """启动 ComfyUI 进程"""
    root = Path(comfyui_root)
    python_exe = root / "python" / "python.exe"
    main_py = root / "main.py"

    if not python_exe.exists():
        raise FileNotFoundError(f"Python 不存在: {python_exe}")
    if not main_py.exists():
        raise FileNotFoundError(f"main.py 不存在: {main_py}")

    if is_comfyui_running():
        info = _read_pid_info()
        print(f"ComfyUI 已在运行中 (pid={info.get('pid')})")
        return

    # WSL 下需要将 main_py 参数转为 Windows 格式，因为 python.exe 是 Windows 程序
    # 但 python.exe 路径和 cwd 保持 WSL 格式（subprocess 从 WSL 执行）
    if _is_wsl():
        cmd = [
            str(python_exe),
            _to_windows_path(str(main_py)),
            "--listen", listen,
            "--port", str(port),
        ]
    else:
        cmd = [
            str(python_exe),
            str(main_py),
            "--listen", listen,
            "--port", str(port),
        ]

    print(f"启动 ComfyUI: {' '.join(cmd)}")

    log_dir = _PID_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "comfyui.log"

    with open(log_path, "a") as log_f:
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=log_f,
            cwd=str(root),
            start_new_session=True,
        )

    _write_pid_info(proc.pid, comfyui_root, listen, port)
    print(f"ComfyUI 已启动 (pid={proc.pid})")
    print(f"  地址: http://{listen}:{port}")
    print(f"  日志: {log_path}")


def stop_comfyui():
    """关闭 ComfyUI 进程"""
    info = _read_pid_info()
    if not info:
        print("ComfyUI 未在运行")
        return

    pid = info.get("pid")
    if not pid:
        print("PID 信息缺失，请手动关闭")
        return

    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        print(f"进程 {pid} 不存在，清理 PID 文件")
        _remove_pid_info()
        return

    try:
        try:
            import psutil
            p = psutil.Process(pid)
            p.terminate()
            p.wait(timeout=5)
            print(f"ComfyUI 已停止 (pid={pid})")
        except ImportError:
            if sys.platform == "win32":
                os.system(f"taskkill /PID {pid} /F")
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"ComfyUI 已停止 (pid={pid})")
    except Exception as e:
        try:
            if sys.platform == "win32":
                os.system(f"taskkill /PID {pid} /F")
            else:
                os.kill(pid, signal.SIGKILL)
            print(f"ComfyUI 已强制停止 (pid={pid})")
        except Exception:
            print(f"停止 ComfyUI 失败: {e}")

    _remove_pid_info()


def check_comfyui():
    """检查 ComfyUI 运行状态，返回状态信息 dict"""
    info = _read_pid_info()
    running = is_comfyui_running()

    return {
        "running": running,
        "pid": info.get("pid") if running else None,
        "comfyui_root": info.get("comfyui_root", ""),
        "listen": info.get("listen", ""),
        "port": info.get("port", ""),
        "started_at": info.get("started_at", "") if running else "",
    }


# ═══════════════════════════════════════════════════════════════
# 工作流提交
# ═══════════════════════════════════════════════════════════════

def generate_random_seed():
    """生成15位随机数种子"""
    return random.randint(10**14, 10**15 - 1)


def find_nodes_by_class(workflow: dict) -> dict:
    """
    自动识别工作流中的关键节点，返回节点ID映射。
    兼容 class_type 精确匹配和 _meta.title 模糊匹配。
    """
    nodes = {
        "load_image": None,       # LoadImage
        "ksampler": None,         # KSampler
        "save_image": None,       # SaveImage / PreviewImage
        "prompt_nodes": [],       # 含 "prompt" 或 "text" 输入的节点
        "seed_nodes": [],         # 含 "seed" 输入的节点（KSampler 等）
    }

    for node_id, node_data in workflow.items():
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs", {})

        # 加载图像
        if class_type == "LoadImage":
            nodes["load_image"] = node_id

        # KSampler
        if class_type == "KSampler":
            nodes["ksampler"] = node_id

        # 保存图像
        if class_type in ("SaveImage", "PreviewImage"):
            if nodes["save_image"] is None or class_type == "SaveImage":
                nodes["save_image"] = node_id

        # 提示词节点（包含 prompt 或 text 输入）
        if "prompt" in inputs or "text" in inputs:
            nodes["prompt_nodes"].append(node_id)

        # 种子节点
        if "seed" in inputs:
            nodes["seed_nodes"].append(node_id)

    return nodes


def _get_windows_host_ip() -> str | None:
    """WSL2 中获取 Windows 宿主 IP"""
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.startswith("nameserver"):
                    return line.split()[1]
    except Exception:
        pass
    return None


def check_server(server_url: str, max_attempts: int = 3, delay: float = 2) -> bool:
    """检查 ComfyUI 服务器是否可访问（WSL2 下自动尝试 Windows 宿主 IP）"""
    urls_to_try = [server_url]

    # WSL2 下 127.0.0.1 不通 Windows 服务，自动补充宿主 IP
    if "127.0.0.1" in server_url or "localhost" in server_url:
        host_ip = _get_windows_host_ip()
        if host_ip and host_ip != "127.0.0.1":
            alt_url = server_url.replace("127.0.0.1", host_ip).replace("localhost", host_ip)
            if alt_url != server_url:
                urls_to_try.append(alt_url)

    for url in urls_to_try:
        for attempt in range(max_attempts):
            try:
                urllib.request.urlopen(url, timeout=5)
                return True
            except Exception:
                if attempt < max_attempts - 1:
                    time.sleep(delay)

    return False


def queue_prompt(server_url: str, prompt_workflow: dict, max_retries: int = 3) -> str | None:
    """将 workflow 提交到 ComfyUI /prompt 接口，返回 prompt_id"""
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode("utf-8")
    url = f"{server_url}/prompt"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    for attempt in range(max_retries):
        try:
            print(f"  提交工作流到 ComfyUI...")
            response = urllib.request.urlopen(req, timeout=10)
            result = json.loads(response.read().decode("utf-8"))
            prompt_id = result.get("prompt_id")
            if prompt_id:
                print(f"  工作流已提交，prompt_id: {prompt_id}")
                return prompt_id
            else:
                # 检查是否有错误信息
                error_msg = result.get("error", "") or json.dumps(result)
                print(f"  提交返回异常: {error_msg}")
                return None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            print(f"  HTTP {e.code} (尝试 {attempt + 1}/{max_retries}): {body}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  提交失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return None


def wait_for_completion(server_url: str, prompt_id: str, timeout: int = 300) -> dict | None:
    """
    轮询 /history/{prompt_id} 直到任务完成，返回 history 数据。
    返回 None 表示超时或失败。
    """
    start_time = time.time()
    check_count = 0

    while time.time() - start_time < timeout:
        check_count += 1

        try:
            url = f"{server_url}/history/{prompt_id}"
            response = urllib.request.urlopen(url, timeout=5)
            result = json.loads(response.read().decode("utf-8"))

            if prompt_id in result:
                history = result[prompt_id]
                status = history.get("status", {})

                if status.get("completed", False):
                    elapsed = int(time.time() - start_time)
                    print(f"  任务完成 (耗时 {elapsed}s, 检查 {check_count} 次)")
                    return history

                # 检查是否有执行错误
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    for msg in messages:
                        if msg[0] == "execution_error":
                            err = msg[1]
                            print(f"\n  执行错误:")
                            print(f"    节点类型: {err.get('node_type', '?')}")
                            print(f"    节点ID: {err.get('node_id', '?')}")
                            print(f"    异常: {err.get('exception_message', '').strip().split(chr(10))[0]}")
                            print(f"    类型: {err.get('exception_type', '?')}")
                    return None

            # 每10次检查打印进度
            if check_count % 10 == 0:
                elapsed = int(time.time() - start_time)
                print(f"  等待中... (已 {elapsed}s, 检查 {check_count} 次)")

        except urllib.error.HTTPError as e:
            if e.code == 404:
                if check_count <= 3:
                    print(f"  任务排队中...")
            else:
                print(f"  HTTP 错误: {e.code}")
        except Exception as e:
            print(f"  状态查询异常: {e}")

        time.sleep(3 if check_count > 10 else 2)

    elapsed = int(time.time() - start_time)
    print(f"  等待超时 ({elapsed}s > {timeout}s)")
    return None


def get_output_from_history(history: dict, comfyui_output_dir: str) -> list[str]:
    """从 history 数据中提取输出文件路径列表"""
    output_files = []
    outputs = history.get("outputs", {})

    for node_id, node_output in outputs.items():
        images = node_output.get("images", [])
        for img in images:
            filename = img.get("filename", "")
            subfolder = img.get("subfolder", "")
            if subfolder:
                filepath = os.path.join(comfyui_output_dir, subfolder, filename)
            else:
                filepath = os.path.join(comfyui_output_dir, filename)
            if os.path.exists(filepath):
                output_files.append(filepath)

    return output_files


def _find_comfyui_output_dir(server_url: str) -> str:
    """尝试通过 ComfyUI 的 /object_info 推断 output 目录"""
    # 默认路径
    info = _read_pid_info()
    comfyui_root = info.get("comfyui_root", "")
    if comfyui_root:
        output_dir = os.path.join(comfyui_root, "output")
        if os.path.isdir(output_dir):
            return output_dir

    # 回退：从环境变量读取
    env_root = os.environ.get("COMFYUI_ROOT", "")
    if env_root:
        output_dir = os.path.join(env_root, "output")
        if os.path.isdir(output_dir):
            return output_dir

    return ""


def _resolve_server_url(server_url: str) -> str:
    """WSL2 下自动将 127.0.0.1 替换为 Windows 宿主 IP"""
    if "127.0.0.1" in server_url or "localhost" in server_url:
        host_ip = _get_windows_host_ip()
        if host_ip and host_ip not in ("127.0.0.1", "::1"):
            return server_url.replace("127.0.0.1", host_ip).replace("localhost", host_ip)
    return server_url


def submit_workflow(
    workflow_path: str,
    server_url: str = "http://127.0.0.1:8188",
    image: str | None = None,
    prompt: str | None = None,
    seed: int | None = None,
    output_dir: str | None = None,
    timeout: int = 300,
    # 节点ID覆盖（通常自动检测）
    load_image_node: str | None = None,
    ksampler_node: str | None = None,
    save_image_node: str | None = None,
    prompt_node: str | None = None,
    seed_node: str | None = None,
    # 额外参数
    steps: int | None = None,
    cfg: float | None = None,
    denoise: float | None = None,
    output_prefix: str | None = None,
):
    """
    提交工作流到 ComfyUI 并等待完成，返回输出文件路径列表。

    自动检测工作流中的关键节点（LoadImage / KSampler / SaveImage / prompt节点），
    也可通过参数手动指定节点ID覆盖自动检测结果。

    :param workflow_path: 工作流 JSON 文件路径
    :param server_url: ComfyUI 服务地址
    :param image: 输入图片路径（复制到 ComfyUI input 目录）
    :param prompt: 提示词文本
    :param seed: 随机种子（不指定则自动生成）
    :param output_dir: 结果输出目录（默认当前目录）
    :param timeout: 最大等待时间（秒）
    :param load_image_node: LoadImage 节点 ID（覆盖自动检测）
    :param ksampler_node: KSampler 节点 ID（覆盖自动检测）
    :param save_image_node: SaveImage 节点 ID（覆盖自动检测）
    :param prompt_node: 提示词输入节点 ID（覆盖自动检测）
    :param seed_node: 种子节点 ID（覆盖自动检测）
    :param steps: 采样步数
    :param cfg: CFG scale
    :param denoise: 去噪强度
    :param output_prefix: 输出文件名前缀
    :return: 输出文件路径列表
    """
    # 0. WSL2 下自动解析 Windows 宿主 IP
    server_url = _resolve_server_url(server_url)
    print(f"  ComfyUI 服务地址: {server_url}")

    # 1. 检查服务器
    if not check_server(server_url):
        raise RuntimeError(f"ComfyUI 服务器不可访问: {server_url}\n请先启动 ComfyUI: opc comfyui --start")

    # 2. 加载工作流
    wf_path = Path(workflow_path)
    if not wf_path.exists():
        raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")

    with open(wf_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    print(f"已加载工作流: {wf_path.name} ({len(workflow)} 个节点)")

    # 3. 自动检测关键节点
    detected = find_nodes_by_class(workflow)
    _load_img = load_image_node or detected["load_image"]
    _ksampler = ksampler_node or detected["ksampler"]
    _save_img = save_image_node or detected["save_image"]
    _prompt_n = prompt_node or (detected["prompt_nodes"][0] if detected["prompt_nodes"] else None)
    _seed_n = seed_node or (_ksampler if _ksampler else (detected["seed_nodes"][0] if detected["seed_nodes"] else None))

    print(f"  检测节点: LoadImage={_load_img}, KSampler={_ksampler}, SaveImage={_save_img}, Prompt={_prompt_n}")

    # 4. 设置参数

    # 4a. 输入图片
    if image:
        if not _load_img:
            raise RuntimeError("工作流中未找到 LoadImage 节点，无法设置输入图片。请用 --load-image-node 指定节点ID。")

        image_path = Path(image)
        if not image_path.exists():
            raise FileNotFoundError(f"输入图片不存在: {image}")

        # 获取 ComfyUI input 目录
        comfyui_root = ""
        info = _read_pid_info()
        comfyui_root = info.get("comfyui_root", "") or os.environ.get("COMFYUI_ROOT", "")
        if comfyui_root:
            comfyui_input = os.path.join(comfyui_root, "input")
        else:
            comfyui_input = os.path.join(os.path.dirname(workflow_path), "input")

        # 复制图片到 ComfyUI input 目录
        os.makedirs(comfyui_input, exist_ok=True)
        dest_path = os.path.join(comfyui_input, image_path.name)
        if not os.path.exists(dest_path) or not os.path.samefile(str(image_path), dest_path):
            shutil.copy2(str(image_path), dest_path)
            print(f"  输入图片已复制: {image_path.name} -> {comfyui_input}")
        else:
            print(f"  使用已有图片: {image_path.name}")

        workflow[_load_img]["inputs"]["image"] = image_path.name
        print(f"  设置输入图片: {image_path.name}")

    # 4b. 种子
    if seed is None:
        seed = generate_random_seed()
    if _seed_n and "seed" in workflow[_seed_n].get("inputs", {}):
        workflow[_seed_n]["inputs"]["seed"] = int(seed)
        print(f"  设置种子: {seed}")
    elif _seed_n:
        print(f"  警告: 节点 {_seed_n} 没有 seed 输入")

    # 4c. 提示词
    if prompt:
        if not _prompt_n:
            raise RuntimeError("工作流中未找到提示词节点，无法设置 prompt。请用 --prompt-node 指定节点ID。")
        inputs = workflow[_prompt_n].get("inputs", {})
        if "prompt" in inputs:
            workflow[_prompt_n]["inputs"]["prompt"] = prompt
        elif "text" in inputs:
            workflow[_prompt_n]["inputs"]["text"] = prompt
        else:
            print(f"  警告: 节点 {_prompt_n} 没有 prompt/text 输入，可用: {list(inputs.keys())}")
        print(f"  设置提示词: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    # 4d. 输出前缀
    if _save_img:
        if output_prefix:
            workflow[_save_img]["inputs"]["filename_prefix"] = output_prefix
            print(f"  设置输出前缀: {output_prefix}")
        else:
            # 记录原始前缀用于后续查找
            current_prefix = workflow[_save_img]["inputs"].get("filename_prefix", "ComfyUI")
            if not output_prefix:
                output_prefix = current_prefix
    else:
        output_prefix = output_prefix or "ComfyUI"

    # 4e. 额外采样参数
    if _ksampler:
        sampler_inputs = workflow[_ksampler].get("inputs", {})
        if steps is not None and "steps" in sampler_inputs:
            sampler_inputs["steps"] = steps
            print(f"  设置步数: {steps}")
        if cfg is not None and "cfg" in sampler_inputs:
            sampler_inputs["cfg"] = cfg
            print(f"  设置 CFG: {cfg}")
        if denoise is not None and "denoise" in sampler_inputs:
            sampler_inputs["denoise"] = denoise
            print(f"  设置去噪: {denoise}")

    # 5. 提交工作流
    prompt_id = queue_prompt(server_url, workflow)
    if not prompt_id:
        raise RuntimeError("工作流提交失败")

    # 6. 等待完成
    print(f"\n  等待任务完成 (prompt_id: {prompt_id})...")
    history = wait_for_completion(server_url, prompt_id, timeout=timeout)
    if not history:
        raise RuntimeError(f"任务未完成或超时 (prompt_id: {prompt_id})")

    # 7. 获取输出文件
    comfyui_output = _find_comfyui_output_dir(server_url)
    output_files = get_output_from_history(history, comfyui_output)

    if not output_files:
        raise RuntimeError(f"任务完成但未找到输出文件 (prompt_id: {prompt_id})")

    print(f"\n  找到 {len(output_files)} 个输出文件")

    # 8. 复制到目标目录
    if output_dir:
        dest_dir = Path(output_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        result_paths = []
        for src in output_files:
            filename = os.path.basename(src)
            dst = dest_dir / filename
            shutil.copy2(src, str(dst))
            result_paths.append(str(dst))
            print(f"  输出: {dst}")
        return result_paths

    return output_files

"""UI 截图转 Vue 前端代码：视觉模型分析 UI + LLM 生成 Vue 代码 + 创建工程并自动修复"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .vision import encode_image, _is_url
from .config import get_vision_config, get_llm_config


# ── Prompt 模板 ────────────────────────────────────────────────────

VISION_PROMPT = """请详细分析这个 UI 界面截图，输出以下内容：

1. **布局结构**：描述整体布局（头部、侧栏、内容区、底部等）
2. **组件清单**：逐个列出所有可见的 UI 组件（按钮、输入框、表格、卡片、导航等），描述其文字内容、位置、样式特征
3. **配色方案**：提取主要颜色值（背景色、主色调、文字色、边框色等）
4. **交互元素**：列出所有可交互元素及其预期行为
5. **数据结构**：推断界面需要的数据模型（表格列、表单字段、列表项等）

请尽可能详细、准确，以便后续根据此描述生成代码。"""

CODE_GEN_SYSTEM_PROMPT = """你是一位资深前端开发专家，擅长根据 UI 描述生成高质量的 Vue 组件代码。

要求：
1. 使用 Vue 3 Composition API（<script setup>）
2. 使用 TypeScript
3. 样式使用 <style scoped>，采用 Flexbox/Grid 布局
4. 代码结构清晰、语义化标签、合理拆分组件
5. 响应式设计，使用 rem/百分比等相对单位
6. 为交互元素添加合适的响应式数据（ref/reactive）
7. 如有表单，添加基本的验证逻辑
8. 如有列表数据，使用 computed/methods 处理
9. 注释关键逻辑

输出格式：
- 先用简短文字描述组件拆分思路
- 然后输出完整的 Vue SFC 代码（包含 <template>、<script setup lang="ts">、<style scoped>）
- 如果界面较复杂，可拆分为多个组件，每个组件用 "=== 组件名.vue ===" 分隔"""

FIX_SYSTEM_PROMPT = """你是一位资深前端开发专家，擅长调试和修复 Vue 3 项目中的编译错误。

当前 Vue 项目使用 Vite + TypeScript 构建。请根据编译错误信息，分析错误原因并给出修复后的完整文件内容。

修复规则：
1. 只输出需要修改的文件的完整内容
2. 每个文件用 "=== 文件名 ===" 标记开头（文件名相对于项目 src/ 目录）
3. 不要输出无需修改的文件
4. 确保修复后的代码语法正确、类型正确
5. 如果错误涉及缺失的 npm 依赖，在输出的第一行用 "=== NPM_INSTALL: 包名 ===" 标记
6. 不要修改与错误无关的代码"""

PROMPT_TEMPLATES = {
    "default": "请根据以下 UI 分析描述，生成对应的 Vue 3 组件代码。",
    "element-plus": "请根据以下 UI 分析描述，使用 Element Plus 组件库生成 Vue 3 代码。",
    "ant-design-vue": "请根据以下 UI 分析描述，使用 Ant Design Vue 组件库生成 Vue 3 代码。",
    "naive-ui": "请根据以下 UI 分析描述，使用 Naive UI 组件库生成 Vue 3 代码。",
    "vuetify": "请根据以下 UI 分析描述，使用 Vuetify 组件库生成 Vue 3 代码。",
    "tailwind": "请根据以下 UI 分析描述，使用 Tailwind CSS 生成 Vue 3 代码（无需 <style> 块）。",
    "pure": "请根据以下 UI 分析描述，使用纯 HTML/CSS 生成 Vue 3 代码（不使用任何 UI 框架）。",
}


def _build_client(api_key: str, base_url: str):
    """构建 OpenAI 兼容客户端，自动处理 URL 路径"""
    from openai import OpenAI

    client_base_url = base_url.rstrip("/")
    if not client_base_url.endswith(("/v4", "/v1")):
        client_base_url += "/v1"

    return OpenAI(api_key=api_key, base_url=client_base_url)


# ── 步骤1：视觉模型分析 UI ────────────────────────────────────────

def analyze_ui(image: str, vision_model: str = "glm-5v-turbo") -> str:
    """
    第一步：使用视觉模型分析 UI 截图，输出结构化描述。

    Args:
        image: 本地图片路径或网络 URL
        vision_model: 视觉模型名称

    Returns:
        UI 结构化描述文本
    """
    api_key, base_url = get_vision_config()

    if _is_url(image):
        image_url = image
    else:
        if not os.path.exists(image):
            print(f"错误: 图片文件不存在: {image}")
            sys.exit(1)
        file_size = os.path.getsize(image)
        print(f"编码图片: {image} ({file_size / 1024:.1f} KB)")
        image_url = encode_image(image)

    client = _build_client(api_key, base_url)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }
    ]

    print(f"[步骤1/3] 视觉分析 UI 截图 (模型: {vision_model})...")

    response = client.chat.completions.create(
        model=vision_model,
        messages=messages,
        max_tokens=4096,
        temperature=0.3,
    )

    return response.choices[0].message.content


# ── 步骤2：LLM 生成 Vue 代码 ──────────────────────────────────────

def generate_vue_code(
    ui_description: str,
    framework: str = "default",
    component_name: str = "",
    llm_model: str = "",
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> str:
    """
    第二步：使用 LLM 根据 UI 描述生成 Vue 组件代码。

    Args:
        ui_description: UI 结构化描述文本
        framework: UI 框架
        component_name: 组件名称
        llm_model: LLM 模型名称（为空则使用 LLM_MODEL 环境变量）
        max_tokens: 最大输出 token 数
        temperature: 生成温度

    Returns:
        Vue 组件代码
    """
    api_key, base_url, default_model = get_llm_config()
    model = llm_model or default_model

    client = _build_client(api_key, base_url)

    prompt_text = PROMPT_TEMPLATES.get(framework, PROMPT_TEMPLATES["default"])
    if component_name:
        prompt_text += f"\n\n组件名称：{component_name}"

    messages = [
        {"role": "system", "content": CODE_GEN_SYSTEM_PROMPT},
        {"role": "user", "content": f"{prompt_text}\n\n---\n\n{ui_description}"},
    ]

    print(f"[步骤2/3] 生成 Vue 代码 (模型: {model}, 框架: {framework})...")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return response.choices[0].message.content


# ── 步骤3：创建 Vue 工程 + 自动检查修复 ────────────────────────────

def _run_cmd(cmd: list, cwd: str, timeout: int = 120) -> tuple:
    """
    执行命令，返回 (returncode, stdout, stderr)。
    优先使用 WSL（如果在 Windows 上运行），否则本地执行。
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except FileNotFoundError:
        return -2, "", f"命令未找到: {cmd[0]}"


def _check_npm_available() -> str:
    """检查 npm 是否可用，返回 npm 路径或空字符串"""
    # 优先检查 WSL 中的 npm
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wsl", "-e", "zsh", "-c", "which npm"],
                capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                return "wsl"
        except Exception:
            pass
        # 检查 Windows 本地 npm
        try:
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                return "local"
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                return "local"
        except Exception:
            pass
    return ""


def _wsl_path(win_path: str) -> str:
    """将 Windows 路径转为 WSL 路径"""
    path = Path(win_path).resolve()
    drive = path.drive[0].lower()
    return f"/mnt/{drive}{path.as_posix()[2:]}"


def _run_npm(args: list, cwd: str, shell_env: str, timeout: int = 120) -> tuple:
    """根据环境执行 npm 命令"""
    if shell_env == "wsl":
        wsl_cwd = _wsl_path(cwd)
        cmd = ["wsl", "-e", "zsh", "-c", f"cd {wsl_cwd} && npm {' '.join(args)}"]
    else:
        cmd = ["npm"] + args

    return _run_cmd(cmd, cwd if shell_env != "wsl" else ".", timeout=timeout)


def _run_npx(args: list, cwd: str, shell_env: str, timeout: int = 120) -> tuple:
    """根据环境执行 npx 命令"""
    if shell_env == "wsl":
        wsl_cwd = _wsl_path(cwd)
        cmd = ["wsl", "-e", "zsh", "-c", f"cd {wsl_cwd} && npx {' '.join(args)}"]
    else:
        cmd = ["npx"] + args

    return _run_cmd(cmd, cwd if shell_env != "wsl" else ".", timeout=timeout)


def create_vue_project(project_dir: str, project_name: str = "vue-app", shell_env: str = "") -> str:
    """
    创建 Vue 3 + Vite + TypeScript 项目。

    Args:
        project_dir: 项目所在目录
        project_name: 项目名称
        shell_env: 执行环境 ("wsl" / "local")

    Returns:
        项目根目录路径
    """
    if not shell_env:
        shell_env = _check_npm_available()
    if not shell_env:
        print("错误: 未找到 npm，请先安装 Node.js")
        sys.exit(1)

    project_path = os.path.join(project_dir, project_name)

    # 如果项目已存在，跳过创建
    if os.path.exists(os.path.join(project_path, "package.json")):
        print(f"  项目已存在: {project_path}")
        # 确保依赖已安装
        if not os.path.exists(os.path.join(project_path, "node_modules")):
            print("  安装依赖...")
            _run_npm(["install"], project_path, shell_env, timeout=180)
        return project_path

    print(f"  创建 Vue 项目: {project_path} (环境: {shell_env})")

    # 使用 npm create vite 创建项目
    if shell_env == "wsl":
        wsl_dir = _wsl_path(project_dir)
        cmd = ["wsl", "-e", "zsh", "-c",
               f"cd {wsl_dir} && npm create vite@5 {project_name} -- --template vue-ts 2>&1"]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
    else:
        subprocess.run(
            ["npm", "create", "vite@5", project_name, "--", "--template", "vue-ts"],
            cwd=project_dir, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
        )

    # 安装依赖
    print("  安装基础依赖...")
    _run_npm(["install"], project_path, shell_env, timeout=180)

    return project_path


def _read_vue_files(project_path: str) -> dict:
    """读取项目 src/ 目录下所有 .vue 和 .ts 文件内容"""
    files = {}
    src_dir = os.path.join(project_path, "src")
    for root, _, filenames in os.walk(src_dir):
        for fname in filenames:
            if fname.endswith((".vue", ".ts")) and not fname.endswith(".d.ts"):
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, src_dir)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        files[rel_path] = f.read()
                except Exception:
                    pass
    return files


def _check_vue_build(project_path: str, shell_env: str) -> tuple:
    """
    检查 Vue 项目是否能构建成功。

    Returns:
        (success: bool, error_output: str)
    """
    # 先尝试 vue-tsc 类型检查
    rc, stdout, stderr = _run_npx(
        ["vue-tsc", "--noEmit"], project_path, shell_env, timeout=120
    )
    if rc != 0:
        error_text = (stdout + "\n" + stderr).strip()
        return False, f"[vue-tsc 类型检查失败]\n{error_text}"

    # 再尝试 vite build
    rc, stdout, stderr = _run_npx(
        ["vite", "build"], project_path, shell_env, timeout=120
    )
    if rc != 0:
        error_text = (stdout + "\n" + stderr).strip()
        return False, f"[vite build 构建失败]\n{error_text}"

    return True, ""


def _extract_fixes(fix_text: str) -> tuple:
    """
    从 LLM 修复输出中提取文件修复内容和 npm 安装指令。

    Returns:
        (files: dict[str, str], npm_packages: list[str])
        files: 相对路径 -> 文件内容
        npm_packages: 需要安装的 npm 包名列表
    """
    files = {}
    npm_packages = []

    # 提取 npm 安装指令: "=== NPM_INSTALL: 包名 ==="
    npm_pattern = r"===\s*NPM_INSTALL:\s*(.+?)\s*==="
    for match in re.finditer(npm_pattern, fix_text):
        npm_packages.append(match.group(1).strip())

    # 提取文件修复: "=== 相对路径 ===" 后面跟文件内容，直到下一个 "===" 或文件结尾
    # 支持多行文件内容
    file_pattern = r"===\s*(\S+\.(?:vue|ts|js|css))\s*===\s*\n(.*?)(?====\s*\S+\.(?:vue|ts|js|css)\s*===|$)"
    for match in re.finditer(file_pattern, fix_text, re.DOTALL):
        rel_path = match.group(1)
        content = match.group(2).strip()
        # 清理可能残留的 markdown 代码围栏
        content = re.sub(r"^```(?:\w+)?\s*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)
        content = content.strip()
        if content:
            files[rel_path] = content

    # 如果上面的模式没匹配到，尝试更宽松的模式
    if not files:
        # 尝试匹配 "=== 文件名 ===" 后紧跟 ```代码块
        block_pattern = r"===\s*(\S+\.(?:vue|ts|js|css))\s*===\s*\n```(?:\w+)?\s*\n(.*?)```"
        for match in re.finditer(block_pattern, fix_text, re.DOTALL):
            rel_path = match.group(1)
            content = match.group(2).strip()
            if content:
                files[rel_path] = content

    return files, npm_packages


def _apply_fixes(project_path: str, files: dict, npm_packages: list, shell_env: str) -> list:
    """
    应用修复到项目文件。

    Returns:
        修复的文件路径列表
    """
    src_dir = os.path.join(project_path, "src")
    applied = []

    for rel_path, content in files.items():
        fpath = os.path.join(src_dir, rel_path)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        applied.append(fpath)
        print(f"    修复文件: {rel_path}")

    # 安装缺失的 npm 依赖
    if npm_packages:
        for pkg in npm_packages:
            print(f"    安装依赖: {pkg}")
            _run_npm(["install", pkg], project_path, shell_env, timeout=120)

    return applied


def _call_llm_for_fix(error_output: str, project_files: dict, llm_model: str) -> str:
    """调用 LLM 修复构建错误"""
    api_key, base_url, _ = get_llm_config()

    client = _build_client(api_key, base_url)

    # 构建项目文件摘要（只取文件名和前20行，避免 token 过长）
    file_summaries = []
    for rel_path, content in project_files.items():
        lines = content.split("\n")
        summary_lines = lines[:30]
        if len(lines) > 30:
            summary_lines.append(f"  ... (共 {len(lines)} 行)")
        file_summaries.append(f"--- {rel_path} ---\n" + "\n".join(summary_lines))

    files_text = "\n\n".join(file_summaries)

    # 构建错误相关的完整文件内容（最多5个文件）
    error_files_text = ""
    # 尝试从错误信息中提取文件名
    error_file_names = re.findall(r"(\S+\.(?:vue|ts))", error_output)
    for ef in set(error_file_names[:5]):
        # 查找匹配的项目文件
        for rel_path, content in project_files.items():
            if rel_path.endswith(ef) or ef.endswith(rel_path):
                error_files_text += f"\n\n=== {rel_path} (完整内容) ===\n{content}"
                break

    user_content = f"""## 编译错误信息

```
{error_output[:3000]}
```

## 项目文件结构概览

{files_text}

## 错误相关文件完整内容

{error_files_text[:8000]}

请分析错误原因，并输出需要修改的文件的完整修复内容。每个文件用 "=== 文件名 ===" 标记。"""

    messages = [
        {"role": "system", "content": FIX_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = client.chat.completions.create(
        model=llm_model,
        messages=messages,
        max_tokens=8192,
        temperature=0.2,
    )

    return response.choices[0].message.content


def setup_vue_project(
    vue_result: str,
    output_dir: str,
    component_name: str = "GeneratedComponent",
    project_name: str = "vue-app",
    max_retries: int = 3,
    llm_model: str = "",
) -> dict:
    """
    第三步：创建 Vue 工程，写入组件代码，自动检查并修复构建错误。

    Args:
        vue_result: LLM 生成的 Vue 代码文本
        output_dir: 输出目录
        component_name: 主组件名称
        project_name: Vue 项目名称
        max_retries: 最大修复重试次数
        llm_model: 用于修复的 LLM 模型名称

    Returns:
        结果字典: {
            "project_path": str,
            "saved_files": list,
            "success": bool,
            "retries": int,
            "errors": list,
        }
    """
    api_key, base_url, default_model = get_llm_config()
    model = llm_model or default_model
    shell_env = _check_npm_available()

    print(f"[步骤3/3] 创建 Vue 工程并验证...")

    # 3.1 创建 Vue 项目
    project_path = create_vue_project(output_dir, project_name, shell_env)

    # 3.2 提取并保存 Vue 组件文件
    saved_files = save_vue_files(vue_result, os.path.join(project_path, "src", "components"), component_name)
    print(f"  保存组件: {', '.join(saved_files)}")

    # 3.3 更新 App.vue 引入主组件
    main_component = saved_files[0] if saved_files else f"{component_name}.vue"
    comp_name_no_ext = Path(main_component).stem
    app_vue_path = os.path.join(project_path, "src", "App.vue")
    app_vue_content = f"""<template>
  <{comp_name_no_ext} />
</template>

<script setup lang="ts">
import {comp_name_no_ext} from './components/{main_component}'
</script>

<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
</style>
"""
    with open(app_vue_path, "w", encoding="utf-8") as f:
        f.write(app_vue_content)
    print(f"  更新 App.vue: 引入 {comp_name_no_ext}")

    # 3.4 检查构建 + 自动修复循环
    errors_history = []
    success = False
    retries = 0

    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"\n  修复重试 {attempt}/{max_retries}...")

        # 构建检查
        ok, error_output = _check_vue_build(project_path, shell_env)

        if ok:
            success = True
            print(f"  构建成功！(尝试 {attempt} 次)")
            break

        errors_history.append(error_output)
        retries = attempt

        if attempt >= max_retries:
            print(f"  达到最大重试次数 ({max_retries})，停止修复")
            break

        print(f"  构建失败，调用 LLM 修复 (模型: {model})...")

        # 截取关键错误信息
        error_lines = error_output.split("\n")
        # 取最后 50 行错误（通常最有用）
        concise_error = "\n".join(error_lines[-50:])
        print(f"  错误摘要: {concise_error[:200]}...")

        # 读取当前项目文件
        project_files = _read_vue_files(project_path)

        # 调用 LLM 修复
        fix_text = _call_llm_for_fix(error_output, project_files, model)

        # 提取修复内容
        fix_files, npm_packages = _extract_fixes(fix_text)

        if not fix_files and not npm_packages:
            print("  LLM 未返回有效的修复内容")
            # 尝试将整个修复输出作为单个文件保存
            continue

        # 应用修复
        applied = _apply_fixes(project_path, fix_files, npm_packages, shell_env)
        if applied:
            print(f"  已应用 {len(applied)} 个文件修复")

    return {
        "project_path": project_path,
        "saved_files": saved_files,
        "success": success,
        "retries": retries,
        "errors": errors_history,
    }


# ── 完整流程入口 ──────────────────────────────────────────────────

def ui2vue(
    image: str,
    framework: str = "default",
    component_name: str = "",
    output: str = "",
    project_name: str = "vue-app",
    vision_model: str = "glm-5v-turbo",
    llm_model: str = "",
    max_tokens: int = 8192,
    temperature: float = 0.3,
    max_retries: int = 3,
    create_project: bool = True,
) -> tuple:
    """
    完整流程：视觉分析 UI 截图 + LLM 生成 Vue 代码 + 创建工程并自动修复。

    Args:
        image: 本地图片路径或网络 URL
        framework: UI 框架
        component_name: 组件名称
        output: 输出目录
        project_name: Vue 项目名称
        vision_model: 视觉模型名称
        llm_model: LLM 模型名称
        max_tokens: 最大输出 token 数
        temperature: 生成温度
        max_retries: 最大修复重试次数
        create_project: 是否创建 Vue 工程（步骤3）

    Returns:
        (ui_description, vue_result, setup_result) 元组
        setup_result 为 None 当 create_project=False
    """
    # 步骤1：视觉模型分析 UI
    ui_description = analyze_ui(image, vision_model=vision_model)

    print("\n" + "─" * 50)
    print("UI 分析完成，开始生成代码...")
    print("─" * 50 + "\n")

    # 步骤2：LLM 生成 Vue 代码
    vue_code = generate_vue_code(
        ui_description,
        framework=framework,
        component_name=component_name,
        llm_model=llm_model,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    # 步骤3：创建 Vue 工程 + 自动修复
    setup_result = None
    if create_project:
        output_dir = output or "."
        setup_result = setup_vue_project(
            vue_code,
            output_dir=output_dir,
            component_name=component_name or "GeneratedComponent",
            project_name=project_name,
            max_retries=max_retries,
            llm_model=llm_model,
        )

    return ui_description, vue_code, setup_result


# ── 文件保存工具 ──────────────────────────────────────────────────

def save_vue_files(result: str, output_dir: str, component_name: str = "GeneratedComponent"):
    """
    从模型输出中提取 Vue 组件代码并保存为 .vue 文件。

    如果输出包含多个组件（以 "=== 组件名.vue ===" 分隔），
    则分别保存；否则整体保存为单个 .vue 文件。
    """
    os.makedirs(output_dir, exist_ok=True)

    pattern = r"===\s*(\S+\.vue)\s*==="
    splits = re.split(pattern, result)

    if len(splits) > 1:
        saved = []
        for i in range(1, len(splits), 2):
            filename = splits[i]
            code = splits[i + 1].strip() if i + 1 < len(splits) else ""
            vue_code = _extract_vue_code(code)
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(vue_code)
            saved.append(filename)
        return saved
    else:
        vue_code = _extract_vue_code(result)
        filename = f"{component_name}.vue"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(vue_code)
        return [filename]


def _extract_vue_code(text: str) -> str:
    """从文本中提取 Vue SFC 代码块"""
    code_block_pattern = r"```(?:vue|html)\s*\n(.*?)```"
    matches = re.findall(code_block_pattern, text, re.DOTALL)
    if matches:
        return max(matches, key=len).strip()

    template_pattern = r"(<template>.*?</style(?:\s+scoped)?>)"
    matches = re.findall(template_pattern, text, re.DOTALL)
    if matches:
        return max(matches, key=len).strip()

    return text.strip()

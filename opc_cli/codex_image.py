"""通过本机 codex CLI 的内置 image_gen 工具生成图片（gpt-image 驱动）。

`opc image generate --engine gpt-image` 不再直接调用 OpenAI 兼容 API，
改为调用本机 `codex exec`：codex 内置 `image_gen__imagegen` 工具（由 gpt-image
驱动，需 ChatGPT 账号登录）。本机已验证 codex-cli 0.147+ 可用。

实现方式：``codex exec --output-schema`` + ``-o`` 让 agent 把最终图片保存到
指定路径，并以结构化 JSON 返回图片路径。
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# codex exec 内置 image_gen 工具可用的最低版本
CODEX_MIN_VERSION = (0, 147)


class CodexImageError(RuntimeError):
    """codex 图像生成失败。"""


def _parse_version(text: str) -> tuple:
    """从 codex --version 输出中解析版本号，如 (0, 147, 0)。"""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups() if part is not None)


def codex_available() -> bool:
    """codex CLI 是否安装且版本 >= 0.147。"""
    exe = shutil.which("codex")
    if not exe:
        return False
    try:
        result = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _parse_version(result.stdout or result.stderr) >= CODEX_MIN_VERSION


def _size_hint(size: str) -> str:
    """把 `-s/--size` 转成提示词里的画面比例说明。

    内置 image_gen 工具不暴露尺寸参数，比例通过提示词控制
    （工具会自动把比例诉求带入生成）。
    """
    s = (size or "").strip().lower()
    if not s or s in ("auto", "1:1"):
        return "方形构图（1:1）"
    if "*" in s:  # 像素写法，如 1024*1536
        try:
            w, h = (int(part) for part in s.split("*", 1)[:2])
        except ValueError:
            return f"分辨率约 {s.replace('*', '×')}"
        orientation = "横版" if w > h else "竖版" if h > w else "方形"
        return f"{orientation}，分辨率约 {w}×{h}"
    try:
        w, h = (int(part) for part in s.split(":"))
    except ValueError:
        return f"画面比例 {s}"
    if w > h:
        return f"横版构图（{s}）"
    if h > w:
        return f"竖版构图（{s}）"
    return "方形构图（1:1）"


def _build_schema(single: bool) -> dict:
    """codex exec --output-schema 使用的最终回复 JSON Schema。"""
    if single:
        return {
            "type": "object",
            "properties": {"image_path": {"type": "string"}},
            "required": ["image_path"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "image_paths": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["image_paths"],
        "additionalProperties": False,
    }


def _output_paths(output: str, n: int) -> list[str]:
    """计算最终保存路径：n=1 用原路径；n>1 在文件名后追加 _1/_2/...。"""
    if n <= 1:
        return [output]
    target = Path(output)
    paths = []
    for index in range(1, n + 1):
        paths.append(
            str(target.with_name(f"{target.stem}_{index}{target.suffix or '.png'}"))
        )
    return paths


def generate_with_codex(
    prompt: str,
    output: str,
    size: str = "2:3",
    n: int = 1,
    ref: list = None,
    enhance: bool = True,
    timeout: int = 600,
) -> list[str]:
    """调用 `codex exec` 生成一张或多张图片，返回最终保存的绝对路径列表。

    Args:
        prompt: 图像提示词。
        output: 保存路径（n>1 时作为基名，自动追加 _1/_2/...）。
        size: 宽高比或像素（如 2:3 / 16:9 / 1024*1536），转成提示词比例说明。
        n: 生成张数（变体）。
        ref: 参考图路径列表（通过 codex exec --image 附到会话）。
        enhance: 是否允许模型优化/丰富提示词。
        timeout: codex exec 最大等待秒数。

    Raises:
        CodexImageError: codex 不可用、执行失败或结果缺失。
    """
    exe = shutil.which("codex")
    if not exe:
        raise CodexImageError(
            "未找到 codex CLI：请先安装 codex-cli（brew install codex）"
            "并用 ChatGPT 账号登录（codex login）"
        )
    try:
        version = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=15
        )
        installed = _parse_version(version.stdout or version.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CodexImageError(f"无法运行 codex CLI: {error}") from error
    if installed < CODEX_MIN_VERSION:
        raise CodexImageError(
            f"codex CLI 版本过低（{'.'.join(map(str, installed))}），"
            f"需要 {'.'.join(map(str, CODEX_MIN_VERSION))}+"
        )

    paths = _output_paths(output, n)
    for path in paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    single = len(paths) == 1
    schema = _build_schema(single)

    lines = [
        "使用内置 image_gen 工具（image_gen__imagegen）生成图片，"
        "不要使用 CLI 回退模式，不要向用户提问。",
        "",
        "图片要求：",
        prompt,
        f"画面比例：{_size_hint(size)}",
    ]
    if ref:
        lines.append(f"参考图片：共 {len(ref)} 张，作为风格/构图/内容参考（已在会话中附上）。")
    if enhance:
        lines.append("允许适度优化、丰富提示词表述，但不要改变用户的核心意图。")
    else:
        lines.append("严格按给定提示词生成，不要改写或增删内容。")
    lines.append("不要添加任何文字、标题、Logo 或水印，除非提示词明确要求。")

    if single:
        save_step = f"将最终选定的图片保存到 {paths[0]}（如已存在则覆盖）"
        final_json = '{"image_path": "<保存图片的绝对路径>"}'
    else:
        save_step = "生成 {n} 个变体，分别保存到：\n{files}".format(
            n=n, files="\n".join(f"- {path}" for path in paths)
        )
        final_json = '{"image_paths": ["<绝对路径1>", "<绝对路径2>", ...]}'

    lines += [
        "",
        "任务步骤：",
        "1. 调用内置 image_gen 工具生成图片。",
        f"2. {save_step}。",
        "3. 最后只输出一个 JSON 对象（不要输出其他任何内容，不要用代码块包裹）：",
        final_json,
    ]
    agent_prompt = "\n".join(lines)

    with tempfile.TemporaryDirectory(prefix="opc-codex-") as temp_dir:
        schema_path = os.path.join(temp_dir, "schema.json")
        last_path = os.path.join(temp_dir, "last.txt")
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False)

        cmd = [
            exe, "exec",
            "--skip-git-repo-check",
            "-C", os.getcwd(),
            "--output-schema", schema_path,
            "-o", last_path,
        ]
        for reference in ref or []:
            cmd += ["--image", reference]
        cmd.append(agent_prompt)

        try:
            result = subprocess.run(cmd, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise CodexImageError(
                f"codex exec 超时（>{timeout}s），可增大 --timeout"
            ) from error
        if result.returncode != 0:
            raise CodexImageError(
                f"codex exec 失败（退出码 {result.returncode}），"
                "请确认 codex 已用 ChatGPT 账号登录（codex login）"
            )

        if not os.path.exists(last_path):
            raise CodexImageError("codex exec 未返回结构化结果")
        try:
            data = json.loads(Path(last_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CodexImageError(f"codex 返回结果解析失败: {error}") from error

        if single:
            saved = [data["image_path"]] if data.get("image_path") else []
        else:
            saved = data.get("image_paths") or []
        if not saved:
            raise CodexImageError("codex 返回结果缺少图片路径")

    missing = [path for path in saved if not os.path.exists(path)]
    if missing:
        raise CodexImageError(f"图片文件不存在: {', '.join(missing)}")
    return saved

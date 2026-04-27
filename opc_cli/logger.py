"""终端输出日志记录：将所有 print/console.print 输出同步保存到 logs/ 目录"""

import os
import re
import sys
import time
from pathlib import Path


# ── ANSI 转义码清理 ──────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[.*?[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    """移除 ANSI 转义码，返回纯文本"""
    return _ANSI_RE.sub("", text)


# ── TeeWriter: 同时写入终端和日志文件 ─────────────────────────────

class TeeWriter:
    """
    包装 stdout/stderr，在写入终端的同时将内容追加到日志文件。
    日志文件自动去除 ANSI 转义码，保持纯文本可读性。
    """

    def __init__(self, original_stream, log_path: str):
        self._original = original_stream
        self._log_path = log_path
        self._log_file = None
        self._buffer = ""

    def _ensure_log_file(self):
        """延迟打开日志文件（首次写入时才创建）"""
        if self._log_file is None:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
            self._log_file = open(self._log_path, "a", encoding="utf-8", errors="replace")

    def write(self, text: str):
        # 写入终端
        self._original.write(text)

        if not text:
            return

        # 写入日志文件
        self._ensure_log_file()
        clean = _strip_ansi(text)
        if clean:
            self._log_file.write(clean)
            self._log_file.flush()

    def write_log_only(self, text: str):
        """仅写入日志文件，不输出到终端"""
        if not text:
            return
        self._ensure_log_file()
        clean = _strip_ansi(text)
        if clean:
            self._log_file.write(clean)
            self._log_file.flush()

    def flush(self):
        self._original.flush()
        if self._log_file:
            self._log_file.flush()

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return self._original.isatty()

    def reconfigure(self, **kwargs):
        """代理 reconfigure 调用到原始流"""
        if hasattr(self._original, "reconfigure"):
            self._original.reconfigure(**kwargs)

    @property
    def encoding(self):
        return self._original.encoding

    def close(self):
        """关闭日志文件（不要关闭原始流）"""
        if self._log_file:
            self._log_file.flush()
            self._log_file.close()
            self._log_file = None


# ── 日志管理 ─────────────────────────────────────────────────────

def get_log_path(base_dir: str = None) -> str:
    """
    获取当日日志文件路径。

    Args:
        base_dir: 日志目录根路径，默认为项目根目录下的 logs/

    Returns:
        日志文件绝对路径，格式: logs/YYYY-MM-DD.log
    """
    if not base_dir:
        # 项目根目录: 从 opc_cli/ 上层取
        base_dir = str(Path(__file__).resolve().parent.parent / "logs")
    date_str = time.strftime("%Y-%m-%d")
    return os.path.join(base_dir, f"{date_str}.log")


def install_tee(log_path: str = None) -> str:
    """
    安装 TeeWriter，将 stdout 和 stderr 重定向到日志文件。
    在 CLI 入口处调用一次即可。

    Args:
        log_path: 日志文件路径，默认为 logs/YYYY-MM-DD.log

    Returns:
        实际使用的日志文件路径
    """
    if not log_path:
        log_path = get_log_path()

    # 记录会话分隔线
    separator = f"\n{'='*60}\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] opc 会话开始\n{'='*60}\n"

    # 写入分隔线到日志
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(separator)

    # 包装 stdout 和 stderr
    sys.stdout = TeeWriter(sys.stdout, log_path)
    sys.stderr = TeeWriter(sys.stderr, log_path)

    return log_path


def log_only(text: str):
    """
    仅写入日志文件，不输出到终端。
    用于大段内容（如完整分析/代码）的日志记录，终端只显示摘要。
    """
    if isinstance(sys.stdout, TeeWriter):
        sys.stdout.write_log_only(text)
    elif isinstance(sys.stderr, TeeWriter):
        sys.stderr.write_log_only(text)

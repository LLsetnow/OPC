"""日志系统：终端 + 按日期写入 logs/ 目录 + 错误捕获"""

import asyncio
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_stderr_file = {"file": None, "date": None}


class DateRotatingFileHandler(logging.Handler):
    """按日期自动轮转的文件 Handler，同一天日志追加到同一文件"""

    def __init__(self):
        super().__init__()
        self._current_date = None
        self._file = None
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return LOG_DIR / f"{today}.log"

    def emit(self, record):
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date:
            if self._file:
                self._file.close()
            self._current_date = today
            self._file = open(self._get_log_path(), "a", encoding="utf-8")
        if self._file:
            msg = self.format(record)
            self._file.write(msg + "\n")
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()
        super().close()


def setup_logger(name: str = "voice-chat", level: int = logging.DEBUG) -> logging.Logger:
    """初始化日志系统，返回 logger 实例"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    # 终端 handler
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter(
        f"%(asctime)s [%(levelname)s] %(message)s",
        datefmt=_DATE_FORMAT,
    ))

    # 文件 handler（按日期轮转）
    file_handler = DateRotatingFileHandler()
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        f"%(asctime)s [%(levelname)s] %(message)s",
        datefmt=_DATE_FORMAT,
    ))

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "voice-chat") -> logging.Logger:
    """获取已初始化的 logger"""
    return logging.getLogger(name)


# ── 错误捕获：unhandled exception + stderr ──────────────────────────

class _StderrTee:
    """将 stderr 输出同时写入日志文件"""

    def __init__(self):
        self._stderr = sys.stderr

    def _get_file(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if _stderr_file["date"] != today:
            if _stderr_file["file"]:
                _stderr_file["file"].close()
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            _stderr_file["file"] = open(LOG_DIR / f"{today}.log", "a", encoding="utf-8")
            _stderr_file["date"] = today
        return _stderr_file["file"]

    def write(self, data):
        self._stderr.write(data)
        f = self._get_file()
        if f and data.strip():
            ts = datetime.now().strftime("%H:%M:%S")
            for line in data.rstrip("\n").split("\n"):
                f.write(f"{ts} [STDERR] {line}\n")
            f.flush()

    def flush(self):
        self._stderr.flush()


def setup_error_capture(logger: logging.Logger):
    """安装全局错误捕获：sys.excepthook + asyncio 异常 + stderr 重定向"""

    def _excepthook(exc_type, exc_value, exc_tb):
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        logger.error(f"未捕获异常:\n{''.join(tb_lines).rstrip()}")

    sys.excepthook = _excepthook
    sys.stderr = _StderrTee()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda loop, ctx: logger.error(
        f"asyncio 异常: {ctx.get('message', '')}",
        exc_info=ctx.get('exception'),
    ))

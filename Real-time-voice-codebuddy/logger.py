"""日志系统：终端 + 按日期写入 logs/ 目录"""

import logging
from datetime import datetime
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent / "logs"
_DATE_FORMAT = "%H:%M:%S"


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

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt=_DATE_FORMAT,
    )

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)

    file_handler = DateRotatingFileHandler()
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "voice-chat") -> logging.Logger:
    """获取已初始化的 logger"""
    return logging.getLogger(name)

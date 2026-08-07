"""抖音视频下载为 MP4。"""

from __future__ import annotations

from ._video import download_video as _download_video


class DouyinDownloadError(RuntimeError):
    """抖音视频下载失败。"""


def download_video(url: str, output_dir: str, cookies: str | None = None) -> str:
    """下载单个抖音视频并返回最终 MP4 的绝对路径。"""
    return _download_video(
        url,
        output_dir,
        cookies,
        source_label="抖音",
        error_cls=DouyinDownloadError,
    )

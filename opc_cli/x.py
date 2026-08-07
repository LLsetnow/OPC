"""X (Twitter) 视频下载为 MP4。"""

from __future__ import annotations

from ._video import download_video as _download_video


class XDownloadError(RuntimeError):
    """X (Twitter) 视频下载失败。"""


# X 未登录时大量视频不可见（yt-dlp 报 "No video could be found"）；
# 下载失败时统一附带这条提示，指引用户用 cookies 重试。
_COOKIES_HINT = (
    "若提示 'No video could be found' 或需要登录，请用 --cookies 传入从浏览器导出的 "
    "cookies.txt（或设置环境变量 YT_DLP_COOKIES）后重试。"
)


def download_video(url: str, output_dir: str, cookies: str | None = None) -> str:
    """下载单个 X (Twitter) 视频并返回最终 MP4 的绝对路径。"""
    return _download_video(
        url,
        output_dir,
        cookies,
        source_label="X",
        error_cls=XDownloadError,
        failure_hint=_COOKIES_HINT,
    )

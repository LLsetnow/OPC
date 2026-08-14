"""统一媒体下载：bilibili / 抖音 / X / 网易云 平台自动识别与下载分发。

`opc media download <URL>` 通过 URL 域名自动识别平台，统一入口：
- bilibili：默认下载音频；--audio-only 转 MP3（含 ID3）；--summarize 走下载→ASR→总结
- douyin / x：默认下载 MP4；--summarize 走下载音频→ASR→总结
- netease（网易云）：下载单曲/专辑/歌单 → MP3（含 ID3）
"""

import os

from . import bili
from .config import get_bili_folder, get_douyin_folder, get_x_folder, get_music_folder
from .douyin import DouyinDownloadError, download_video as download_douyin_video
from .music import run_music
from .x import XDownloadError, download_video as download_x_video

SUPPORTED_PLATFORMS = ("bilibili", "douyin", "x", "netease")

# 平台识别：URL 子串 → 平台名（顺序敏感，先匹配更具体的域名）
_PLATFORM_MARKERS = (
    ("bilibili.com", "bilibili"),
    ("b23.tv", "bilibili"),
    ("douyin.com", "douyin"),
    ("x.com", "x"),
    ("twitter.com", "x"),
    ("music.163.com", "netease"),
)


class MediaError(RuntimeError):
    """媒体下载参数或平台识别错误。"""


def detect_platform(url: str) -> str:
    """根据 URL 域名识别平台，返回 bilibili / douyin / x / netease。

    无法识别时抛出 :class:`MediaError`，并列出支持的平台。
    """
    lowered = (url or "").lower()
    for marker, platform in _PLATFORM_MARKERS:
        if marker in lowered:
            return platform
    raise MediaError(
        f"无法识别的媒体平台 URL: {url}\n"
        "支持平台: bilibili（bilibili.com / b23.tv）、douyin（douyin.com）、"
        "x（x.com / twitter.com）、netease（music.163.com）"
    )


def download_media(
    url: str,
    output_dir: str = "",
    cookies: str = None,
    audio_only: bool = False,
    bitrate: int = 192,
    no_metadata: bool = False,
    playlist: bool = False,
    summarize: bool = False,
    skip_download: bool = False,
    audio_file: str = None,
    skip_asr: bool = False,
    asr_file: str = None,
    llm_fix: bool = False,
):
    """统一媒体下载入口，按 URL 平台分发。

    参数语义与原有命令保持一致：
    - ``--summarize`` 启用 下载音频 → ASR → LLM 总结 流水线（bilibili/douyin/x 通用）
    - ``--audio-only`` 仅对 bilibili 生效：下载并转 MP3（含 ID3 元数据）
    - ``--bitrate/--no-metadata`` 影响 MP3 输出（bilibili --audio-only 与 netease）
    - ``--playlist`` 仅 netease（网易云）歌单下载生效
    - ``--skip-download/--audio-file/--skip-asr/--asr-file/--llm-fix`` 仅与 --summarize 搭配
    """
    platform = detect_platform(url)

    pipeline_flags = skip_download or audio_file or skip_asr or asr_file
    if pipeline_flags and not summarize:
        raise MediaError(
            "参数 --skip-download / --audio-file / --skip-asr / --asr-file 仅能与 "
            "--summarize 一起使用（用于跳过流水线中的下载/转写步骤）"
        )
    if summarize and audio_only:
        raise MediaError("--summarize 与 --audio-only 不能同时使用")

    if platform == "netease":
        if summarize:
            raise MediaError("网易云音乐下载不支持 --summarize 内容总结（该功能用于视频平台）")
        out_dir = output_dir or get_music_folder() or "./output"
        return run_music(
            url=url,
            output_dir=out_dir,
            bitrate=bitrate,
            no_metadata=no_metadata,
            cookies=cookies,
            playlist=playlist,
        )

    if platform == "bilibili":
        out_dir = output_dir or get_bili_folder() or "./output"
        if summarize:
            return bili.run_bili(
                url=url,
                output_dir=out_dir,
                cookies=cookies,
                skip_download=skip_download,
                audio_file=audio_file,
                skip_asr=skip_asr,
                asr_file=asr_file,
                llm_fix=llm_fix,
                bitrate=bitrate,
                no_metadata=no_metadata,
            )
        if audio_only:
            return bili.run_bili(
                url=url,
                output_dir=out_dir,
                cookies=cookies,
                audio_only=True,
                bitrate=bitrate,
                no_metadata=no_metadata,
            )
        # 默认：仅下载音频文件（不转换）
        audio_path = bili.download_audio(url, out_dir, cookies=cookies)
        print(f"完成! 已下载音频: {audio_path}")
        return audio_path

    # douyin / x
    if platform == "douyin":
        out_dir = output_dir or get_douyin_folder() or "./output"
    else:
        out_dir = output_dir or get_x_folder() or "./output"
    if summarize:
        # run_bili 内部基于 yt-dlp，对抖音/X 同样可下载音频并完成 ASR + 总结
        return bili.run_bili(
            url=url,
            output_dir=out_dir,
            cookies=cookies,
            skip_download=skip_download,
            audio_file=audio_file,
            skip_asr=skip_asr,
            asr_file=asr_file,
            llm_fix=llm_fix,
            bitrate=bitrate,
            no_metadata=no_metadata,
        )
    if audio_only:
        raise MediaError("--audio-only 仅对 bilibili 平台生效（抖音/X 请直接下载视频）")
    cookies = cookies or os.environ.get("YT_DLP_COOKIES")
    if platform == "douyin":
        try:
            output_path = download_douyin_video(url, out_dir, cookies)
        except DouyinDownloadError as error:
            raise MediaError(f"抖音下载失败: {error}") from error
    else:
        try:
            output_path = download_x_video(url, out_dir, cookies)
        except XDownloadError as error:
            raise MediaError(f"X 下载失败: {error}") from error
    print(f"完成! 已保存 MP4: {output_path}")
    return output_path

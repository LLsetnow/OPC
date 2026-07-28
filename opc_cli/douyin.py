"""抖音视频下载为 MP4。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class DouyinDownloadError(RuntimeError):
    """抖音视频下载失败。"""


def _ensure_ytdlp() -> None:
    """确认 yt-dlp 可用，避免下载到一半才报缺少依赖。"""
    try:
        subprocess.run(
            ["yt-dlp", "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise DouyinDownloadError(
            "未找到可用的 yt-dlp；请先运行 `pip install -U yt-dlp`。"
        ) from error


def _metadata_arguments() -> list[str]:
    """构造把原链接 / 作者 / 发布信息写入 MP4 元数据的 yt-dlp 参数。

    - ``--embed-metadata`` 将标题、作者(artist)、发布日期(date)等标准字段写入 MP4；
    - ``--parse-metadata`` 把「原链接 + 作者 + 发布日期」合并写入 comment 字段，
      这样在播放器 / 文件属性 / ffprobe 中都能直接看到视频来源。

    注意：yt-dlp 的 ``--parse-metadata`` 以第一个半角冒号 ``:`` 分隔 FROM / TO，
    因此 FROM 模板里的标签使用全角冒号「：」与全角竖线「｜」，避免被误当作分隔符；
    同时 FROM 模板必须保持单行（换行会导致 yt-dlp 解析失败）。
    """
    comment_template = (
        "来源：%(webpage_url)s"
        " ｜ 作者：%(uploader)s"
        " ｜ 发布：%(upload_date>%Y-%m-%d)s"
    )
    return [
        "--embed-metadata",
        "--parse-metadata",
        f"{comment_template}:%(meta_comment)s",
    ]


def _find_downloaded_mp4(stdout: str, output_dir: Path) -> Path | None:
    """从 yt-dlp 的 after_move 输出中取得实际保存路径。"""
    for line in reversed(stdout.splitlines()):
        candidate = Path(line.strip())
        if candidate.suffix.lower() == ".mp4" and candidate.is_file():
            return candidate

    candidates = sorted(
        output_dir.glob("*.mp4"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _read_embedded_comment(mp4_path: str) -> str:
    """用 ffprobe 读取 MP4 内部 comment 标签（下载时已写入来源信息）。"""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format_tags=comment",
                "-of",
                "default=nw=1:nk=1",
                mp4_path,
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _write_finder_comment(mp4_path: str) -> bool:
    """在 macOS 上把来源信息写入 Finder 评注（显示简介 → 评注）。

    macOS 的「显示简介 → 评注」读取的是 Spotlight/Finder 注释
    （``kMDItemFinderComment``，存于扩展属性），与 MP4 容器内部的 comment
    标签是两套独立数据。这里把内部标签里的来源信息同步一份到 Finder 评注，
    方便在访达里直接看到视频出处。

    仅 macOS 生效；其他平台直接跳过。任何失败都视为 best-effort，不影响下载。
    """
    if sys.platform != "darwin":
        return False
    comment = _read_embedded_comment(mp4_path)
    if not comment:
        return False
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                "on run argv",
                "-e",
                'tell application "Finder" to set comment of '
                "(POSIX file (item 1 of argv) as alias) to (item 2 of argv)",
                "-e",
                "end run",
                mp4_path,
                comment,
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def download_video(url: str, output_dir: str, cookies: str | None = None) -> str:
    """下载单个抖音视频并返回最终 MP4 的绝对路径。"""
    _ensure_ytdlp()

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output_template = str(destination / "%(title)s.%(ext)s")

    command = [
        "yt-dlp",
        "--no-playlist",
        # 优先选择原生 MP4 + M4A，其他可用组合则交由 ffmpeg 封装为 MP4。
        "-f",
        "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--remux-video",
        "mp4",
        # 把原链接 / 作者 / 发布信息写入 MP4 元数据（comment / artist / date）。
        *_metadata_arguments(),
        "--print",
        "after_move:filepath",
        "-o",
        output_template,
    ]
    if cookies:
        command.extend(["--cookies", cookies])
    command.append(url)

    print(f"下载抖音视频: {url}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise DouyinDownloadError(f"yt-dlp 下载失败: {detail or '未知错误'}")

    downloaded = _find_downloaded_mp4(result.stdout, destination)
    if downloaded is None:
        raise DouyinDownloadError(
            f"下载完成但未在 {destination} 找到 MP4 文件，请检查 yt-dlp 输出。"
        )
    if _write_finder_comment(str(downloaded)):
        print("已将来源信息写入 Finder 评注（显示简介 → 评注）。")
    return str(downloaded)

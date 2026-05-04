"""Bilibili 音乐下载：下载视频音频并转为 MP3"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _check_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def download_audio(url, output_dir, cookies=None):
    """下载 Bilibili 视频最佳音频轨道，返回 (audio_path, video_info_dict)"""
    if not _check_ytdlp():
        print("正在安装 yt-dlp...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)

    print(f"获取视频信息: {url}")
    info_cmd = ["yt-dlp", "--dump-json", "--no-playlist"]
    if cookies:
        info_cmd += ["--cookies", cookies]
    info_cmd.append(url)

    result = subprocess.run(info_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"获取视频信息失败: {result.stderr}")

    info = json.loads(result.stdout)
    title = info.get("title", "unknown")
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    print(f"视频标题: {title}")
    print(f"UP主: {info.get('uploader', 'unknown')}")
    print(f"时长: {info.get('duration_string', 'unknown')}")

    if not _check_ffmpeg():
        raise RuntimeError("需要 ffmpeg 才能下载并转换音频，请安装 ffmpeg")

    output_template = os.path.join(output_dir, f"{safe_title}.%(ext)s")
    dl_cmd = [
        "yt-dlp", "-f", "bestaudio/best", "-x",
        "--audio-format", "m4a", "--audio-quality", "0",
        "-o", output_template, "--no-playlist",
    ]
    if cookies:
        dl_cmd += ["--cookies", cookies]
    dl_cmd.append(url)

    print("下载音频...")
    result = subprocess.run(dl_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"下载音频失败: {result.stderr}")

    audio_path = None
    for ext in ["m4a", "mp3", "webm", "opus", "wav", "ogg", "mp4"]:
        candidate = os.path.join(output_dir, f"{safe_title}.{ext}")
        if os.path.exists(candidate):
            audio_path = candidate
            break

    if not audio_path:
        audio_exts = {".m4a", ".mp3", ".webm", ".opus", ".wav", ".ogg", ".mp4"}
        candidates = [str(f) for f in Path(output_dir).iterdir() if f.suffix.lower() in audio_exts]
        if candidates:
            audio_path = max(candidates, key=os.path.getmtime)

    if not audio_path:
        raise FileNotFoundError(f"找不到下载的音频文件，请检查 {output_dir} 目录")

    print(f"音频已下载: {audio_path}")
    return audio_path, info


def convert_to_mp3(input_path, output_path, bitrate=192):
    """使用 ffmpeg 将音频转为 MP3"""
    print(f"转换为 MP3 ({bitrate}kbps)...")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vn", "-b:a", f"{bitrate}k", output_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MP3 转换失败: {result.stderr}")
    print(f"MP3 已保存: {output_path}")
    return output_path


def _download_cover(thumbnail_url, output_dir):
    """下载封面图片，返回本地路径"""
    import requests
    try:
        resp = requests.get(thumbnail_url, timeout=30)
        resp.raise_for_status()
        cover_path = os.path.join(output_dir, "_cover_temp.jpg")
        with open(cover_path, "wb") as f:
            f.write(resp.content)
        return cover_path
    except Exception as e:
        print(f"封面下载失败: {e}")
        return None


def embed_metadata(mp3_path, info, cover_path=None):
    """使用 mutagen 写入 ID3 标签（标题、UP主、封面）"""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TPE1, APIC
    except ImportError:
        print("警告: mutagen 未安装，跳过元数据写入（pip install mutagen）")
        return

    audio = MP3(mp3_path, ID3=ID3)

    if audio.tags is None:
        audio.add_tags()

    title = info.get("title", "")
    if title:
        audio.tags.add(TIT2(encoding=3, text=title))

    uploader = info.get("uploader", "")
    if uploader:
        audio.tags.add(TPE1(encoding=3, text=uploader))

    if cover_path and os.path.exists(cover_path):
        try:
            with open(cover_path, "rb") as f:
                cover_data = f.read()
            mime = "image/png" if cover_path.endswith(".png") else "image/jpeg"
            audio.tags.add(
                APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_data)
            )
        except Exception as e:
            print(f"封面嵌入失败: {e}")

    audio.save()
    print("ID3 元数据已写入")


def run_bilimusic(url, output_dir="./output", bitrate=192, no_metadata=False, cookies=None):
    """bilimusic 主流程：下载 B 站视频音频 → 转为 MP3 → 嵌入元数据"""
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 下载音频
    audio_path, info = download_audio(url, output_dir, cookies=cookies)

    # Step 2: 转为 MP3
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', info.get("title", "unknown"))
    mp3_path = os.path.join(output_dir, f"{safe_title}.mp3")
    convert_to_mp3(audio_path, mp3_path, bitrate=bitrate)

    # 删除原始音频文件（非 MP3）
    if audio_path != mp3_path and os.path.exists(audio_path):
        os.remove(audio_path)
        print(f"已清理原始文件: {os.path.basename(audio_path)}")

    # Step 3: 嵌入元数据
    if not no_metadata:
        thumbnail = info.get("thumbnail", "")
        cover_path = None
        if thumbnail:
            cover_path = _download_cover(thumbnail, output_dir)
        embed_metadata(mp3_path, info, cover_path=cover_path)
        if cover_path and os.path.exists(cover_path):
            os.remove(cover_path)

    file_size = os.path.getsize(mp3_path) / 1024 / 1024
    print(f"\n===== 完成 =====")
    print(f"  MP3 文件: {mp3_path}")
    print(f"  文件大小: {file_size:.1f} MB")
    return mp3_path

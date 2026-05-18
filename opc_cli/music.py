"""网易云音乐下载：从网易云链接下载音乐文件"""

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


def _normalize_url(url):
    """处理网易云 URL，去除 #/ 等 hash 路由片段"""
    # https://music.163.com/#/song?id=xxx → https://music.163.com/song?id=xxx
    # https://music.163.com/#/playlist?id=xxx → https://music.163.com/playlist?id=xxx
    url = re.sub(r'/#/', '/', url)
    # 处理 #/song?id=xxx → song?id=xxx（无前导 / 的情况）
    url = re.sub(r'#/', '', url)
    return url


def _get_type_from_url(url):
    """从 URL 推断下载类型: single / album / playlist / artist"""
    if re.search(r'/album\b', url):
        return "album"
    if re.search(r'/playlist\b', url):
        return "playlist"
    if re.search(r'/artist\b', url):
        return "artist"
    return "single"


def download_music(url, output_dir, cookies=None, playlist=False):
    """下载网易云音乐，返回 (audio_path, info_dict)

    支持 song / album / playlist / artist 四种 URL 类型。
    playlist=True 时 album/playlist/artist 链接会下载全部曲目。
    """
    if not _check_ytdlp():
        print("正在安装 yt-dlp...")
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)

    url = _normalize_url(url)
    url_type = _get_type_from_url(url)

    # 是否下载全部曲目
    is_playlist = playlist or url_type in ("album", "playlist", "artist")

    print(f"获取音乐信息: {url}")
    info_cmd = ["yt-dlp", "--dump-json"]
    if not is_playlist:
        info_cmd.append("--no-playlist")
    if cookies:
        info_cmd += ["--cookies", cookies]
    info_cmd.append(url)

    result = subprocess.run(info_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"获取音乐信息失败: {result.stderr}")

    # 如果是列表（playlist/album），取第一首的信息打印
    if is_playlist:
        entries = []
        total = 0
        for line in result.stdout.strip().split("\n"):
            if line:
                entries.append(json.loads(line))
                total += 1
        if not entries:
            raise RuntimeError("未获取到任何曲目信息")
        info = entries[0]  # 第一首用于打印摘要
        print(f"共 {total} 首曲目")
    else:
        info = json.loads(result.stdout)
        total = 1

    title = info.get("title", "unknown")
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    artist = info.get("artist", info.get("uploader", "unknown"))
    album = info.get("album", "")
    duration = info.get("duration_string", "")

    print(f"歌曲: {title}")
    print(f"歌手: {artist}")
    if album:
        print(f"专辑: {album}")
    if duration:
        print(f"时长: {duration}")

    if not _check_ffmpeg():
        raise RuntimeError("需要 ffmpeg 才能下载并转换音频，请安装 ffmpeg")

    output_template = os.path.join(output_dir, f"%(title)s.%(ext)s")
    dl_cmd = [
        "yt-dlp", "-f", "bestaudio/best", "-x",
        "--audio-format", "m4a", "--audio-quality", "0",
        "-o", output_template,
    ]
    if not is_playlist:
        dl_cmd.append("--no-playlist")
    if cookies:
        dl_cmd += ["--cookies", cookies]
    dl_cmd.append(url)

    # 摘要信息
    type_label = {"single": "单曲", "album": "专辑", "playlist": "歌单", "artist": "歌手"}
    print(f"下载{type_label.get(url_type, '音乐')}...")
    result = subprocess.run(dl_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"下载失败: {result.stderr}")

    # 同目录可能有多个文件（playlist 下很多首），取最新的一个或当前 title 匹配的
    audio_path = None
    for ext in ["m4a", "mp3", "webm", "opus", "wav", "ogg", "mp4"]:
        candidate = os.path.join(output_dir, f"{safe_title}.{ext}")
        if os.path.exists(candidate):
            audio_path = candidate
            break

    if not audio_path:
        audio_exts = {".m4a", ".mp3", ".webm", ".opus", ".wav", ".ogg", ".mp4"}
        # 如果是 playlist，不尝试匹配单个文件
        if is_playlist:
            print(f"下载完成，共 {total} 首，文件在 {output_dir}/")
            return None, info
        candidates = [str(f) for f in Path(output_dir).iterdir() if f.suffix.lower() in audio_exts]
        if candidates:
            audio_path = max(candidates, key=os.path.getmtime)

    if not audio_path and not is_playlist:
        raise FileNotFoundError(f"找不到下载的音频文件，请检查 {output_dir} 目录")

    if audio_path:
        print(f"音乐已下载: {audio_path}")
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
    """使用 mutagen 写入 ID3 标签（标题、歌手、专辑、封面）"""
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
    except ImportError:
        print("警告: mutagen 未安装，跳过元数据写入（pip install mutagen）")
        return

    audio = MP3(mp3_path, ID3=ID3)

    if audio.tags is None:
        audio.add_tags()

    title = info.get("title", "")
    if title:
        audio.tags.add(TIT2(encoding=3, text=title))

    artist = info.get("artist", info.get("uploader", ""))
    if artist:
        audio.tags.add(TPE1(encoding=3, text=artist))

    album = info.get("album", "")
    if album:
        audio.tags.add(TALB(encoding=3, text=album))

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
    print("ID3 元数据已写入（标题 + 歌手 + 专辑 + 封面）")


def run_music(url, output_dir="./output", bitrate=192, no_metadata=False, cookies=None, playlist=False):
    """music 主流程：下载网易云音乐 → 转为 MP3 → 嵌入元数据"""
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 下载音频
    audio_path, info = download_music(url, output_dir, cookies=cookies, playlist=playlist)

    # 如果是 playlist/album/artist，批量下载后直接返回
    if audio_path is None:
        print(f"\n===== 完成 =====")
        print(f"  输出目录: {output_dir}/")
        return

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

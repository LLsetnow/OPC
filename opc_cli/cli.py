"""OPC CLI 入口：B站视频转写 + 音乐理解 + 语音合成 + 图片理解 + 文生图"""

import os
import sys
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# Windows 终端编码修复
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

from .config import get_api_config, load_env, get_image_config, get_llm_config, get_gpt_image_config, get_gpt_img_proxy, get_comfyui_config, get_bili_folder, get_douyin_folder, get_x_folder, get_news_folder, get_music_folder, _is_wsl
from .bili import run_bili, asr_transcribe, generate_srt, resegment_asr
from .audio import (
    AudioUnderstandingError,
    analyze_audio,
    detect_beats,
    filter_beat_events,
    format_librosa_analysis,
)
from .douyin import DouyinDownloadError, download_video as download_douyin_video
from .x import XDownloadError, download_video as download_x_video
from .music import run_music
from .tts import text_to_speech, clone_voice, list_voices as _tts_list_voices
from .local_tts import (
    load_model as _local_load_model,
    generate_custom_voice as _local_custom_voice,
    generate_voice_design as _local_voice_design,
    generate_voice_clone as _local_voice_clone,
    list_speakers as _local_list_speakers,
    SUPPORTED_LANGUAGES as _LOCAL_LANGUAGES,
)
from .tts_server import (
    start_server as _start_tts_server,
    stop_server as _stop_tts_server,
    get_server_url as _get_tts_server_url,
    get_ws_url as _get_tts_ws_url,
    call_server_generate as _call_server_generate,
    call_server_load as _call_server_load,
    call_server_unload as _call_server_unload,
    _is_server_running as _is_tts_server_running,
    _read_pid_info as _read_tts_pid_info,
    DEFAULT_PORT as _TTS_DEFAULT_PORT,
)
from .vision import understand_image
from .ai_daily import run_ai_daily
from .check_api import get_command_availability, run_check_api
from .comfyui import start_comfyui, stop_comfyui, check_comfyui, is_comfyui_running, submit_workflow
from .aigate import (
    AigateError,
    control_instance as _aigate_control_instance,
    create_instance as _aigate_create_instance,
    discover_running_comfyui as _aigate_discover_running_comfyui,
    instance_summary as _aigate_instance_summary,
    list_instances as _aigate_list_instances,
    list_community_images as _aigate_list_community_images,
    list_personal_images as _aigate_list_personal_images,
    list_skus as _aigate_list_skus,
    list_workflow_files as _aigate_list_workflow_files,
    start_comfyui as _aigate_start_comfyui,
    submit_workflow as _aigate_submit_workflow,
    wait_for_comfyui as _aigate_wait_for_comfyui,
)
from .text2img import generate_image, download_image, enhance_prompt
from .gpt_image import (
    submit_and_wait as _gpt_submit_and_wait,
    enhance_prompt as _gpt_enhance_prompt,
    download_image as _gpt_download_image,
    load_image_as_base64 as _gpt_load_base64,
    _build_proxies as _gpt_build_proxies,
    SUPPORTED_SIZES as _GPT_SIZES,
)

app = typer.Typer(
    name="opc",
    help="OPC 工具集：B站视频转写 + 音乐理解 + 音乐下载 + 语音合成 + 图片理解 + 文生图/图像编辑 + ComfyUI + 云扉 AIGate",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

# ── bili 子命令 ────────────────────────────────────────────────────

@app.command()
def bili(
    url: str = typer.Argument("", help="Bilibili 视频链接（--skip-download 时可省略）"),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="输出目录（默认从 .env BILI_FOLDER 读取，或 ./output）"),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="yt-dlp cookies 文件路径"),
    audio_only: bool = typer.Option(False, "--audio-only", help="下载音频并转为 MP3，不进行 ASR"),
    bitrate: int = typer.Option(192, "--bitrate", help="MP3 比特率 (kbps，仅 --audio-only 生效)"),
    no_metadata: bool = typer.Option(False, "--no-metadata", help="跳过 MP3 的 ID3 元数据写入（仅 --audio-only 生效）"),
    skip_download: bool = typer.Option(False, "--skip-download", help="跳过下载，使用已有音频文件"),
    audio_file: Optional[str] = typer.Option(None, "--audio-file", help="指定已有音频文件路径"),
    skip_asr: bool = typer.Option(False, "--skip-asr", help="跳过 ASR，使用已有字幕文件生成总结"),
    asr_file: Optional[str] = typer.Option(None, "--asr-file", help="指定已有 ASR JSON 或 SRT 文件路径"),
    llm_fix: bool = typer.Option(False, "--llm-fix", help="使用 LLM 修复 ASR 断词和标点错误"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """B站视频下载 + ASR 转写 + 内容总结

    自动检测：视频目录下已有字幕文件则跳过ASR。
    """
    load_env(env_file)

    if output_dir is None:
        output_dir = get_bili_folder() or "./output"

    if not url and not skip_download:
        console.print("[red]错误: 请提供 Bilibili 视频链接，或使用 --skip-download 跳过下载[/red]")
        raise typer.Exit(1)

    run_bili(
        url=url,
        output_dir=output_dir,
        cookies=cookies,
        audio_only=audio_only,
        skip_download=skip_download,
        audio_file=audio_file,
        skip_asr=skip_asr,
        asr_file=asr_file,
        llm_fix=llm_fix,
        bitrate=bitrate,
        no_metadata=no_metadata,
    )


# ── douyin 子命令 ────────────────────────────────────────────────

@app.command()
def douyin(
    url: str = typer.Argument(..., help="抖音视频链接"),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="输出目录（默认从 .env DOUYIN_FOLDER 读取，或 ./output）"),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="yt-dlp cookies 文件路径"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """下载单个抖音视频为 MP4。"""
    load_env(env_file)
    output_dir = output_dir or get_douyin_folder() or "./output"
    cookies = cookies or os.environ.get("YT_DLP_COOKIES")

    try:
        output_path = download_douyin_video(url, output_dir, cookies)
    except DouyinDownloadError as error:
        console.print(f"[red]错误: {error}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]完成![/green] 已保存 MP4: {output_path}")


# ── x 子命令 ─────────────────────────────────────────────────────

@app.command("x")
def x(
    url: str = typer.Argument(..., help="X (Twitter) 视频/帖子链接"),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="输出目录（默认从 .env X_FOLDER 读取，或 ./output）"),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="yt-dlp cookies 文件路径（X 视频通常需要登录 cookies）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """下载单个 X (Twitter) 视频为 MP4。

    X 大量视频对未登录用户不可见。若报 "No video could be found"，
    请用 --cookies 传入从浏览器导出的 cookies.txt（或设置环境变量 YT_DLP_COOKIES）。

    示例:

        opc x "https://x.com/i/status/2038177089082261736"

        opc x "URL" --cookies ~/cookies.txt -o ~/Downloads
    """
    load_env(env_file)
    output_dir = output_dir or get_x_folder() or "./output"
    cookies = cookies or os.environ.get("YT_DLP_COOKIES")

    try:
        output_path = download_x_video(url, output_dir, cookies)
    except XDownloadError as error:
        console.print(f"[red]错误: {error}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]完成![/green] 已保存 MP4: {output_path}")


# ── music 子命令 ───────────────────────────────────────────────

@app.command("music")
def music_cmd(
    url: str = typer.Argument(..., help="网易云音乐链接（单曲/专辑/歌单/歌手）"),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="输出目录（默认从 .env MUSIC_FOLDER 读取，或 ./output）"),
    bitrate: int = typer.Option(192, "--bitrate", help="MP3 比特率 (kbps)"),
    no_metadata: bool = typer.Option(False, "--no-metadata", help="跳过 ID3 元数据写入"),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="yt-dlp cookies 文件路径"),
    playlist: bool = typer.Option(False, "--playlist", help="下载全部曲目（专辑/歌单/歌手链接默认已启用）"),
):
    """网易云音乐下载 → 转为 MP3（带 ID3 元数据）

    下载网易云音乐音频，转为 MP3 格式，自动写入标题、歌手、专辑、封面等 ID3 标签。

    支持链接类型：

        opc music "https://music.163.com/song?id=xxx"       # 单曲
        opc music "https://music.163.com/album?id=xxx"      # 专辑
        opc music "https://music.163.com/playlist?id=xxx"   # 歌单
        opc music "https://music.163.com/artist?id=xxx"     # 歌手

    示例:

        opc music "https://music.163.com/song?id=2143914149"

        opc music "URL" -o ./music --bitrate 320

        opc music "URL" --no-metadata
    """
    load_env()

    if output_dir is None:
        output_dir = get_music_folder() or "./output"

    run_music(
        url=url,
        output_dir=output_dir,
        bitrate=bitrate,
        no_metadata=no_metadata,
        cookies=cookies,
        playlist=playlist,
    )


# ── asr 子命令 ────────────────────────────────────────────────────

@app.command()
def asr(
    audio: str = typer.Argument(..., help="输入音频文件路径（.wav/.mp3/.m4a 等）"),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="输出目录（默认与输入文件同目录）"),
    no_resegment: bool = typer.Option(False, "--no-resegment", help="禁用自动重断句（保留 ASR 原始切分）"),
    llm_fix: bool = typer.Option(False, "--llm-fix", help="使用 LLM 修复 ASR 断词和标点错误"),
    trim: Optional[int] = typer.Option(None, "-t", "--trim", help="只识别音频的前 N 秒（方便测试）"),
):
    """语音识别（ASR）：将音频文件转写为 SRT 和 JSON 字幕文件

    使用阿里云 DashScope fun-asr-realtime 模型，支持精确时间戳。

    示例:

        opc asr audio.wav

        opc asr recording.mp3 -o ./output
    """
    load_env()

    audio_path = Path(audio)
    if not audio_path.exists():
        console.print(f"[red]错误: 文件不存在: {audio}[/red]")
        raise typer.Exit(1)

    if audio_path.suffix.lower() not in (".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".opus", ".mov", ".mkv"):
        console.print(f"[red]错误: 不支持的音频格式: {audio_path.suffix}（支持 .wav/.mp3/.m4a/.webm/.ogg/.opus）[/red]")
        raise typer.Exit(1)

    # 输出目录：默认与输入文件同目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = audio_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_base = audio_path.stem
    srt_path = out_dir / f"{audio_base}.srt"
    json_path = out_dir / f"{audio_base}.asr.json"

    console.print(f"[bold]=== ASR 语音识别 ===[/bold]")
    console.print(f"输入: {audio_path}")
    console.print(f"输出: {out_dir}")

    # ASR 转写（asr_transcribe 内部会自动转换格式）
    asr_result = asr_transcribe(str(audio_path), trim_seconds=trim)

    # 保存原始 ASR 结果（JSON），不经过重断句处理
    with open(str(json_path), "w", encoding="utf-8") as f:
        import json
        json.dump(asr_result, f, ensure_ascii=False, indent=2)
    console.print(f"ASR JSON 已保存（原始结果）: {json_path}")

    # 自动重断句：按自然语句重新切分
    if not no_resegment:
        console.print("[dim]  自动重断句（按逗号逐句切分）...[/dim]")
        asr_result = resegment_asr(asr_result, llm_fix=llm_fix)

    # 生成 SRT
    generate_srt(asr_result, str(srt_path))

    console.print(f"\n[green]完成![/green]")
    console.print(f"  SRT:  {srt_path}")
    console.print(f"  JSON: {json_path}")


# ── audio 命令组 ──────────────────────────────────────────────────

def _save_audio_result(result: str, output: Optional[str]) -> None:
    """输出音乐分析结果，可选保存到文本文件。"""
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result + "\n", encoding="utf-8")
        console.print(f"结果已保存: {output_path}")
    console.print("\n" + result)


@app.command("audio")
def audio_cmd(
    audio: str = typer.Argument(..., help="输入音频路径，或使用 librosa 模式"),
    audio_file: Optional[str] = typer.Argument(None, help="librosa 模式下的输入音频文件路径"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="将分析结果保存到文本文件"),
    model: str = typer.Option("", "--model", help="音乐理解模型（默认读取 .env AUDIO_MODEL，默认为 qwen3-omni-30b-a3b-captioner）"),
    beat_strength_threshold: float = typer.Option(0.2, "--beat-strength-threshold", "--beat-threshold", help="librosa 模式保留的相对强度阈值（0~1，默认 0.2）"),
    beat_min_interval: float = typer.Option(1.0, "--beat-min-interval", help="librosa 模式的时间窗口（秒，默认每秒最多 1 个）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help="自定义 .env 文件路径"),
):
    """音乐理解，或使用 `opc audio librosa <音频>` 检测鼓点。"""
    load_env(env_file)

    if audio == "librosa":
        if not audio_file:
            console.print("[red]错误: librosa 模式需要提供音频文件路径[/red]")
            raise typer.Exit(1)
        return _run_librosa_audio(
            audio_file,
            output=output,
            beat_strength_threshold=beat_strength_threshold,
            beat_min_interval=beat_min_interval,
        )

    if audio_file:
        console.print("[red]错误: 只有 `opc audio librosa <音频>` 支持两个位置参数[/red]")
        raise typer.Exit(1)

    audio_path = Path(audio)
    console.print("[bold]=== 音乐理解 ===[/bold]")
    console.print(f"输入: {audio_path}")

    try:
        result = analyze_audio(str(audio_path), model=model)
        _save_audio_result(result, output)
    except (AudioUnderstandingError, OSError) as error:
        console.print(f"[red]错误: {error}[/red]")
        raise typer.Exit(1)


def _run_librosa_audio(
    audio: str,
    output: Optional[str],
    beat_strength_threshold: float,
    beat_min_interval: float,
):
    """运行 librosa 鼓点检测并输出筛选结果。"""
    audio_path = Path(audio)
    console.print("[bold]=== Librosa 鼓点检测 ===[/bold]")
    console.print(f"输入: {audio_path}")

    try:
        beat_analysis = detect_beats(str(audio_path))
        beat_analysis["filtered"] = filter_beat_events(
            beat_analysis,
            strength_threshold=beat_strength_threshold,
            min_interval=beat_min_interval,
        )
        result = format_librosa_analysis(beat_analysis)
        _save_audio_result(result, output)
    except (AudioUnderstandingError, OSError) as error:
        console.print(f"[red]错误: {error}[/red]")
        raise typer.Exit(1)


# ── tts 子命令 ────────────────────────────────────────────────────

@app.command()
def tts(
    text: str = typer.Argument("", help="要转换为语音的文本（--list-voices 时可省略）"),
    output: str = typer.Option("output.wav", "-o", "--output", help="输出音频文件路径"),
    voice: str = typer.Option("tongtong", "--voice", help="音色名称或克隆音色 ID"),
    speed: float = typer.Option(1.0, "--speed", help="语速 [0.5, 2]"),
    volume: float = typer.Option(1.0, "--volume", help="音量 (0, 10]"),
    format: str = typer.Option("wav", "--format", help="音频格式: wav/pcm"),
    watermark: bool = typer.Option(False, "--watermark", help="添加 AI 生成水印"),
    clone: bool = typer.Option(False, "--clone", help="启用音色克隆模式"),
    ref_audio: Optional[str] = typer.Option(None, "--ref-audio", help="克隆参考音频文件路径"),
    ref_text: Optional[str] = typer.Option(None, "--ref-text", help="参考音频对应的文本内容"),
    voice_name: Optional[str] = typer.Option(None, "--voice-name", help="克隆音色名称"),
    list_voices: bool = typer.Option(False, "--list-voices", help="列出系统音色"),
    list_cloned: bool = typer.Option(False, "--list-cloned", help="列出已克隆的音色"),
    engine: str = typer.Option("qwen-tts", "--engine", help="TTS 引擎: glm-tts (智谱) / qwen-tts (阿里云 CosyVoice)"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """文字转语音（默认 CosyVoice v3-flash + 龙呼呼音色）

    支持阿里云 CosyVoice 和智谱 GLM-TTS 双引擎。默认使用 CosyVoice v3-flash 模型，
    音色为龙呼呼（天真烂漫女童）。可通过 --engine glm-tts 切换回智谱引擎。

    使用 --list-voices 查看系统音色，--list-cloned 查看克隆音色。
    """
    load_env(env_file)
    # Qwen TTS 直接使用 ALIYUN_API_KEY；智谱凭证只在 GLM-TTS、音色列表
    # 或音色克隆等智谱功能需要时读取。
    api_key = base_url = ""
    if engine == "glm-tts" or list_voices or list_cloned or clone:
        api_key, base_url = get_api_config()

    # 列出音色
    if list_voices or list_cloned:
        voice_type = "PRIVATE" if list_cloned else None
        voice_list = _tts_list_voices(api_key, base_url, voice_type=voice_type)

        if list_cloned:
            if not voice_list:
                console.print("暂无克隆音色")
                return
            console.print("\n[bold]已克隆音色:[/bold]")
            for v in voice_list:
                console.print(f"  {v.get('voice', ''):<40} {v.get('voice_name', ''):<20} {v.get('create_time', ''):<20}")
        else:
            console.print("\n[bold]系统音色:[/bold]")
            for v in voice_list:
                if v.get("voice_type") == "OFFICIAL":
                    console.print(f"  {v.get('voice', ''):<20} {v.get('voice_name', ''):<15} {v.get('voice_type', '')}")
        return

    if not text:
        console.print("[red]错误: 请提供要转换的文本，或使用 --list-voices / --list-cloned 查看音色[/red]")
        raise typer.Exit(1)

    selected_voice = voice
    # qwen-tts 引擎默认音色
    if engine == "qwen-tts" and voice == "tongtong":
        selected_voice = "longhuhu_v3"

    if clone:
        if not ref_audio:
            console.print("[red]错误: 克隆模式需要指定 --ref-audio 参考音频文件[/red]")
            raise typer.Exit(1)

        if not Path(ref_audio).exists():
            console.print(f"[red]错误: 参考音频文件不存在: {ref_audio}[/red]")
            raise typer.Exit(1)

        ext = Path(ref_audio).suffix.lower()
        if ext not in (".mp3", ".wav"):
            console.print(f"[red]错误: 参考音频格式不支持: {ext}，仅支持 mp3 和 wav[/red]")
            raise typer.Exit(1)

        file_size = Path(ref_audio).stat().st_size
        if file_size > 10 * 1024 * 1024:
            console.print(f"[red]错误: 参考音频文件过大: {file_size / 1024 / 1024:.1f}MB，最大 10MB[/red]")
            raise typer.Exit(1)

        console.print(f"[bold]=== 音色克隆模式 ===[/bold]")
        console.print(f"参考音频: {ref_audio} ({file_size / 1024:.1f} KB)")
        if ref_text:
            console.print(f"参考文本: {ref_text}")

        clone_result = clone_voice(
            api_key, base_url,
            ref_audio_path=ref_audio,
            voice_name=voice_name,
            ref_text=ref_text or "",
            sample_text=text,
        )
        selected_voice = clone_result.get("voice", "")
        if not selected_voice:
            console.print("[red]错误: 克隆失败，未获取到音色 ID[/red]")
            raise typer.Exit(1)
        console.print(f"使用克隆音色: {selected_voice}")

    text_to_speech(
        api_key, base_url,
        text=text,
        voice=selected_voice,
        output_path=output,
        speed=speed,
        volume=volume,
        response_format=format,
        watermark=watermark,
        engine=engine,
    )


# ── 音频播放 ──────────────────────────────────────────────────────

def _play_audio(filepath: str):
    """播放 WAV 文件。优先 sounddevice，否则用系统/Windows 播放器。"""

    def _try_windows_player(path: str) -> bool:
        """WSL 环境下用 Windows 播放器打开文件。"""
        import subprocess
        try:
            if path.startswith("/mnt/"):
                win_path = subprocess.check_output(
                    ["wslpath", "-w", path], text=True
                ).strip()
            else:
                win_path = path
            subprocess.Popen(["cmd.exe", "/c", "start", "", win_path])
            console.print(f"[cyan]已用 Windows 播放器打开[/cyan]")
            return True
        except Exception:
            return False

    def _is_wsl() -> bool:
        """检测是否运行在 WSL 中。"""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False

    # 1. 优先 sounddevice（需要 PortAudio + 音频设备）
    try:
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(filepath, dtype='float32')
        console.print(f"[cyan]播放中...[/cyan] ({len(data)/sr:.1f}s)")
        sd.play(data, samplerate=sr, blocking=True)
        console.print("[dim]播放结束[/dim]")
        return
    except (ImportError, OSError) as e:
        if "PortAudio" in str(e):
            console.print("[dim]PortAudio 未安装，跳过 sounddevice[/dim]")

    # 2. WSL 环境 → 直接走 Windows 播放器
    if _is_wsl():
        if _try_windows_player(filepath):
            return
        console.print(f"[yellow]无法调用 Windows 播放器[/yellow]")

    # 3. 非 WSL 的 Linux / macOS
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["afplay", filepath])
        else:
            subprocess.Popen(["aplay", filepath])
        console.print(f"[cyan]已用系统播放器打开[/cyan]")
    except FileNotFoundError:
        console.print(f"[yellow]无可用的播放器，请手动播放:[/yellow] {filepath}")


# ── WebSocket 流式 TTS 客户端 ─────────────────────────────────────

def _stream_generate(ws_url: str, params: dict, output_path: str, play: bool = False):
    """通过 WebSocket 流式生成 TTS 音频，边生成边写入文件，可选实时播放。"""
    import asyncio
    import numpy as np
    import soundfile as sf

    # 实时播放用的 sounddevice（按需导入）
    sd = None
    if play:
        try:
            import sounddevice as _sd
            sd = _sd
        except ImportError:
            console.print("[yellow]sounddevice 未安装，无法实时播放（pip install sounddevice）[/yellow]")
            console.print("[yellow]仅保存到文件[/yellow]")

    async def _run():
        import websockets

        url = f"{ws_url}/ws/generate"
        all_pcm = []
        sample_rate = None
        chunk_count = 0

        async with websockets.connect(url) as ws:
            await ws.send(json.dumps(params))

            while True:
                try:
                    message = await ws.recv()
                except websockets.exceptions.ConnectionClosed:
                    break

                if isinstance(message, bytes):
                    # PCM 音频数据
                    pcm = np.frombuffer(message, dtype=np.float32)
                    all_pcm.append(pcm)
                    chunk_count += 1
                    console.print(f"  [dim]收到音频块 #{chunk_count} ({len(pcm)} 采样点)[/dim]")

                    # 实时播放该块
                    if sd and sample_rate:
                        sd.play(pcm, samplerate=sample_rate, blocking=False)
                        sd.wait()  # 等播放完再接收下一块（避免重叠）
                else:
                    # JSON 控制消息
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "stream_info":
                        sample_rate = data.get("sample_rate", 24000)
                        console.print(f"  [dim]采样率: {sample_rate}Hz[/dim]")

                    elif msg_type == "chunk_start":
                        idx = data.get("index", 0)
                        chunk_text = data.get("text", "")
                        console.print(f"  [cyan]生成块 #{idx}: {chunk_text[:30]}...[/cyan]")

                    elif msg_type == "chunk_end":
                        idx = data.get("index", 0)
                        dur = data.get("duration", 0)
                        gt = data.get("gen_time", 0)
                        console.print(f"  [green]块 #{idx} 完成[/green] "
                                      f"(音频: {dur:.1f}s, 生成: {gt:.1f}s)")

                    elif msg_type == "stream_end":
                        total_dur = data.get("total_duration", 0)
                        total_gen = data.get("total_gen_time", 0)
                        rtf = data.get("rtf", 0)
                        console.print(
                            f"[green]流式生成完成![/green] "
                            f"共 {data.get('total_chunks', 0)} 块, "
                            f"音频: {total_dur:.1f}s, 生成: {total_gen:.1f}s, RTF: {rtf:.2f}"
                        )
                        break

                    elif msg_type == "error":
                        console.print(f"[red]服务端错误: {data.get('error', '')}[/red]")
                        break

        # 合并所有 PCM 数据并写入 WAV
        if all_pcm and sample_rate:
            audio = np.concatenate(all_pcm)
            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            sf.write(output_path, audio, sample_rate)
            console.print(f"[green]已保存: {output_path}[/green] "
                          f"({len(audio)/sample_rate:.1f}s, {os.path.getsize(output_path)/1024:.1f}KB)")
        else:
            console.print("[yellow]未收到音频数据[/yellow]")

    asyncio.run(_run())


# ── local-tts 子命令 ─────────────────────────────────────────────

@app.command("local-tts")
def local_tts(
    text: str = typer.Argument("", help="要转换为语音的文本，或 .txt/.md 文件路径"),
    output: str = typer.Option("output.wav", "-o", "--output", help="输出文件路径"),
    mode: str = typer.Option("custom", "-m", "--mode", help="模型变体: custom=预设音色, design=设计音色, base=语音克隆"),
    speaker: str = typer.Option("Vivian", "-s", "--speaker", help="预设音色名称（custom 模式）"),
    language: str = typer.Option("Chinese", "-l", "--language", help=f"语言: {'/'.join(_LOCAL_LANGUAGES)}"),
    instruct: str = typer.Option("", "--instruct", help="自然语言指令（custom 控制语气 / design 描述音色）"),
    ref_audio: Optional[str] = typer.Option(None, "--ref-audio", help="参考音频路径（base 模式）"),
    ref_text: Optional[str] = typer.Option(None, "--ref-text", help="参考音频对应文本（base 模式必填）"),
    device: str = typer.Option("cuda:0", "--device", help="设备（默认: cuda:0）"),
    attn: str = typer.Option("sdpa", "--attn", help="注意力实现: sdpa/flash_attention_2/eager"),
    list_speakers_flag: bool = typer.Option(False, "--list-speakers", help="列出预设音色"),
    no_server: bool = typer.Option(False, "--no-server", help="不使用常驻服务，直接加载模型"),
    stream: bool = typer.Option(False, "--stream", help="使用 WebSocket 流式生成"),
    play: bool = typer.Option(False, "--play", help="流式生成时实时播放音频（需 sounddevice）"),
    # 服务管理选项
    serve: bool = typer.Option(False, "--serve", help="启动 TTS 常驻服务"),
    no_load: bool = typer.Option(False, "--no-load", help="启动服务时不加载本地模型（仅云引擎可用）"),
    stop: bool = typer.Option(False, "--stop", help="停止 TTS 常驻服务"),
    status: bool = typer.Option(False, "--status", help="查看 TTS 服务状态"),
    unload: bool = typer.Option(False, "--unload", help="释放常驻服务中的模型缓存（服务保持运行）"),
    port: int = typer.Option(_TTS_DEFAULT_PORT, "-p", "--port", help="服务端口（--serve 时使用）"),
):
    """本地语音合成 + 服务管理（Qwen3-TTS）

    语音合成: opc local-tts "你好" （默认使用常驻服务）

    服务管理: opc local-tts --serve / --stop / --status / --unload

    ⚠️  必须在 WSL zsh + qwen3-tts-venv 环境下运行：
        source ~/qwen3-tts-venv/bin/activate
    """
    # ── 服务管理操作 ──
    if status:
        if _is_tts_server_running():
            info = _read_tts_pid_info()
            console.print(f"[green]TTS 服务运行中[/green]")
            console.print(f"  PID: {info.get('pid')}")
            console.print(f"  端口: {info.get('port')}")
            console.print(f"  模式: {info.get('mode')}")
            console.print(f"  设备: {info.get('device')}")
            console.print(f"  启动时间: {info.get('started_at')}")
        else:
            console.print("[yellow]TTS 服务未运行[/yellow]")
        return

    if stop:
        _stop_tts_server()
        return

    if serve:
        _start_tts_server(mode=mode, device=device, attn=attn, port=port, no_load=no_load)
        return

    if unload:
        server_url = _get_tts_server_url()
        if not server_url:
            console.print("[yellow]TTS 服务未运行，无需释放[/yellow]")
            raise typer.Exit(0)
        try:
            result = _call_server_unload(server_url, mode=mode)
            if "error" in result:
                console.print(f"[red]错误: {result['error']}[/red]")
            else:
                unloaded = result.get("modes", []) or [result.get("mode", "")]
                console.print(f"[green]已释放模型缓存:[/green] {', '.join(unloaded)}")
        except Exception as e:
            console.print(f"[red]释放失败: {e}[/red]")
            raise typer.Exit(1)
        return

    # ── 语音合成 ──
    # 列出音色
    if list_speakers_flag:
        console.print("\n[bold]预设音色 (custom 模式):[/bold]")
        console.print("-" * 50)
        for name, desc in _local_list_speakers().items():
            console.print(f"  {name:<12} {desc}")
        console.print(f"\n支持语言: {', '.join(_LOCAL_LANGUAGES)}")
        return

    if not text:
        console.print("[red]错误: 语音合成需要提供文本参数，或使用 --serve/--stop/--status/--unload[/red]")
        raise typer.Exit(1)

    # 文本输入：支持直接文本或读取 .txt/.md 文件
    from pathlib import Path as _Path
    _text_path = _Path(text)
    _is_file_input = False
    if _text_path.exists() and _text_path.suffix.lower() in (".txt", ".md"):
        _is_file_input = True
        text = _text_path.read_text(encoding="utf-8").strip()
        console.print(f"[dim]  已读取文件: {_text_path.name} ({len(text)} 字)[/dim]")
        if not text:
            console.print(f"[red]错误: 文件内容为空: {_text_path}[/red]")
            raise typer.Exit(1)
        # 未指定 -o 时，在源文件同目录生成同名 .wav
        if output == "output.wav":
            output = str(_text_path.with_suffix(".wav"))
            console.print(f"[dim]  输出路径: {output}[/dim]")

    # 参数校验
    if mode not in ("custom", "design", "base"):
        console.print(f"[red]错误: 不支持的模式 '{mode}'，可选: custom, design, base[/red]")
        raise typer.Exit(1)

    if language not in _LOCAL_LANGUAGES:
        console.print(f"[red]错误: 不支持的语言 '{language}'[/red]")
        console.print(f"可选: {', '.join(_LOCAL_LANGUAGES)}")
        raise typer.Exit(1)

    if mode == "base" and not ref_audio:
        console.print("[red]错误: base 模式需要 --ref-audio 参数[/red]")
        raise typer.Exit(1)

    if mode == "base" and not ref_text:
        console.print("[red]错误: base 模式需要 --ref-text 参数（参考音频的文字内容）[/red]")
        raise typer.Exit(1)

    if mode == "design" and not instruct:
        console.print("[red]错误: design 模式需要 --instruct 参数描述音色[/red]")
        raise typer.Exit(1)

    if mode == "custom" and speaker not in _local_list_speakers():
        console.print(f"[yellow]警告: 音色 '{speaker}' 不在预设列表中，可能无法正常工作[/yellow]")

    # 检测是否使用常驻服务
    import time
    total_t0 = time.time()

    server_url = _get_tts_server_url()
    use_server = server_url and not no_server

    console.print(f"[bold]=== Qwen3-TTS 本地语音合成 ===[/bold]")
    console.print(f"模式: {mode} | 音色: {speaker} | 语言: {language}")

    # ── 流式生成模式 ──
    if stream:
        ws_url = _get_tts_ws_url()
        if not ws_url:
            console.print("[red]流式模式需要常驻服务支持，请先启动: opc local-tts --serve[/red]")
            raise typer.Exit(1)

        # --play 时打开浏览器播放器
        if play:
            from urllib.parse import urlencode
            server_url = _get_tts_server_url()
            player_url = server_url + "/player?" + urlencode({
                "text": text,
                "mode": mode,
                "speaker": speaker,
                "language": language,
                "instruct": instruct,
                "auto": "1",
            })
            console.print(f"[cyan]→ 打开流式播放器: {player_url}[/cyan]")
            import subprocess
            try:
                # WSL 中用 Windows 浏览器打开
                with open("/proc/version", "r") as _f:
                    _is_wsl = "microsoft" in _f.read().lower()
                if _is_wsl:
                    subprocess.Popen(["cmd.exe", "/c", "start", "", player_url])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", player_url])
                else:
                    subprocess.Popen(["xdg-open", player_url])
                console.print("[green]浏览器已打开，音频将通过浏览器播放（支持蓝牙耳机）[/green]")
            except Exception as e:
                console.print(f"[yellow]无法自动打开浏览器: {e}[/yellow]")
                console.print(f"[yellow]请手动访问: {player_url}[/yellow]")
            return

        # 非播放模式：接收 PCM 并保存到文件
        console.print(f"[cyan]→ WebSocket 流式模式 {ws_url}[/cyan]")
        try:
            _stream_generate(ws_url, {
                "type": "generate",
                "text": text,
                "mode": mode,
                "speaker": speaker,
                "language": language,
                "instruct": instruct,
                "ref_audio": ref_audio or "",
                "ref_text": ref_text or "",
                "attn": attn,
            }, output, play=False)
        except Exception as e:
            console.print(f"[red]流式生成失败: {e}[/red]")
            raise typer.Exit(1)
        return

    if use_server:
        # 通过常驻服务生成（模型已加载，秒出结果）
        console.print(f"[cyan]→ 使用常驻服务 {server_url}[/cyan]")
        params = {
            "mode": mode,
            "text": text,
            "speaker": speaker,
            "language": language,
            "device": device,
            "attn": attn,
        }
        if instruct:
            params["instruct"] = instruct
        if ref_audio:
            params["ref_audio"] = ref_audio
        if ref_text:
            params["ref_text"] = ref_text

        try:
            result = _call_server_generate(server_url, params, output)
            if "error" in result:
                console.print(f"[red]服务端错误: {result['error']}[/red]")
                raise typer.Exit(1)

            total_elapsed = time.time() - total_t0
            console.print(
                f"[green]完成![/green] 输出: {output} "
                f"(音频: {result.get('duration', '?')}s, "
                f"生成: {result.get('gen_time', '?')}s, "
                f"RTF: {result.get('rtf', '?')}, "
                f"总耗时: {total_elapsed:.1f}s)"
            )
        except Exception as e:
            if "Connection" in str(e) or "refused" in str(e).lower():
                console.print("[yellow]服务连接失败，回退到直接加载模式[/yellow]")
                use_server = False
            else:
                raise

    if not use_server:
        # 直接加载模型（慢，约1分钟）
        console.print("[dim]  直接加载模式（提示：使用 opc local-tts --serve 启动常驻服务可跳过模型加载）[/dim]")
        try:
            model = _local_load_model(mode, device=device, attn=attn)
        except FileNotFoundError as e:
            console.print(f"[red]错误: {e}[/red]")
            raise typer.Exit(1)

        # 生成
        if mode == "custom":
            _local_custom_voice(
                model, text,
                speaker=speaker,
                language=language,
                instruct=instruct,
                output_path=output,
            )
        elif mode == "design":
            _local_voice_design(
                model, text,
                instruct=instruct,
                language=language,
                output_path=output,
            )
        elif mode == "base":
            _local_voice_clone(
                model, text,
                ref_audio=ref_audio,
                ref_text=ref_text or "",
                language=language,
                output_path=output,
            )

        total_elapsed = time.time() - total_t0
        console.print(f"[green]完成![/green] 输出: {output} (总耗时: {total_elapsed:.1f}s)")

    # 生成后播放
    if play and os.path.exists(output):
        _play_audio(output)


# ── img 子命令 ────────────────────────────────────────────────────

@app.command("read-img")
def img(
    image: str = typer.Argument(help="图片路径或 URL"),
    prompt: str = typer.Option("请详细描述这张图片的内容", "-p", "--prompt", help="提问内容"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出到文件（默认打印到终端）"),
    model: str = typer.Option("", "--model", help="视觉模型名称（默认从 .env 读取 VISION_MODEL）"),
    max_tokens: int = typer.Option(4096, "--max-tokens", help="最大输出 token 数"),
    temperature: float = typer.Option(0.7, "--temperature", help="生成温度 0-1"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """图片理解：使用视觉模型分析图片内容"""
    load_env(env_file)

    result = understand_image(
        image=image,
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    if output:
        output_dir = str(Path(output).parent)
        if output_dir:
            import os
            os.makedirs(output_dir, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)
        console.print(f"\n结果已保存: {output}")
    else:
        console.print("\n" + "=" * 50)
        console.print(result)
        console.print("=" * 50)


# ── gpt-img 子命令 ──────────────────────────────────────────────

@app.command("gpt-img")
def gpt_img(
    prompt: str = typer.Argument(help="提示词（中英文，描述期望生成的图像）"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出图片路径（默认: output/gpt_img_<时间戳>.png）"),
    size: str = typer.Option("2:3", "-s", "--size", help=f"宽高比: {', '.join(_GPT_SIZES)}，或像素如 1024*1536"),
    resolution: str = typer.Option("1k", "-r", "--resolution", help="分辨率档位: 1k / 2k / 4k（全比例均支持 4K）"),
    quality: str = typer.Option("auto", "--quality", help="图片质量: auto / low / medium / high"),
    enhance: bool = typer.Option(True, "--enhance/--no-enhance", help="使用 LLM 丰富提示词（默认开启）"),
    ref: Optional[list[str]] = typer.Option(None, "--ref", help="参考图路径或 URL（可多次指定，最多16张）"),
    n: int = typer.Option(1, "--n", help="生成张数 1 ~ 4"),
    output_format: str = typer.Option("png", "--output-format", help="输出格式: png / jpeg / webp"),
    output_compression: Optional[int] = typer.Option(None, "--output-compression", help="压缩强度 0-100（仅 jpeg/webp）"),
    moderation: str = typer.Option("auto", "--moderation", help="审核强度: auto / low"),
    no_download: bool = typer.Option(False, "--no-download", help="仅返回图片 URL，不下载到本地"),
    use_proxy: bool = typer.Option(False, "--proxy/--no-proxy", help="强制使用/禁用代理（WSL 下默认自动启用，无需此参数）"),
    timeout: int = typer.Option(600, "--timeout", help="最大等待时间（秒）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """GPT-Image-2-Official 文生图：OpenAI 官方模型（异步，自动轮询等待结果）

    默认使用 LLM (LLM_MODEL) 丰富提示词，可用 --no-enhance 关闭。
    WSL 下代理默认自动启用（无需 --proxy），Windows 下需手动 --proxy。

    宽高比: 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 2:1, 1:2, 3:1, 1:3, 21:9, 9:21, auto

    分辨率: 1k(默认) / 2k / 4k（全比例均支持 4K，不再有限制）

    图生图: 使用 --ref 指定参考图（本地路径或 URL）

    批量生成: --n 4 一次生成 4 张
    """
    load_env(env_file)
    api_key, base_url, cfg_model = get_gpt_image_config()

    # 构建 gpt-img 专用代理（WSL 下自动启用，直连不通）
    proxies = None
    if use_proxy or _is_wsl():
        proxy_url = get_gpt_img_proxy()
        proxies = _gpt_build_proxies(proxy_url)
        if proxies:
            console.print(f"[dim]代理: {proxy_url}[/dim]")

    console.print(f"[bold]=== GPT-Image-2-Official 文生图 ===[/bold]")
    console.print(f"原始提示词: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    console.print(f"宽高比: {size} | 分辨率: {resolution} | 质量: {quality} | 张数: {n} | 模型: {cfg_model}")

    # 使用 LLM 丰富提示词
    use_prompt = prompt
    use_prompt_json = None
    if enhance:
        console.print("\n[cyan]🧠 使用 LLM 丰富提示词...[/cyan]")
        try:
            llm_key, llm_url, llm_model = get_llm_config()
            enhanced = _gpt_enhance_prompt(
                prompt=prompt,
                llm_api_key=llm_key,
                llm_base_url=llm_url,
                llm_model=llm_model,
                aspect_ratio=size,
            )
            use_prompt = enhanced["flat"]
            use_prompt_json = enhanced["json_str"]
            console.print(f"[dim]  原始: {prompt[:80]}[/dim]")
            if use_prompt_json:
                console.print(f"[cyan]  丰富(JSON): {use_prompt_json[:300]}{'...' if len(use_prompt_json) > 300 else ''}[/cyan]")
            else:
                console.print(f"[cyan]  丰富: {use_prompt[:150]}{'...' if len(use_prompt) > 150 else ''}[/cyan]")
        except Exception as e:
            console.print(f"[yellow]⚠ LLM 丰富失败，使用原始提示词: {e}[/yellow]")

    # 处理参考图
    image_urls = None
    if ref:
        image_urls = []
        for r in ref:
            if r.startswith("http://") or r.startswith("https://"):
                image_urls.append(r)
            elif r.startswith("data:"):
                image_urls.append(r)
            else:
                try:
                    data_uri = _gpt_load_base64(r)
                    image_urls.append(data_uri)
                    console.print(f"[dim]  参考图: {r} → base64[/dim]")
                except Exception as e:
                    console.print(f"[yellow]⚠ 参考图加载失败 {r}: {e}[/yellow]")
        console.print(f"参考图: {len(image_urls)} 张")

    # 提交任务 + 轮询
    import time as _time
    t0 = _time.time()

    def on_status(status, task_id):
        console.print(f"[dim]  任务 {task_id} → {status}[/dim]")

    try:
        result = _gpt_submit_and_wait(
            prompt=use_prompt,
            api_key=api_key,
            base_url=base_url,
            model=cfg_model,
            size=size,
            resolution=resolution,
            quality=quality,
            image_urls=image_urls,
            n=n,
            output_format=output_format,
            output_compression=output_compression,
            moderation=moderation,
            timeout=timeout,
            on_status=on_status,
            proxies=proxies,
            prompt_json=use_prompt_json,
        )
    except ValueError as e:
        console.print(f"[red]参数错误: {e}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]生成失败: {e}[/red]")
        raise typer.Exit(1)

    elapsed = _time.time() - t0
    image_url = result.get("image_url")

    if not image_url:
        console.print("[red]未获取到图片 URL[/red]")
        raise typer.Exit(1)

    cost = result.get("cost", 0)
    actual_time = result.get("actual_time", "?")
    console.print(f"[green]生成成功![/green] ({elapsed:.1f}s, 实际生成: {actual_time}s, 费用: ${cost:.5f})")

    # 输出
    if no_download:
        console.print(f"\n图片 URL: {image_url}")
        console.print("[yellow]注意: URL 有效期 24 小时，请及时保存[/yellow]")
    else:
        if not output:
            ts = _time.strftime("%Y%m%d_%H%M%S")
            output = f"output/gpt_img_{ts}.{output_format}"

        try:
            saved = _gpt_download_image(image_url, output, proxies=proxies)
            file_size = Path(saved).stat().st_size
            console.print(f"[green]已保存:[/green] {saved} ({file_size / 1024:.0f} KB)")
        except Exception as e:
            console.print(f"[red]下载失败: {e}[/red]")
            console.print(f"图片 URL（有效期 24 小时）: {image_url}")
            raise typer.Exit(1)

    console.print(f"[dim]URL: {image_url}[/dim]")


# ── image 子命令 ─────────────────────────────────────────────────

@app.command("image")
def image_cmd(
    prompt: str = typer.Argument(help="提示词或图像编辑指令"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出图片路径（默认: output/image_<时间戳>.png）"),
    size: str = typer.Option("2:3", "-s", "--size", help="输出分辨率：宽*高（如 1024*1536）或宽高比（如 2:3, 16:9）"),
    model: str = typer.Option("", "--model", help="模型名称（默认读取 .env IMAGE_MODEL，默认为 qwen-image-3.0）"),
    image: Optional[list[str]] = typer.Option(None, "-i", "--image", help="编辑输入图片路径、URL 或 data URI，可重复指定，最多 3 张"),
    negative_prompt: Optional[str] = typer.Option(None, "--negative-prompt", help="负向提示词"),
    n: int = typer.Option(1, "--n", help="生成张数（1~6）"),
    enhance: bool = typer.Option(True, "--enhance/--no-enhance", help="使用 DeepSeek 丰富提示词（默认开启）"),
    prompt_extend: bool = typer.Option(True, "--prompt-extend/--no-prompt-extend", help="启用 Qwen Image 智能提示词改写（默认开启）"),
    seed: Optional[int] = typer.Option(None, "--seed", help="随机种子（0~2147483647）"),
    watermark: bool = typer.Option(False, "--watermark/--no-watermark", help="是否添加水印"),
    no_download: bool = typer.Option(False, "--no-download", help="仅返回图片 URL，不下载到本地"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """使用阿里云 Qwen Image 3.0 进行文生图或图像编辑。

    不提供 --image 时执行文生图；提供 1~3 张 --image 时执行图像编辑。
    默认使用 DeepSeek 丰富提示词，可通过 --no-enhance 关闭。
    """
    load_env(env_file)
    api_key, cfg_model = get_image_config()
    use_model = model or cfg_model
    editing = bool(image)

    console.print(f"[bold]=== {'图像编辑' if editing else '文生图'} (Qwen Image 3.0) ===[/bold]")
    console.print(f"原始提示词: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    console.print(f"分辨率: {size} | 模型: {use_model}")
    if image:
        console.print(f"参考图: {len(image)} 张")

    use_prompt = prompt
    if enhance:
        console.print("\n[cyan]🧠 使用 DeepSeek 丰富提示词...[/cyan]")
        try:
            llm_key, llm_url, llm_model = get_llm_config()
            enhanced = enhance_prompt(
                prompt=prompt,
                llm_api_key=llm_key,
                llm_base_url=llm_url,
                llm_model=llm_model,
                aspect_ratio=size,
            )
            use_prompt = enhanced["flat"]
            console.print(f"[dim]  原始: {prompt[:80]}[/dim]")
            console.print(f"[cyan]  丰富: {use_prompt[:150]}{'...' if len(use_prompt) > 150 else ''}[/cyan]")
        except Exception as e:
            console.print(f"[yellow]⚠ DeepSeek 丰富失败，使用原始提示词: {e}[/yellow]")

    import time
    t0 = time.time()
    try:
        result = generate_image(
            prompt=use_prompt,
            api_key=api_key,
            size=size,
            model=use_model,
            prompt_extend=prompt_extend,
            seed=seed,
            images=image,
            negative_prompt=negative_prompt,
            n=n,
            watermark=watermark,
        )
    except ValueError as e:
        console.print(f"[red]参数错误: {e}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]生成失败: {e}[/red]")
        raise typer.Exit(1)

    elapsed = time.time() - t0
    image_urls = result.get("image_urls") or []
    if not image_urls and result.get("image_url"):
        image_urls = [result["image_url"]]
    if not image_urls:
        console.print("[red]未获取到图片 URL[/red]")
        raise typer.Exit(1)

    console.print(f"[green]生成成功![/green] ({elapsed:.1f}s) {result.get('width')}*{result.get('height')}，共 {len(image_urls)} 张")
    if result.get("text") and prompt_extend:
        console.print(f"[dim]改写后提示词: {result['text'][:200]}[/dim]")

    if no_download:
        for index, image_url in enumerate(image_urls, 1):
            console.print(f"\n图片 URL {index}: {image_url}")
        console.print("[yellow]注意: URL 有效期 24 小时，请及时保存[/yellow]")
        return

    if not output:
        ts = time.strftime("%Y%m%d_%H%M%S")
        output = f"output/image_{ts}.png"

    try:
        for index, image_url in enumerate(image_urls, 1):
            save_path = output
            if len(image_urls) > 1:
                output_path = Path(output)
                save_path = str(output_path.with_name(f"{output_path.stem}_{index}{output_path.suffix or '.png'}"))
            saved = download_image(image_url, save_path)
            file_size = Path(saved).stat().st_size
            console.print(f"[green]已保存:[/green] {saved} ({file_size / 1024:.0f} KB)")
            console.print(f"[dim]URL {index}: {image_url}[/dim]")
    except Exception as e:
        console.print(f"[red]下载失败: {e}[/red]")
        raise typer.Exit(1)


# ── check-api 子命令 ──────────────────────────────────────────────

@app.command("check-api")
def check_api(
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
    only: Optional[list[str]] = typer.Option(None, "--only", help="只检查指定 API，可多次使用。如 --only deepseek --only vision"),
):
    """检查 API 连通性，并显示当前可用的 opc 命令。

    可用 API 名称: deepseek (或 llm), zhipu, asr, audio, qwen-tts, vision, image, gpt-image, proxy, cookies

    示例:
      opc check-api                # 检查全部
      opc check-api --only deepseek     # 只检查 DeepSeek
      opc check-api --only deepseek --only vision  # 检查 DeepSeek 和 Vision
    """
    # 可用性表也依赖 .env，必须在读取环境变量前加载配置。
    load_env(env_file)
    console.print("[bold]=== OPC 命令可用性 ===[/bold]\n")

    availability = get_command_availability()
    availability_table = Table(show_header=True, header_style="bold")
    availability_table.add_column("命令", style="cyan", width=14)
    availability_table.add_column("状态", width=10)
    availability_table.add_column("配置依据", width=42)
    availability_table.add_column("说明")

    status_styles = {
        "可用": "[green]可用[/green]",
        "部分可用": "[yellow]部分可用[/yellow]",
        "不可用": "[red]不可用[/red]",
    }
    available_count = 0
    for item in availability:
        availability_table.add_row(
            f"opc {item.command}",
            status_styles.get(item.status, item.status),
            item.required,
            item.detail,
        )
        if item.available:
            available_count += 1

    console.print(availability_table)
    console.print(f"可用命令: [green]{available_count}[/green]/{len(availability)}\n")
    console.print("[bold]=== API 连通性检查 ===[/bold]\n")

    try:
        results = run_check_api(env_file=env_file, only=only)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    table = Table(show_header=True, header_style="bold")
    table.add_column("API", style="cyan", width=20)
    table.add_column("状态", width=6)
    table.add_column("耗时", width=8)
    table.add_column("详情")

    ok_count = 0
    for r in results:
        status = "[green]OK[/green]" if r.ok else "[red]FAIL[/red]"
        latency = f"{r.latency_ms}ms" if r.latency_ms else "-"
        table.add_row(r.name, status, latency, r.detail)
        if r.ok:
            ok_count += 1

    console.print(table)
    console.print(f"\n结果: [green]{ok_count}[/green]/{len(results)} 通过")

    if ok_count < len(results):
        raise typer.Exit(1)


# ── comfyui 子命令 ──────────────────────────────────────────────

@app.command("comfyui")
def comfyui_cmd(
    start: bool = typer.Option(False, "--start", help="启动 ComfyUI"),
    stop: bool = typer.Option(False, "--stop", help="关闭 ComfyUI"),
    status: bool = typer.Option(False, "--status", help="检查 ComfyUI 运行状态"),
    listen: str = typer.Option("0.0.0.0", "--listen", help="监听地址（默认 0.0.0.0）"),
    port: int = typer.Option(8188, "--port", help="监听端口（默认 8188）"),
    # 工作流提交参数
    run: bool = typer.Option(False, "--run", help="提交工作流到 ComfyUI 执行"),
    workflow: str = typer.Option("confyui/Qwen_remove.json", "-w", "--workflow", help="工作流 JSON 文件路径"),
    image: Optional[str] = typer.Option(None, "-i", "--image", help="输入图片路径"),
    prompt: Optional[str] = typer.Option(None, "-p", "--prompt", help="提示词（用于支持 prompt 的工作流）"),
    seed: Optional[int] = typer.Option(None, "-s", "--seed", help="随机种子（不指定则自动生成）"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出目录（默认打印输出路径）"),
    server: str = typer.Option("http://127.0.0.1:8188", "--server", help="ComfyUI 服务地址"),
    timeout: int = typer.Option(300, "-t", "--timeout", help="最大等待时间（秒）"),
    steps: Optional[int] = typer.Option(None, "--steps", help="采样步数"),
    cfg: Optional[float] = typer.Option(None, "--cfg", help="CFG scale"),
    denoise: Optional[float] = typer.Option(None, "--denoise", help="去噪强度"),
    output_prefix: Optional[str] = typer.Option(None, "--output-prefix", help="输出文件名前缀"),
    # 节点ID覆盖（高级用法）
    load_image_node: Optional[str] = typer.Option(None, "--load-image-node", help="LoadImage 节点 ID（覆盖自动检测）"),
    ksampler_node: Optional[str] = typer.Option(None, "--ksampler-node", help="KSampler 节点 ID（覆盖自动检测）"),
    save_image_node: Optional[str] = typer.Option(None, "--save-image-node", help="SaveImage 节点 ID（覆盖自动检测）"),
    prompt_node: Optional[str] = typer.Option(None, "--prompt-node", help="提示词节点 ID（覆盖自动检测）"),
    seed_node: Optional[str] = typer.Option(None, "--seed-node", help="种子节点 ID（覆盖自动检测）"),
):
    """ComfyUI 进程管理 + 工作流提交

    进程管理:

        opc comfyui --start           # 启动 ComfyUI
        opc comfyui --start --port 8189
        opc comfyui --stop            # 关闭 ComfyUI
        opc comfyui --status          # 查看运行状态

    工作流提交:

        opc comfyui --run -i photo.jpg                    # 使用默认工作流处理图片
        opc comfyui --run -w my_workflow.json -i img.png  # 指定工作流文件
        opc comfyui --run -i img.png -p "去掉背景"         # 带提示词
        opc comfyui --run -i img.png --steps 8 --cfg 2.0  # 自定义采样参数
        opc comfyui --run -i img.png -o ./results         # 输出到指定目录
    """
    load_env()

    # ── 工作流提交 ──
    if run:
        try:
            result_paths = submit_workflow(
                workflow_path=workflow,
                server_url=server.rstrip("/"),
                image=image,
                prompt=prompt,
                seed=seed,
                output_dir=output or ".",
                timeout=timeout,
                load_image_node=load_image_node,
                ksampler_node=ksampler_node,
                save_image_node=save_image_node,
                prompt_node=prompt_node,
                seed_node=seed_node,
                steps=steps,
                cfg=cfg,
                denoise=denoise,
                output_prefix=output_prefix,
            )
            if result_paths:
                console.print(f"\n[green]完成![/green] 共 {len(result_paths)} 个输出文件:")
                for p in result_paths:
                    console.print(f"  {p}")
        except (FileNotFoundError, RuntimeError) as e:
            console.print(f"[red]错误: {e}[/red]")
            raise typer.Exit(1)
        return

    # ── 进程管理 ──
    if start:
        comfyui_root = get_comfyui_config()
        try:
            start_comfyui(comfyui_root, listen=listen, port=port)
        except FileNotFoundError as e:
            console.print(f"[red]错误: {e}[/red]")
            raise typer.Exit(1)
    elif stop:
        stop_comfyui()
    else:
        # 默认显示状态
        info = check_comfyui()
        if info["running"]:
            console.print("[green]ComfyUI 运行中[/green]")
            console.print(f"  PID: {info['pid']}")
            console.print(f"  地址: http://{info['listen']}:{info['port']}")
            console.print(f"  路径: {info['comfyui_root']}")
            console.print(f"  启动时间: {info['started_at']}")
        else:
            console.print("[yellow]ComfyUI 未运行[/yellow]")


# ── aigate 子命令 ───────────────────────────────────────────────

@app.command("aigate")
def aigate_cmd(
    start: bool = typer.Option(False, "--start", help="启动已有的云扉 ComfyUI 实例并等待服务就绪"),
    create: bool = typer.Option(False, "--create", help="创建一台新实例（仅可与 --start 一起使用，可能产生云资源费用）"),
    stop: bool = typer.Option(False, "--stop", help="关闭指定的云扉实例"),
    release: bool = typer.Option(False, "--release", help="释放指定的云扉实例（会删除实例资源）"),
    status: bool = typer.Option(False, "--status", help="查看云扉实例状态"),
    gpus: bool = typer.Option(False, "--gpus", "--list-gpus", help="查询当前可创建实例的 GPU SKU（可用 --area 筛选）"),
    images: bool = typer.Option(False, "--images", "--list-images", help="查询当前账户的个人镜像"),
    community_images: bool = typer.Option(False, "--community-images", help="查询指定区域和 GPU SKU 下的社区镜像"),
    workflows: bool = typer.Option(False, "--workflows", "--list-workflows", help="列出仓库中可提交的本地工作流（无需云扉 Token）"),
    workflow_dir: Optional[str] = typer.Option(None, "--workflow-dir", help="要列出的本地工作流目录（默认仓库的 workflows/）"),
    run: bool = typer.Option(False, "--run", help="向运行中的云扉 ComfyUI 提交工作流"),
    token: Optional[str] = typer.Option(None, "--token", help="云扉 Bearer Token（默认读取 AIGATE_TOKEN）"),
    instance: Optional[str] = typer.Option(None, "--instance", help="云扉实例 ID；省略时自动选择第一个可用 ComfyUI 实例"),
    sku: Optional[str] = typer.Option(None, "--sku", help="创建实例使用的 GPU SKU（默认读取 AIGATE_SKU_NAME）"),
    area: Optional[str] = typer.Option(None, "--area", help="创建实例所在区域（默认读取 AIGATE_AREA_NAME）"),
    image_id: Optional[str] = typer.Option(None, "--image-id", help="创建实例使用的云扉镜像 ID（默认读取 AIGATE_IMAGE_ID）"),
    image_type: Optional[str] = typer.Option(None, "--image-type", help="云扉镜像类型：2=社区，3=个人（默认读取 AIGATE_IMAGE_TYPE）"),
    workflow: Optional[str] = typer.Option(None, "-w", "--workflow", help="ComfyUI API 格式工作流 JSON（--run 时必填）"),
    image: Optional[str] = typer.Option(None, "-i", "--image", help="上传到云端 ComfyUI 的输入图片"),
    video: Optional[str] = typer.Option(None, "--video", help="上传到云端 ComfyUI 的输入视频（自动写入 VHS_LoadVideo / LoadVideo 节点）"),
    audio: Optional[str] = typer.Option(None, "--audio", help="上传到云端 ComfyUI 的输入音频（自动写入 LoadAudio 节点）"),
    reference_image: Optional[str] = typer.Option(None, "--reference-image", help="参考角色图片（自动写入 LoadImage 节点）"),
    video_node: Optional[str] = typer.Option(None, "--video-node", help="视频加载节点 ID（VHS_LoadVideo / LoadVideo，覆盖自动检测）"),
    audio_node: Optional[str] = typer.Option(None, "--audio-node", help="音频加载节点 ID（LoadAudio，覆盖自动检测）"),
    reference_image_node: Optional[str] = typer.Option(None, "--reference-image-node", help="参考图片 LoadImage 节点 ID（覆盖自动检测）"),
    video_output_node: Optional[str] = typer.Option(None, "--video-output-node", help="临时替换为 VHS_VideoCombine 的视频输出节点 ID"),
    prompt: Optional[str] = typer.Option(None, "-p", "--prompt", help="提示词（自动识别 prompt/text 节点）"),
    seed: Optional[int] = typer.Option(None, "-s", "--seed", help="随机种子（默认自动生成）"),
    output: str = typer.Option(".", "-o", "--output", help="云端输出下载目录"),
    timeout: int = typer.Option(300, "-t", "--timeout", help="工作流最大等待时间（秒）"),
    ready_timeout: int = typer.Option(300, "--ready-timeout", help="启动实例后等待 ComfyUI 就绪的最长时间（秒）"),
    steps: Optional[int] = typer.Option(None, "--steps", help="采样步数"),
    cfg: Optional[float] = typer.Option(None, "--cfg", help="CFG scale"),
    denoise: Optional[float] = typer.Option(None, "--denoise", help="去噪强度"),
    output_prefix: Optional[str] = typer.Option(None, "--output-prefix", help="输出文件名前缀"),
    load_image_node: Optional[str] = typer.Option(None, "--load-image-node", help="LoadImage 节点 ID（覆盖自动检测）"),
    ksampler_node: Optional[str] = typer.Option(None, "--ksampler-node", help="KSampler 节点 ID（覆盖自动检测）"),
    save_image_node: Optional[str] = typer.Option(None, "--save-image-node", help="SaveImage 节点 ID（覆盖自动检测）"),
    prompt_node: Optional[str] = typer.Option(None, "--prompt-node", help="提示词节点 ID（覆盖自动检测）"),
    seed_node: Optional[str] = typer.Option(None, "--seed-node", help="种子节点 ID（覆盖自动检测）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help="自定义 .env 文件路径"),
):
    """云扉（AIGate）ComfyUI：启动实例、提交工作流并下载结果

    常用示例：

        opc aigate --status
        opc aigate --gpus --area 华东一区
        opc aigate --images
        opc aigate --workflows
        opc aigate --start --instance INSTANCE_ID
        opc aigate --start --run -w workflow_api.json -i photo.png -o ./results
        opc aigate --start --create --sku SKU --area AREA --image-id ID --image-type 2

    ``--start`` 只会启动已有实例。新建实例必须额外明确传入 ``--create``，
    并配置 SKU、区域和镜像；这样不会因为一次工作流提交意外创建计费资源。
    """
    load_env(env_file)
    aigate_token = token or os.environ.get("AIGATE_TOKEN", "")

    if create and not start:
        console.print("[red]错误: --create 必须与 --start 一起使用[/red]")
        raise typer.Exit(1)
    if (gpus or images or community_images or workflows) and (start or create or stop or release or status or run):
        console.print("[red]错误: 资源或工作流查询不能与实例操作同时使用[/red]")
        raise typer.Exit(1)
    if workflows and (gpus or images or community_images):
        console.print("[red]错误: --workflows 不能与资源查询同时使用[/red]")
        raise typer.Exit(1)
    if workflow_dir and not workflows:
        console.print("[red]错误: --workflow-dir 必须与 --workflows 一起使用[/red]")
        raise typer.Exit(1)
    if stop and release:
        console.print("[red]错误: --stop 与 --release 不能同时使用[/red]")
        raise typer.Exit(1)
    if (stop or release) and (start or create or run):
        console.print("[red]错误: --stop / --release 不能与 --start、--create 或 --run 同时使用[/red]")
        raise typer.Exit(1)
    if run and not workflow:
        console.print("[red]错误: --run 时必须通过 -w/--workflow 指定工作流 JSON[/red]")
        raise typer.Exit(1)
    if (video or audio or reference_image or video_node or audio_node or reference_image_node or video_output_node) and not run:
        console.print("[red]错误: 视频、音频与参考图片参数只能与 --run 一起使用[/red]")
        raise typer.Exit(1)
    if (stop or release) and not instance:
        console.print("[red]错误: 为避免操作错误实例，--stop / --release 时必须提供 --instance INSTANCE_ID[/red]")
        raise typer.Exit(1)

    if workflows:
        try:
            workflow_paths = _aigate_list_workflow_files(workflow_dir)
        except AigateError as e:
            console.print(f"[red]错误: {e}[/red]")
            raise typer.Exit(1)
        if not workflow_paths:
            console.print("[yellow]工作流目录中没有 JSON 工作流[/yellow]")
            return
        table = Table(title="本地 ComfyUI 工作流")
        table.add_column("文件")
        table.add_column("完整路径")
        for workflow_path in workflow_paths:
            table.add_row(workflow_path.name, str(workflow_path))
        console.print(table)
        return

    if not aigate_token.strip():
        console.print("[red]错误: 未设置 AIGATE_TOKEN。请在 .env 中配置，或通过 --token 传入。[/red]")
        raise typer.Exit(1)

    try:
        if gpus:
            skus = _aigate_list_skus(aigate_token, area)
            if not skus:
                console.print("[yellow]未查询到可用 GPU SKU[/yellow]")
            else:
                table = Table(title="云扉可用 GPU SKU")
                table.add_column("区域")
                table.add_column("GPU SKU")
                table.add_column("价格")
                table.add_column("CPU")
                table.add_column("内存")
                table.add_column("最大 GPU 数")
                for sku_info in skus:
                    table.add_row(
                        str(sku_info.get("areaName") or "-"),
                        str(sku_info.get("skuName") or "-"),
                        str(sku_info.get("price") or "-"),
                        "{} 核 / {}".format(
                            str(sku_info.get("cpuCore") or "-"),
                            str(sku_info.get("cpuMf") or "-"),
                        ),
                        str(sku_info.get("memorySize") or "-"),
                        str(sku_info.get("maxGpuCount") or "-"),
                    )
                console.print(table)

        if images:
            personal_images = _aigate_list_personal_images(aigate_token)
            if not personal_images:
                console.print("[yellow]当前账户没有个人镜像[/yellow]")
            else:
                table = Table(title="云扉个人镜像")
                table.add_column("镜像 ID")
                table.add_column("名称")
                table.add_column("区域")
                table.add_column("状态")
                table.add_column("大小（字节）")
                table.add_column("版本")
                for image_info in personal_images:
                    table.add_row(
                        str(image_info.get("worksId") or "-"),
                        str(image_info.get("name") or "未命名镜像"),
                        str(image_info.get("areaName") or "-"),
                        {"1": "可用", "2": "保存中", "3": "保存失败"}.get(
                            str(image_info.get("status") or ""),
                            str(image_info.get("status") or "未知"),
                        ),
                        str(image_info.get("size") or "-"),
                        str(image_info.get("imageVersion") or "-"),
                    )
                console.print(table)

        if community_images:
            community = _aigate_list_community_images(
                aigate_token, area or "", sku or "", image_name=""
            )
            if not community:
                console.print("[yellow]未查询到社区镜像[/yellow]")
            else:
                table = Table(title="云扉社区镜像")
                table.add_column("镜像 ID")
                table.add_column("名称")
                table.add_column("区域")
                table.add_column("版本")
                for image_info in community:
                    table.add_row(
                        str(image_info.get("worksId") or "-"),
                        str(image_info.get("name") or "未命名镜像"),
                        str(image_info.get("areaName") or "-"),
                        str(image_info.get("imageVersion") or "-"),
                    )
                console.print(table)

        if gpus or images or community_images:
            return

        if stop:
            _aigate_control_instance(aigate_token, instance or "", "close")
            console.print(f"[green]已请求关闭云扉实例: {instance}[/green]")
            return

        if release:
            _aigate_control_instance(aigate_token, instance or "", "release")
            console.print(f"[green]已请求释放云扉实例: {instance}[/green]")
            return

        server_info = None
        if start:
            if create:
                created = _aigate_create_instance(
                    aigate_token,
                    sku or os.environ.get("AIGATE_SKU_NAME", ""),
                    area or os.environ.get("AIGATE_AREA_NAME", ""),
                    image_id or os.environ.get("AIGATE_IMAGE_ID", ""),
                    image_type or os.environ.get("AIGATE_IMAGE_TYPE", ""),
                )
                instance = str(created["instanceId"])
                console.print(f"[yellow]云扉实例已提交创建: {instance}[/yellow]")
                server_info = _aigate_wait_for_comfyui(
                    aigate_token,
                    instance,
                    timeout=ready_timeout,
                    on_wait=lambda message: console.print(f"[dim]{message}[/dim]"),
                )
            else:
                server_info = _aigate_start_comfyui(
                    aigate_token,
                    instance,
                    timeout=ready_timeout,
                    on_wait=lambda message: console.print(f"[dim]{message}[/dim]"),
                )
            console.print("[green]云扉 ComfyUI 已就绪[/green]")
            console.print(f"  实例: {server_info['instance_name']} ({server_info['instance_id']})")
            console.print(f"  地址: {server_info['base_url']}")

        if run:
            server_info = server_info or _aigate_discover_running_comfyui(
                aigate_token, instance
            )
            console.print(f"[dim]提交到云扉 ComfyUI: {server_info['base_url']}[/dim]")
            result_paths = _aigate_submit_workflow(
                workflow or "",
                server_info["base_url"],
                image=image,
                video=video,
                audio=audio,
                reference_image=reference_image,
                video_node=video_node,
                audio_node=audio_node,
                reference_image_node=reference_image_node,
                video_output_node=video_output_node,
                prompt=prompt,
                seed=seed,
                output_dir=output,
                timeout=timeout,
                load_image_node=load_image_node,
                ksampler_node=ksampler_node,
                save_image_node=save_image_node,
                prompt_node=prompt_node,
                seed_node=seed_node,
                steps=steps,
                cfg=cfg,
                denoise=denoise,
                output_prefix=output_prefix,
            )
            console.print(f"\n[green]完成![/green] 共 {len(result_paths)} 个输出文件:")
            for path in result_paths:
                console.print(f"  {path}")
            return

        if status or not start:
            instances = _aigate_list_instances(aigate_token)
            if not instances:
                console.print("[yellow]云扉控制台中没有实例[/yellow]")
                return
            table = Table(title="云扉实例")
            table.add_column("实例 ID")
            table.add_column("名称")
            table.add_column("状态")
            for record in instances:
                summary = _aigate_instance_summary(record)
                table.add_row(
                    summary["instance_id"],
                    summary["instance_name"],
                    summary["status"] or "未知",
                )
            console.print(table)
    except AigateError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# ── news 子命令 ──────────────────────────────────────────────

@app.command("news")
def ai_daily(
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出路径，支持文件路径或目录路径（目录时文件名默认 ai_daily_YYYY-MM-DD.md）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
    no_llm: bool = typer.Option(False, "--no-llm", help="不调用 LLM，仅输出原始素材"),
    save_raw: bool = typer.Option(False, "--save-raw", help="额外保存原始 JSON 数据"),
    json_mode: bool = typer.Option(False, "--json", help="以 JSON 格式输出到 stdout（跳过 markdown 文件写入）"),
):
    """AI 日报：自动收集当日 AI 技术/科研/项目新闻，LLM 整合输出专业简报

    信息来源：36氪、虎嗅、IT之家、InfoQ（RSS）、GitHub、Arxiv
    使用 DEEPSEEK_API_KEY / LLM_BASE_URL / LLM_MODEL 配置大模型

    --json 模式：LLM 直接输出结构化 JSON，无需 markdown 解析，适合 CI/CD 集成
    """
    if output is None and not json_mode:
        output = get_news_folder()
    run_ai_daily(output=output, env_file=env_file, no_llm=no_llm, save_raw=save_raw, json_mode=json_mode)



# ── 入口 ──────────────────────────────────────────────────────────

def main():
    from .logger import install_tee
    install_tee()
    app()


if __name__ == "__main__":
    main()

"""OPC CLI 入口：B站视频转写 + 语音合成"""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .config import get_api_config, load_env
from .bili import run_bili
from .tts import text_to_speech, clone_voice, list_voices as _tts_list_voices

app = typer.Typer(
    name="opc",
    help="OPC 工具集：B站视频转写 + 语音合成",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ── bili 子命令 ────────────────────────────────────────────────────

@app.command()
def bili(
    url: str = typer.Argument(help="Bilibili 视频链接"),
    output_dir: str = typer.Option("./output", "-o", "--output-dir", help="输出目录"),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="yt-dlp cookies 文件路径"),
    audio_only: bool = typer.Option(False, "--audio-only", help="仅下载音频，不进行 ASR"),
    skip_download: bool = typer.Option(False, "--skip-download", help="跳过下载，使用已有音频文件"),
    audio_file: Optional[str] = typer.Option(None, "--audio-file", help="指定已有音频文件路径"),
    skip_asr: bool = typer.Option(False, "--skip-asr", help="跳过 ASR，使用已有字幕文件生成总结"),
    asr_file: Optional[str] = typer.Option(None, "--asr-file", help="指定已有 ASR JSON 或 SRT 文件路径"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """B站视频下载 + ASR 转写 + 内容总结"""
    load_env(env_file)
    run_bili(
        url=url,
        output_dir=output_dir,
        cookies=cookies,
        audio_only=audio_only,
        skip_download=skip_download,
        audio_file=audio_file,
        skip_asr=skip_asr,
        asr_file=asr_file,
    )


# ── tts 子命令 ────────────────────────────────────────────────────

@app.command()
def tts(
    text: str = typer.Argument(help="要转换为语音的文本"),
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
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """文字转语音（支持音色克隆）"""
    load_env(env_file)
    api_key, base_url = get_api_config()

    selected_voice = voice

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
    )


# ── voices 子命令 ─────────────────────────────────────────────────

@app.command()
def voices(
    clone_type: bool = typer.Option(False, "--clone", help="仅显示已克隆的音色"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """列出可用音色"""
    load_env(env_file)
    api_key, base_url = get_api_config()

    voice_type = "PRIVATE" if clone_type else None
    voice_list = _tts_list_voices(api_key, base_url, voice_type=voice_type)

    if clone_type:
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


# ── 入口 ──────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()

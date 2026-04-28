"""OPC CLI 入口：B站视频转写 + 语音合成 + 本地TTS + 图片理解 + UI转Vue + AI日报 + 文生图"""

import os
import sys
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

from .config import get_api_config, load_env, get_image_config, get_llm_config, get_gpt_image_config, get_gpt_img_proxy
from .bili import run_bili, asr_transcribe, generate_srt, resegment_asr
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
    call_server_generate as _call_server_generate,
    call_server_load as _call_server_load,
    call_server_unload as _call_server_unload,
    _is_server_running as _is_tts_server_running,
    _read_pid_info as _read_tts_pid_info,
    DEFAULT_PORT as _TTS_DEFAULT_PORT,
)
from .vision import understand_image
from .ui2vue import ui2vue, save_vue_files, setup_vue_project
from .ai_daily import run_ai_daily
from .check_api import run_check_api
from .text2img import generate_image, download_image, enhance_prompt, RECOMMENDED_SIZES
from .gpt_image import (
    submit_and_wait as _gpt_submit_and_wait,
    enhance_prompt as _gpt_enhance_prompt,
    download_image as _gpt_download_image,
    load_image_as_base64 as _gpt_load_base64,
    _build_proxies as _gpt_build_proxies,
    SUPPORTED_SIZES as _GPT_SIZES,
    SIZE_4K_ONLY as _GPT_4K_SIZES,
)

app = typer.Typer(
    name="opc",
    help="OPC 工具集：B站视频转写 + 语音合成 + 本地TTS + 图片理解 + UI转Vue + AI日报 + 文生图",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


# ── bili 子命令 ────────────────────────────────────────────────────

@app.command()
def bili(
    url: str = typer.Argument("", help="Bilibili 视频链接（--skip-download 时可省略）"),
    output_dir: str = typer.Option("./output", "-o", "--output-dir", help="输出目录"),
    cookies: Optional[str] = typer.Option(None, "--cookies", help="yt-dlp cookies 文件路径"),
    audio_only: bool = typer.Option(False, "--audio-only", help="仅下载音频，不进行 ASR"),
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
    )


# ── asr 子命令 ────────────────────────────────────────────────────

@app.command()
def asr(
    audio: str = typer.Argument(..., help="输入音频文件路径（.wav/.mp3/.m4a 等）"),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="输出目录（默认与输入文件同目录）"),
    no_resegment: bool = typer.Option(False, "--no-resegment", help="禁用自动重断句（保留 ASR 原始切分）"),
    llm_fix: bool = typer.Option(False, "--llm-fix", help="使用 LLM 修复 ASR 断词和标点错误"),
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

    if audio_path.suffix.lower() not in (".wav", ".mp3", ".m4a", ".webm", ".ogg", ".opus"):
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
    asr_result = asr_transcribe(str(audio_path))

    # 自动重断句：按自然语句重新切分
    if not no_resegment:
        console.print("[dim]  自动重断句（按逗号逐句切分）...[/dim]")
        asr_result = resegment_asr(asr_result, llm_fix=llm_fix)

    # 生成 SRT
    generate_srt(asr_result, str(srt_path))

    # 生成 JSON
    with open(str(json_path), "w", encoding="utf-8") as f:
        import json
        json.dump(asr_result, f, ensure_ascii=False, indent=2)
    console.print(f"ASR JSON 已保存: {json_path}")

    console.print(f"\n[green]完成![/green]")
    console.print(f"  SRT:  {srt_path}")
    console.print(f"  JSON: {json_path}")


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
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """文字转语音（支持音色克隆）

    使用 --list-voices 查看系统音色，--list-cloned 查看克隆音色。
    """
    load_env(env_file)
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
    # 服务管理选项
    serve: bool = typer.Option(False, "--serve", help="启动 TTS 常驻服务"),
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
        _start_tts_server(mode=mode, device=device, attn=attn, port=port)
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
        model = _local_load_model(mode, device=device, attn=attn)

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


# ── ui2vue 子命令 ──────────────────────────────────────────────────

UI_FRAMEWORKS = ["default", "element-plus", "ant-design-vue", "naive-ui", "vuetify", "tailwind", "pure"]


@app.command("ui2vue")
def ui2vue_cmd(
    image: str = typer.Argument("", help="UI 界面截图路径或 URL（使用 --analysis 时可省略）"),
    framework: str = typer.Option("default", "-f", "--framework", help=f"UI 框架: {'/'.join(UI_FRAMEWORKS)}"),
    component: str = typer.Option("", "-c", "--component", help="组件名称（如 UserProfile）"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出目录或 .vue 文件路径"),
    project_name: str = typer.Option("vue-app", "-p", "--project", help="Vue 项目名称（步骤3创建工程时使用）"),
    vision_model: str = typer.Option("", "--vision-model", help="视觉模型名称（用于分析 UI，默认读取 VISION_MODEL 环境变量）"),
    llm_model: str = typer.Option("", "--llm-model", help="LLM 模型名称（用于生成代码，默认读取 LLM_MODEL 环境变量）"),
    max_tokens: int = typer.Option(16384, "--max-tokens", help="最大输出 token 数"),
    temperature: float = typer.Option(0.3, "--temperature", help="生成温度 0-1"),
    max_retries: int = typer.Option(3, "--max-retries", help="步骤3 最大自动修复重试次数"),
    analysis: str = typer.Option("", "--analysis", help="已有的 UI 分析 md 文件路径（提供后跳过步骤1，直接使用已有分析结果）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
    save_vue: bool = typer.Option(True, "--save-vue/--no-save-vue", help="是否自动提取并保存 .vue 文件"),
    create_project: bool = typer.Option(True, "--create-project/--no-create-project", help="是否创建 Vue 工程并自动修复（步骤3）"),
):
    """UI截图转Vue：视觉分析 → 生成Vue代码 → 创建工程并自动修复

    使用 --analysis 可跳过步骤1，直接使用已有的分析结果生成代码。
    """
    load_env(env_file)

    if not analysis and not image:
        console.print("[red]错误: 必须提供 image 参数或 --analysis 文件路径[/red]")
        raise typer.Exit(1)

    if framework not in UI_FRAMEWORKS:
        console.print(f"[red]错误: 不支持的 UI 框架 '{framework}'[/red]")
        console.print(f"可选: {', '.join(UI_FRAMEWORKS)}")
        raise typer.Exit(1)

    ui_description, vue_result, setup_result = ui2vue(
        image=image,
        framework=framework,
        component_name=component,
        output=output or ".",
        project_name=project_name,
        vision_model=vision_model,
        llm_model=llm_model,
        max_tokens=max_tokens,
        temperature=temperature,
        max_retries=max_retries,
        create_project=create_project,
        analysis_file=analysis,
    )

    # 保存文件（优先，避免终端编码中断导致文件未保存）
    comp_name = component or "GeneratedComponent"
    saved_files = []

    if save_vue and not create_project:
        # 仅在未创建工程时手动保存 .vue 文件（创建工程时步骤3已自动保存）
        if output:
            output_path = Path(output)
            if output_path.suffix == ".vue":
                output_path.parent.mkdir(parents=True, exist_ok=True)
                from .ui2vue import _extract_vue_code
                vue_code = _extract_vue_code(vue_result)
                with open(str(output_path), "w", encoding="utf-8") as f:
                    f.write(vue_code)
                saved_files.append(str(output_path))
            else:
                saved = save_vue_files(vue_result, str(output_path), comp_name)
                saved_files.extend([str(output_path / f) for f in saved])
        else:
            saved = save_vue_files(vue_result, ".", comp_name)
            saved_files.extend(saved)

    # 保存完整分析报告
    md_path = None
    if output:
        output_path = Path(output)
        if create_project:
            # 报告放在项目目录下
            md_path = output_path / project_name / "analysis.md"
        elif output_path.suffix == ".vue":
            md_path = output_path.with_suffix(".md")
        else:
            md_path = output_path / "analysis.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(md_path), "w", encoding="utf-8") as f:
            f.write(f"# UI 截图分析\n\n框架: {framework}\n\n## UI 结构分析\n\n{ui_description}\n\n---\n\n## 生成的 Vue 代码\n\n{vue_result}")
            if setup_result:
                f.write(f"\n\n---\n\n## 工程构建结果\n\n")
                f.write(f"- 项目路径: {setup_result['project_path']}\n")
                f.write(f"- 构建成功: {'是' if setup_result['success'] else '否'}\n")
                f.write(f"- 修复重试次数: {setup_result['retries']}\n")
                if not setup_result['success']:
                    for i, err in enumerate(setup_result['errors']):
                        f.write(f"\n### 错误 {i+1}\n\n```\n{err}\n```\n")

    # 步骤1和步骤2已在 ui2vue() 中实时打印，这里只输出步骤3的最终构建结果
    if setup_result:
        try:
            console.print("\n[bold yellow]== 步骤3: 工程构建结果 ==[/bold yellow]")
            if setup_result['success']:
                console.print(f"[green]构建成功！[/green] 项目路径: {setup_result['project_path']}")
                console.print(f"  修复重试: {setup_result['retries']} 次")
            else:
                console.print(f"[red]构建失败[/red]，重试 {setup_result['retries']} 次后仍未通过")
                console.print(f"  项目路径: {setup_result['project_path']}")
                console.print("  请手动检查错误或增加 --max-retries")
        except UnicodeEncodeError:
            print("\n[终端编码限制，完整内容请查看日志文件]")

    if saved_files:
        for f in saved_files:
            print(f"[已保存] {f}")
    if setup_result and setup_result['saved_files']:
        for f in setup_result['saved_files']:
            print(f"[组件已保存] {f}")
    if md_path:
        print(f"[分析报告] {md_path}")


# ── gpt-img 子命令 ──────────────────────────────────────────────

@app.command("gpt-img")
def gpt_img(
    prompt: str = typer.Argument(help="提示词（中英文，描述期望生成的图像）"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出图片路径（默认: output/gpt_img_<时间戳>.png）"),
    size: str = typer.Option("2:3", "-s", "--size", help=f"宽高比: {', '.join(_GPT_SIZES)}"),
    resolution: str = typer.Option("1k", "-r", "--resolution", help="分辨率档位: 1k / 2k / 4k"),
    enhance: bool = typer.Option(True, "--enhance/--no-enhance", help="使用 LLM 丰富提示词（默认开启）"),
    ref: Optional[list[str]] = typer.Option(None, "--ref", help="参考图路径或 URL（可多次指定，最多16张）"),
    no_download: bool = typer.Option(False, "--no-download", help="仅返回图片 URL，不下载到本地"),
    use_proxy: bool = typer.Option(False, "--proxy/--no-proxy", help="是否使用 GPT_IMG_PROXY 代理（默认不使用）"),
    timeout: int = typer.Option(300, "--timeout", help="最大等待时间（秒）"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """GPT-Image-2 文生图：高质量 AI 绘图（异步，自动轮询等待结果）

    默认使用 LLM (LLM_MODEL) 丰富提示词，可用 --no-enhance 关闭。

    宽高比: 1:1, 2:3, 3:2, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 2:1, 1:2, 21:9, 9:21

    分辨率: 1k(默认) / 2k / 4k（4K仅支持6个宽屏/竖屏比例）

    图生图: 使用 --ref 指定参考图（本地路径或 URL）
    """
    load_env(env_file)
    api_key, base_url, cfg_model = get_gpt_image_config()

    # 构建 gpt-img 专用代理（默认不使用）
    proxies = None
    if use_proxy:
        proxy_url = get_gpt_img_proxy()
        proxies = _gpt_build_proxies(proxy_url)
        if proxies:
            console.print(f"[dim]代理: {proxy_url}[/dim]")

    console.print(f"[bold]=== GPT-Image-2 文生图 ===[/bold]")
    console.print(f"原始提示词: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    console.print(f"宽高比: {size} | 分辨率: {resolution} | 模型: {cfg_model}")

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
                # 显示 JSON 结构化提示词
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
                # 本地文件转 base64
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
            image_urls=image_urls,
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

    console.print(f"[green]生成成功![/green] ({elapsed:.1f}s, 实际生成: {result.get('actual_time', '?')}s)")

    # 输出
    if no_download:
        console.print(f"\n图片 URL: {image_url}")
        console.print("[yellow]注意: URL 有效期 24 小时，请及时保存[/yellow]")
    else:
        if not output:
            ts = _time.strftime("%Y%m%d_%H%M%S")
            output = f"output/gpt_img_{ts}.png"

        try:
            saved = _gpt_download_image(image_url, output, proxies=proxies)
            file_size = Path(saved).stat().st_size
            console.print(f"[green]已保存:[/green] {saved} ({file_size / 1024:.0f} KB)")
        except Exception as e:
            console.print(f"[red]下载失败: {e}[/red]")
            console.print(f"图片 URL（有效期 24 小时）: {image_url}")
            raise typer.Exit(1)

    console.print(f"[dim]URL: {image_url}[/dim]")


# ── Z-image 子命令 ──────────────────────────────────────────────

@app.command("Z-image")
def text2img(
    prompt: str = typer.Argument(help="提示词（中英文，描述期望生成的图像）"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出图片路径（默认: output/text2img_<时间戳>.png）"),
    size: str = typer.Option("2:3", "-s", "--size", help="输出分辨率：宽*高（如 1024*1536）或宽高比（如 2:3, 16:9）"),
    model: str = typer.Option("z-image-turbo", "--model", help="模型名称"),
    enhance: bool = typer.Option(True, "--enhance/--no-enhance", help="使用 LLM 丰富提示词（默认开启）"),
    prompt_extend: bool = typer.Option(False, "--prompt-extend", help="启用 z-image 智能提示词改写（会增加响应时间和费用）"),
    seed: Optional[int] = typer.Option(None, "--seed", help="随机种子（0~2147483647）"),
    no_download: bool = typer.Option(False, "--no-download", help="仅返回图片 URL，不下载到本地"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
):
    """文生图：使用阿里云 z-image-turbo 根据提示词生成图片

    默认使用 LLM (LLM_MODEL) 丰富提示词，可用 --no-enhance 关闭。

    分辨率格式：宽*高（如 512*512）或宽高比（如 2:3, 16:9）

    常用宽高比：1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9, 21:9

    默认输出 2:3 竖图 (1024*1536)，总像素范围 [512*512, 2048*2048]
    """
    load_env(env_file)
    api_key, cfg_model = get_image_config()

    # 命令行 model 优先
    use_model = model if model != "z-image-turbo" else cfg_model

    console.print(f"[bold]=== 文生图 (z-image-turbo) ===[/bold]")
    console.print(f"原始提示词: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    console.print(f"分辨率: {size} | 模型: {use_model}")

    # 使用 LLM 丰富提示词
    use_prompt = prompt
    use_prompt_json = None
    if enhance:
        console.print("\n[cyan]🧠 使用 LLM 丰富提示词...[/cyan]")
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
            use_prompt_json = enhanced["json_str"]
            console.print(f"[dim]  原始: {prompt[:80]}[/dim]")
            console.print(f"[cyan]  丰富: {use_prompt[:150]}{'...' if len(use_prompt) > 150 else ''}[/cyan]")
        except Exception as e:
            console.print(f"[yellow]⚠ LLM 丰富失败，使用原始提示词: {e}[/yellow]")

    if prompt_extend:
        console.print("[cyan]z-image 智能提示词改写: 已开启[/cyan]")

    # 生成图片
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
        )
    except ValueError as e:
        console.print(f"[red]参数错误: {e}[/red]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]生成失败: {e}[/red]")
        raise typer.Exit(1)

    elapsed = time.time() - t0
    image_url = result.get("image_url")

    if not image_url:
        console.print("[red]未获取到图片 URL[/red]")
        raise typer.Exit(1)

    console.print(f"[green]生成成功![/green] ({elapsed:.1f}s) {result.get('width')}*{result.get('height')}")

    if result.get("text") and prompt_extend:
        console.print(f"[dim]改写后提示词: {result['text'][:200]}[/dim]")

    # 输出
    if no_download:
        console.print(f"\n图片 URL: {image_url}")
        console.print("[yellow]注意: URL 有效期 24 小时，请及时保存[/yellow]")
    else:
        # 生成默认路径
        if not output:
            ts = time.strftime("%Y%m%d_%H%M%S")
            output = f"output/text2img_{ts}.png"

        try:
            saved = download_image(image_url, output)
            file_size = Path(saved).stat().st_size
            console.print(f"[green]已保存:[/green] {saved} ({file_size / 1024:.0f} KB)")
        except Exception as e:
            console.print(f"[red]下载失败: {e}[/red]")
            console.print(f"图片 URL（有效期 24 小时）: {image_url}")
            raise typer.Exit(1)

    # 输出 URL（方便复制）
    console.print(f"[dim]URL: {image_url}[/dim]")


# ── check-api 子命令 ──────────────────────────────────────────────

@app.command("check-api")
def check_api(
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
    only: Optional[list[str]] = typer.Option(None, "--only", help="只检查指定 API，可多次使用。如 --only llm --only vision"),
):
    """检查 .env 中 API 的连通性和密钥有效性

    可用 API 名称: llm, zhipu, vision, image, gpt-image, proxy, cookies

    示例:
      opc check-api                # 检查全部
      opc check-api --only llm     # 只检查 LLM
      opc check-api --only llm --only vision  # 检查 LLM 和 Vision
    """
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


# ── news 子命令 ──────────────────────────────────────────────

@app.command("news")
def ai_daily(
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出文件完整路径（优先级高于 --output-dir）"),
    output_dir: Optional[str] = typer.Option(None, "-d", "--output-dir", help="输出目录，文件名默认 ai_daily_YYYY-MM-DD.md"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
    no_llm: bool = typer.Option(False, "--no-llm", help="不调用 LLM，仅输出原始素材"),
    save_raw: bool = typer.Option(False, "--save-raw", help="额外保存原始 JSON 数据"),
):
    """AI 日报：自动收集当日 AI 技术/科研/项目新闻，LLM 整合输出专业简报

    信息来源：36氪、虎嗅、IT之家、InfoQ（RSS）、GitHub、Arxiv
    使用 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 配置大模型
    """
    run_ai_daily(output=output, output_dir=output_dir, env_file=env_file, no_llm=no_llm, save_raw=save_raw)


# ── 入口 ──────────────────────────────────────────────────────────

def main():
    from .logger import install_tee
    install_tee()
    app()


if __name__ == "__main__":
    main()

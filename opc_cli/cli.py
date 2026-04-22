"""OPC CLI 入口：B站视频转写 + 语音合成 + 本地TTS + 图片理解 + UI转Vue"""

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

# Windows 终端编码修复
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")

from .config import get_api_config, load_env
from .bili import run_bili
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

app = typer.Typer(
    name="opc",
    help="OPC 工具集：B站视频转写 + 语音合成 + 本地TTS + 图片理解 + UI转Vue",
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


# ── local-tts 子命令 ─────────────────────────────────────────────

@app.command("local-tts")
def local_tts(
    text: str = typer.Argument(help="要转换为语音的文本"),
    output: str = typer.Option("output.wav", "-o", "--output", help="输出文件路径"),
    mode: str = typer.Option("custom", "-m", "--mode", help="模型变体: custom=预设音色, design=设计音色, base=语音克隆"),
    speaker: str = typer.Option("Vivian", "-s", "--speaker", help="预设音色名称（custom 模式）"),
    language: str = typer.Option("Chinese", "-l", "--language", help=f"语言: {'/'.join(_LOCAL_LANGUAGES)}"),
    instruct: str = typer.Option("", "--instruct", help="自然语言指令（custom 控制语气 / design 描述音色）"),
    ref_audio: Optional[str] = typer.Option(None, "--ref-audio", help="参考音频路径（base 模式）"),
    ref_text: Optional[str] = typer.Option(None, "--ref-text", help="参考音频对应文本（base 模式，可选）"),
    device: str = typer.Option("cuda:0", "--device", help="设备（默认: cuda:0）"),
    attn: str = typer.Option("sdpa", "--attn", help="注意力实现: sdpa/flash_attention_2/eager"),
    list_speakers_flag: bool = typer.Option(False, "--list-speakers", help="列出预设音色"),
):
    """本地语音合成（Qwen3-TTS：预设音色 / 设计音色 / 语音克隆）"""
    # 列出音色
    if list_speakers_flag:
        console.print("\n[bold]预设音色 (custom 模式):[/bold]")
        console.print("-" * 50)
        for name, desc in _local_list_speakers().items():
            console.print(f"  {name:<12} {desc}")
        console.print(f"\n支持语言: {', '.join(_LOCAL_LANGUAGES)}")
        return

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

    if mode == "design" and not instruct:
        console.print("[red]错误: design 模式需要 --instruct 参数描述音色[/red]")
        raise typer.Exit(1)

    if mode == "custom" and speaker not in _local_list_speakers():
        console.print(f"[yellow]警告: 音色 '{speaker}' 不在预设列表中，可能无法正常工作[/yellow]")

    # 加载模型
    import time
    total_t0 = time.time()

    console.print(f"[bold]=== Qwen3-TTS 本地语音合成 ===[/bold]")
    console.print(f"模式: {mode} | 音色: {speaker} | 语言: {language}")
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

@app.command()
def img(
    image: str = typer.Argument(help="图片路径或 URL"),
    prompt: str = typer.Option("请详细描述这张图片的内容", "-p", "--prompt", help="提问内容"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出到文件（默认打印到终端）"),
    model: str = typer.Option("glm-5v-turbo", "--model", help="视觉模型名称"),
    max_tokens: int = typer.Option(1024, "--max-tokens", help="最大输出 token 数"),
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


@app.command()
def ui2vue_cmd(
    image: str = typer.Argument(help="UI 界面截图路径或 URL"),
    framework: str = typer.Option("default", "-f", "--framework", help=f"UI 框架: {'/'.join(UI_FRAMEWORKS)}"),
    component: str = typer.Option("", "-c", "--component", help="组件名称（如 UserProfile）"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="输出目录或 .vue 文件路径"),
    project_name: str = typer.Option("vue-app", "-p", "--project", help="Vue 项目名称（步骤3创建工程时使用）"),
    vision_model: str = typer.Option("", "--vision-model", help="视觉模型名称（用于分析 UI，默认读取 VISION_MODEL 环境变量）"),
    llm_model: str = typer.Option("", "--llm-model", help="LLM 模型名称（用于生成代码，默认读取 LLM_MODEL 环境变量）"),
    max_tokens: int = typer.Option(8192, "--max-tokens", help="最大输出 token 数"),
    temperature: float = typer.Option(0.3, "--temperature", help="生成温度 0-1"),
    max_retries: int = typer.Option(3, "--max-retries", help="步骤3 最大自动修复重试次数"),
    env_file: Optional[str] = typer.Option(None, "--env-file", help=".env 文件路径"),
    save_vue: bool = typer.Option(True, "--save-vue/--no-save-vue", help="是否自动提取并保存 .vue 文件"),
    create_project: bool = typer.Option(True, "--create-project/--no-create-project", help="是否创建 Vue 工程并自动修复（步骤3）"),
):
    """UI截图转Vue：视觉分析 → 生成Vue代码 → 创建工程并自动修复"""
    load_env(env_file)

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

    # 安全输出到终端（处理 Windows GBK 编码）
    try:
        console.print("\n[bold cyan]== 步骤1: UI 结构分析 ==[/bold cyan]")
        console.print(ui_description[:500] + ("..." if len(ui_description) > 500 else ""))
        console.print("\n[bold green]== 步骤2: 生成的 Vue 代码 ==[/bold green]")
        console.print(vue_result[:800] + ("..." if len(vue_result) > 800 else ""))
        if setup_result:
            console.print("\n[bold yellow]== 步骤3: 工程构建结果 ==[/bold yellow]")
            if setup_result['success']:
                console.print(f"[green]构建成功！[/green] 项目路径: {setup_result['project_path']}")
                console.print(f"  修复重试: {setup_result['retries']} 次")
            else:
                console.print(f"[red]构建失败[/red]，重试 {setup_result['retries']} 次后仍未通过")
                console.print(f"  项目路径: {setup_result['project_path']}")
                console.print("  请手动检查错误或增加 --max-retries")
    except UnicodeEncodeError:
        print("\n[终端编码限制，完整内容请查看输出文件]")

    if saved_files:
        for f in saved_files:
            print(f"[已保存] {f}")
    if setup_result and setup_result['saved_files']:
        for f in setup_result['saved_files']:
            print(f"[组件已保存] {f}")
    if md_path:
        print(f"[分析报告] {md_path}")


# ── 入口 ──────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()

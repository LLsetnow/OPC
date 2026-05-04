# bilimusic Command Design

## Overview

Add `opc bilimusic` subcommand: download best audio from a Bilibili video and convert it to MP3 format with embedded ID3 metadata (title, uploader, cover art).

## CLI Signature

```bash
opc bilimusic "URL"                    # Default: 192kbps MP3 with metadata
opc bilimusic "URL" -o ./music         # Custom output directory
opc bilimusic "URL" --bitrate 320      # Custom MP3 bitrate (kbps)
opc bilimusic "URL" --no-metadata      # Skip ID3 tag writing
opc bilimusic "URL" --cookies path     # Custom cookies file for yt-dlp
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | Argument (str) | required | Bilibili video URL |
| `-o, --output-dir` | Option (str) | `./output` | Output directory |
| `--bitrate` | Option (int) | `192` | MP3 bitrate in kbps |
| `--no-metadata` | Option (bool) | False | Skip metadata embedding |
| `--cookies` | Option (str) | None | yt-dlp cookies file path |

## Implementation

### New file: `opc_cli/bilimusic.py`

**`download_audio(url, output_dir, cookies)`**
- Use `yt-dlp` with `--format bestaudio` to download audio
- If ffmpeg available, extract audio stream (without re-encoding) as `.m4a`
- If no ffmpeg, keep original format
- Returns: `(audio_path, video_info_dict)` where video_info_dict contains title, uploader, thumbnail URL

**`convert_to_mp3(input_path, output_path, bitrate)`**
- Run: `ffmpeg -y -i input -vn -b:a {bitrate}k output.mp3`
- Preserve audio quality from source
- Requires ffmpeg on PATH

**`embed_metadata(mp3_path, info, cover_path=None)`**
- Use `mutagen.mp3.MP3` + `mutagen.id3` to write ID3v2 tags:
  - TIT2 (title)
  - TPE1 (artist — uploader name)
  - APIC (cover art) if cover downloaded
- Download cover image from thumbnail URL via `requests`
- Skip if `--no-metadata` or if mutagen unavailable

**`run_bilimusic(url, output_dir, bitrate, no_metadata, cookies)`**
- Orchestrator: download → convert → embed metadata
- Typer progress feedback via `rich.console.Console().print()`

### Modify: `opc_cli/cli.py`

- Import `run_bilimusic` from `.bilimusic`
- Add `@app.command("bilimusic")` decorated function calling `run_bilimusic`

### New dependency: `mutagen`

- Add `mutagen>=1.47.0` to `pyproject.toml` `[project].dependencies`
- Add `mutagen>=1.47.0` to `requirements.txt`

## Error Handling

- ffmpeg not found: error message "需要 ffmpeg 才能转换为 MP3 格式", exit
- yt-dlp download fails: propagate yt-dlp error
- mutagen not installed: warn and skip metadata, still output MP3
- Cover download fails: warn and skip cover, still embed title/artist

## Testing

Manual test with a known Bilibili video URL:
1. `opc bilimusic "https://www.bilibili.com/video/BV1xx"` → verify `.mp3` output
2. Verify metadata: `ffprobe output.mp3` or check in music player
3. `opc bilimusic "URL" --no-metadata` → verify clean MP3 without tags
4. `opc bilimusic "URL" --bitrate 320` → verify 320kbps encoding

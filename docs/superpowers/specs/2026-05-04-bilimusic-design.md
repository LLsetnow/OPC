# B站 MP3 导出设计

## Overview

Extend `opc bili` with an audio-only mode: download the best audio from a Bilibili video and convert it to MP3 format with embedded ID3 metadata (title, uploader, cover art).

## CLI Signature

```bash
opc bili "URL" --audio-only                    # Default: 192kbps MP3 with metadata
opc bili "URL" --audio-only -o ./music         # Custom output directory
opc bili "URL" --audio-only --bitrate 320      # Custom MP3 bitrate (kbps)
opc bili "URL" --audio-only --no-metadata      # Skip ID3 tag writing
opc bili "URL" --audio-only --cookies path     # Custom cookies file for yt-dlp
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | Argument (str) | required | Bilibili video URL |
| `--audio-only` | Option (bool) | False | Download audio, convert to MP3, and skip ASR |
| `-o, --output-dir` | Option (str) | `./output` | Output directory |
| `--bitrate` | Option (int) | `192` | MP3 bitrate in kbps |
| `--no-metadata` | Option (bool) | False | Skip metadata embedding |
| `--cookies` | Option (str) | None | yt-dlp cookies file path |

## Implementation

### Modify: `opc_cli/bili.py`

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

**`run_bili(url, output_dir, bitrate, no_metadata, cookies, audio_only)`**
- Orchestrator: download → convert → embed metadata
- Reuse the existing B站 download flow and run the MP3 conversion when `audio_only` is enabled.
- Remove the standalone `bilimusic` command and module.

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
1. `opc bili "https://www.bilibili.com/video/BV1xx" --audio-only` → verify `.mp3` output
2. Verify metadata: `ffprobe output.mp3` or check in music player
3. `opc bili "URL" --audio-only --no-metadata` → verify clean MP3 without tags
4. `opc bili "URL" --audio-only --bitrate 320` → verify 320kbps encoding

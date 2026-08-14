"""音乐理解命令的离线单元测试。"""

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from opc_cli import audio, cli


class _FakeResponse:
    status_code = 200

    class output:
        class choices:
            class _Choice:
                class message:
                    content = [{"text": "这是一首电子音乐。"}]

            _Choice = _Choice

            @classmethod
            def __class_getitem__(cls, index):
                return cls._Choice()


class AudioUnderstandingTests(unittest.TestCase):
    def test_detect_beats_returns_timestamps(self):
        fake_librosa = SimpleNamespace(
            load=lambda path, sr, mono: ("samples", 44100),
            beat=SimpleNamespace(
                beat_track=lambda y, sr, units, hop_length: (120.0, [1, 2])
            ),
            onset=SimpleNamespace(
                onset_detect=lambda y, sr, units, backtrack, hop_length: [0, 1],
                onset_strength=lambda y, sr, hop_length: [0.5, 1.0, 0.25],
            ),
            frames_to_time=lambda frames, sr, hop_length: [
                frame * hop_length / sr for frame in frames
            ],
        )
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "song.mp3"
            audio_path.write_bytes(b"audio")
            with patch.dict(sys.modules, {"librosa": fake_librosa}):
                result = audio.detect_beats(str(audio_path))

        self.assertEqual(result["tempo_bpm"], 120.0)
        self.assertEqual(result["beat_times"], [512 / 44100, 1024 / 44100])
        self.assertEqual(result["beat_strengths"], [1.0, 0.25])
        self.assertEqual(result["onset_times"], [0.0, 512 / 44100])
        self.assertEqual(result["onset_strengths"], [0.5, 1.0])

    def test_filter_beat_events_keeps_one_strongest_event_per_window(self):
        result = audio.filter_beat_events(
            {
                "beat_times": [0.1, 0.4, 1.2],
                "beat_strengths": [0.8, 0.9, 0.7],
                "onset_times": [0.6, 1.7],
                "onset_strengths": [0.95, 0.6],
            },
            strength_threshold=0.7,
            min_interval=1.0,
        )
        self.assertEqual(result["events"], [
            {"time": 0.6, "strength": 0.95, "kind": "onset"},
            {"time": 1.2, "strength": 0.7, "kind": "beat"},
        ])

    def test_analyze_audio_uses_base64_audio_only_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "song.m4a"
            audio_path.write_bytes(b"audio-bytes")

            with patch.dict(
                os.environ,
                {"ALIYUN_API_KEY": "test-key", "AUDIO_MODEL": audio.DEFAULT_AUDIO_MODEL},
                clear=False,
            ), patch.object(
                audio.dashscope.MultiModalConversation,
                "call",
                return_value=_FakeResponse(),
            ) as call:
                result = audio.analyze_audio(str(audio_path))

        self.assertEqual(result, "这是一首电子音乐。")
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "test-key")
        self.assertEqual(kwargs["model"], audio.DEFAULT_AUDIO_MODEL)
        message = kwargs["messages"][0]
        self.assertEqual(message["role"], "user")
        self.assertEqual(
            message["content"][0]["audio"],
            "data:;base64," + base64.b64encode(b"audio-bytes").decode("ascii"),
        )

    def test_cli_audio_calls_captioner(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "song.mp3"
            audio_path.write_bytes(b"audio")
            with patch("opc_cli.cli.analyze_audio", return_value="音乐分析结果") as analyze:
                result = runner.invoke(cli.app, ["music", "understand", str(audio_path)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("音乐分析结果", result.output)
            analyze.assert_called_once_with(str(audio_path), model="")

    def test_cli_librosa_prints_and_saves_analysis(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary:
            audio_path = Path(temporary) / "song.mp3"
            output_path = Path(temporary) / "nested" / "analysis.txt"
            audio_path.write_bytes(b"audio")

            with patch(
                "opc_cli.cli.detect_beats",
                return_value={
                    "tempo_bpm": 120.0,
                    "beat_times": [0.5],
                    "beat_strengths": [0.75],
                    "onset_times": [0.25],
                    "onset_strengths": [0.5],
                },
            ) as detect:
                result = runner.invoke(
                    cli.app,
                    [
                        "music",
                        "beats",
                        str(audio_path),
                        "--beat-strength-threshold",
                        "0.6",
                        "-o",
                        str(output_path),
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Librosa 鼓点检测", result.output)
            self.assertIn("估计 BPM: 120.00", result.output)
            self.assertIn("筛选阈值: 0.60", result.output)
            self.assertIn("0.500", result.output)
            self.assertIn("0.500s:0.75", result.output)
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "## Librosa 鼓点检测\n估计 BPM: 120.00\n"
                "原始节拍数量: 1\n原始起音数量: 1\n筛选阈值: 0.60\n最小间隔: 1.00s\n"
                "筛选后事件总数: 1\n筛选后节拍时刻（beat_times，单位：秒）:\n0.500\n"
                "筛选后起音/打击候选时刻（onset_times，单位：秒）:\n（无）\n"
                "筛选后节拍时刻与相对强度（beat_times:beat_strengths，0-1）:\n0.500s:0.75\n"
                "筛选后起音时刻与相对强度（onset_times:onset_strengths，0-1）:\n",
            )
            detect.assert_called_once_with(str(audio_path))


if __name__ == "__main__":
    unittest.main()

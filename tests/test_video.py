"""共享视频下载辅助函数 (``opc_cli._video``) 的离线单元测试。"""

import subprocess
import unittest
from unittest.mock import patch

from opc_cli import _video


class WriteFinderCommentTests(unittest.TestCase):
    def test_write_finder_comment_skips_off_macos(self):
        with patch("opc_cli._video.sys.platform", "linux"), patch(
            "opc_cli._video.subprocess.run"
        ) as run:
            self.assertFalse(_video.write_finder_comment("/tmp/video.mp4"))
        run.assert_not_called()

    def test_write_finder_comment_copies_embedded_comment_on_macos(self):
        ffprobe = subprocess.CompletedProcess(
            ["ffprobe"], 0, stdout="来源：url ｜ 作者：a ｜ 发布：2024-12-02\n", stderr=""
        )
        osascript = subprocess.CompletedProcess(["osascript"], 0, stdout="", stderr="")
        with patch("opc_cli._video.sys.platform", "darwin"), patch(
            "opc_cli._video.subprocess.run", side_effect=[ffprobe, osascript]
        ) as run:
            self.assertTrue(_video.write_finder_comment("/tmp/video.mp4"))

        osascript_call = run.call_args_list[1].args[0]
        self.assertEqual(osascript_call[0], "osascript")
        self.assertEqual(osascript_call[-2], "/tmp/video.mp4")
        self.assertEqual(osascript_call[-1], "来源：url ｜ 作者：a ｜ 发布：2024-12-02")


if __name__ == "__main__":
    unittest.main()

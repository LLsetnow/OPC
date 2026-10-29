"""Cookie expiry detection and browser-export renewal tests."""

import os
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from opc_cli.cookies import inspect_cookie_file, prepare_cookie_file


def _cookie_line(expires: int, value: str = "value") -> str:
    return f".example.com\tTRUE\t/\tFALSE\t{expires}\tauth_token\t{value}\n"


class CookieInspectionTests(unittest.TestCase):
    def test_renewal_is_due_after_half_of_observed_lifetime(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cookies.txt"
            path.write_text("# Netscape HTTP Cookie File\n" + _cookie_line(1000), encoding="utf-8")
            os.utime(path, (100, 100))

            before_half = inspect_cookie_file(path, now=400)
            after_half = inspect_cookie_file(path, now=600)

        self.assertIsNotNone(before_half)
        self.assertFalse(before_half.renewal_needed)
        self.assertIsNotNone(after_half)
        self.assertTrue(after_half.renewal_needed)

    def test_session_only_cookie_file_has_no_renewal_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cookies.txt"
            path.write_text(_cookie_line(0), encoding="utf-8")
            status = inspect_cookie_file(path, now=time.time())

        self.assertIsNotNone(status)
        self.assertEqual(status.persistent_cookie_count, 0)
        self.assertFalse(status.renewal_needed)

    def test_sidecar_preserves_lifecycle_when_yt_dlp_rewrites_cookie_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cookies.txt"
            path.write_text(_cookie_line(1000), encoding="utf-8")
            os.utime(path, (100, 100))
            Path(f"{path}.opc-renewal.json").write_text(
                json.dumps({"earliest_expires_at": 1000, "observed_at": 100}),
                encoding="utf-8",
            )
            # Simulate a normal yt-dlp save that refreshed only the file mtime.
            os.utime(path, (500, 500))
            status = inspect_cookie_file(path, now=600)

        self.assertIsNotNone(status)
        self.assertEqual(status.observed_at, 100)
        self.assertTrue(status.renewal_needed)


class CookieRenewalTests(unittest.TestCase):
    def test_browser_export_replaces_cookie_file_only_after_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cookies.txt"
            path.write_text(_cookie_line(1, value="old"), encoding="utf-8")

            def runner(command, **kwargs):
                target = Path(command[command.index("--cookies") + 1])
                target.write_text(
                    "# Netscape HTTP Cookie File\n" + _cookie_line(2_000_000_000, value="new"),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            result = prepare_cookie_file(
                path,
                "https://example.com/video/1",
                browser="chrome:Default",
                runner=runner,
            )
            contents = path.read_text(encoding="utf-8")

        self.assertEqual(result, str(path))
        self.assertIn("\tnew\n", contents)

    def test_failed_browser_export_keeps_original_cookie_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cookies.txt"
            path.write_text(_cookie_line(1, value="old"), encoding="utf-8")

            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

            prepare_cookie_file(
                path,
                "https://example.com/video/1",
                browser="chrome",
                runner=runner,
            )
            contents = path.read_text(encoding="utf-8")
            temporary_outputs = list(Path(temporary).glob(".cookies.txt.renew-*.txt"))

        self.assertIn("\told\n", contents)
        self.assertEqual(temporary_outputs, [])


if __name__ == "__main__":
    unittest.main()

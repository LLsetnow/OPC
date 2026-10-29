"""Cookie file inspection and optional sliding renewal for yt-dlp.

The Netscape cookie format stores an expiry timestamp, but not the time at
which a cookie was issued.  We use the cookie file's mtime for the first
observation and keep that observation in a non-secret sidecar, because yt-dlp
may rewrite the cookie file during normal use.  When the earliest persistent
cookie has less than half of that observed lifetime left, a configured browser
profile can be exported again by yt-dlp.

The original file is never edited in place during renewal.  yt-dlp writes to
a temporary file and the refreshed file replaces the original only after a
successful command and a basic format check.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


COOKIE_RENEW_BROWSER_ENV = "YT_DLP_COOKIES_FROM_BROWSER"
COOKIE_RENEWAL_FRACTION = 0.5
COOKIE_RENEWAL_METADATA_SUFFIX = ".opc-renewal.json"


@dataclass(frozen=True)
class CookieFileStatus:
    """Expiry information derived from one Netscape cookie file."""

    path: Path
    persistent_cookie_count: int
    earliest_expires_at: float | None
    observed_at: float
    remaining_seconds: float | None
    lifetime_seconds: float | None
    renewal_needed: bool


def _persistent_expiries(cookie_file: Path) -> list[float]:
    """Read persistent expiry timestamps without ever reading cookie values."""
    expiries: list[float] = []
    try:
        with cookie_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip() or line.startswith("#"):
                    continue
                fields = line.rstrip("\r\n").split("\t")
                # Netscape format: domain, include-subdomains, path, secure,
                # expires, name, value.  The value is intentionally ignored.
                if len(fields) < 7:
                    continue
                try:
                    expires_at = float(fields[4].strip())
                except ValueError:
                    continue
                # 0 is the Netscape representation for a session cookie.
                if expires_at > 0:
                    expiries.append(expires_at)
    except (OSError, UnicodeError):
        return []
    return expiries


def _metadata_path(cookie_file: Path) -> Path:
    """Return the non-secret sidecar used to survive yt-dlp mtime rewrites."""
    return cookie_file.with_name(cookie_file.name + COOKIE_RENEWAL_METADATA_SUFFIX)


def _stored_observed_at(cookie_file: Path, earliest_expires_at: float) -> float | None:
    """Load a matching observation without treating malformed metadata as fatal."""
    try:
        data = json.loads(_metadata_path(cookie_file).read_text(encoding="utf-8"))
        if float(data.get("earliest_expires_at")) != earliest_expires_at:
            return None
        observed_at = float(data.get("observed_at"))
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        return None
    return observed_at if observed_at >= 0 else None


def _store_observation(cookie_file: Path, earliest_expires_at: float, observed_at: float) -> None:
    """Atomically persist non-secret renewal bookkeeping next to the cookie file."""
    metadata_path = _metadata_path(cookie_file)
    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{metadata_path.name}.tmp-",
            suffix=".json",
            dir=str(metadata_path.parent),
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        temporary_path.write_text(
            json.dumps(
                {
                    "earliest_expires_at": earliest_expires_at,
                    "observed_at": observed_at,
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, metadata_path)
        temporary_path = None
    except OSError:
        # A read-only cookie directory should not make downloads fail.
        pass
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def inspect_cookie_file(cookie_file: str | os.PathLike[str], now: float | None = None) -> CookieFileStatus | None:
    """Return expiry status for a cookie file, or ``None`` if it is unreadable."""
    path = Path(cookie_file).expanduser()
    try:
        file_stat = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None

    expiries = _persistent_expiries(path)
    current_time = time.time() if now is None else float(now)
    if not expiries:
        return CookieFileStatus(
            path=path,
            persistent_cookie_count=0,
            earliest_expires_at=None,
            observed_at=min(file_stat.st_mtime, current_time),
            remaining_seconds=None,
            lifetime_seconds=None,
            renewal_needed=False,
        )

    earliest_expires_at = min(expiries)
    # A future mtime can occur after copying a file between machines.  Treat
    # that as "observed now" instead of producing a negative lifetime.
    observed_at = _stored_observed_at(path, earliest_expires_at)
    if observed_at is None:
        observed_at = min(file_stat.st_mtime, current_time)
    else:
        observed_at = min(observed_at, current_time)
    lifetime_seconds = earliest_expires_at - observed_at
    remaining_seconds = earliest_expires_at - current_time
    renewal_needed = (
        lifetime_seconds <= 0
        or remaining_seconds <= 0
        or remaining_seconds < lifetime_seconds * COOKIE_RENEWAL_FRACTION
    )
    return CookieFileStatus(
        path=path,
        persistent_cookie_count=len(expiries),
        earliest_expires_at=earliest_expires_at,
        observed_at=observed_at,
        remaining_seconds=remaining_seconds,
        lifetime_seconds=lifetime_seconds,
        renewal_needed=renewal_needed,
    )


def _has_cookie_records(cookie_file: Path) -> bool:
    """Check that a refreshed file contains at least one cookie record."""
    try:
        with cookie_file.open("r", encoding="utf-8", errors="replace") as handle:
            return any(line.strip() and not line.startswith("#") for line in handle)
    except OSError:
        return False


def _renew_from_browser(
    cookie_file: Path,
    url: str,
    browser: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    """Export the browser cookie jar to ``cookie_file`` using yt-dlp."""
    try:
        original_mode = stat.S_IMODE(cookie_file.stat().st_mode)
    except OSError:
        original_mode = 0o600

    temporary_path: Path | None = None
    try:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{cookie_file.name}.renew-",
            suffix=".txt",
            dir=str(cookie_file.parent),
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        # A nonexistent cookie file makes yt-dlp use the browser jar as the
        # source while still assigning the requested output filename to the
        # cookie jar it saves on exit.
        temporary_path.unlink()

        command = [
            "yt-dlp",
            "--cookies-from-browser",
            browser,
            "--cookies",
            str(temporary_path),
            "--skip-download",
            "--simulate",
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            url,
        ]
        result = runner(command, capture_output=True, text=True)
        if result.returncode != 0 or not temporary_path.is_file() or not _has_cookie_records(temporary_path):
            return False

        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, cookie_file)
        temporary_path = None
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def prepare_cookie_file(
    cookie_file: str | os.PathLike[str] | None,
    url: str,
    *,
    browser: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str | None:
    """Maybe renew a cookie file before passing it to yt-dlp.

    ``browser`` accepts yt-dlp's browser specification, for example
    ``chrome`` or ``chrome:Default``.  If omitted, the
    ``YT_DLP_COOKIES_FROM_BROWSER`` environment variable is used.  Renewal is
    best-effort: an unavailable browser profile never prevents the existing
    cookie file from being used.
    """
    if not cookie_file:
        return None

    path = Path(cookie_file).expanduser()
    status = inspect_cookie_file(path)
    if status is None or not status.renewal_needed:
        if status and status.earliest_expires_at is not None:
            _store_observation(path, status.earliest_expires_at, status.observed_at)
        return str(path)

    browser = browser or os.environ.get(COOKIE_RENEW_BROWSER_ENV, "").strip()
    if not browser:
        if status.earliest_expires_at is not None:
            _store_observation(path, status.earliest_expires_at, status.observed_at)
        print(
            f"提示: cookie 文件 {path} 的剩余寿命已少于一半；未配置 "
            f"{COOKIE_RENEW_BROWSER_ENV}，继续使用现有文件。"
        )
        return str(path)

    print(f"cookie 文件即将过期，尝试从浏览器 {browser!r} 滑动续签...")
    if _renew_from_browser(path, url, browser, runner=runner):
        refreshed = inspect_cookie_file(path)
        if refreshed and refreshed.earliest_expires_at is not None:
            _store_observation(
                path,
                refreshed.earliest_expires_at,
                time.time(),
            )
        print(f"cookie 已续签并更新: {path}")
    else:
        if status.earliest_expires_at is not None:
            _store_observation(path, status.earliest_expires_at, status.observed_at)
        print(f"警告: cookie 续签失败，继续使用现有文件: {path}")
    return str(path)

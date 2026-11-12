#!/usr/bin/env python3
"""Download the Nasdaq TotalView-ITCH 5.0 captures used by this project.

    S112825-v50.txt.gz -> data/functional/functional.txt.gz
    S061226-v50.txt.gz -> data/stress/stress.txt.gz

Downloads go to a ``.part`` file and resume after interruption (HTTP Range). The
finished file is checked against its known size before it replaces the target.
Run ``scripts/decompress.py`` afterwards to produce the ``.bin`` files.
"""

from __future__ import annotations

import argparse
import http.client
import shutil
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Final, final

if TYPE_CHECKING:
    from collections.abc import Sequence

EMI_HOST: Final = "emi.nasdaq.com"
EMI_PATH: Final = "/ITCH/Nasdaq%20ITCH"
REPO_ROOT: Final = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR: Final = REPO_ROOT / "data"
CHUNK_SIZE: Final = 4 * 1024 * 1024
KIB: Final = 1024
TIMEOUT_SECONDS: Final = 60
REPORT_INTERVAL_SECONDS: Final = 1.0
USER_AGENT: Final = "the-stock-market-project/get_itch_data"


@dataclass(frozen=True, slots=True)
class Capture:
    """One ITCH capture published on the Nasdaq EMI server."""

    role: str
    remote_name: str
    size: int

    @property
    def path(self) -> str:
        """Request path on the EMI server."""
        return f"{EMI_PATH}/{self.remote_name}"

    @property
    def url(self) -> str:
        """Absolute download URL, for display."""
        return f"https://{EMI_HOST}{self.path}"

    def local_path(self, data_dir: Path) -> Path:
        """Return where this capture lives under ``data_dir``."""
        return data_dir / self.role / f"{self.role}.txt.gz"


CAPTURES: Final = (
    Capture("functional", "S112825-v50.txt.gz", 4_735_308_661),
    Capture("stress", "S061226-v50.txt.gz", 17_894_268_560),
)
ROLES: Final = tuple(capture.role for capture in CAPTURES)


class DownloadError(Exception):
    """Raised when a capture cannot be downloaded or verified."""


@final
class Args(argparse.Namespace):
    """Typed view of the parsed command line."""

    # argparse keeps pre-set attributes, so these are the effective defaults.
    roles: Sequence[str] = ()
    data_dir: Path = DEFAULT_DATA_DIR
    force: bool = False


def log(message: str, end: str = "\n") -> None:
    """Write a status line to stderr."""
    _ = sys.stderr.write(message + end)
    _ = sys.stderr.flush()


def human(size: float) -> str:
    """Format a byte count with binary units."""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < KIB:
            return f"{size:.1f} {unit}"
        size /= KIB
    return f"{size:.1f} TiB"


def check_disk_space(target_dir: Path, needed: int) -> None:
    """Fail early if ``target_dir`` cannot hold ``needed`` more bytes."""
    free = shutil.disk_usage(target_dir).free
    if free < needed:
        msg = f"need {human(needed)} in {target_dir}, only {human(free)} free"
        raise DownloadError(msg)


def send_request(
    conn: http.client.HTTPSConnection,
    capture: Capture,
    offset: int,
) -> http.client.HTTPResponse:
    """Send a GET for ``capture``, asking for a byte range when ``offset`` > 0."""
    headers = {"User-Agent": USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    try:
        conn.request("GET", capture.path, headers=headers)
        return conn.getresponse()
    except (OSError, http.client.HTTPException) as exc:
        msg = f"{capture.remote_name}: {exc}"
        raise DownloadError(msg) from exc


def http_error(capture: Capture, response: http.client.HTTPResponse) -> DownloadError:
    """Build the error for a response that carries no usable body."""
    if response.status == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
        reason = "partial file exceeds server copy; use --force"
    else:
        reason = f"HTTP {response.status} {response.reason}"
    return DownloadError(f"{capture.remote_name}: {reason}")


def open_stream(
    conn: http.client.HTTPSConnection,
    capture: Capture,
    offset: int,
) -> tuple[http.client.HTTPResponse, int]:
    """Request ``capture`` from ``offset``; return the response and served offset."""
    response = send_request(conn, capture, offset)
    if response.status == HTTPStatus.PARTIAL_CONTENT:
        return response, offset
    if response.status == HTTPStatus.OK:
        return response, 0
    response.close()
    raise http_error(capture, response)


def stream_to_file(
    response: http.client.HTTPResponse,
    part_path: Path,
    offset: int,
    total: int,
) -> None:
    """Write ``response`` into ``part_path`` from ``offset``, reporting progress."""
    buf = bytearray(CHUNK_SIZE)
    view = memoryview(buf)
    received = offset
    start = last_report = time.monotonic()

    try:
        with response, part_path.open("r+b" if offset else "wb") as out:
            _ = out.seek(offset)
            _ = out.truncate()
            while n := response.readinto(buf):
                _ = out.write(view[:n])
                received += n
                now = time.monotonic()
                if now - last_report >= REPORT_INTERVAL_SECONDS:
                    last_report = now
                    rate = human((received - offset) / (now - start))
                    pct = 100.0 * received / total
                    done = f"{human(received)} / {human(total)}"
                    log(f"\r  {pct:5.1f}%  {done}  {rate}/s", end="")
    except (OSError, http.client.HTTPException) as exc:
        msg = f"{part_path.name}: transfer interrupted ({exc}); rerun to resume"
        raise DownloadError(msg) from exc
    finally:
        log("")


def is_complete(target: Path, capture: Capture, *, force: bool) -> bool:
    """Return True if ``target`` is already a complete download to keep."""
    if force or not target.exists():
        return False
    if target.stat().st_size == capture.size:
        return True
    msg = f"{target} has an unexpected size; use --force to replace it"
    raise DownloadError(msg)


def resume_offset(part_path: Path, size: int, *, force: bool) -> int:
    """Return the byte offset to resume from, discarding unusable partials."""
    if force:
        part_path.unlink(missing_ok=True)
    offset = part_path.stat().st_size if part_path.exists() else 0
    if offset > size:
        part_path.unlink()
        return 0
    return offset


def fetch(capture: Capture, target: Path, part_path: Path, offset: int) -> None:
    """Stream the rest of ``capture`` from ``offset`` into ``part_path``."""
    check_disk_space(target.parent, capture.size - offset)
    log(f"{capture.role}: {capture.url} -> {target} ({human(capture.size)})")
    if offset:
        log(f"  resuming at {human(offset)}")
    conn = http.client.HTTPSConnection(EMI_HOST, timeout=TIMEOUT_SECONDS)
    try:
        response, offset = open_stream(conn, capture, offset)
        stream_to_file(response, part_path, offset, capture.size)
    finally:
        conn.close()


def download(capture: Capture, data_dir: Path, *, force: bool) -> None:
    """Download ``capture`` into ``data_dir``, resuming any partial download."""
    target = capture.local_path(data_dir)
    part_path = target.with_name(target.name + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)

    if is_complete(target, capture, force=force):
        log(f"skip {capture.role}: {target} already complete")
        return

    offset = resume_offset(part_path, capture.size, force=force)
    if offset < capture.size:
        fetch(capture, target, part_path, offset)

    actual = part_path.stat().st_size
    if actual != capture.size:
        msg = f"{part_path}: {actual:,} bytes, expected {capture.size:,}; rerun"
        raise DownloadError(msg)
    _ = part_path.replace(target)
    log(f"  done: {target}")


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Parse the command line into :class:`Args`."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _ = parser.add_argument(
        "roles",
        nargs="*",
        choices=ROLES,
        metavar="ROLE",
        help=f"captures to download: {', '.join(ROLES)} (default: all)",
    )
    _ = parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="destination root (default: %(default)s)",
    )
    _ = parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="discard existing and partial files and download again",
    )
    return parser.parse_args(argv, namespace=Args())


def main(argv: Sequence[str] | None = None) -> int:
    """Download the requested captures; return a process exit code."""
    args = parse_args(argv)
    selected = [c for c in CAPTURES if not args.roles or c.role in args.roles]
    try:
        for capture in selected:
            download(capture, args.data_dir, force=args.force)
    except DownloadError as exc:
        log(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\ninterrupted; rerun to resume")
        sys.exit(130)

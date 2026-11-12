#!/usr/bin/env python3
"""Decompress Nasdaq TotalView-ITCH captures under data/ into sibling .bin files.

    data/functional/functional.txt.gz -> data/functional/functional.bin
    data/stress/stress.txt.gz         -> data/stress/stress.bin

Chunk size is derived from the host (RAM and the output filesystem's block size)
unless overridden with --chunk-mib.
"""

from __future__ import annotations

import argparse
import gzip
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

MIB = 1024 * 1024
MIN_CHUNK = 1 * MIB
MAX_CHUNK = 64 * MIB
RAM_FRACTION = 1024  # use ~0.1% of physical RAM per chunk
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"


def physical_ram_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def pick_chunk_size(output_dir: Path) -> int:
    ram = physical_ram_bytes()
    chunk = ram // RAM_FRACTION if ram else MIN_CHUNK
    chunk = max(MIN_CHUNK, min(chunk, MAX_CHUNK))
    block = max(os.stat(output_dir).st_blksize, 4096)
    return max(block, chunk - chunk % block)


def output_path_for(gz_path: Path) -> Path:
    # functional.txt.gz -> functional.bin
    return gz_path.with_name(
        gz_path.name.removesuffix(".gz").removesuffix(".txt") + ".bin"
    )


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def decompress(gz_path: Path, out_path: Path, chunk_size: int) -> None:
    total_in = gz_path.stat().st_size
    tmp_path = out_path.with_name(out_path.name + ".part")
    buf = bytearray(chunk_size)
    view = memoryview(buf)
    written = 0
    start = last_report = time.monotonic()

    try:
        # Buffered writer: unlike raw FileIO it never returns a short write.
        with open(gz_path, "rb", buffering=chunk_size) as raw, gzip.GzipFile(
            fileobj=raw
        ) as f_in, open(tmp_path, "wb", buffering=chunk_size) as f_out:
            while n := f_in.readinto(buf):
                _ = f_out.write(view[:n])
                written += n
                now = time.monotonic()
                if now - last_report >= 1.0:
                    last_report = now
                    pct = 100.0 * raw.tell() / total_in if total_in else 100.0
                    rate = written / (now - start)
                    print(
                        f"\r  {pct:5.1f}%  {human(written)} out  {human(rate)}/s",
                        end="",
                        file=sys.stderr,
                        flush=True,
                    )
        os.replace(tmp_path, out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    elapsed = time.monotonic() - start
    print(
        f"\r  done: {human(written)} in {elapsed:.1f}s -> {out_path}" + " " * 20,
        file=sys.stderr,
    )


class Args(argparse.Namespace):
    # argparse keeps pre-set attributes, so these are the effective defaults.
    paths: Sequence[Path] = ()
    data_dir: Path = DEFAULT_DATA_DIR
    chunk_mib: int | None = None
    force: bool = False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    _ = parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Specific .gz files to decompress (default: every *.gz under --data-dir)",
    )
    _ = parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Root to scan (default: %(default)s)",
    )
    _ = parser.add_argument(
        "--chunk-mib", type=int, help="Override the auto-detected chunk size, in MiB"
    )
    _ = parser.add_argument(
        "-f", "--force", action="store_true", help="Overwrite existing .bin files"
    )
    args = parser.parse_args(namespace=Args())

    if args.chunk_mib is not None and args.chunk_mib <= 0:
        parser.error("--chunk-mib must be positive")

    sources = args.paths or sorted(args.data_dir.rglob("*.gz"))
    if not sources:
        print(f"No .gz files found under {args.data_dir}", file=sys.stderr)
        return 1

    for gz_path in sources:
        out_path = output_path_for(gz_path)
        if out_path.exists() and not args.force:
            print(
                f"skip {gz_path} ({out_path.name} exists; use --force to overwrite)",
                file=sys.stderr,
            )
            continue
        chunk = (
            args.chunk_mib * MIB if args.chunk_mib else pick_chunk_size(out_path.parent)
        )
        print(
            f"{gz_path} ({human(gz_path.stat().st_size)}), chunk {human(chunk)}",
            file=sys.stderr,
        )
        decompress(gz_path, out_path, chunk)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

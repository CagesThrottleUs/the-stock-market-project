#!/usr/bin/env python3
"""Tell the story of a Nasdaq TotalView-ITCH 5.0 capture, one message at a time.

Walks a length-prefixed .bin capture made by scripts/decompress.py and writes one log
line per message to logs/<capture>.story.log (git-ignored). Only the message types
written down in scripts/README.md are decoded. The first message of any other type
stops the walk with an error naming the spec section to learn next. The log is
written either way.

    scripts/itch_story.py                          # data/functional/functional.bin
    scripts/itch_story.py data/stress/stress.bin
"""

from __future__ import annotations

import argparse
import mmap
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAPTURE = REPO_ROOT / "data" / "functional" / "functional.bin"
DEFAULT_LOG_DIR = REPO_ROOT / "logs"
SPEC = "docs/NQTVITCHSpecification.pdf"

FRAME_LENGTH_SIZE = 2  # every message is preceded by its length (big-endian)
HEADER_SIZE = 11  # Message Type, Stock Locate, Tracking Number, Timestamp

# Where each message type is described in the spec. Only used to point at what to learn next.
SPEC_SECTIONS = {
    "S": "1.1 System Event Message",
    "R": "1.2.1 Stock Directory",
    "H": "1.2.2 Stock Trading Action",
    "Y": "1.2.3 Reg SHO Short Sale Price Test Restricted Indicator",
    "L": "1.2.4 Market Participant Position",
    "V": "1.2.5 MWCB Decline Level",
    "W": "1.2.5 MWCB Status",
    "K": "1.2.6 Quoting Period Update",
    "J": "1.2.7 LULD Auction Collar",
    "h": "1.2.8 Operational Halt",
    "A": "1.3.1 Add Order - No MPID Attribution",
    "F": "1.3.2 Add Order with MPID Attribution",
    "E": "1.4.1 Order Executed",
    "C": "1.4.2 Order Executed With Price",
    "X": "1.4.3 Order Cancel",
    "D": "1.4.4 Order Delete",
    "U": "1.4.5 Order Replace",
    "P": "1.5.1 Trade Message (Non-Cross)",
    "Q": "1.5.2 Cross Trade",
    "B": "1.5.3 Broken Trade / Order Execution",
    "I": "1.6 Net Order Imbalance Indicator (NOII)",
    "N": "1.7 Retail Price Improvement Indicator (RPII)",
    "O": "1.8 Direct Listing with Capital Raise Price Discovery",
}

# System Event codes in the order they arrive during a day: (name, story).
SYSTEM_EVENTS = {
    "O": (
        "Start of Messages",
        "The feed opens. This is the first message of the trading day.",
    ),
    "S": (
        "Start of System hours",
        "Nasdaq is open and starts accepting orders.",
    ),
    "Q": (
        "Start of Market hours",
        "Regular market hours begin: market-hours orders can now execute.",
    ),
    "M": (
        "End of Market hours",
        "Regular market hours end: market-hours orders can no longer execute.",
    ),
    "E": (
        "End of System hours",
        (
            "Nasdaq is closed and accepts no new orders today. Broken Trade and Order "
            "Delete messages can still arrive."
        ),
    ),
    "C": (
        "End of Messages",
        "The feed closes. This is the last message of the trading day.",
    ),
}
DAILY_ORDER = list(SYSTEM_EVENTS)


class StoryError(Exception):
    """The capture contradicts what we have written down, or reaches something we haven't learnt yet."""


def read_be(buf: memoryview, offset: int, size: int) -> int:
    """Read an unsigned big-endian integer of `size` bytes.

    int.from_bytes(..., "big") reads the bytes in network order whatever the host's
    byte order (sys.byteorder) is, so no swap is needed. Single bytes and Alpha fields
    have no byte order, so they're never converted.
    """
    return int.from_bytes(buf[offset : offset + size], "big")


def read_alpha(buf: memoryview, offset: int, size: int) -> str:
    """Read an Alpha field: ASCII, left-justified and padded on the right with spaces."""
    return bytes(buf[offset : offset + size]).decode("ascii").rstrip(" ")


def format_timestamp(ns: int) -> str:
    seconds, nanos = divmod(ns, 1_000_000_000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{nanos:09d}"


def logfmt(**fields: object) -> str:
    """One `key=value` record per line, so the log reads as text and parses as data."""
    parts: list[str] = []
    for key, value in fields.items():
        text = str(value)
        if not text or any(c in text for c in ' "='):
            text = '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
        parts.append(f"{key}={text}")
    return " ".join(parts)


@dataclass(frozen=True, slots=True)
class Header:
    """The 11 bytes every ITCH 5.0 message starts with."""

    message_type: str  # offset 0, 1 byte
    stock_locate: (
        int  # offset 1, 2 bytes: index of the stock for today, 0 if not stock related
    )
    tracking_number: int  # offset 3, 2 bytes: Nasdaq internal tracking number
    timestamp_ns: int  # offset 5, 6 bytes: nanoseconds since midnight

    @classmethod
    def decode(cls, msg: memoryview) -> Header:
        return cls(
            message_type=chr(msg[0]),
            stock_locate=read_be(msg, 1, 2),
            tracking_number=read_be(msg, 3, 2),
            timestamp_ns=read_be(msg, 5, 6),
        )


class Story:
    """Decodes the message types we know and remembers what the day has shown so far."""

    def __init__(self) -> None:
        self.last_system_event: str | None = None
        self.tellers: dict[
            str, tuple[int, Callable[[Header, memoryview], dict[str, object]]]
        ] = {
            "S": (12, self.system_event),
        }

    def tell(self, header: Header, msg: memoryview) -> dict[str, object]:
        if header.message_type not in self.tellers:
            section = SPEC_SECTIONS.get(header.message_type, "not in the spec")
            raise StoryError(
                f"message type {header.message_type!r} isn't mapped yet. Read {SPEC} section "
                + f"'{section}', explain it, then add it to scripts/README.md and this script."
            )
        length, teller = self.tellers[header.message_type]
        if len(msg) != length:
            raise StoryError(
                f"a {header.message_type!r} message is {length} bytes, but this one is {len(msg)}"
            )
        return teller(header, msg)

    def system_event(self, header: Header, msg: memoryview) -> dict[str, object]:
        if header.stock_locate != 0:
            raise StoryError(
                f"a System Event's Stock Locate is always 0, got {header.stock_locate}"
            )
        code = read_alpha(msg, 11, 1)
        if code not in SYSTEM_EVENTS:
            raise StoryError(
                f"unknown System Event code {code!r}. Read {SPEC} section 1.1."
            )
        if self.last_system_event is not None and DAILY_ORDER.index(
            code
        ) <= DAILY_ORDER.index(self.last_system_event):
            day = " -> ".join(DAILY_ORDER)
            raise StoryError(
                f"System Event {code!r} arrived after {self.last_system_event!r}, but the day runs {day}"
            )
        self.last_system_event = code
        name, story = SYSTEM_EVENTS[code]
        return {"event": code, "story": f"{name}. {story}"}


def read_frame(buf: memoryview, pos: int) -> tuple[int, str | None]:
    """Read the length prefix at `pos`. Returns (message length, framing error or None)."""
    if pos + FRAME_LENGTH_SIZE > len(buf):
        return 0, "the file ends inside a length prefix"
    length = read_be(buf, pos, FRAME_LENGTH_SIZE)
    if length < HEADER_SIZE:
        return length, f"length {length} is shorter than the {HEADER_SIZE}-byte header"
    if pos + FRAME_LENGTH_SIZE + length > len(buf):
        return length, f"the {length}-byte message runs past the end of the file"
    return length, None


def tell_message(story: Story, msg: memoryview, pos: int, log: TextIO) -> str | None:
    """Log one message as a `message` record, or as an `error` record if the story can't tell it."""
    header = Header.decode(msg)
    common = {
        "offset": pos,
        "time": format_timestamp(header.timestamp_ns),
        "type": header.message_type,
        "locate": header.stock_locate,
        "tracking": header.tracking_number,
    }
    try:
        fields = story.tell(header, msg)
    except StoryError as error:
        record = logfmt(
            record="error",
            **common,
            length=len(msg),
            hex=bytes(msg).hex(" "),
            error=error,
        )
        _ = log.write(record + "\n")
        return str(error)
    _ = log.write(logfmt(record="message", **common, **fields) + "\n")
    return None


def walk(
    buf: memoryview, log: TextIO, limit: int | None
) -> tuple[int, Counter[str], str | None]:
    """Log every message until the end, the limit, or the first error. Returns (messages, counts, error)."""
    story = Story()
    counts: Counter[str] = Counter()
    max_messages = sys.maxsize if limit is None else limit
    pos = 0
    while pos < len(buf) and counts.total() < max_messages:
        length, error = read_frame(buf, pos)
        start = pos + FRAME_LENGTH_SIZE
        if error is not None:
            _ = log.write(logfmt(record="error", offset=pos, error=error) + "\n")
        else:
            error = tell_message(story, buf[start : start + length], pos, log)
        if error is not None:
            return counts.total(), counts, f"offset {pos}: {error}"
        counts[chr(buf[start])] += 1
        pos = start + length
    return counts.total(), counts, None


class Args(argparse.Namespace):
    # argparse keeps pre-set attributes, so these are the effective defaults.
    capture: Path = DEFAULT_CAPTURE
    log: Path | None = None
    limit: int | None = None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    _ = parser.add_argument(
        "capture",
        nargs="?",
        type=Path,
        default=DEFAULT_CAPTURE,
        help="Capture to walk (default: %(default)s)",
    )
    _ = parser.add_argument(
        "--log",
        type=Path,
        help=f"Log file (default: {DEFAULT_LOG_DIR}/<capture>.story.log)",
    )
    _ = parser.add_argument("--limit", type=int, help="Stop after this many messages")
    args = parser.parse_args(namespace=Args())
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")

    log_path = args.log or DEFAULT_LOG_DIR / f"{args.capture.stem}.story.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # mmap lets the OS page the capture in on demand instead of reading gigabytes into memory.
    with (
        open(args.capture, "rb") as capture,
        mmap.mmap(capture.fileno(), 0, access=mmap.ACCESS_READ) as mapped,
        open(log_path, "w", encoding="utf-8") as log,
    ):
        _ = log.write(
            logfmt(
                record="start",
                capture=args.capture,
                bytes=len(mapped),
                host_byte_order=sys.byteorder,
                itch_byte_order="big",
            )
            + "\n"
        )
        with memoryview(mapped) as buf:
            messages, counts, error = walk(buf, log, args.limit)
        _ = log.write(
            logfmt(
                record="summary",
                messages=messages,
                by_type=",".join(f"{t}:{n}" for t, n in sorted(counts.items()))
                or "none",
                stopped="error"
                if error
                else "limit"
                if args.limit == messages
                else "end",
            )
            + "\n"
        )

    print(f"{messages} messages told -> {log_path}", file=sys.stderr)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

# Scripts

| Script             | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `get_itch_data.py` | Download the Nasdaq ITCH captures into `data/`                          |
| `decompress.py`    | `data/**/*.gz` → sibling `.bin` files                                   |
| `itch_story.py`    | Walk a `.bin` capture and tell its story, one message per log line      |
| `pre-push.sh`      | Local quality gates, then `git push` (see the root README)              |

## `itch_story.py`: learning ITCH one message type at a time

```bash
scripts/itch_story.py                          # data/functional/functional.bin
scripts/itch_story.py data/stress/stress.bin
scripts/itch_story.py --limit 1000             # stop after 1000 messages
```

The script decodes only the message types written down in this file. The first message of any other type stops the
walk with an error that names the spec section to read next. The loop is:

1. Run the script. It stops at a message type we haven't learnt yet.
2. Read that section of `docs/NQTVITCHSpecification.pdf` and explain it in your own words.
3. Once that explanation is checked against the spec and the data, write it below and teach the script the type.

Each run writes `logs/<capture>.story.log` (git-ignored), including runs that stop with an error. Every line is one
[logfmt] record, so it reads as text and also parses as data:

```text
record=start capture=…/functional.bin bytes=11269366583 host_byte_order=little itch_byte_order=big
record=message offset=0 time=03:01:29.349046735 type=S locate=0 tracking=0 event=O story="Start of Messages. …"
record=error offset=14 time=03:05:04.453632235 type=R locate=1 tracking=0 length=39 hex="52 00 01 …" error="…"
record=summary messages=1 by_type=S:1 stopped=error
```

The capture is opened with `mmap`, so the OS pages it in as the walk reaches it instead of reading 10–40 GB into
memory.

## What we know so far

### Framing

The `.bin` files have no separator between messages. Each message is preceded by a 2-byte big-endian length, and the
next message starts right after it: `next = offset + 2 + length`. MoldUDP64 frames the messages inside each packet the
same way.

### Data types

- **Integers** are unsigned and big-endian (network byte order). Byte order only matters for integers of 2 or more
  bytes. Python's `int.from_bytes(b, "big")` reads them correctly on any host. In C++, `std::endian::native` tells you
  the host's byte order, and `std::byteswap` (C++23) converts a value when the host is little-endian (x86, Apple
  silicon).
- **Alpha** fields are ASCII, left-justified and padded on the right with spaces: think `std::array<char, N>`. They are
  sequences of single bytes, so they never need byte-order conversion.
- **Timestamps** are nanoseconds since midnight. Midnight is in New York time: in both captures the regular session
  opens (`Q`) at exactly 09:30:00.

### Common header (every message)

| Field           | Offset | Length | Type    | Meaning                                                                                  |
| --------------- | -----: | -----: | ------- | ---------------------------------------------------------------------------------------- |
| Message Type    |      0 |      1 | Alpha   | Which message this is                                                                    |
| Stock Locate    |      1 |      2 | Integer | Today's index of the stock, assigned from 1 by Stock Directory messages; 0 if not about a stock |
| Tracking Number |      3 |      2 | Integer | Nasdaq internal tracking number                                                          |
| Timestamp       |      5 |      6 | Integer | Nanoseconds since midnight (a 48-bit integer)                                            |

A locate code doesn't change during a day, but the same stock can get a different code on another day.

### `S`: System Event (spec 1.1, 12 bytes)

| Field      | Offset | Length | Type  | Notes                          |
| ---------- | -----: | -----: | ----- | ------------------------------ |
| Header     |      0 |     11 |       | Stock Locate is always 0       |
| Event Code |     11 |      1 | Alpha | One of the codes below         |

The event codes arrive in this order, once each per day:

| Code | Name                  | What it means                                                                                     |
| ---- | --------------------- | ------------------------------------------------------------------------------------------------- |
| `O`  | Start of Messages     | The feed opens. This is the first message of the day.                                             |
| `S`  | Start of System hours | Nasdaq is open and starts accepting orders. Pre-market trading runs from here until `Q`.          |
| `Q`  | Start of Market hours | Regular market hours begin: market-hours orders can now execute.                                  |
| `M`  | End of Market hours   | Regular market hours end: market-hours orders can no longer execute. Post-market runs until `E`.  |
| `E`  | End of System hours   | Nasdaq is closed and accepts no new orders today. Broken Trade and Order Delete messages can still arrive. |
| `C`  | End of Messages       | The feed closes. This is the last message of the day.                                             |

`M` is not a halt. Halts arrive as Stock Trading Action (`H`) messages. `M` doesn't delete orders either: every
deletion arrives as its own Order Delete (`D`) message.

When the events arrived in our captures (New York time):

| Capture                   | `O`      | `S`   | `Q`   | `M`   | `E`   | `C`   |
| ------------------------- | -------- | ----- | ----- | ----- | ----- | ----- |
| functional (`S112825`, Fri 2025-11-28) | 03:01:29 | 04:00 | 09:30 | 13:00 | 17:00 | 17:05 |
| stress (`S061226`, Fri 2026-06-12)     | 03:01:32 | 04:00 | 09:30 | 16:00 | 20:00 | 20:05 |

The functional day is the Friday after Thanksgiving, when US markets close early: `M` comes at 13:00 instead of 16:00,
and `E` at 17:00 instead of 20:00.

[logfmt]: https://brandur.org/logfmt

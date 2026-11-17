# Quant Engine

A from-scratch, low-latency **stock exchange simulator** written in modern C++ (C++23). It's a showcase of
high-performance systems engineering: every message on the hot path has to be decoded, matched, and reported within a
few hundred nanoseconds, with no heap allocation.

> **Status:** early development. The build, toolchain, and quality gates are in place. The engine components below
> haven't been implemented yet. See [CHANGELOG.md](CHANGELOG.md) for progress.

## Architecture

The system is a single pipeline with four stages:

```mermaid
flowchart LR
    A[Raw market data] --> B[Ingestion feed<br/>decode]
    B --> C[Transfer<br/>hand-off]
    C --> D[Matching engine<br/>order book]
    D --> E[Dissemination feed<br/>execution reports]
    E --> F[Participants]
```

| Component                     | Responsibility                                                        |
| ----------------------------- | --------------------------------------------------------------------- |
| **Market data ingestion**     | Decodes raw incoming market data messages into internal order events. |
| **Transfer system**           | Moves decoded messages from the ingestion feed to the engine core.    |
| **Matching engine core**      | Maintains the bid/ask order book and matches incoming orders.         |
| **Market data dissemination** | Publishes trade execution reports to market participants.             |

## Performance targets

These targets apply to the **end-to-end hot path** (ingestion → dissemination), measured in steady state **after
warmup**.

| Metric                       | Target                                 | How it is measured                                |
| ---------------------------- | -------------------------------------- | ------------------------------------------------- |
| Latency (p50 / p99 / p99.9)  | < 100 ns / < 250 ns / < 500 ns         | [Google Benchmark] or [nanobench]                 |
| Heap allocations             | 0 `malloc`/`free` and 0 `new`/`delete` | [Valgrind] (`memcheck` heap summary)              |
| Cache-miss rate              | < 1.0 %                                | `perf stat` (`cache-misses` / `cache-references`) |
| Instructions per cycle (IPC) | > 2.5                                  | `perf stat` (`instructions` / `cycles`)           |
| Branch misprediction rate    | < 0.5 %                                | `perf stat` (`branch-misses` / `branches`)        |

> `perf` and Valgrind are Linux tools, so the official numbers are captured on Linux. Development happens on macOS.

## Getting started

### Prerequisites

- CMake **≥ 4.3**
- [Ninja] (`brew install ninja`). Every preset uses it, because the Makefile generators don't support C++ modules.
- A C++23 compiler. The repository doesn't pin one: CMake picks the system default (AppleClang on macOS) unless you
  choose another one in a user preset (see below). The tooling is tested with Homebrew LLVM (`brew install llvm`).
- macOS: a working Xcode Command Line Tools install. The CMake configure step fails early with a fix-it hint if
  `xcode-select -p` or the SDK path is broken.

### Build and run

Builds are driven by [CMake presets][cmake-presets] in `CMakePresets.json`. Each preset builds into `build/<preset>`,
except the two analysis presets, which `scripts/pre-push.sh` owns and recreates in `.cmake-analysis-build/<preset>`:

```bash
cmake --preset release
cmake --build --preset release
./build/release/the_stock_market_project
```

| Preset           | Purpose                                                                |
| ---------------- | ---------------------------------------------------------------------- |
| `debug`          | Day-to-day development. clangd reads its `compile_commands.json`       |
| `release`        | Optimized build                                                        |
| `relwithdebinfo` | Optimized build with debug info (profiling)                            |
| `clang-tidy`     | Compilation database for clang-tidy (used by `scripts/pre-push.sh`)    |
| `scan-build`     | Clang Static Analyzer build (used by `scripts/pre-push.sh`)            |

`cmake --workflow --preset ci` configures and builds `debug` in one command. List everything with
`cmake --list-presets=all`.

### Choosing your compiler (user presets)

Machine-specific settings go in a git-ignored `CMakeUserPresets.json` that inherits the shared presets, never in a
tracked file. Start from the template:

```bash
cp CMakeUserPresets.json.example CMakeUserPresets.json   # edit paths for your machine
cmake --preset llvm-debug
cmake --build --preset llvm-debug
```

The template shows how to set the compiler, a compiler launcher (ccache) and a custom build directory. CLion and the
VS Code CMake Tools extension pick up both files automatically.

A build directory remembers the compiler it was first configured with. After changing compilers, reconfigure from
scratch with `cmake --preset <name> --fresh`.

> Don't set `CMAKE_C_COMPILER`/`CMAKE_CXX_COMPILER` on the `scan-build` preset or anything it inherits. scan-build
> selects the compiler through `CC`/`CXX`, and an explicit compiler bypasses it, so the analyzer silently checks
> nothing.

## Code quality

The repository ships strict, opinionated tooling configuration:

| Tool                                   | Config                | Purpose                                                      |
| -------------------------------------- | --------------------- | ------------------------------------------------------------ |
| [clang-format]                         | `.clang-format`       | Consistent formatting                                        |
| [clang-tidy]                           | `.clang-tidy`         | Lints (bugprone, performance, modernize, Core Guidelines, …) |
| [clangd]                               | `.clangd`             | IDE diagnostics with `-Weverything -Werror`                  |
| [Clang Static Analyzer] (`scan-build`) | `scripts/pre-push.sh` | Path-sensitive bug finding                                   |
| [CodeScene] (`cs delta`)               | n/a                   | Code Health regression check against the base branch         |

`scripts/pre-push.sh` runs every gate and then calls `git push`. It isn't installed as a git hook, so run it directly or
through an alias:

```bash
git config alias.checked-push '!scripts/pre-push.sh'

git checked-push                 # run all gates, push only if they pass
git checked-push --no-push       # run the gates without pushing
git checked-push --push-on-fail  # push even if a gate fails
git checked-push --preset llvm-debug  # use the compilers of one of your presets
```

The gates build with the compilers CMake resolves for a configure preset: `debug` (CMake's default compiler) unless you
pass `--preset <name>` or set `PRE_PUSH_PRESET`, usually to one of your user presets. `CC`/`CXX` in the environment
override the preset. clang-tidy and clang-format are taken from the same LLVM install as the compiler when available.
Run `scripts/pre-push.sh --help` for all overrides (`CC`, `CXX`, `CLANG_FORMAT`, `CLANG_TIDY`, `CS_DELTA_BASE`).

## Project layout

```text
.
├── CMakeLists.txt           # Build definition (C++23, macOS SDK sanity checks)
├── CMakePresets.json        # Shared build presets (Ninja, build/<preset>)
├── CMakeUserPresets.json.example # Template for your git-ignored CMakeUserPresets.json
├── main.cpp                 # Entry point (placeholder)
├── scripts/pre-push.sh      # Local quality gates + git push
├── scripts/get_itch_data.py # Download Nasdaq ITCH captures into data/
├── scripts/decompress.py    # data/**/*.gz -> sibling .bin (Nasdaq ITCH captures)
├── .clang-format            # Formatting rules
├── .clang-tidy              # Lint rules
├── .clangd                  # Language-server flags
└── CHANGELOG.md             # Project journal
```

[Google Benchmark]: https://github.com/google/benchmark
[Ninja]: https://ninja-build.org/
[cmake-presets]: https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html
[nanobench]: https://github.com/martinus/nanobench
[Valgrind]: https://valgrind.org/
[clang-format]: https://clang.llvm.org/docs/ClangFormat.html
[clang-tidy]: https://clang.llvm.org/extra/clang-tidy/
[clangd]: https://clangd.llvm.org/
[Clang Static Analyzer]: https://clang-analyzer.llvm.org/
[CodeScene]: https://codescene.com/

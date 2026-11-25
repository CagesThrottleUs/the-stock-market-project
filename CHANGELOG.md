# CHANGELOG

This document is the one that would act as a marker for history of the changes that have been introduced to the project.
The core goal is communication of this project as a lifetime.

## 2026-11-25

Where LLVM lives on a machine now comes from the user preset's `CMAKE_PREFIX_PATH`, not from shell exports (#9).
Homebrew's llvm caveats suggest exporting `LDFLAGS`, `CPPFLAGS` and `CMAKE_PREFIX_PATH`. CMake copied the `LDFLAGS` into
each build directory's cache on its first configure, ignored `CPPFLAGS` altogether, and the project needed none of them.
The first configure now warns when shell flags are about to be stored in the cache.

`CMakeLists.txt` finds `clang-format`, `clang-tidy` and `scan-build` with `find_program`. It searches
`CMAKE_PREFIX_PATH` first, then the compiler's directory, then `PATH`. `scripts/pre-push.sh` uses whatever CMake found
for the chosen preset. Before this, scan-build always came from `PATH` and could be a different LLVM version from the
compiler.

Found along the way for #11: Homebrew clang can't locate its own `libc++.modules.json`, so `import std` will need
`CMAKE_CXX_STDLIB_MODULES_JSON`.

## 2026-11-17

Builds now go through CMake presets (#20). `CMakePresets.json` holds the shared Ninja presets (`debug`, `release`,
`relwithdebinfo`, `clang-tidy`, `scan-build` and a `ci` workflow) that build into `build/<preset>`. Machine-specific
choices, such as which compiler to use, live in a git-ignored `CMakeUserPresets.json` started from
`CMakeUserPresets.json.example`.

The hardcoded Homebrew compiler paths are gone from `CMakeLists.txt`. Setting them after `project()` had quietly
disabled the scan-build gate: it reported "No bugs found" even with a planted null dereference. The gate catches it
again. `scripts/pre-push.sh` now uses the same presets as everyone else and takes its compilers from a preset
(`--preset` / `PRE_PUSH_PRESET`) instead of hardcoded paths.

The warning policy (`-Weverything` as errors, `-std=c++23`) moved from `.clangd` into `CMakeLists.txt`. Until now
only the editor enforced it; the build, clang-tidy and scan-build never saw it. clangd picks the flags up from the
compilation database of whichever preset you point it at.

## 2026-11-12

Added a full automation of downloading and decompression of the market data downloaded from the EMI server - which would
allow me to repeat this later on a new system without worrying about finding and downloading from alternate sources.

Post this automation - I am going to spend time on actually building the architecture and understanding how to build the
proper solution that passes the functional test.

## 2026-11-08

The README.md has been updated to current state where we have pointed out what we currently have in the project itself.

Next important task is to get the relevant market data and specifications on what these data are guaranteed to do - on
whose basis we will have to create the system architecture.

Data is being downloaded from: [EMI Server](https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/) and I have downloaded two of the
many - `S112825-v50.txt.gz` for Normal testing and `S061226-v50.txt.gz` for stress testing.

I have also added the document architecture that I am going to use to build more of the project.

## 2026-11-07

I have completed issue #3 of the project. This issue primarily involved understanding the different tools that a project
can use in their work. It was a good way of using AI as well to learn more on how to question and expand my own
understanding and learning by doing and actually challenging and creating more friction and trying to overcome that.

The tools that have been initially selected for the job is - clang-format, clang-tidy, clang static analyzer, clangd. I
also searched on CodeScene, Repowise, SonarQube, Doxygen & MrDocs.

A key thing that I have noticed is that I am actually not moving forward with actually creating and completing a quant
project and optimizing the repository for the core goal of having Quant information. Learning by doing is what matters
the most and I have been skipping that. I will lock in the README.md next and we will have a full idea where to go next
and what the challenge is going to be.

## 2026-09-17

Today marks the day that the project was created and we are moving forward to build. For this we are going to create a
new build that is basically Hello World.

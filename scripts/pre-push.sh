#!/usr/bin/env bash
#
# Runs local quality gates and then forwards remaining arguments to `git push`.
# This is intentionally NOT installed as a git hook; invoke it directly or via an alias:
#   git config alias.checked-push '!scripts/pre-push.sh'
#   git checked-push [--preset NAME] [--push-on-fail] [--no-push] [--] [git push args...]
#
# Gates: clang-format, clang-tidy, Clang Static Analyzer (scan-build), CodeScene (cs delta).
# A missing CLI always aborts (exit 127), even with --push-on-fail.

set -uo pipefail

usage() {
  cat <<USAGE
Usage: scripts/pre-push.sh [options] [--] [git push args...]

Options:
  --preset NAME    Configure preset whose compilers the checks use, typically one from your
                   CMakeUserPresets.json (env: PRE_PUSH_PRESET; default: debug, i.e. CMake's default compiler).
  --push-on-fail   Push even if a check fails (env: PUSH_ON_FAIL=1). Missing tools still abort.
  --no-push        Run checks only; do not invoke git push.
  -h, --help       Show this help.

Any other argument is forwarded verbatim to 'git push'.

Environment overrides:
  CC, CXX                 Compilers for clang-tidy and scan-build (override the preset's compilers)
  CLANG_FORMAT, CLANG_TIDY Tool binaries (default: next to \$CC, else from PATH)
  CS_DELTA_BASE           Git ref CodeScene compares against (default: merge-base with origin's default branch)
USAGE
}

PUSH_ON_FAIL="${PUSH_ON_FAIL:-0}"
PRESET="${PRE_PUSH_PRESET:-debug}"
DO_PUSH=1
GIT_PUSH_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --push-on-fail) PUSH_ON_FAIL=1 ;;
    --no-push) DO_PUSH=0 ;;
    --preset)
      if [ $# -lt 2 ]; then echo "❌ --preset needs a preset name." >&2; exit 2; fi
      PRESET="$2"; shift ;;
    --preset=*) PRESET="${1#--preset=}" ;;
    -h | --help) usage; exit 0 ;;
    --) shift; GIT_PUSH_ARGS+=("$@"); break ;;
    *) GIT_PUSH_ARGS+=("$1") ;;
  esac
  shift
done

REPO_ROOT="$(git rev-parse --show-toplevel)" || exit 1
cd "$REPO_ROOT" || exit 1

# Must match the binaryDir of the clang-tidy / scan-build presets in CMakePresets.json.
# Kept out of build/ so deleting them never touches a directory an IDE (e.g. a CLion preset profile) uses.
ANALYSIS_DIR=".cmake-analysis-build"
SCAN_BUILD_DIR="$ANALYSIS_DIR/scan-build"
TIDY_BUILD_DIR="$ANALYSIS_DIR/clang-tidy"

# Compilers: CC/CXX from the environment win; otherwise use the compilers CMake resolves for $PRESET.
# The preset is configured into a scratch directory and the result read back from its cache, so
# inherits, macros and toolchain files resolve exactly as in a normal build (no JSON parsing here).
read_cache_var() { sed -n "s/^$1:[A-Z]*=//p" "$2"; }
COMPILER_SOURCE="CC/CXX environment"
if [ -z "${CC:-}" ] || [ -z "${CXX:-}" ]; then
  COMPILER_SOURCE="preset '$PRESET' (CC/CXX environment overrides)"
  if ! command -v cmake >/dev/null 2>&1; then
    echo "❌ cmake is not installed or not on PATH (cannot be bypassed with --push-on-fail)."
    exit 127
  fi
  PROBE_DIR="$ANALYSIS_DIR/preset-probe"
  rm -rf "$PROBE_DIR"
  if ! cmake --preset "$PRESET" -B "$PROBE_DIR" >/dev/null; then
    echo "❌ Could not configure preset '$PRESET' to find its compilers. List presets: cmake --list-presets"
    exit 2
  fi
  CC="${CC:-$(read_cache_var CMAKE_C_COMPILER "$PROBE_DIR/CMakeCache.txt")}"
  CXX="${CXX:-$(read_cache_var CMAKE_CXX_COMPILER "$PROBE_DIR/CMakeCache.txt")}"
  rm -rf "$PROBE_DIR"
fi
echo "🔧 Compilers from $COMPILER_SOURCE: CC=$CC CXX=$CXX"

# Prefer tools from the same LLVM install as the compiler to avoid version skew.
LLVM_BIN_DIR="$(dirname "$CC")"
default_llvm_tool() {
  if [ -x "$LLVM_BIN_DIR/$1" ]; then echo "$LLVM_BIN_DIR/$1"; else echo "$1"; fi
}
CLANG_FORMAT="${CLANG_FORMAT:-$(default_llvm_tool clang-format)}"
CLANG_TIDY="${CLANG_TIDY:-$(default_llvm_tool clang-tidy)}"
CODESCENE="${CODESCENE:-cs}"
export CS_DISABLE_VERSION_CHECK="${CS_DISABLE_VERSION_CHECK:-1}"

##############################
#### Required tools check ####
##############################

missing=()
for tool in "$CC" "$CXX" cmake ninja scan-build "$CLANG_FORMAT" "$CLANG_TIDY" "$CODESCENE"; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "❌ Required CLI tool(s) not installed or not on PATH:"
  printf '   - %s\n' "${missing[@]}"
  echo "   Install them before pushing (this cannot be bypassed with --push-on-fail)."
  exit 127
fi

SOURCES=()
while IFS= read -r -d '' file; do
  SOURCES+=("$file")
done < <(git ls-files -z -- '*.c' '*.cc' '*.cpp' '*.cxx' '*.h' '*.hh' '*.hpp' '*.hxx')

FAILED=()

#######################
#### clang-format  ####
#######################

run_clang_format() {
  echo "🎨 Running clang-format ($CLANG_FORMAT)..."
  if [ ${#SOURCES[@]} -eq 0 ]; then echo "   No C/C++ sources tracked; skipping."; return 0; fi
  if ! "$CLANG_FORMAT" --dry-run --Werror "${SOURCES[@]}"; then
    echo "❌ clang-format found unformatted files. Fix with:"
    echo "   $CLANG_FORMAT -i ${SOURCES[*]}"
    return 1
  fi
  echo "✅ clang-format passed."
}

#####################
#### clang-tidy  ####
#####################

run_clang_tidy() {
  echo "🧹 Running clang-tidy ($CLANG_TIDY)..."
  local tidy_sources=()
  local file
  for file in "${SOURCES[@]+"${SOURCES[@]}"}"; do
    case "$file" in *.c | *.cc | *.cpp | *.cxx) tidy_sources+=("$file") ;; esac
  done
  if [ ${#tidy_sources[@]} -eq 0 ]; then echo "   No translation units tracked; skipping."; return 0; fi

  rm -rf "$TIDY_BUILD_DIR"
  if ! cmake --preset clang-tidy \
    -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" >/dev/null; then
    echo "❌ CMake configure for clang-tidy failed."
    return 1
  fi
  # Ninja enables C++ module scanning, so compile commands reference @<obj>.modmap files that only
  # exist after a build. clang-tidy fails with "no such file or directory" without this step.
  if ! cmake --build --preset clang-tidy >/dev/null; then
    echo "❌ Build for clang-tidy failed."
    return 1
  fi
  if ! "$CLANG_TIDY" -p "$TIDY_BUILD_DIR" --quiet --warnings-as-errors='*' "${tidy_sources[@]}"; then
    echo "❌ clang-tidy reported issues."
    return 1
  fi
  echo "✅ clang-tidy passed."
}

#####################################
#### Clang Static Analyzer Block ####
#####################################

run_scan_build() {
  echo "🔍 Running Clang Static Analysis..."
  echo "   CC  -> $CC"
  echo "   CXX -> $CXX"

  # Never pass -DCMAKE_<LANG>_COMPILER here: scan-build selects the compiler through CC/CXX,
  # and an explicit compiler bypasses its interceptors so nothing gets analysed.
  rm -rf "$SCAN_BUILD_DIR"

  if ! scan-build \
    --use-cc="$CC" \
    --use-c++="$CXX" \
    cmake --preset scan-build; then
    echo "❌ CMake configure for scan-build failed."
    return 1
  fi

  # --status-bugs forces a non-zero exit code if bugs are found
  if ! scan-build \
    --use-cc="$CC" \
    --use-c++="$CXX" \
    -enable-checker optin.performance.Padding \
    -enable-checker cplusplus.Move \
    -enable-checker cplusplus.InnerPointer \
    -enable-checker unix.BlockInCriticalSection \
    -enable-checker alpha.cplusplus.InvalidatedIterator \
    -enable-checker alpha.cplusplus.UseAfterLifetimeEnd \
    -enable-checker optin.cplusplus.UninitializedObject \
    -enable-checker optin.core.EnumCastOutOfRange \
    -enable-checker security.ArrayBound \
    -enable-checker security.PointerSub \
    -enable-checker optin.taint.TaintedAlloc \
    -enable-checker optin.taint.TaintedDiv \
    -enable-checker security.FloatLoopCounter \
    --status-bugs \
    -o "$SCAN_BUILD_DIR/reports" \
    cmake --build --preset scan-build; then

    echo "❌ Clang Static Analyzer found bugs."
    local report_path
    report_path=$(find "$SCAN_BUILD_DIR/reports" -name "index.html" 2>/dev/null | head -n 1)
    if [ -n "$report_path" ]; then
      echo "📊 View the interactive complex bug path report here:"
      echo "   open $report_path"
    fi
    return 1
  fi
  echo "✅ Static analysis passed."
}

###################
#### CodeScene ####
###################

resolve_cs_base() {
  if [ -n "${CS_DELTA_BASE:-}" ]; then echo "$CS_DELTA_BASE"; return 0; fi
  local default_ref candidate
  default_ref="$(git symbolic-ref -q refs/remotes/origin/HEAD 2>/dev/null)"
  for candidate in "$default_ref" refs/remotes/origin/main refs/remotes/origin/master; do
    if [ -n "$candidate" ] && git rev-parse --verify -q "$candidate" >/dev/null; then
      git merge-base HEAD "$candidate"
      return $?
    fi
  done
  return 1
}

run_codescene() {
  echo "🩺 Running CodeScene delta analysis ($CODESCENE)..."
  local base
  if ! base="$(resolve_cs_base)" || [ -z "$base" ]; then
    echo "❌ Could not determine a base ref for CodeScene. Set CS_DELTA_BASE=<ref>."
    return 1
  fi
  echo "   Comparing against $base"
  if ! "$CODESCENE" delta "$base" --error-on-warnings; then
    echo "❌ CodeScene reported Code Health findings."
    return 1
  fi
  echo "✅ CodeScene passed."
}

##################
#### Run all  ####
##################

run_clang_format || FAILED+=("clang-format")
run_clang_tidy || FAILED+=("clang-tidy")
run_scan_build || FAILED+=("scan-build")
run_codescene || FAILED+=("codescene")

echo
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "❌ Failed checks: ${FAILED[*]}"
  if [ "$PUSH_ON_FAIL" != "1" ]; then
    echo "   Push blocked. Re-run with --push-on-fail to push anyway."
    exit 1
  fi
  echo "⚠️  --push-on-fail set; pushing despite failures."
else
  echo "✅ All checks passed!"
fi

if [ "$DO_PUSH" -eq 0 ]; then
  echo "ℹ️  --no-push set; skipping git push."
  [ ${#FAILED[@]} -eq 0 ]
  exit $?
fi

echo "🚀 git push ${GIT_PUSH_ARGS[*]+"${GIT_PUSH_ARGS[*]}"}"
exec git push "${GIT_PUSH_ARGS[@]+"${GIT_PUSH_ARGS[@]}"}"

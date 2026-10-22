#!/usr/bin/env bash

# Exit immediately if any command fails
set -e

# Parameterize compilers (uses CC/CXX env vars if set, otherwise falls back to Homebrew LLVM paths)
CC="${CC:-/opt/homebrew/opt/llvm/bin/clang}"
CXX="${CXX:-/opt/homebrew/opt/llvm/bin/clang++}"

#####################################
#### Clang Static Analyzer Block ####
#####################################

echo "🔍 Running pre-push Clang Static Analysis..."
echo "   CC  -> $CC"
echo "   CXX -> $CXX"

# 1. Create a dedicated analysis build directory to avoid messing up your IDE's cmake-build-debug
ANALYSIS_DIR=".cmake-analysis-build"
rm -rf "$ANALYSIS_DIR"
mkdir -p "$ANALYSIS_DIR"

# 2. Configure CMake using scan-build and parameterized compiler paths
scan-build \
  --use-cc="$CC" \
  --use-c++="$CXX" \
  cmake -DCMAKE_BUILD_TYPE=Debug -S . -B "$ANALYSIS_DIR"

# 3. Execute the full analysis build
# The --status-bugs flag forces a non-zero exit code if bugs are found, which halts the git push
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
  -o "$ANALYSIS_DIR/reports" \
  cmake --build "$ANALYSIS_DIR"; then

  echo "❌ Git push blocked! Clang Static Analyzer found bugs."
  # Find the generated index.html file path
  REPORT_PATH=$(find "$ANALYSIS_DIR/reports" -name "index.html" | head -n 1)
  if [ -n "$REPORT_PATH" ]; then
    echo "📊 View the interactive complex bug path report here:"
    echo "   open $REPORT_PATH"
  fi
  exit 1
fi

echo "✅ Static analysis passed! Proceeding with push..."
exit 0
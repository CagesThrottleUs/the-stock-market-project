cmake_minimum_required(VERSION 4.3)

# Should fix Issue #2 
if (APPLE)
    execute_process(
            COMMAND xcode-select -p
            OUTPUT_VARIABLE OSX_DEVELOPEMENT_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE OSX_DEVELOPEMENT_DIR_RESULT
    )
    if (NOT OSX_DEVELOPEMENT_DIR_RESULT EQUAL 0 OR NOT EXISTS "${OSX_DEVELOPEMENT_DIR}")
        message(FATAL_ERROR "Active Xcode developer directory is missing or broken (`xcode-select -p` -> '${OSX_DEVELOPEMENT_DIR}'). Fix: sudo xcode-select -switch /Library/Developer/CommandLineTools")
    endif ()

    execute_process(
            COMMAND xcrun --show-sdk-path
            OUTPUT_VARIABLE OSX_SDK_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE OSX_SDK_DIR_RESULT
    )
    if (NOT OSX_SDK_DIR_RESULT EQUAL 0 OR NOT EXISTS "${OSX_SDK_DIR}")
        message(FATAL_ERROR "macOS SDK path is missing or broken (`xcrun --show-sdk-path` -> '${OSX_SDK_DIR}'), likely from active developer directory '${OSX_DEVELOPEMENT_DIR}' not matching an installed SDK after an OS/Xcode upgrade. Fix: sudo xcode-select -switch /Library/Developer/CommandLineTools")
    endif ()

    if (NOT CMAKE_OSX_SYSROOT)
        set(CMAKE_OSX_SYSROOT "macosx" CACHE STRING "Platform SDK root navigation")
    endif ()
endif ()

# CMake copies these shell variables into the cache on the first configure only, so build directories made from
# different shells silently differ (Homebrew's llvm caveats suggest exporting LDFLAGS). Issue #9.
if (NOT DEFINED CACHE{CMAKE_EXE_LINKER_FLAGS})
    set(LEAKED_FLAG_VARS "")
    foreach (flag_var IN ITEMS CFLAGS CXXFLAGS LDFLAGS)
        if (NOT "$ENV{${flag_var}}" STREQUAL "")
            list(APPEND LEAKED_FLAG_VARS "${flag_var}='$ENV{${flag_var}}'")
        endif ()
    endforeach ()
    if (LEAKED_FLAG_VARS)
        list(JOIN LEAKED_FLAG_VARS ", " LEAKED_FLAG_VARS)
        message(WARNING "Shell variables ${LEAKED_FLAG_VARS} are being stored in this build's cache. The project needs "
                "none of them. Unset them in your shell, put flags you really want in your CMakeUserPresets.json, and "
                "reconfigure with --fresh. Tell CMake where LLVM lives with CMAKE_PREFIX_PATH instead (see README).")
    endif ()
endif ()

project(the_stock_market_project)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# -std=c++23 rather than -std=gnu++23
set(CMAKE_CXX_EXTENSIONS OFF)

# Clang tools for scripts/pre-push.sh, which reads these cache entries. find_program searches the bin/ directory of
# each CMAKE_PREFIX_PATH entry first (set it in your user preset), then the compiler's directory, then PATH, so every
# gate runs from the same LLVM install.
cmake_path(GET CMAKE_CXX_COMPILER PARENT_PATH CXX_COMPILER_DIR)
find_program(CLANG_FORMAT_EXECUTABLE clang-format HINTS "${CXX_COMPILER_DIR}")
find_program(CLANG_TIDY_EXECUTABLE clang-tidy HINTS "${CXX_COMPILER_DIR}")
find_program(SCAN_BUILD_EXECUTABLE scan-build HINTS "${CXX_COMPILER_DIR}")

# Project warning policy. Link it into every first-party target; third-party code must not inherit it.
# -Weverything is Clang-only; GCC gets the closest common set.
add_library(the_stock_market_project_warnings INTERFACE)
target_compile_options(the_stock_market_project_warnings INTERFACE
        $<$<CXX_COMPILER_ID:Clang,AppleClang>:-Weverything -Wno-c++98-compat -Wno-c++98-compat-pedantic -Wno-switch-default>
        $<$<CXX_COMPILER_ID:GNU>:-Wall -Wextra -Wpedantic>
)

add_executable(the_stock_market_project main.cpp)
target_link_libraries(the_stock_market_project PRIVATE the_stock_market_project_warnings)
# Adds -Werror; override locally with `cmake --compile-no-warning-as-error`.
set_target_properties(the_stock_market_project PROPERTIES COMPILE_WARNING_AS_ERROR ON)

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

project(the_stock_market_project)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# -std=c++23 rather than -std=gnu++23
set(CMAKE_CXX_EXTENSIONS OFF)

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

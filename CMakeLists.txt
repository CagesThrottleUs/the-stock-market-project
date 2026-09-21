cmake_minimum_required(VERSION 4.3)

# Should fix Issue #2 
if(APPLE)
    execute_process(
        COMMAND xcode-select -p
        OUTPUT_VARIABLE OSX_DEVELOPEMENT_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE OSX_DEVELOPEMENT_DIR_RESULT
    )
    if(NOT OSX_DEVELOPEMENT_DIR_RESULT EQUAL 0 OR NOT EXISTS "${OSX_DEVELOPEMENT_DIR}")
        message(FATAL_ERROR "Active Xcode developer directory is missing or broken (`xcode-select -p` -> '${OSX_DEVELOPEMENT_DIR}'). Fix: sudo xcode-select -switch /Library/Developer/CommandLineTools")
    endif()

    execute_process(
        COMMAND xcrun --show-sdk-path
        OUTPUT_VARIABLE OSX_SDK_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE OSX_SDK_DIR_RESULT
    )
    if(NOT OSX_SDK_DIR_RESULT EQUAL 0 OR NOT EXISTS "${OSX_SDK_DIR}")
        message(FATAL_ERROR "macOS SDK path is missing or broken (`xcrun --show-sdk-path` -> '${OSX_SDK_DIR}'), likely from active developer directory '${OSX_DEVELOPEMENT_DIR}' not matching an installed SDK after an OS/Xcode upgrade. Fix: sudo xcode-select -switch /Library/Developer/CommandLineTools")
    endif()

    if(NOT CMAKE_OSX_SYSROOT)
        set(CMAKE_OSX_SYSROOT "macosx" CACHE STRING "Platform SDK root navigation")
    endif()
endif()

project(the_stock_market_project)

set(CMAKE_CXX_STANDARD 23)

# TODO: Remove this in favour of Independent Toolchain as used by users
set(CMAKE_C_COMPILER /opt/homebrew/opt/llvm/bin/clang)
set(CMAKE_CXX_COMPILER /opt/homebrew/opt/llvm/bin/clang++)

add_executable(the_stock_market_project main.cpp)

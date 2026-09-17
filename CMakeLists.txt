cmake_minimum_required(VERSION 4.3)
project(the_stock_market_project)

set(CMAKE_CXX_STANDARD 23)

# TODO: This only worked because I had to run on the terminal:
#       sudo xcode-select -switch /Library/Developer/CommandLineTools
#       this should be considered a BUG as it should be automatically handled.
# Issue #2

set(CMAKE_C_COMPILER /opt/homebrew/opt/llvm/bin/clang)
set(CMAKE_CXX_COMPILER /opt/homebrew/opt/llvm/bin/clang++)

add_executable(the_stock_market_project main.cpp)

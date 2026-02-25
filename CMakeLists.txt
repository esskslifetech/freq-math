cmake_minimum_required(VERSION 3.12)
project(FreqMath)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Python and pybind11
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)

# Add C++ library
add_library(freq_math_cpp SHARED
    src/cpp/equation_parser.cpp
    src/cpp/math_evaluator.cpp
    src/cpp/audio_mapper.cpp
)

target_include_directories(freq_math_cpp PUBLIC include)

# Create Python module
pybind11_add_module(freq_math_bindings
    src/cpp/bindings.cpp
)

target_link_libraries(freq_math_bindings PRIVATE freq_math_cpp)

# Set output directory
set_target_properties(freq_math_bindings PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/src/python
)

# Freq-Math Test Suite

This directory contains comprehensive test files for the Freq-Math project.

## Test Files

### Core Component Tests

- **`test_freq_math_calculator.py`** - Tests for the refactored FreqMathCalculator
  - Equation preprocessing and compilation
  - Math parameter handling
  - Audio generation pipeline
  - Security validation
  - Integration with audio synthesis

- **`test_math_evaluator_updated.py`** - Updated tests for math evaluation functionality
  - Basic arithmetic operations
  - Trigonometric functions
  - Variable and constant handling
  - Complex expressions
  - Unicode operator normalization
  - Implicit multiplication
  - Error handling

- **`test_audio_synthesizer_updated.py`** - Updated tests for the refactored audio synthesizer
  - DSP operations and effects
  - Tone generation with various waveforms
  - Signal mixing and processing
  - PCM rendering and playback
  - Configuration validation

### C++ Binding Tests

- **`test_equation_parser.py`** - Tests for C++ equation parser bindings
  - Basic arithmetic parsing
  - Trigonometric function parsing
  - Variable and constant handling
  - Error handling

- **`test_math_evaluator_cpp.py`** - Tests for C++ math evaluator bindings
  - Interface validation
  - Compilation and evaluation methods

- **`test_audio_mapper.py`** - Tests for C++ audio mapper bindings
  - Interface validation
  - Audio mapping methods

### Integration Tests

- **`test_integration.py`** - End-to-end integration tests
  - Complete math-to-audio pipeline
  - Complex equation processing
  - Custom parameter usage
  - Polyphonic chord generation
  - Performance characteristics
  - File output integration

### Application Tests

- **`test_main.py`** - Tests for main.py entry point
  - Import functionality
  - Command-line argument handling
  - Error handling
  - Complex equation processing

- **`test_examples.py`** - Tests for example scripts
  - Basic usage example
  - Demo script functionality
  - Output file generation

### Legacy Tests

- **`test_math_evaluator.py`** - Original math evaluator tests (backward compatibility)
- **`test_audio_synthesizer.py`** - Original audio synthesizer tests (backward compatibility)

## Test Runner

- **`run_all_tests.py`** - Comprehensive test runner
  - Discovers and runs all test files
  - Provides detailed reporting
  - Supports running specific tests
  - Handles test discovery errors gracefully

## Usage

### Run All Tests
```bash
make test-all
# or
cd tests && python3 run_all_tests.py
```

### Run Specific Test Categories
```bash
make test-math          # Math evaluator tests
make test-audio         # Audio synthesizer tests
make test-integration     # Integration tests
make test-main          # Main entry point tests
make test-examples       # Example tests
make test-cpp           # C++ binding tests
```

### Run Specific Test
```bash
make test-specific TEST_NAME=test_math_evaluator_updated
# or
cd tests && python3 run_all_tests.py TestMathEvaluatorUpdated
```

### Development Workflow
```bash
make dev-test           # Build and run all tests
make dev-quick          # Build and run quick tests
make coverage           # Run tests with coverage report
```

## Test Coverage

The test suite covers:

- ✅ **Mathematical Expression Processing**
  - Equation parsing and preprocessing
  - Variable substitution and parameter handling
  - Security validation and error handling
  - Unicode and implicit multiplication support

- ✅ **Audio Synthesis**
  - DSP operations and effects
  - Multi-waveform generation
  - Signal mixing and processing
  - PCM conversion and file output

- ✅ **Integration**
  - End-to-end equation to audio pipeline
  - Complex mathematical expressions
  - Real-world usage scenarios
  - Performance and error handling

- ✅ **C++ Bindings**
  - Interface compatibility
  - Error handling and edge cases
  - Memory management and resource cleanup

## Notes

- Some tests may be skipped if C++ bindings are not available
- Audio tests may show ALSA warnings in headless environments (expected)
- Tests automatically fall back to file output when audio hardware is unavailable
- All tests are designed to be robust and handle missing dependencies gracefully

## Troubleshooting

If tests fail:

1. **Build Issues**: Run `make build` first
2. **Import Errors**: Check PYTHONPATH includes `src/python`
3. **Audio Errors**: ALSA warnings are expected in headless environments
4. **C++ Binding Issues**: Ensure CMake build completed successfully
5. **Permission Issues**: Make sure test files are executable: `chmod +x tests/*.py`

The test suite is designed to work both in development environments and CI/CD pipelines.

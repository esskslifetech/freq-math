# Developer Guide

This guide provides comprehensive information for developers who want to contribute to, extend, or understand the Freq-Math codebase.

## Table of Contents

- [Development Setup](#development-setup)
- [Architecture Overview](#architecture-overview)
- [C++ Backend Development](#c-backend-development)
- [Python Core Development](#python-core-development)
- [Testing Framework](#testing-framework)
- [Performance Optimization](#performance-optimization)
- [Security Considerations](#security-considerations)
- [Contributing Guidelines](#contributing-guidelines)
- [Build System](#build-system)

---

## Development Setup

### Prerequisites

- **C++17 compatible compiler** (GCC 7+, Clang 5+, MSVC 2019+)
- **Python 3.8+** with development headers
- **CMake 3.12+**
- **pybind11** (for Python bindings)
- **Git** for version control

### Initial Setup

```bash
# Clone repository
git clone https://github.com/esskslifetech/freq-math.git
cd freq-math

# Create development environment
python3 -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black mypy flake8

# Build in debug mode
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Debug ..
make -j$(nproc)
cd ..
```

### Development Tools

#### Code Formatting

```bash
# C++ formatting
clang-format -i src/cpp/*.cpp include/*.h

# Python formatting
black src/python/ tests/ main.py

# Type checking
mypy src/python/ main.py

# Linting
flake8 src/python/ tests/ main.py
```

#### Testing

```bash
# Run all tests with coverage
make test-all
make coverage

# Run specific test categories
make test-math
make test-audio
make test-cpp

# Run tests in debug mode
python -m pytest tests/ -v -s --tb=short
```

---

## Architecture Overview

### System Design Principles

1. **Separation of Concerns**: Clear boundaries between parsing, evaluation, and audio synthesis
2. **Type Safety**: Strong typing and explicit error handling
3. **Performance**: Zero-cost abstractions and efficient algorithms
4. **Security**: AST-based validation prevents code injection
5. **Testability**: Pure functions and dependency injection

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Python Layer                          │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │   GUI/CLI       │  │   Plot Manager   │              │
│  └─────────────────┘  └─────────────────┘              │
│           │                    │                        │
│  ┌─────────────────────────────────────────────────┐      │
│  │           FreqMathCalculator                 │      │
│  │         (Orchestration Layer)               │      │
│  └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                Python-C++ Bindings                        │
│              (pybind11 Interface)                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   C++ Backend                            │
│  ┌─────────────────┐  ┌─────────────────┐              │
│  │ Equation Parser │  │ Math Evaluator  │              │
│  └─────────────────┘  └─────────────────┘              │
│           │                    │                        │
│  ┌─────────────────────────────────────────────────┐      │
│  │              Audio Mapper                      │      │
│  └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Input**: Mathematical equation string
2. **Parsing**: Tokenization and lexical analysis
3. **Compilation**: Convert to RPN bytecode
4. **Evaluation**: Execute bytecode with parameters
5. **Audio Mapping**: Convert mathematical results to audio
6. **Output**: Audio samples and visualization data

---

## C++ Backend Development

### Core Components

#### Equation Parser

Located in `src/cpp/equation_parser.cpp` and `include/equation_parser.h`.

**Key Classes**:
- `EquationParser`: Static parsing functions
- `Token`: Lexical token representation
- `MathEnvironment`: Thread-safe variable/function storage

**Design Patterns**:
- **Static Factory**: Parser cannot be instantiated
- **Value Objects**: Tokens are immutable and copyable
- **Thread Safety**: Reader-writer locks for environment

**Adding New Functions**:

1. **Register in Environment**:
```cpp
env.register_function("my_func", 2, [](const std::vector<double>& args) {
    return args[0] + args[1];  // Implementation
});
```

2. **Add to Tokenizer** (if needed):
```cpp
// In _Tokenizer::tokenize()
if (ch == '£') {  // New operator
    tokens.append(_Token(_TokenKind.OP, "my_op"));
}
```

#### Math Evaluator

Located in `src/cpp/math_evaluator.cpp` and `include/math_evaluator.h`.

**Key Classes**:
- `MathCompiler`: Shunting-yard algorithm implementation
- `MathEvaluator`: RPN bytecode execution
- `CompiledExpression`: Immutable bytecode container

**Performance Optimizations**:

1. **SIMD Operations**:
```cpp
#include <immintrin.h>

auto simd_add = [](const __m256d& a, const __m256d& b) {
    return _mm256_add_pd(a, b);
};
```

2. **Memory Pool Allocation**:
```cpp
class MemoryPool {
    std::vector<std::unique_ptr<uint8_t[]>> pools_;
    size_t current_pool_{0};
    size_t offset_{0};
    
public:
    template<typename T>
    T* allocate(size_t count) {
        // Pool allocation implementation
    }
};
```

#### Audio Mapper

Located in `src/cpp/audio_mapper.cpp` and `include/audio_mapper.h`.

**Key Classes**:
- `AudioMapper`: Static audio synthesis functions
- `AudioConfig`: Configuration parameters
- `AdsrConfig`: Envelope parameters

**DSP Implementation**:

1. **Oscillator Generation**:
```cpp
double generate_oscillator_sample(Waveform wave, double phase) noexcept {
    switch (wave) {
        case Waveform::Sine:
            return std::sin(phase);
        case Waveform::Square:
            return std::sin(phase) > 0.0 ? 1.0 : -1.0;
        case Waveform::Sawtooth:
            return 2.0 * (phase / (2.0 * M_PI) - std::floor(phase / (2.0 * M_PI) + 0.5));
        case Waveform::Triangle:
            return 2.0 * std::abs(2.0 * (phase / (2.0 * M_PI) - std::floor(phase / (2.0 * M_PI) + 0.5)) - 1.0;
    }
    return 0.0;
}
```

2. **Parallel Processing**:
```cpp
void calculate_phases_parallel(std::span<const double> frequencies,
                           std::span<double> out_phases,
                           int sample_rate) noexcept {
    std::transform(std::execution::par_unseq,
                  frequencies.begin(), frequencies.end(),
                  out_phases.begin(),
                  [sample_rate](double freq) {
                      return 2.0 * M_PI * freq / sample_rate;
                  });
}
```

### Error Handling

#### Expected Type Pattern

The C++ backend uses `freq_math::expected<T, E>` for error handling:

```cpp
template<typename T, typename E>
class expected {
    std::variant<T, E> value_;
    
public:
    bool has_value() const noexcept;
    const T& value() const;
    const E& error() const;
    
    // Conversion operators
    explicit operator bool() const noexcept;
};
```

#### Error Types

```cpp
struct ParseError {
    SourceLocation location;
    std::string message;
};

struct EvalError {
    std::string message;
};

struct AudioError {
    std::string message;
};
```

### Memory Management

#### RAII Principles

All resources follow RAII:

```cpp
class AudioBuffer {
    std::unique_ptr<double[]> data_;
    size_t size_;
    
public:
    explicit AudioBuffer(size_t size) 
        : data_(std::make_unique<double[]>(size)), size_(size) {}
    
    // No copy constructor
    AudioBuffer(const AudioBuffer&) = delete;
    
    // Move constructor
    AudioBuffer(AudioBuffer&& other) noexcept = default;
    
    // Automatic cleanup
    ~AudioBuffer() = default;
};
```

#### Zero-Copy Operations

```cpp
// Use spans for views instead of copies
void process_audio(std::span<const double> input,
                  std::span<double> output) noexcept;
```

---

## Python Core Development

### FreqMathCalculator

Located in `src/python/freq_math_calculator.py`.

**Key Design Patterns**:

1. **Protocol-Based Design**:
```python
@runtime_checkable
class CalculatorPort(Protocol):
    @property
    def sample_rate(self) -> int: ...
    
    def compile_and_validate(self, equation: str) -> str | None: ...
```

2. **Adapter Pattern**:
```python
class RealCalculatorAdapter:
    def __init__(self, sample_rate: int = _DEFAULT_SAMPLE_RATE) -> None:
        self._calc = FreqMathCalculator(sample_rate=sample_rate)
        self._synth = AudioSynthesizer(...)
```

3. **Immutable Configuration**:
```python
@dataclass(frozen=True, slots=True)
class SynthesisParams:
    equation: str
    duration_s: float = _DEFAULT_DURATION_S
    base_frequency_hz: float = _DEFAULT_FREQUENCY_HZ
```

### Security Implementation

#### AST Validation

```python
class AstSafetyPolicy:
    _ALLOWED_NODE_TYPES: Final[tuple[type[ast.AST], ...]] = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call,
        ast.Name, ast.Constant, ast.Load, ast.Tuple,
        # Operators only
    )
    
    def validate(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            self._check_node_type(node)
            self._check_call(node)
            self._check_constant(node)
```

#### Equation Preprocessing

```python
class EquationPreprocessor:
    def preprocess(self, equation: str) -> str:
        expr = self._collapse_whitespace(equation)
        expr = self._strip_lhs(expr)
        expr = self._normalize_unicode(expr)
        expr = self._insert_implicit_multiplication(expr)
        self._validate_parentheses(expr)
        return expr
```

### Audio Synthesizer

Located in `src/python/audio_synthesizer.py`.

**Key Features**:

1. **Protocol-Based Audio Players**:
```python
@runtime_checkable
class AudioPlayerProtocol(Protocol):
    def play(self, audio: npt.NDArray[np.float32]) -> None: ...
    def stop(self) -> None: ...
```

2. **Efficient DSP Operations**:
```python
def apply_envelope_inplace(audio: np.ndarray, 
                         envelope: np.ndarray) -> None:
    np.multiply(audio, envelope, out=audio)  # In-place operation
```

### Concurrency Model

#### Thread-Safe Design

```python
class AudioWorker(threading.Thread):
    def __init__(self, params: SynthesisParams,
                 msg_queue: queue.Queue[WorkerMessage],
                 calculator: CalculatorPort) -> None:
        super().__init__(daemon=True)
        self._params = params
        self._queue = msg_queue
        self._calc = calculator
        self._cancel = threading.Event()
```

#### Message Passing

```python
@dataclass(frozen=True, slots=True)
class WorkerMessage:
    state: WorkerState
    payload: Any = None
```

---

## Testing Framework

### Test Structure

```
tests/
├── test_freq_math_calculator.py      # Main calculator tests
├── test_math_evaluator_updated.py    # Math evaluation tests
├── test_audio_synthesizer_updated.py # Audio synthesis tests
├── test_integration.py               # End-to-end tests
├── test_equation_parser.py          # C++ binding tests
├── test_math_evaluator_cpp.py       # C++ evaluator tests
├── test_audio_mapper.py             # C++ audio tests
├── test_main.py                    # Main application tests
├── test_examples.py                 # Example script tests
└── run_all_tests.py               # Test runner
```

### Test Categories

#### Unit Tests

```python
class TestMathEvaluatorUpdated(unittest.TestCase):
    def test_basic_arithmetic(self):
        """Test basic arithmetic operations."""
        calc = FreqMathCalculator()
        result = calc.generate_math_array("2+3*4", x_range=(0, 1), steps=10)
        np.testing.assert_array_almost_equal(result, np.full(10, 14.0))
    
    def test_trigonometric_functions(self):
        """Test trigonometric function evaluation."""
        calc = FreqMathCalculator()
        result = calc.generate_math_array("sin(pi/2)", x_range=(0, 1), steps=1)
        self.assertAlmostEqual(result[0], 1.0, places=6)
```

#### Integration Tests

```python
class TestIntegration(unittest.TestCase):
    def test_complete_pipeline(self):
        """Test complete math-to-audio pipeline."""
        calc = FreqMathCalculator()
        
        # Generate math function
        math_array = calc.generate_math_array(
            "sin(2*pi*x) + 0.5*sin(4*pi*x)",
            x_range=(0, 1), steps=1000
        )
        
        # Generate audio
        audio_array = calc.generate_audio_array(
            "sin(2*pi*x) + 0.5*sin(4*pi*x)",
            duration_s=1.0, x_range=(0, 1),
            base_frequency_hz=440.0, mode=MappingMode.FM_SINE
        )
        
        # Verify results
        self.assertEqual(len(math_array), 1000)
        self.assertEqual(len(audio_array), 44100)  # 1 second at 44.1kHz
```

#### Property-Based Tests

```python
@given(st.floats(min_value=-10, max_value=10))
def test_sin_periodicity(x):
    """Test that sin(x + 2π) = sin(x)."""
    calc = FreqMathCalculator()
    result1 = calc.generate_math_array("sin(x)", x_range=(x, x, 1), steps=1)
    result2 = calc.generate_math_array("sin(x + 2*pi)", x_range=(x, x, 1), steps=1)
    np.testing.assert_array_almost_equal(result1, result2, decimal=6)
```

### Test Utilities

#### Mock Calculator

```python
class MockCalculatorAdapter:
    """Fallback adapter for testing without C++ bindings."""
    
    def __init__(self, sample_rate: int = _DEFAULT_SAMPLE_RATE) -> None:
        self._sr = sample_rate
    
    def generate_math_array(self, equation: str, *, x_range, steps):
        x = np.linspace(x_range[0], x_range[1], steps)
        return np.sin(2.0 * np.pi * x * 5.0).astype(np.float32)
```

#### Test Fixtures

```python
@pytest.fixture
def calculator():
    """Provide a calculator instance for testing."""
    return FreqMathCalculator(sample_rate=44100)

@pytest.fixture
def sample_audio():
    """Provide sample audio data for testing."""
    return np.sin(2.0 * np.pi * 440.0 * np.linspace(0, 1, 44100)).astype(np.float32)
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=src/python --cov-report=html

# Run specific test file
python -m pytest tests/test_math_evaluator_updated.py -v

# Run with specific markers
python -m pytest tests/ -m "not slow" -v
```

---

## Performance Optimization

### Profiling Tools

#### Python Profiling

```bash
# CPU profiling
python -m cProfile -o profile.stats main.py

# Memory profiling
pip install memory-profiler
python -m memory_profiler main.py

# Line profiling
pip install line_profiler
kernprof -l -v main.py
```

#### C++ Profiling

```bash
# With gprof
g++ -pg -o freq_math src/cpp/*.cpp
./freq_math
gprof freq_math gmon.out > analysis.txt

# With perf
perf record --call-graph=dwarf ./freq_math
perf report
```

### Optimization Strategies

#### Vectorization

```python
# Slow: Python loop
def slow_sin(x_array):
    result = []
    for x in x_array:
        result.append(math.sin(x))
    return np.array(result)

# Fast: NumPy vectorization
def fast_sin(x_array):
    return np.sin(x_array)
```

#### Memory Efficiency

```python
# Avoid unnecessary copies
def process_audio(audio: np.ndarray) -> np.ndarray:
    # Bad: Creates copy
    processed = audio * 2.0
    
    # Good: In-place operation
    audio *= 2.0
    return audio
```

#### Caching

```python
@lru_cache(maxsize=512)
def compile_equation(equation: str) -> CompiledEquation:
    """Cache compiled equations for reuse."""
    # Compilation logic
```

### Benchmarking

#### Python Benchmarks

```python
import timeit

def benchmark_equation_evaluation():
    setup = """
from src.python.freq_math_calculator import FreqMathCalculator
calc = FreqMathCalculator()
"""
    stmt = """
calc.generate_math_array("sin(2*pi*x) + 0.5*sin(4*pi*x)", 
                       x_range=(0, 1), steps=1000)
"""
    
    time = timeit.timeit(stmt, setup=setup, number=1000)
    print(f"Average time: {time/1000:.6f} seconds")
```

#### C++ Benchmarks

```cpp
#include <chrono>

void benchmark_evaluation() {
    auto start = std::chrono::high_resolution_clock::now();
    
    for (int i = 0; i < 10000; ++i) {
        auto result = MathEvaluator::evaluate(compiled, 1.0, env);
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    
    std::cout << "Average time: " << duration.count() / 10000.0 << " μs\n";
}
```

---

## Security Considerations

### Threat Model

#### Potential Attacks

1. **Code Injection**: Malicious equations trying to execute arbitrary code
2. **Resource Exhaustion**: Equations causing excessive CPU/memory usage
3. **Denial of Service**: Complex expressions causing system hangs
4. **Memory Corruption**: Buffer overflows or invalid memory access

#### Security Layers

1. **Input Validation**: Unicode normalization and sanitization
2. **AST Validation**: Whitelist-based node type checking
3. **Resource Limits**: Configurable complexity and size restrictions
4. **Memory Safety**: Bounds checking and safe array operations

### Implementation Details

#### AST Safety Policy

```python
class AstSafetyPolicy:
    _ALLOWED_FUNCTIONS: Final[frozenset[str]] = frozenset({
        'sin', 'cos', 'tan', 'asin', 'acos', 'atan',
        'sinh', 'cosh', 'tanh', 'exp', 'log', 'log2', 'log10',
        'sqrt', 'cbrt', 'abs', 'sign', 'floor', 'ceil', 'round',
        'min', 'max', 'atan2', 'sinc'
    })
    
    def _check_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            raise MathSecurityError("Only direct function calls allowed")
        
        func_name = node.func.id.lower()
        if func_name not in self._ALLOWED_FUNCTIONS:
            raise MathSecurityError(f"Unknown function: {func_name}")
```

#### Resource Limits

```python
@dataclass(frozen=True, slots=True)
class CompilationLimits:
    max_ast_nodes: int = 500
    max_constant_abs: float = 1e9
    max_power_abs: float = 128.0

@dataclass(frozen=True, slots=True)
class GenerationLimits:
    max_steps: int = 5_000_000
    max_duration_s: float = 60.0
```

### Security Testing

#### Fuzzing

```python
import random
import string

def generate_random_equation(length: int) -> str:
    """Generate potentially malicious equations for testing."""
    chars = string.ascii_letters + string.digits + "+-*/^()[]{}.,"
    return ''.join(random.choice(chars) for _ in range(length))

def test_security_limits():
    """Test that security limits are enforced."""
    calc = FreqMathCalculator()
    
    # Test overly complex equation
    complex_eq = '+'.join(['sin(x)' for _ in range(1000)])
    with self.assertRaises(MathSecurityError):
        calc.compile_and_validate(complex_eq)
```

---

## Contributing Guidelines

### Code Style

#### C++ Style

```cpp
// Naming conventions
class ClassName {
public:
    void method_name();           // snake_case for methods
    static const int kConstant;   // kCamelCase for constants
    
private:
    int member_variable_;          // snake_case with trailing underscore
};

// Use constexpr where possible
constexpr double kPi = 3.14159265359;

// Use noexcept for functions that don't throw
double safe_function(int x) noexcept {
    return x * 2.0;
}
```

#### Python Style

```python
# Follow PEP 8
class ClassName:
    def method_name(self, parameter: int) -> str:
        """Use type hints and docstrings."""
        return str(parameter)

# Use f-strings for formatting
message = f"Processing {count} items"

# Prefer composition over inheritance
class AudioProcessor:
    def __init__(self, synthesizer: AudioSynthesizer):
        self._synthesizer = synthesizer
```

### Pull Request Process

1. **Fork Repository**: Create your own fork
2. **Create Branch**: `git checkout -b feature/your-feature`
3. **Make Changes**: Implement with tests
4. **Run Tests**: Ensure all tests pass
5. **Update Docs**: Update relevant documentation
6. **Submit PR**: Create pull request with description

### Code Review Checklist

#### Functionality
- [ ] Code works as intended
- [ ] Edge cases are handled
- [ ] Error conditions are properly managed
- [ ] Performance is acceptable

#### Quality
- [ ] Code follows style guidelines
- [ ] Tests have adequate coverage
- [ ] Documentation is updated
- [ ] No debugging code remains

#### Security
- [ ] Input validation is present
- [ ] Resource limits are enforced
- [ ] No unsafe operations
- [ ] Memory management is correct

---

## Build System

### CMake Configuration

#### Main CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.12)
project(FreqMath)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find dependencies
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)

# Compiler-specific options
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -O2")
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -O2")
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /W4 /O2")
endif()
```

#### Library Configuration

```cmake
# C++ library
add_library(freq_math_cpp SHARED
    src/cpp/equation_parser.cpp
    src/cpp/math_evaluator.cpp
    src/cpp/audio_mapper.cpp
)

target_include_directories(freq_math_cpp PUBLIC include)
target_compile_features(freq_math_cpp PUBLIC cxx_std_17)

# Python bindings
pybind11_add_module(freq_math_bindings
    src/cpp/bindings.cpp
)

target_link_libraries(freq_math_bindings PRIVATE freq_math_cpp)
```

### Makefile Integration

#### Build Targets

```makefile
# Default target
all: build

# Build C++ components and Python bindings
build:
	@echo "Building Freq-Math..."
	mkdir -p build
	cd build && cmake .. && make
	@echo "Build complete!"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build
	rm -f src/python/freq_math_bindings*.so
```

#### Test Targets

```makefile
# Run all tests
test-all:
	@echo "Running all tests..."
	cd tests && python3 run_all_tests.py

# Development workflow
dev-test: build test-all
	@echo "Development test cycle completed!"
```

### Continuous Integration

#### GitHub Actions

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, '3.10', 3.11]
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        sudo apt-get install libportaudio2
    
    - name: Build
      run: make build
    
    - name: Test
      run: make test-all
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

---

This developer guide provides comprehensive information for contributing to Freq-Math. For specific API details, see the [API Reference](api-reference.md). For user-facing documentation, see the [User Guide](user-guide.md).

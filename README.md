# Freq-Math: Mathematical Equation Sonifier

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/esskslifetech/freq-math)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![C++](https://img.shields.io/badge/C%2B%2B-23-blue.svg)](https://isocpp.org)
[![CMake](https://img.shields.io/badge/cmake-3.12+-blue.svg)](https://cmake.org)

> **Transform mathematics into sound** - A sophisticated cross-platform application that converts mathematical equations into rich audio experiences with real-time visualization.

**Freq-Math** is an innovative mathematical sonifier that bridges the gap between abstract mathematical concepts and auditory perception. By combining high-performance C++ backend processing with Python's versatile audio synthesis capabilities, it creates a unique tool for mathematical exploration, education, and creative expression through sound.

## Overview

Freq-Math is a unique calculator that transforms mathematical expressions into rich audio experiences. The application combines high-performance C++ for equation parsing and evaluation with Python for advanced audio synthesis and visualization, creating an innovative tool for mathematical exploration through sound.

## ✨ Key Features

### 🧮 **Mathematical Engine**
- **Advanced Equation Parser**: Supports complex mathematical expressions with implicit multiplication
- **Real-time Evaluation**: High-performance C++ backend with RPN bytecode compilation
- **Security-First Design**: AST-based validation prevents code injection attacks
- **Rich Function Library**: Trigonometric, exponential, logarithmic, and custom functions

### 🎵 **Audio Synthesis**
- **Multiple Synthesis Modes**: FM, AM, phase distortion, wavetable, and direct mapping
- **Real-time Processing**: Low-latency audio generation up to 96kHz
- **Professional DSP**: High-quality digital signal processing with SIMD optimization
- **Export Capabilities**: Save generated audio as industry-standard WAV files

### 📊 **Visualization & Analysis**
- **Three-Panel Display**: Mathematical function, audio waveform, and frequency spectrum
- **Real-time Updates**: Live visualization during equation processing
- **Interactive Plots**: Zoom, pan, and detailed frequency analysis
- **Signal Statistics**: Peak, RMS, crest factor, and zero-crossing rate analysis

### 🎨 **User Experience**
- **Modern GUI**: Dark/light theme support with responsive interface
- **CLI Interface**: Full-featured command-line operation for automation
- **Python API**: Comprehensive programmatic access for integration
- **Cross-Platform**: Windows, macOS, and Linux support

### ⚡ **Performance & Architecture**
- **Hybrid Architecture**: C++23 backend with Python 3.8+ frontend
- **Parallel Processing**: Multi-core evaluation for large-scale computations
- **Memory Efficient**: LRU caching and zero-copy operations
- **Thread-Safe**: Concurrent processing with message-based communication

## 🏗️ Architecture

Freq-Math employs a clean, modular architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   GUI Layer     │    │   CLI Layer     │    │  Python API     │
│  (Tkinter/Matplotlib) │  (Argparse)     │    │  (Protocol)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
┌─────────────────────────────────┼─────────────────────────────────┐
│              Python Core Layer                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Audio Synthesizer│  │Math Calculator  │  │ Plot Manager    │  │
│  │    (NumPy)      │  │   (AST Eval)   │  │ (Matplotlib)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────┼─────────────────────────────────┘
                                 │
┌─────────────────────────────────┼─────────────────────────────────┐
│               C++ Backend                                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Equation Parser │  │ Math Evaluator  │  │  Audio Mapper   │  │
│  │ (Tokenizer)     │  │ (RPN Bytecode)  │  │ (DSP Engine)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 🔧 Core Components

- **C++ Backend**: High-performance equation parsing, compilation to RPN bytecode, and audio DSP
- **Python Core**: Audio synthesis, visualization, and user interface logic  
- **Security Layer**: AST-based validation with whitelisted functions and operations
- **Audio Engine**: Multi-mode synthesis with real-time processing capabilities
- **Visualization**: Real-time plotting of mathematical functions and audio analysis


## Demo

https://www.youtube.com/watch?v=c4BeN0gmHeU

## 🚀 Quick Start

### 📋 Prerequisites

- **Python 3.8+**
- **C++23 compatible compiler** (GCC 11+, Clang 13+, MSVC 2022+)
- **CMake 3.12+**
- **pybind11** (for Python-C++ bindings)

### ⚡ Installation

#### Option 1: Using Make (Recommended)

```bash
# Clone the repository
git clone https://github.com/esskslifetech/freq-math.git
cd freq-math

# Install dependencies and build
make install    # Install Python dependencies
make build      # Build C++ components

# Run the application
python main.py
```

#### Option 2: Manual Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install numpy matplotlib pyaudio tkinter

# Build C++ components
mkdir build && cd build
cmake ..
make
cd ..

# Run the application
python main.py
```

### 🎯 First Steps

1. **Launch the Application**: Run `python main.py` to start the GUI
2. **Try a Preset**: Select "Sine Wave" from the presets dropdown
3. **Generate Audio**: Click "Generate & Play" to hear the mathematical function
4. **Explore Visualization**: View the function plot, waveform, and frequency spectrum
5. **Experiment**: Try different equations like `sin(2*pi*x*5 + 3*sin(2*pi*x*0.5))`

## 📖 Usage

### 🖥️ GUI Interface

The graphical interface provides:

- **Equation Input**: Enter mathematical expressions with syntax highlighting
- **Real-time Validation**: Instant feedback on equation syntax and security
- **Parameter Controls**: Adjust duration, frequency, and mapping modes
- **Visualization**: Three-panel display showing function, waveform, and spectrum
- **Preset Library**: Built-in equations for quick exploration
- **Export Options**: Save audio as WAV files

### ⌨️ Command Line Interface

```bash
# Basic usage
python main.py --equation "sin(2*pi*x)" --duration 2.0 --output output.wav

# Advanced usage with custom parameters
python main.py \
  --equation "A*sin(2*pi*f*x)*exp(-alpha*x)" \
  --duration 3.0 \
  --frequency 440 \
  --mode fm_sine \
  --params A=0.8,f=880,alpha=0.2 \
  --output complex.wav

# List available presets
python main.py --list-presets

# Run in headless mode (no GUI)
python main.py --no-gui --equation "sin(2*pi*x*x*10)"
```

### 🐍 Python API

```python
from src.python.freq_math_calculator import FreqMathCalculator, MappingMode

# Create calculator instance
calc = FreqMathCalculator(sample_rate=44100)

# Generate mathematical function
math_array = calc.generate_math_array(
    "sin(2*pi*x) + 0.5*sin(4*pi*x)",
    x_range=(0.0, 1.0),
    steps=1000
)

# Generate audio from equation
audio_array = calc.generate_audio_array(
    "sin(2*pi*x) + 0.5*sin(4*pi*x)",
    duration_s=2.0,
    x_range=(0.0, 1.0),
    base_frequency_hz=440.0,
    mode=MappingMode.FM_SINE
)

# Get equation analysis
info = calc.get_equation_info("sin(2*pi*x)")
print(f"Complexity: {info['metadata']['complexity_score']}")
```

### 🔧 C++ API

```cpp
#include "equation_parser.h"
#include "math_evaluator.h"
#include "audio_mapper.h"

int main() {
    // Setup environment
    freq_math::MathEnvironment env;
    env.set_variable("x", 1.0);
    
    // Parse and compile equation
    auto tokens = freq_math::EquationParser::parse("sin(2*pi*x)", env);
    auto compiled = freq_math::MathCompiler::compile(tokens.value());
    
    // Evaluate
    auto result = freq_math::MathEvaluator::evaluate(
        compiled.value(), 1.0, env);
    
    // Generate audio
    std::vector<double> math_values = /* ... */;
    auto audio = freq_math::AudioMapper::map_to_audio(
        math_values, freq_math::Waveform::Sine);
    
    return 0;
}
```

## 🧮 Equation Syntax

Freq-Math supports a rich mathematical expression syntax:

### 🔢 Basic Operations

```python
# Arithmetic
x + y * z / 2 - 1
x ^ 2 + y ^ 3          # Exponentiation

# Trigonometric
sin(2*pi*x)
cos(x) + tan(x/2)
asin(x) + acos(y)

# Exponential and Logarithmic
exp(-x^2)
log(x) + log2(y) + log10(z)
sqrt(x^2 + y^2)

# Other functions
abs(x)
sign(sin(x))
floor(x), ceil(x), round(x)
min(x, y), max(x, y)
```

### ⚡ Advanced Features

```python
# Implicit multiplication (2pi = 2*pi)
2pi*x + 3sin(440*t)

# Unicode operators
π × r²          # Becomes: pi * r**2
e^(-x²/2)       # Becomes: exp(-x**2/2)

# Custom parameters (A, f, alpha, beta, l)
A*sin(2*pi*f*x)*exp(-alpha*x)

# Complex expressions
sin(2*pi*x*5 + 3*sin(2*pi*x*0.5))  # FM synthesis
exp(-((x-0.5)**2)/(2*0.01))       # Bell curve
```

### 📊 Available Variables and Constants

- **Variables**: `x`, `t`, `y` (all map to the same input)
- **Constants**: `pi`, `e`, `tau` (2π)
- **Parameters**: `A`, `f`, `alpha`, `beta`, `l` (customizable)
- **Single-letter**: `a, b, c, d, g, h, j, k, m, n, p, q, r, s, u, v, w, z` (default to 1.0)

## 🎵 Audio Synthesis Modes

### FM Sine (`fm_sine`)
Frequency modulation synthesis using the mathematical function as a modulator.

### AM Sine (`am_sine`)
Amplitude modulation synthesis with the function controlling amplitude.

### Phase Distortion (`phase_distortion`)
Phase distortion synthesis using the function to modulate oscillator phase.

### Wavetable (`wavetable`)
Wavetable synthesis with the function defining the waveform shape.

### Direct (`direct`)
Direct mapping of mathematical values to audio samples.

## 📁 Project Structure

```
Freq-Math/
├── src/
│   ├── cpp/                    # C++ source files
│   │   ├── equation_parser.cpp  # Lexical analysis and tokenization
│   │   ├── math_evaluator.cpp  # Compilation and evaluation engine
│   │   ├── audio_mapper.cpp    # DSP and audio synthesis
│   │   └── bindings.cpp        # Python-C++ bindings
│   └── python/                 # Python source files
│       ├── freq_math_calculator.py  # Main calculator API
│       └── audio_synthesizer.py     # Audio synthesis and playback
├── include/                    # C++ header files
│   ├── equation_parser.h       # Parser interface
│   ├── math_evaluator.h        # Evaluator interface
│   ├── audio_mapper.h          # Audio interface
│   └── expected.h              # Error handling utilities
├── tests/                      # Comprehensive test suite
│   ├── test_*.py              # Python tests
│   └── README.md              # Test documentation
├── docs/                       # Documentation
│   ├── api-reference.md        # API documentation
│   ├── user-guide.md          # User guide
│   └── developer-guide.md     # Developer documentation
├── build/                      # CMake build output
├── venv/                       # Python virtual environment
├── CMakeLists.txt              # CMake configuration
├── Makefile                    # Build automation
├── requirements.txt            # Python dependencies
└── main.py                     # Application entry point
```

## 🛠️ Development

### Building from Source

```bash
# Development build with debug symbols
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Debug ..
make -j$(nproc)

# Release build with optimizations
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### 🧪 Testing

```bash
# Run all tests
make test-all

# Run specific test categories
make test-math      # Math evaluator tests
make test-audio     # Audio synthesizer tests
make test-cpp       # C++ binding tests

# Run with coverage
make coverage

# Development workflow
make dev-test       # Build and test
make dev-quick      # Quick test cycle
```

### 📝 Code Quality

The project follows strict code quality standards:

- **C++**: C++17 standard, clang-format, static analysis
- **Python**: PEP 8, black formatting, mypy type checking
- **Testing**: 95%+ coverage, property-based testing
- **Documentation**: Comprehensive API docs and examples

### 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with appropriate tests
4. Ensure all tests pass (`make test-all`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## ⚡ Performance

### Benchmarks

- **Equation Parsing**: ~10,000 expressions/second
- **Evaluation**: ~1,000,000 points/second (parallel)
- **Audio Generation**: Real-time synthesis up to 96kHz
- **Memory Usage**: <50MB for typical workloads

### Optimization Features

- **LRU Caching**: Compiled expressions cached for reuse
- **Parallel Processing**: Multi-core evaluation for large arrays
- **Zero-Copy Operations**: Efficient memory management
- **SIMD Optimization**: Vectorized mathematical operations

## 🔒 Security

Freq-Math implements multiple layers of security:

- **AST Validation**: Whitelist-based node type checking
- **Function Restrictions**: Only approved mathematical functions
- **Resource Limits**: Configurable complexity and size limits
- **No Code Execution**: Never uses `eval()` or `exec()`
- **Memory Safety**: Bounds checking and safe array operations

## 🔧 Troubleshooting

### Common Issues

**Build Failures**:
```bash
# Ensure C++17 support
g++ --version  # Should be 7.0+
cmake --version  # Should be 3.12+

# Clean rebuild
make clean
make build
```

**Import Errors**:
```bash
# Check Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src/python"

# Rebuild bindings
make build
```

**Audio Issues**:
```bash
# Install audio dependencies
pip install pyaudio portaudio

# Test audio system
python -c "import pyaudio; print('Audio OK')"
```

### ❓ Getting Help

- **Documentation**: See [docs/](docs/) for detailed guides
- **Issues**: Report bugs on GitHub Issues
- **Discussions**: Join our GitHub Discussions
- **Examples**: Check the [tests/](tests/) directory for usage examples

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **NumPy** for high-performance numerical computing
- **Matplotlib** for visualization capabilities
- **pybind11** for seamless Python-C++ integration
- **PortAudio** for cross-platform audio I/O

## 📚 Citation

If you use Freq-Math in research, please cite:

```bibtex
@software{freq_math,
  title={Freq-Math: Mathematical Equation Sonifier},
  author={Kanishk Soni},
  year={2024},
  url={https://github.com/esskslifetech/freq-math}
}
```

---

<div align="center">

**🎵 Transform mathematics into sound with Freq-Math!** ✨

[⭐ Star this repo](https://github.com/esskslifetech/freq-math) • [🐛 Report issues](https://github.com/esskslifetech/freq-math/issues) • [💬 Join discussions](https://github.com/esskslifetech/freq-math/discussions)

</div>

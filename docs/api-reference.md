# API Reference

This document provides comprehensive API documentation for the Freq-Math project, covering both C++ and Python components.

## Table of Contents

- [C++ API](#c-api)
  - [Equation Parser](#equation-parser)
  - [Math Evaluator](#math-evaluator)
  - [Audio Mapper](#audio-mapper)
- [Python API](#python-api)
  - [FreqMathCalculator](#freqmathcalculator)
  - [Audio Synthesizer](#audio-synthesizer)
  - [Main Application](#main-application)
- [Error Handling](#error-handling)
- [Examples](#examples)

---

## C++ API

### Equation Parser

The equation parser provides lexical analysis and tokenization of mathematical expressions.

#### Classes

##### `Token`

Represents a single token in a mathematical expression.

```cpp
struct Token {
    TokenType type;
    std::string_view text;
    double numeric_value{0.0};
    SourceLocation location{};
    
    [[nodiscard]] constexpr bool is_operator() const noexcept;
};
```

**Fields:**
- `type`: The token type (NUMBER, VARIABLE, OPERATOR, FUNCTION, LEFT_PAREN, RIGHT_PAREN, END_OF_STREAM)
- `text`: String view of the token text
- `numeric_value`: Numeric value for NUMBER tokens
- `location`: Source location information

##### `SourceLocation`

Provides source code location for error reporting.

```cpp
struct SourceLocation {
    uint32_t line{1};
    uint32_t column{1};
    uint32_t length{0};
};
```

##### `ParseError`

Error information for parsing failures.

```cpp
struct ParseError {
    SourceLocation location;
    std::string message;
};
```

##### `MathEnvironment`

Thread-safe environment for variables and functions.

```cpp
class MathEnvironment {
public:
    MathEnvironment();
    
    void set_variable(std::string_view name, double value);
    void register_function(std::string_view name, size_t arity, MathFunction func);
    
    [[nodiscard]] freq_math::expected<double, std::string> get_variable(std::string_view name) const;
    [[nodiscard]] bool is_function(std::string_view name) const;
};
```

**Methods:**
- `set_variable()`: Set a variable value (requires write lock)
- `register_function()`: Register a custom function (requires write lock)
- `get_variable()`: Get a variable value (thread-safe read)
- `is_function()`: Check if a name is a registered function (thread-safe read)

##### `EquationParser`

Static class for parsing mathematical expressions.

```cpp
class EquationParser {
public:
    EquationParser() = delete;
    
    [[nodiscard]] static freq_math::expected<std::vector<Token>, ParseError> 
    parse(std::string_view equation, const MathEnvironment& env) noexcept;
};
```

**Methods:**
- `parse()`: Parse an equation string into tokens. Returns expected type containing either token vector or ParseError.

---

### Math Evaluator

The math evaluator compiles and evaluates mathematical expressions with high performance.

#### Classes

##### `CompiledExpression`

Represents a compiled expression in RPN (Reverse Polish Notation) bytecode.

```cpp
class CompiledExpression {
public:
    explicit CompiledExpression(std::vector<Token> rpn_bytecode) noexcept;
    
    [[nodiscard]] std::span<const Token> bytecode() const noexcept;
};
```

**Methods:**
- `bytecode()`: Get read-only view of the compiled bytecode

##### `EvalError`

Error information for evaluation failures.

```cpp
struct EvalError {
    std::string message;
};
```

##### `MathCompiler`

Compiles infix tokens to RPN bytecode using the Shunting-Yard algorithm.

```cpp
class MathCompiler {
public:
    MathCompiler() = delete;
    
    [[nodiscard]] static freq_math::expected<CompiledExpression, EvalError> 
    compile(std::span<const Token> infix_tokens) noexcept;
};
```

**Methods:**
- `compile()`: Compile infix tokens to RPN bytecode

##### `MathEvaluator`

Evaluates compiled expressions with various execution modes.

```cpp
class MathEvaluator {
public:
    MathEvaluator() = delete;
    
    // Single point evaluation
    [[nodiscard]] static freq_math::expected<double, EvalError> 
    evaluate(const CompiledExpression& expr, 
             double x, 
             const MathEnvironment& env) noexcept;
    
    // Linear range evaluation (parallel)
    [[nodiscard]] static freq_math::expected<std::vector<double>, EvalError> 
    evaluate_range(const CompiledExpression& expr, 
                   double start, double end, size_t steps, 
                   const MathEnvironment& env) noexcept;
    
    // Arbitrary batch evaluation
    [[nodiscard]] static freq_math::expected<std::vector<double>, EvalError> 
    evaluate_batch(const CompiledExpression& expr, 
                   std::span<const double> x_values, 
                   const MathEnvironment& env) noexcept;
};
```

**Methods:**
- `evaluate()`: Evaluate expression at a single point
- `evaluate_range()`: Evaluate expression over a linear range (uses parallel execution)
- `evaluate_batch()`: Evaluate expression at arbitrary points

---

### Audio Mapper

The audio mapper converts mathematical results to audio waveforms.

#### Types and Enums

```cpp
using AudioSample = double;
using AudioBuffer = std::vector<AudioSample>;

enum class Waveform { Sine, Square, Sawtooth, Triangle };
enum class MathOperation { Add, Subtract, Multiply, Divide, Power, Unary };
```

#### Structs

##### `AudioConfig`

Configuration for audio generation.

```cpp
struct AudioConfig {
    double base_frequency{440.0};
    double amplitude_scale{1.0};
    double duration_seconds{1.0};
    int sample_rate{44100};
    bool auto_normalize{true};
};
```

##### `AdsrConfig`

ADSR envelope configuration.

```cpp
struct AdsrConfig {
    double attack_sec{0.05};
    double decay_sec{0.1};
    double sustain_level{0.7};
    double release_sec{0.2};
};
```

##### `AudioError`

Error information for audio operations.

```cpp
struct AudioError {
    std::string message;
};
```

#### Classes

##### `AudioMapper`

Static class for audio mapping and synthesis.

```cpp
class AudioMapper {
public:
    // Map math values to audio
    [[nodiscard]] static freq_math::expected<AudioBuffer, AudioError>
    map_to_audio(std::span<const double> math_values, 
                 Waveform wave_type = Waveform::Sine,
                 const AudioConfig& config = {}) noexcept;
    
    // FM synthesis
    [[nodiscard]] static freq_math::expected<AudioBuffer, AudioError>
    generate_fm_signal(std::span<const double> carrier_freqs,
                       std::span<const double> modulator_freqs,
                       const AudioConfig& config) noexcept;
    
    // Apply ADSR envelope in-place
    static void apply_envelope_inplace(std::span<AudioSample> buffer, 
                                       int sample_rate, 
                                       const AdsrConfig& adsr) noexcept;
    
    // Utility functions
    [[nodiscard]] static double map_operation_to_frequency(MathOperation op, double base_freq) noexcept;
    [[nodiscard]] static double map_magnitude_to_amplitude(double magnitude) noexcept;
};
```

**Methods:**
- `map_to_audio()`: Convert mathematical values to audio waveform
- `generate_fm_signal()`: Generate FM synthesis signal
- `apply_envelope_inplace()`: Apply ADSR envelope to audio buffer
- `map_operation_to_frequency()`: Map math operation to frequency
- `map_magnitude_to_amplitude()`: Map magnitude to amplitude

---

## Python API

### FreqMathCalculator

The main calculator class that orchestrates math evaluation and audio synthesis.

#### Classes

##### `FreqMathCalculator`

```python
class FreqMathCalculator:
    def __init__(self, sample_rate: int = 44100, audio_player: Optional[AudioPlayerProtocol] = None)
    
    def compile_equation(self, equation: str) -> CompiledEquation
    def generate_math_array(self, equation: str, *, x_range: tuple[float, float], steps: int) -> np.ndarray
    def generate_audio_array(self, equation: str, *, duration_s: float, x_range: tuple[float, float], 
                           base_frequency_hz: float, mode: MappingMode) -> np.ndarray
    def get_equation_info(self, equation: str) -> dict[str, Any]
    def stop_audio(self) -> None
    def list_presets(self) -> dict[str, str]
    def list_mapping_modes(self) -> tuple[str, ...]
```

**Constructor Parameters:**
- `sample_rate`: Audio sample rate (default: 44100)
- `audio_player`: Optional audio player for playback

**Methods:**
- `compile_equation()`: Compile and validate an equation
- `generate_math_array()`: Generate mathematical function values
- `generate_audio_array()`: Generate audio from equation
- `get_equation_info()`: Get analysis information about equation
- `stop_audio()`: Stop any playing audio
- `list_presets()`: Get available preset equations
- `list_mapping_modes()`: Get available mapping modes

##### `MappingMode`

```python
class MappingMode(Enum):
    FM_SINE = "fm_sine"
    AM_SINE = "am_sine"
    PHASE_DISTORTION = "phase_distortion"
    WAVETABLE = "wavetable"
    DIRECT = "direct"
```

##### `BuiltinEquation`

```python
class BuiltinEquation(Enum):
    SINE = "sin(2*pi*x)"
    CHIRP = "sin(2*pi*x*x*10)"
    BELL_CURVE = "exp(-((x-0.5)**2)/(2*0.01))"
    # ... more presets
```

#### Configuration Classes

##### `MathParameters`

```python
@dataclass(frozen=True)
class MathParameters:
    A: float = 0.5
    f: float = 440.0
    alpha: float = 0.1
    beta: float = 0.1
    l: float = 0.1
```

##### `CompilationLimits`

```python
@dataclass(frozen=True)
class CompilationLimits:
    max_ast_nodes: int = 500
    max_constant_abs: float = 1e9
    max_power_abs: float = 128.0
```

##### `GenerationLimits`

```python
@dataclass(frozen=True)
class GenerationLimits:
    max_steps: int = 5_000_000
    max_duration_s: float = 60.0
```

---

### Audio Synthesizer

High-performance audio synthesis and playback.

#### Classes

##### `AudioSynthesizer`

```python
class AudioSynthesizer:
    def __init__(self, config: AudioConfig)
    
    def play(self, audio: np.ndarray, *, blocking: bool = False) -> None
    def stop(self) -> None
    def save_wav(self, audio: np.ndarray, path: str) -> None
```

##### `AudioConfig`

```python
@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 44100
    channels: int = 1
    buffer_size: int = 1024
```

---

### Main Application

The main application provides both GUI and CLI interfaces.

#### Classes

##### `FreqMathGUI`

```python
class FreqMathGUI:
    def __init__(self, root, *, colors: ThemeColors = DARK_THEME, calculator: Optional[CalculatorPort] = None)
    
    def run(self) -> None
```

##### `CalculatorPort` (Protocol)

```python
class CalculatorPort(Protocol):
    @property
    def sample_rate(self) -> int: ...
    
    def compile_and_validate(self, equation: str) -> str | None: ...
    def generate_math_array(self, equation: str, *, x_range: tuple[float, float], steps: int) -> np.ndarray: ...
    def generate_audio_array(self, equation: str, *, duration_s: float, x_range: tuple[float, float], 
                           base_frequency_hz: float, mapping_mode: str) -> np.ndarray: ...
    def get_equation_info(self, equation: str) -> dict[str, Any]: ...
    def stop_audio(self) -> None: ...
    def list_presets(self) -> dict[str, str]: ...
    def list_mapping_modes(self) -> tuple[str, ...]: ...
```

---

## Error Handling

### C++ Error Handling

The C++ API uses `freq_math::expected<T, E>` for error handling:

```cpp
auto result = EquationParser::parse("sin(x)", env);
if (result) {
    // Success - use result.value()
    auto tokens = result.value();
} else {
    // Error - handle result.error()
    auto error = result.error();
    std::cerr << "Parse error: " << error.message << std::endl;
}
```

### Python Error Handling

The Python API uses custom exception classes:

```python
try:
    result = calculator.generate_audio_array("sin(2*pi*x)", duration_s=2.0, ...)
except MathSecurityError as e:
    print(f"Security error: {e}")
except MathEvaluationError as e:
    print(f"Evaluation error: {e}")
except MathDomainError as e:
    print(f"Domain error: {e}")
```

**Exception Hierarchy:**
- `FreqMathError` (base class)
  - `MathSecurityError` - Security/compilation issues
  - `MathEvaluationError` - Evaluation failures
  - `MathDomainError` - Domain/parameter issues

---

## Examples

### C++ Examples

#### Basic Equation Parsing

```cpp
#include "equation_parser.h"
#include "math_evaluator.h"

int main() {
    freq_math::MathEnvironment env;
    env.set_variable("x", 1.0);
    
    // Parse equation
    auto parse_result = freq_math::EquationParser::parse("sin(2*pi*x)", env);
    if (!parse_result) {
        std::cerr << "Parse error: " << parse_result.error().message << std::endl;
        return 1;
    }
    
    // Compile to bytecode
    auto compile_result = freq_math::MathCompiler::compile(parse_result.value());
    if (!compile_result) {
        std::cerr << "Compile error: " << compile_result.error().message << std::endl;
        return 1;
    }
    
    // Evaluate
    auto eval_result = freq_math::MathEvaluator::evaluate(
        compile_result.value(), 1.0, env);
    if (eval_result) {
        std::cout << "Result: " << eval_result.value() << std::endl;
    }
    
    return 0;
}
```

#### Audio Generation

```cpp
#include "audio_mapper.h"

int main() {
    // Generate math values
    std::vector<double> math_values;
    for (int i = 0; i < 44100; ++i) {
        double x = static_cast<double>(i) / 44100.0;
        math_values.push_back(std::sin(2.0 * M_PI * 440.0 * x));
    }
    
    // Convert to audio
    freq_math::AudioConfig config;
    config.base_frequency = 440.0;
    config.duration_seconds = 1.0;
    
    auto audio_result = freq_math::AudioMapper::map_to_audio(
        math_values, freq_math::Waveform::Sine, config);
    
    if (audio_result) {
        const auto& audio = audio_result.value();
        std::cout << "Generated " << audio.size() << " audio samples" << std::endl;
    }
    
    return 0;
}
```

### Python Examples

#### Basic Usage

```python
from src.python.freq_math_calculator import FreqMathCalculator, MappingMode

# Create calculator
calc = FreqMathCalculator(sample_rate=44100)

# Generate math function
math_array = calc.generate_math_array(
    "sin(2*pi*x) + 0.5*sin(4*pi*x)",
    x_range=(0.0, 1.0),
    steps=1000
)

# Generate audio
audio_array = calc.generate_audio_array(
    "sin(2*pi*x) + 0.5*sin(4*pi*x)",
    duration_s=2.0,
    x_range=(0.0, 1.0),
    base_frequency_hz=440.0,
    mode=MappingMode.FM_SINE
)

print(f"Generated {len(audio_array)} audio samples")
```

#### Advanced Usage with Custom Parameters

```python
from src.python.freq_math_calculator import FreqMathCalculator, MathParameters

# Create calculator with custom parameters
params = MathParameters(A=0.8, f=880.0, alpha=0.2)
calc = FreqMathCalculator(sample_rate=44100)

# Use parameters in equation
equation = "A * sin(2*pi*f*x) * exp(-alpha*x)"
audio = calc.generate_audio_array(
    equation,
    duration_s=3.0,
    x_range=(0.0, 1.0),
    base_frequency_hz=440.0,
    mode=MappingMode.DIRECT
)

# Get equation analysis
info = calc.get_equation_info(equation)
print(f"Complexity score: {info['metadata']['complexity_score']}")
print(f"Is safe: {info['metadata']['is_safe']}")
```

#### Using Presets

```python
from src.python.freq_math_calculator import FreqMathCalculator, BuiltinEquation

calc = FreqMathCalculator()

# List available presets
presets = calc.list_presets()
for name, equation in presets.items():
    print(f"{name}: {equation}")

# Use a preset
audio = calc.generate_audio_array(
    BuiltinEquation.FM_WOBBLE.value,
    duration_s=2.0,
    x_range=(0.0, 1.0),
    base_frequency_hz=440.0,
    mode=MappingMode.FM_SINE
)
```

---

This API reference provides comprehensive documentation for all public interfaces in the Freq-Math project. For more detailed examples and tutorials, see the [User Guide](user-guide.md) and [Developer Documentation](developer-guide.md).

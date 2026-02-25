# User Guide

Welcome to the Freq-Math User Guide! This comprehensive guide will help you master mathematical equation sonification, from basic concepts to advanced techniques.

## Table of Contents

- [Getting Started](#getting-started)
- [Understanding Mathematical Sonification](#understanding-mathematical-sonification)
- [Basic Usage](#basic-usage)
- [Equation Syntax Guide](#equation-syntax-guide)
- [Audio Synthesis Modes](#audio-synthesis-modes)
- [Practical Examples](#practical-examples)
- [Advanced Techniques](#advanced-techniques)
- [Tips and Best Practices](#tips-and-best-practices)
- [Troubleshooting](#troubleshooting)

---

## Getting Started

### Installation Quick Start

1. **Clone and Build**:
```bash
git clone https://github.com/esskslifetech/freq-math.git
cd freq-math
make install && make build
```

2. **Launch Application**:
```bash
python main.py
```

3. **First Sound**:
   - Select "Sine Wave" from presets
   - Click "Generate & Play"
   - Listen to your first mathematical sound!

### Interface Overview

The Freq-Math interface consists of several key areas:

- **Equation Input**: Where you type mathematical expressions
- **Control Panel**: Adjust synthesis parameters
- **Visualization Area**: Three panels showing function, waveform, and spectrum
- **Preset Library**: Quick access to common equations
- **Export Options**: Save your creations

---

## Understanding Mathematical Sonification

### What is Mathematical Sonification?

Mathematical sonification is the process of converting mathematical functions and relationships into audible sound. In Freq-Math, we treat mathematical expressions as sound generators, where:

- **Function values** become **audio amplitudes**
- **Function shape** determines **timbre and character**
- **Function complexity** creates **rich harmonics**
- **Function parameters** control **sound characteristics**

### Why Sonify Mathematics?

1. **Pattern Recognition**: Ears can detect patterns that eyes might miss
2. **Intuitive Understanding**: Sound provides immediate feedback on mathematical behavior
3. **Educational Value**: Makes abstract concepts tangible
4. **Artistic Expression**: Creates unique soundscapes from mathematical beauty
5. **Scientific Analysis**: Audio feedback helps in data analysis

### Basic Concepts

#### Time Domain vs. Mathematical Domain

In traditional audio synthesis, we think in terms of time. In mathematical sonification:

```
Traditional:   amplitude = f(time)
Mathematical:   amplitude = f(mathematical_variable)
```

The mathematical variable (usually `x`) gets mapped to audio time, creating a direct relationship between mathematical behavior and sound.

#### Frequency Mapping

Different synthesis modes map mathematical values to audio parameters:

- **Direct Mapping**: Math values → Audio samples directly
- **Frequency Mapping**: Math values → Oscillator frequency
- **Amplitude Mapping**: Math values → Volume control
- **Phase Mapping**: Math values → Phase modulation

---

## Basic Usage

### Using Presets

Start with built-in presets to understand different sound types:

1. **Simple Waves**:
   - `Sine Wave`: Pure tone, fundamental frequency
   - `Square Wave`: Rich harmonics, digital character
   - `Triangle Wave`: Soft harmonics, mellow tone

2. **Complex Patterns**:
   - `FM Synthesis`: Frequency modulation for rich timbres
   - `Bell Curve`: Smooth envelope, percussive character
   - `Chirp Sweep`: Frequency sweep over time

3. **Mathematical Functions**:
   - `Harmonic Stack`: Multiple harmonics, organ-like sound
   - `Wave Packet`: Localized oscillation, bell-like
   - `Interference`: Beating patterns, phasing effects

### Creating Your First Equation

Try this step-by-step process:

1. **Start Simple**:
```
sin(2*pi*x)
```
This creates a pure sine wave at the base frequency.

2. **Add Harmonics**:
```
sin(2*pi*x) + 0.5*sin(4*pi*x)
```
Adds an octave harmonic for richer sound.

3. **Introduce Modulation**:
```
sin(2*pi*x + 0.5*sin(8*pi*x))
```
Creates vibrato effect through phase modulation.

4. **Add Envelope**:
```
exp(-3*x) * sin(2*pi*x*8)
```
Applies exponential decay for percussive sound.

### Parameter Controls

#### Duration
- **Range**: 0.1 to 30 seconds
- **Effect**: How long the sound plays
- **Tip**: Shorter durations for percussive sounds, longer for sustained tones

#### Base Frequency
- **Range**: 20 Hz to 8000 Hz
- **Effect**: Fundamental pitch of the sound
- **Tip**: 440 Hz = A4, 220 Hz = A3, etc.

#### X-Range
- **Range**: Mathematical domain to evaluate
- **Effect**: Which portion of the function to use
- **Tip**: (0,1) for standard functions, adjust for special cases

#### Mapping Mode
- **FM Sine**: Frequency modulation synthesis
- **AM Sine**: Amplitude modulation synthesis
- **Phase Distortion**: Phase modulation synthesis
- **Wavetable**: Function as waveform shape
- **Direct**: Direct sample mapping

---

## Equation Syntax Guide

### Basic Mathematical Operations

#### Arithmetic
```python
# Basic operations
x + y
x - y
x * y
x / y
x ^ y          # Exponentiation

# Implicit multiplication (no * needed)
2pi*x          # Same as 2*pi*x
3sin(440*t)    # Same as 3*sin(440*t)
```

#### Parentheses and Order
```python
# Standard order of operations
(x + y) * z
x ^ (y + z)

# Nested functions
sin(cos(x))
exp(-x^2)
```

### Functions

#### Trigonometric
```python
sin(x)          # Sine
cos(x)          # Cosine
tan(x)          # Tangent
asin(x)         # Arc sine
acos(x)         # Arc cosine
atan(x)         # Arc tangent
```

#### Exponential and Logarithmic
```python
exp(x)          # e^x
log(x)          # Natural logarithm
log2(x)         # Base-2 logarithm
log10(x)        # Base-10 logarithm
sqrt(x)         # Square root
```

#### Other Useful Functions
```python
abs(x)          # Absolute value
sign(x)         # Sign function (-1, 0, 1)
floor(x)        # Round down
ceil(x)         # Round up
round(x)        # Round to nearest
min(x, y)       # Minimum
max(x, y)       # Maximum
sinc(x)         # Sinc function
```

### Constants and Variables

#### Built-in Constants
```python
pi              # 3.14159...
e               # 2.71828...
tau             # 2*pi
```

#### Input Variables
```python
x, t, y         # All map to the same input (time/position)
```

#### Custom Parameters
```python
A, f, alpha, beta, l    # Customizable parameters
```

Usage example:
```python
A * sin(2*pi*f*x) * exp(-alpha*x)
```

### Advanced Syntax Features

#### Unicode Support
```python
π × r²          # Becomes: pi * r**2
e^(-x²/2)       # Becomes: exp(-x**2/2)
√(x² + y²)      # Becomes: sqrt(x**2 + y**2)
```

#### Scientific Notation
```python
1.5e-3          # 0.0015
2.998e8         # 299,800,000
```

#### Function Aliases
```python
Csin(x)         # Becomes: sin(x)
Ccos(x)         # Becomes: cos(x)
lambda          # Becomes: l (to avoid Python keyword)
```

---

## Audio Synthesis Modes

### FM Sine (Frequency Modulation)

**Concept**: Use the mathematical function to modulate the frequency of a sine wave oscillator.

**Best For**: Rich, evolving timbres, bell-like sounds, complex harmonics.

**How it Works**:
```
output = sin(2π × (base_freq + math_function) × time)
```

**Examples**:
```python
# Simple FM
sin(2*pi*440*x + 5*sin(2*pi*100*x))

# Complex FM with envelope
exp(-2*x) * sin(2*pi*440*x + 10*sin(2*pi*200*x))

# Cascading FM
sin(2*pi*440*x + 5*sin(2*pi*100*x + 2*sin(2*pi*50*x)))
```

### AM Sine (Amplitude Modulation)

**Concept**: Use the mathematical function to control the amplitude of a sine wave.

**Best For**: Tremolo effects, rhythmic patterns, dynamic swells.

**How it Works**:
```
output = math_function × sin(2π × base_freq × time)
```

**Examples**:
```python
# Simple tremolo
(0.5 + 0.5*sin(2*pi*5*x)) * sin(2*pi*440*x)

# Rhythmic gating
sign(sin(2*pi*8*x)) * sin(2*pi*440*x)

# Crossfade
exp(-abs(x-0.5)*10) * sin(2*pi*440*x)
```

### Phase Distortion

**Concept**: Use the mathematical function to distort the phase of a sine wave oscillator.

**Best For**: Metallic sounds, inharmonic content, digital artifacts.

**How it Works**:
```
output = sin(2π × base_freq × (time + math_function))
```

**Examples**:
```python
# Simple phase distortion
sin(2*pi*440*(x + 0.1*sin(2*pi*1000*x)))

# Complex phase modulation
sin(2*pi*440*(x + 0.2*sin(2*pi*x)*cos(2*pi*5*x)))

# Glitchy digital effect
sin(2*pi*440*(x + 0.5*sign(sin(2*pi*1000*x))))
```

### Wavetable

**Concept**: Use the mathematical function to define the shape of a waveform.

**Best For**: Custom timbres, organic sounds, unique character.

**How it Works**:
```
wavetable = math_function evaluated over one period
output = wavetable[phase_index]
```

**Examples**:
```python
# Custom waveform
sin(2*pi*x) + 0.3*sin(6*pi*x) + 0.1*sin(10*pi*x)

# Asymmetric wave
sin(2*pi*x) * (1 + 0.5*sin(2*pi*x))

# Noise-like texture
sin(2*pi*x) + 0.1*sin(20*pi*x) + 0.05*sin(50*pi*x)
```

### Direct

**Concept**: Directly map mathematical values to audio samples.

**Best For**: Experimental sounds, data sonification, raw mathematical audio.

**How it Works**:
```
output = math_function
```

**Examples**:
```python
# Direct mathematical function
sin(2*pi*x) + 0.5*sin(4*pi*x) + 0.25*sin(8*pi*x)

# Chaotic system
x*(1-x)  # Logistic map (scaled appropriately)

# Fractal pattern
sin(2*pi*x) * sin(2*pi*x*x*10)
```

---

## Practical Examples

### Musical Instruments

#### Piano-like Tone
```python
# Harmonic series with envelope
exp(-2*x) * (sin(2*pi*x) + 0.5*sin(4*pi*x) + 0.25*sin(6*pi*x))
```

#### Brass Sound
```python
# Bright harmonics with slow attack
(1-exp(-5*x)) * (sin(2*pi*x) + 0.7*sin(3*pi*x) + 0.5*sin(5*pi*x))
```

#### String Sound
```python
# Inharmonic partials with sustain
exp(-0.5*x) * (sin(2*pi*x) + 0.8*sin(2.01*pi*x) + 0.6*sin(3*pi*x))
```

### Sound Effects

#### Explosion
```python
exp(-10*x) * sin(2*pi*x*50) * (1 + 0.5*random())
```

#### Laser Beam
```python
exp(-x) * sin(2*pi*x*1000 + 10*sin(2*pi*x*100))
```

#### Wind
```python
sin(2*pi*x*200 + 5*sin(2*pi*x*10)) * exp(-0.1*x)
```

### Mathematical Concepts

#### Interference Pattern
```python
sin(2*pi*x*440) + sin(2*pi*x*442)  # 2 Hz beating
```

#### Standing Wave
```python
sin(2*pi*x*10) * cos(2*pi*x)  # Modulated carrier
```

#### Chaos Theory
```python
# Lorenz attractor projection (simplified)
sin(2*pi*x) + 0.1*sin(20*pi*x) + 0.01*sin(200*pi*x)
```

### Experimental Sounds

#### Granular Texture
```python
sign(sin(2*pi*x*1000)) * exp(-abs(x-0.5)*20)
```

#### Spectral Evolution
```python
exp(-x*2) * sin(2*pi*x*(100 + 900*x))
```

#### Phase Vocoder Effect
```python
sin(2*pi*x*440 + 5*sin(2*pi*x*20)*sin(2*pi*x*200))
```

---

## Advanced Techniques

### Parameter Automation

Create dynamic sounds by using parameters that change over time:

```python
# Frequency sweep
A*sin(2*pi*(f + 100*x)*x)

# Amplitude modulation
(0.5 + 0.5*sin(2*pi*alpha*x)) * sin(2*pi*f*x)

# Filter sweep
sin(2*pi*f*x) * exp(-beta*x*x)
```

### Multi-layer Synthesis

Combine multiple synthesis techniques:

```python
# Layer 1: Bass
0.5*sin(2*pi*55*x)

# Layer 2: Midrange
0.3*sin(2*pi*220*x + 2*sin(2*pi*10*x))

# Layer 3: High frequencies
0.2*sin(2*pi*880*x + 5*sin(2*pi*50*x))

# Combined
0.5*sin(2*pi*55*x) + 0.3*sin(2*pi*220*x + 2*sin(2*pi*10*x)) + 0.2*sin(2*pi*880*x + 5*sin(2*pi*50*x))
```

### Mathematical Transformations

Apply mathematical operations to create variations:

```python
# Frequency doubling
sin(2*pi*x*2)  # Octave up

# Frequency halving
sin(2*pi*x/2)  # Octave down

# Inversion
1 - sin(2*pi*x)  # Phase inversion

# Rectification
abs(sin(2*pi*x))  # Full-wave rectification
```

### Envelope Design

Create custom envelope shapes:

```python
# ADSR envelope
attack = (1-exp(-x*20)) * (x < 0.05)
decay = exp(-(x-0.05)*10) * (x >= 0.05) * (x < 0.15)
sustain = 0.7 * (x >= 0.15) * (x < 0.8)
release = exp(-(x-0.8)*20) * (x >= 0.8)
envelope = attack + decay + sustain + release

# Apply to sound
envelope * sin(2*pi*440*x)
```

---

## Tips and Best Practices

### Sound Design Tips

1. **Start Simple**: Begin with basic sine waves and add complexity gradually
2. **Use Presets**: Learn from built-in examples before creating your own
3. **Listen Carefully**: Pay attention to both the sound and the visualization
4. **Experiment**: Try unusual mathematical combinations for unique sounds
5. **Save Good Results**: Export interesting sounds for later use

### Mathematical Tips

1. **Understand Domains**: Know where functions are defined and well-behaved
2. **Avoid Singularities**: Functions like `1/x` can cause problems at x=0
3. **Scale Appropriately**: Keep function values in reasonable ranges (-1 to 1)
4. **Use Envelopes**: Apply exponential decay for more natural sounds
5. **Combine Functions**: Mix different mathematical behaviors

### Performance Tips

1. **Keep Equations Reasonable**: Very complex equations can be slow to evaluate
2. **Use Appropriate Durations**: Longer durations require more computation
3. **Cache Results**: Save frequently used equations as presets
4. **Monitor Resources**: Watch memory usage with large arrays

### Creative Workflow

1. **Define Your Goal**: What kind of sound are you trying to create?
2. **Choose Base Function**: Start with an appropriate mathematical foundation
3. **Add Modulation**: Introduce time-varying elements
4. **Apply Envelope**: Shape the amplitude over time
5. **Refine and Iterate**: Adjust parameters and listen critically

---

## Troubleshooting

### Common Issues

#### No Sound Output

**Symptoms**: Visualization shows but no audio plays

**Solutions**:
1. Check audio system: `python -c "import pyaudio; print('Audio OK')"`
2. Install audio dependencies: `pip install pyaudio portaudio`
3. Try file output: Add `--output test.wav` to command line
4. Check system volume and audio settings

#### Equation Errors

**Symptoms**: Red error message, no sound generated

**Common Causes**:
1. **Syntax Error**: Check parentheses, operators, function names
2. **Division by Zero**: Avoid expressions like `1/x` when x might be 0
3. **Invalid Functions**: Use only supported mathematical functions
4. **Complexity Limit**: Equation too complex for security limits

**Debugging Steps**:
1. Start with a simple equation: `sin(2*pi*x)`
2. Add complexity gradually
3. Check the error message for specific issues
4. Use the validation feature before generating

#### Performance Issues

**Symptoms**: Slow response, laggy interface

**Solutions**:
1. Reduce duration: Try shorter time periods
2. Simplify equation: Remove unnecessary complexity
3. Close other applications: Free up system resources
4. Check system specifications: Ensure adequate CPU/RAM

#### Visualization Problems

**Symptoms**: Plots don't update or show incorrect data

**Solutions**:
1. Refresh display: Close and reopen the application
2. Check equation: Ensure it produces reasonable values
3. Adjust plot ranges: Modify x-range for better visualization
4. Restart application: Clear any cached state

### Getting Help

#### Documentation Resources
- **API Reference**: Detailed function and class documentation
- **Developer Guide**: Advanced customization and extension
- **Test Suite**: Examples of proper usage patterns

#### Community Support
- **GitHub Issues**: Report bugs and request features
- **GitHub Discussions**: Ask questions and share experiences
- **Example Gallery**: Community-created equations and sounds

#### Debug Mode

Enable debug output for troubleshooting:

```bash
python main.py --debug --equation "sin(2*pi*x)"
```

This provides detailed information about:
- Equation parsing and compilation
- Audio generation process
- Performance metrics
- Error details

---

## Next Steps

Now that you've mastered the basics, explore these advanced topics:

1. **Custom Audio Effects**: Create your own synthesis algorithms
2. **Real-time Control**: Use MIDI controllers for live performance
3. **Data Sonification**: Convert real-world data into sound
4. **Educational Applications**: Use Freq-Math for teaching mathematics
5. **Artistic Projects**: Create musical compositions and sound art

Remember that mathematical sonification is both a science and an art. Experiment freely, learn from your results, and don't be afraid to try unconventional approaches. The beauty of Freq-Math is in its ability to reveal the hidden musical qualities of mathematics.

Happy sonifying! 🎵✨

#pragma once

#include <span>
#include <vector>
#include "expected.h"
#include <string>
#include <numbers>

namespace freq_math {

// ============================================================================
// 1. DOMAIN MODELS & CONTRACTS
// ============================================================================

using AudioSample = double;
using AudioBuffer = std::vector<AudioSample>;

// Modern C++20 Designated Initializers
struct AudioConfig {
    double base_frequency{440.0};
    double amplitude_scale{1.0};
    double duration_seconds{1.0};
    int sample_rate{44100};
    bool auto_normalize{true};
};

struct AdsrConfig {
    double attack_sec{0.05};
    double decay_sec{0.1};
    double sustain_level{0.7};
    double release_sec{0.2};
};

// Strongly typed operations (No more strings)
enum class MathOperation { Add, Subtract, Multiply, Divide, Power, Unary };

// Fun Feature: Multi-oscillator synthesis
enum class Waveform { Sine, Square, Sawtooth, Triangle };

struct AudioError {
    std::string message;
};

// ============================================================================
// 2. STATELESS AUDIO TRANSLATOR & SYNTHESIZER
// ============================================================================

class AudioMapper {
public:
    // Pure Function: Maps abstract mathematical results to an audible waveform.
    // Highly concurrent, thread-safe beyond memory bounds.
    [[nodiscard]] static freq_math::expected<AudioBuffer, AudioError>
    map_to_audio(std::span<const double> math_values, 
                 Waveform wave_type = Waveform::Sine,
                 const AudioConfig& config = {}) noexcept;

    // Advanced FM Synthesis: Modulates carrier frequency using external arrays.
    // Uses Massively Parallel Inclusive Scans.
    [[nodiscard]] static freq_math::expected<AudioBuffer, AudioError>
    generate_fm_signal(std::span<const double> carrier_freqs,
                       std::span<const double> modulator_freqs,
                       const AudioConfig& config) noexcept;

    // In-Place mutation to avoid unnecessary memory allocations
    static void apply_envelope_inplace(std::span<AudioSample> buffer, 
                                       int sample_rate, 
                                       const AdsrConfig& adsr) noexcept;

    // O(1) Branchless Translators
    [[nodiscard]] static double map_operation_to_frequency(MathOperation op, double base_freq) noexcept;
    [[nodiscard]] static double map_magnitude_to_amplitude(double magnitude) noexcept;

private:
    // Expert-Level DSP Primitives
    [[nodiscard]] static double generate_oscillator_sample(Waveform wave, double phase) noexcept;
    
    // Helper to compute phases in parallel across all CPU cores
    static void calculate_phases_parallel(std::span<const double> frequencies, 
                                          std::span<double> out_phases, 
                                          int sample_rate) noexcept;
    
    static void normalize_buffer_inplace(std::span<AudioSample> buffer) noexcept;
};

} // namespace freq_math
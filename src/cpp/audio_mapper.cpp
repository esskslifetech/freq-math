#include "audio_mapper.h"
#include <cmath>
#include <numbers>
#include <algorithm>

namespace freq_math {

// ============================================================================
// AudioMapper Implementation
// ============================================================================

freq_math::expected<AudioBuffer, AudioError>
AudioMapper::map_to_audio(std::span<const double> math_values, 
                         Waveform wave_type,
                         const AudioConfig& config) noexcept {
    if (math_values.empty()) {
        return freq_math::unexpected(AudioError{"Empty input values"});
    }
    
    if (config.sample_rate <= 0 || config.duration_seconds <= 0.0) {
        return freq_math::unexpected(AudioError{"Invalid audio configuration"});
    }
    
    AudioBuffer buffer;
    buffer.reserve(math_values.size());
    
    const double two_pi = 2.0 * std::numbers::pi;
    
    for (size_t i = 0; i < math_values.size(); ++i) {
        double t = static_cast<double>(i) / config.sample_rate;
        double freq = math_values[i];
        double sample = 0.0;
        
        switch (wave_type) {
            case Waveform::Sine:
                sample = std::sin(two_pi * freq * t);
                break;
            case Waveform::Square:
                sample = (std::sin(two_pi * freq * t) > 0.0) ? 1.0 : -1.0;
                break;
            case Waveform::Sawtooth: {
                double phase = std::fmod(freq * t, 1.0);
                sample = 2.0 * phase - 1.0;
                break;
            }
            case Waveform::Triangle: {
                double phase = std::fmod(freq * t, 1.0);
                sample = (phase < 0.5) ? (4.0 * phase - 1.0) : (-4.0 * phase + 3.0);
                break;
            }
        }
        
        // Apply amplitude scaling
        sample *= config.amplitude_scale;
        
        // Apply soft clipping to prevent overflow
        sample = std::tanh(sample);
        
        buffer.push_back(sample);
    }
    
    return buffer;
}

freq_math::expected<AudioBuffer, AudioError>
AudioMapper::generate_fm_signal(std::span<const double> carrier_freqs,
                               std::span<const double> modulator_freqs,
                               const AudioConfig& config) noexcept {
    if (carrier_freqs.empty() || modulator_freqs.empty()) {
        return freq_math::unexpected(AudioError{"Empty frequency arrays"});
    }
    
    if (carrier_freqs.size() != modulator_freqs.size()) {
        return freq_math::unexpected(AudioError{"Carrier and modulator arrays must have same size"});
    }
    
    AudioBuffer buffer;
    buffer.reserve(carrier_freqs.size());
    
    const double two_pi = 2.0 * std::numbers::pi;
    const double modulation_index = 2.0; // FM modulation depth
    
    for (size_t i = 0; i < carrier_freqs.size(); ++i) {
        double t = static_cast<double>(i) / config.sample_rate;
        double carrier_freq = carrier_freqs[i];
        double modulator_freq = modulator_freqs[i];
        
        // FM synthesis: carrier frequency modulated by modulator
        double phase = two_pi * carrier_freq * t + 
                      modulation_index * std::sin(two_pi * modulator_freq * t);
        
        double sample = std::sin(phase) * config.amplitude_scale;
        sample = std::tanh(sample); // Soft clipping
        
        buffer.push_back(sample);
    }
    
    return buffer;
}

void AudioMapper::apply_envelope_inplace(std::span<AudioSample> buffer, 
                                       int sample_rate, 
                                       const AdsrConfig& adsr) noexcept {
    if (buffer.empty()) return;
    
    const size_t total_samples = buffer.size();
    const double attack_samples = adsr.attack_sec * sample_rate;
    const double decay_samples = adsr.decay_sec * sample_rate;
    const double sustain_samples = adsr.sustain_level * sample_rate;
    const double release_samples = adsr.release_sec * sample_rate;
    
    for (size_t i = 0; i < total_samples; ++i) {
        double envelope = 0.0;
        
        if (i < attack_samples) {
            // Attack phase: linear ramp from 0 to 1
            envelope = i / attack_samples;
        } else if (i < attack_samples + decay_samples) {
            // Decay phase: linear ramp from 1 to sustain_level
            double decay_progress = (i - attack_samples) / decay_samples;
            envelope = 1.0 - decay_progress * (1.0 - adsr.sustain_level);
        } else if (i < attack_samples + decay_samples + sustain_samples) {
            // Sustain phase: constant at sustain_level
            envelope = adsr.sustain_level;
        } else {
            // Release phase: linear ramp from sustain_level to 0
            double release_progress = (i - attack_samples - decay_samples - sustain_samples) / release_samples;
            envelope = adsr.sustain_level * (1.0 - release_progress);
        }
        
        buffer[i] *= envelope;
    }
}

double AudioMapper::map_operation_to_frequency(MathOperation op, double base_freq) noexcept {
    switch (op) {
        case MathOperation::Add:
            return base_freq * 1.5;      // Raise frequency for addition
        case MathOperation::Subtract:
            return base_freq * 0.75;     // Lower frequency for subtraction
        case MathOperation::Multiply:
            return base_freq * 2.0;      // Double frequency for multiplication
        case MathOperation::Divide:
            return base_freq * 0.5;      // Halve frequency for division
        case MathOperation::Power:
            return base_freq * 3.0;      // Triple frequency for exponentiation
        default:
            return base_freq;            // Default to base frequency
    }
}

} // namespace freq_math

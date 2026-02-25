/**
 * @file bindings.cpp
 * @brief High-Performance PyBind11 Integration Layer.
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <pybind11/functional.h>

#include <span>
#include <vector>
#include <utility>

#include "math_evaluator.h"
#include "audio_mapper.h"
#include "equation_parser.h"

namespace py = pybind11;
using namespace freq_math;

// ==============================================================================
// Memory Management Utilities (Zero-Copy Architecture)
// ==============================================================================

/**
 * @brief Zero-Copy Python to C++ Bridge.
 */
inline std::span<const double> as_span(const py::array_t<double, py::array::c_style | py::array::forcecast>& arr) {
    py::buffer_info info = arr.request();
    return std::span<const double>(static_cast<const double*>(info.ptr), info.size);
}

/**
 * @brief Zero-Copy C++ to Python Bridge.
 */
inline py::array_t<double> as_numpy_zerocopy(std::vector<double>&& vec) {
    auto* ptr = new std::vector<double>(std::move(vec));
    
    py::capsule free_when_done(ptr, [](void* p) {
        delete reinterpret_cast<std::vector<double>*>(p);
    });

    return py::array_t<double>(
        {ptr->size()},
        {sizeof(double)},
        ptr->data(),
        free_when_done
    );
}

// ==============================================================================
// PyBind11 Module Registration
// ==============================================================================

PYBIND11_MODULE(freq_math_bindings, m) {
    m.doc() = "High-Performance C++ Audio DSP & Mathematical Evaluation Engine";
    
    // --------------------------------------------------------------------------
    // Data Structures
    // --------------------------------------------------------------------------
    
    py::class_<AudioConfig>(m, "AudioConfig")
        .def(py::init<>())
        .def_readwrite("base_frequency", &AudioConfig::base_frequency)
        .def_readwrite("amplitude_scale", &AudioConfig::amplitude_scale)
        .def_readwrite("duration_seconds", &AudioConfig::duration_seconds)
        .def_readwrite("sample_rate", &AudioConfig::sample_rate)
        .def_readwrite("auto_normalize", &AudioConfig::auto_normalize);
    
    py::class_<AdsrConfig>(m, "AdsrConfig")
        .def(py::init<>())
        .def_readwrite("attack_sec", &AdsrConfig::attack_sec)
        .def_readwrite("decay_sec", &AdsrConfig::decay_sec)
        .def_readwrite("sustain_level", &AdsrConfig::sustain_level)
        .def_readwrite("release_sec", &AdsrConfig::release_sec);
    
    py::enum_<Waveform>(m, "Waveform")
        .value("Sine", Waveform::Sine)
        .value("Square", Waveform::Square)
        .value("Sawtooth", Waveform::Sawtooth)
        .value("Triangle", Waveform::Triangle);
    
    py::enum_<MathOperation>(m, "MathOperation")
        .value("Add", MathOperation::Add)
        .value("Subtract", MathOperation::Subtract)
        .value("Multiply", MathOperation::Multiply)
        .value("Divide", MathOperation::Divide)
        .value("Power", MathOperation::Power);
    
    // --------------------------------------------------------------------------
    // Mathematical Evaluation Engine
    // --------------------------------------------------------------------------
    
    py::class_<MathEnvironment>(m, "MathEnvironment")
        .def(py::init<>())
        .def("set_variable", &MathEnvironment::set_variable)
        .def("get_variable", &MathEnvironment::get_variable)
        .def("register_function", &MathEnvironment::register_function)
        .def("is_function", &MathEnvironment::is_function);
    
    // MathEvaluator is static-only, so we expose its methods as module functions
    m.def("evaluate_expression", [](const std::string& equation, double x, MathEnvironment& env) {
        auto tokens = EquationParser::parse(equation, env);
        if (!tokens) {
            throw std::runtime_error("Parse error: " + tokens.error().message);
        }
        
        auto compiled = MathCompiler::compile(*tokens);
        if (!compiled) {
            throw std::runtime_error("Compilation error: " + compiled.error().message);
        }
        
        auto result = MathEvaluator::evaluate(*compiled, x, env);
        if (!result) {
            throw std::runtime_error("Evaluation error: " + result.error().message);
        }
        
        return result.value();
    }, py::arg("equation"), py::arg("x") = 0.0, py::arg("env"));
    
    m.def("evaluate_range", [](const std::string& equation, double start, double end, size_t steps, MathEnvironment& env) {
        auto tokens = EquationParser::parse(equation, env);
        if (!tokens) {
            throw std::runtime_error("Parse error: " + tokens.error().message);
        }
        
        auto compiled = MathCompiler::compile(*tokens);
        if (!compiled) {
            throw std::runtime_error("Compilation error: " + compiled.error().message);
        }
        
        auto result = MathEvaluator::evaluate_range(*compiled, start, end, steps, env);
        if (!result) {
            throw std::runtime_error("Evaluation error: " + result.error().message);
        }
        
        return as_numpy_zerocopy(std::move(result.value()));
    }, py::arg("equation"), py::arg("start"), py::arg("end"), py::arg("steps"), py::arg("env"),
       py::call_guard<py::gil_scoped_release>());
    
    // --------------------------------------------------------------------------
    // Audio Generation Engine
    // --------------------------------------------------------------------------
    
    // AudioMapper is also static-only
    m.def("map_to_audio", [](const py::array_t<double>& math_values, Waveform wave_type, const AudioConfig& config) {
        auto span = as_span(math_values);
        auto result = AudioMapper::map_to_audio(span, wave_type, config);
        if (!result) {
            throw std::runtime_error("Audio mapping error: " + result.error().message);
        }
        return as_numpy_zerocopy(std::move(result.value()));
    }, py::arg("math_values"), py::arg("wave_type") = Waveform::Sine, py::arg("config"));
    
    m.def("generate_fm_signal", [](const py::array_t<double>& carrier_freqs, const py::array_t<double>& modulator_freqs, const AudioConfig& config) {
        auto carrier_span = as_span(carrier_freqs);
        auto modulator_span = as_span(modulator_freqs);
        auto result = AudioMapper::generate_fm_signal(carrier_span, modulator_span, config);
        if (!result) {
            throw std::runtime_error("FM synthesis error: " + result.error().message);
        }
        return as_numpy_zerocopy(std::move(result.value()));
    }, py::arg("carrier_freqs"), py::arg("modulator_freqs"), py::arg("config"));
    
    m.def("apply_envelope_inplace", [](py::array_t<double>& buffer, int sample_rate, const AdsrConfig& adsr) {
        py::buffer_info info = buffer.request();
        std::span<double> span(static_cast<double*>(info.ptr), info.size);
        AudioMapper::apply_envelope_inplace(span, sample_rate, adsr);
    }, py::arg("buffer"), py::arg("sample_rate"), py::arg("adsr"));
    
    m.def("map_operation_to_frequency", &AudioMapper::map_operation_to_frequency,
         py::arg("operation"), py::arg("base_frequency"));
}

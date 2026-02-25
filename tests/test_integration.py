#!/usr/bin/env python3
"""
Integration tests for the complete Freq-Math system
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import numpy as np
import tempfile
import wave
from pathlib import Path

try:
    from freq_math_calculator import FreqMathCalculator, MathParameters
    FREQ_MATH_AVAILABLE = True
except ImportError as e:
    print(f"FreqMathCalculator not available: {e}")
    FREQ_MATH_AVAILABLE = False

try:
    from audio_synthesizer import AudioSynthesizer, AudioConfig
    AUDIO_SYNTH_AVAILABLE = True
except ImportError as e:
    print(f"AudioSynthesizer not available: {e}")
    AUDIO_SYNTH_AVAILABLE = False

class TestFreqMathIntegration(unittest.TestCase):
    """Integration tests for FreqMathCalculator"""
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_end_to_end_equation_processing(self):
        """Test complete equation processing pipeline"""
        calculator = FreqMathCalculator()
        
        # Test various equation formats
        equations = [
            "sin(2*pi*f*t)",
            "y(t)=A*sin(2*pi*f*t)",
            "f(x)=exp(-3*x)*sin(2*pi*880*x)",
            "sin(x) + (1/2)*sin(2*x) + (1/3)*sin(3*x)",
        ]
        
        for equation in equations:
            with self.subTest(equation=equation):
                # Compile equation
                compiled = calculator.compile_equation(equation)
                self.assertIsNotNone(compiled)
                self.assertTrue(compiled.metadata.is_safe)
                
                # Generate math array
                math_array = calculator.generate_math_array(equation, steps=100)
                self.assertEqual(len(math_array), 100)
                self.assertTrue(np.all(np.isfinite(math_array)))
                
                # Generate audio array
                audio_array = calculator.generate_audio_array(equation, duration_s=0.1)
                expected_samples = int(0.1 * calculator.sample_rate)
                self.assertEqual(len(audio_array), expected_samples)
                self.assertTrue(np.all(np.isfinite(audio_array)))
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_custom_parameters(self):
        """Test equation processing with custom parameters"""
        calculator = FreqMathCalculator()
        params = MathParameters(A=0.8, f=880.0, alpha=0.2, beta=0.3)
        
        # Test equation with custom parameters
        equation = "A*sin(2*pi*f*x)"
        math_array = calculator.generate_math_array(equation, steps=10, params=params)
        
        # Verify custom parameters are used
        # At x=0, sin(0) = 0, so result should be 0 regardless of A
        self.assertAlmostEqual(math_array[0], 0.0, places=5)
        
        # At x=0.25, sin(pi/2) = 1, so result should be A
        expected = 0.8 * np.sin(2 * np.pi * 880.0 * 0.25)
        actual = math_array[int(0.25 * 9)]  # Approximate index
        self.assertAlmostEqual(actual, expected, places=1)
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_polyphonic_chord_integration(self):
        """Test polyphonic chord generation"""
        calculator = FreqMathCalculator()
        
        chord = calculator.create_polyphonic_chord(
            "sin(x)",
            duration_s=0.1,
            root_frequency_hz=220.0
        )
        
        expected_samples = int(0.1 * calculator.sample_rate)
        self.assertEqual(len(chord), expected_samples)
        self.assertTrue(np.all(np.isfinite(chord)))
        self.assertLessEqual(np.max(np.abs(chord)), 1.0)
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_equation_analysis_integration(self):
        """Test equation analysis functionality"""
        calculator = FreqMathCalculator()
        
        equation = "A*sin(2*pi*f*x) + exp(-alpha*x)"
        info = calculator.get_equation_info(equation)
        
        self.assertIn("equation", info)
        self.assertIn("metadata", info)
        self.assertIn("min_result", info)
        self.assertIn("max_result", info)
        self.assertIn("span", info)
        
        # Check metadata
        metadata = info["metadata"]
        self.assertIn("operations", metadata)
        self.assertIn("functions", metadata)
        self.assertIn("complexity_score", metadata)
        
        # Should detect sin and exp functions
        functions = set(metadata["functions"])
        self.assertIn("sin", functions)
        self.assertIn("exp", functions)
        
        # Should detect arithmetic operations
        operations = set(metadata["operations"])
        self.assertIn("*", operations)
        self.assertIn("+", operations)

class TestAudioSynthesizerIntegration(unittest.TestCase):
    """Integration tests for AudioSynthesizer"""
    
    @unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "AudioSynthesizer not available")
    def test_complete_audio_pipeline(self):
        """Test complete audio synthesis pipeline"""
        config = AudioConfig(sample_rate=44100, channels=2)
        
        with AudioSynthesizer(config) as synth:
            # Generate test signal
            signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
            
            # Render to PCM
            pcm_bytes, frames = synth.render_pcm16_bytes(signal)
            
            self.assertIsInstance(pcm_bytes, bytes)
            self.assertEqual(frames, len(signal))
            self.assertGreater(len(pcm_bytes), 0)
            
            # Play/export (should work with file backend)
            handle = synth.play(signal, blocking=True)
            
            self.assertIsNotNone(handle)
            self.assertTrue(handle.wait(timeout=5.0))
    
    @unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "AudioSynthesizer not available")
    def test_effects_pipeline(self):
        """Test audio effects pipeline"""
        config = AudioConfig(sample_rate=44100)
        
        with AudioSynthesizer(config) as synth:
            # Generate base signal
            signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
            
            # Apply effects
            from audio_synthesizer import DSP
            effects = [
                lambda x: DSP.overdrive(x, drive=2.0),
                lambda x: DSP.bitcrush(x, bits=8),
                lambda x: DSP.ring_mod(x, sample_rate=44100, mod_freq=10.0),
            ]
            
            # Render with effects
            pcm_bytes, frames = synth.render_pcm16_bytes(signal, effects=effects)
            
            self.assertIsInstance(pcm_bytes, bytes)
            self.assertEqual(frames, len(signal))

class TestFullSystemIntegration(unittest.TestCase):
    """Full system integration tests"""
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_math_to_audio_pipeline(self):
        """Test complete math equation to audio pipeline"""
        calculator = FreqMathCalculator()
        
        # Complex mathematical equation
        equation = "A*exp(-beta*x)*sin(2*pi*f*x) + (1-A)*cos(2*pi*f*2*x)"
        
        # Generate math array
        math_array = calculator.generate_math_array(
            equation,
            steps=1000,
            params=MathParameters(A=0.7, f=440.0, beta=0.5)
        )
        
        # Verify math array properties
        self.assertEqual(len(math_array), 1000)
        self.assertTrue(np.all(np.isfinite(math_array)))
        
        # Generate audio array
        audio_array = calculator.generate_audio_array(
            equation,
            duration_s=0.1,
            base_frequency_hz=440.0,
            params=MathParameters(A=0.7, f=440.0, beta=0.5)
        )
        
        # Verify audio array properties
        expected_samples = int(0.1 * calculator.sample_rate)
        self.assertEqual(len(audio_array), expected_samples)
        self.assertTrue(np.all(np.isfinite(audio_array)))
        self.assertLessEqual(np.max(np.abs(audio_array)), 1.0)
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_error_propagation(self):
        """Test error handling and propagation"""
        calculator = FreqMathCalculator()
        
        # Test invalid equations
        invalid_equations = [
            "__import__('os')",
            "eval('1+1')",
            "open('file.txt')",
            "unknown_function(x)",
        ]
        
        for equation in invalid_equations:
            with self.subTest(equation=equation):
                with self.assertRaises(Exception):  # Should raise some kind of error
                    calculator.compile_equation(equation)
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_performance_characteristics(self):
        """Test performance characteristics"""
        import time
        
        calculator = FreqMathCalculator()
        
        # Test compilation performance
        equation = "A*sin(2*pi*f*x) + exp(-beta*x)"
        
        start_time = time.time()
        for _ in range(100):
            calculator.compile_equation(equation)
        compilation_time = time.time() - start_time
        
        # Should be reasonably fast (less than 1 second for 100 compilations)
        self.assertLess(compilation_time, 1.0)
        
        # Test evaluation performance
        compiled = calculator.compile_equation(equation)
        
        start_time = time.time()
        for _ in range(100):
            calculator.generate_math_array(equation, steps=1000)
        evaluation_time = time.time() - start_time
        
        # Should be reasonably fast (less than 1 second for 100 evaluations)
        self.assertLess(evaluation_time, 1.0)

class TestFileOutputIntegration(unittest.TestCase):
    """Test file output integration"""
    
    @unittest.skipUnless(FREQ_MATH_AVAILABLE, "FreqMathCalculator not available")
    def test_wav_file_output(self):
        """Test WAV file output integration"""
        calculator = FreqMathCalculator()
        
        # Generate audio
        equation = "sin(2*pi*440*x)"
        audio = calculator.generate_audio_array(equation, duration_s=0.1)
        
        # Test that we can write to a WAV file manually
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_path = Path(tmp.name)
        
        try:
            # Write WAV file
            import wave
            import struct
            
            with wave.open(str(temp_path), 'wb') as wav:
                wav.setnchannels(1)  # Mono
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(calculator.sample_rate)
                
                # Convert to int16
                pcm = (audio * 32767).astype(np.int16)
                wav.writeframes(pcm.tobytes())
            
            # Verify file was created and has correct properties
            self.assertTrue(temp_path.exists())
            
            with wave.open(str(temp_path), 'rb') as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), calculator.sample_rate)
                
                # Read back and verify
                data = wav.readframes(-1)
                read_pcm = np.frombuffer(data, dtype=np.int16)
                read_float = read_pcm.astype(np.float32) / 32767.0
                
                # Should be close to original (allowing for quantization)
                np.testing.assert_array_almost_equal(read_float, audio, decimal=3)
        
        finally:
            # Clean up
            if temp_path.exists():
                temp_path.unlink()

if __name__ == "__main__":
    unittest.main()

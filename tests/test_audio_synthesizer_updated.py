#!/usr/bin/env python3
"""
Updated test cases for audio synthesizer component (compatible with refactored codebase)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import numpy as np
import tempfile
from pathlib import Path

try:
    from audio_synthesizer import AudioSynthesizer, AudioConfig, DSP, Synthesis
    AUDIO_SYNTH_AVAILABLE = True
except ImportError as e:
    print(f"Audio synthesizer not available: {e}")
    AUDIO_SYNTH_AVAILABLE = False

@unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "Audio synthesizer not available")
class TestAudioSynthesizerUpdated(unittest.TestCase):
    def setUp(self):
        self.config = AudioConfig(sample_rate=44100)
        self.synthesizer = AudioSynthesizer(config=self.config)
    
    def tearDown(self):
        if hasattr(self, 'synthesizer') and self.synthesizer:
            self.synthesizer.close()
    
    def test_basic_tone_generation(self):
        """Test basic tone generation using Synthesis module"""
        tone = Synthesis.tone(
            self.config,
            frequency_hz=440.0,
            duration_s=0.1,
            waveform='sine'
        )
        
        # Check length
        expected_samples = int(0.1 * self.config.sample_rate)
        self.assertEqual(len(tone), expected_samples)
        
        # Check amplitude range
        self.assertLessEqual(np.max(np.abs(tone)), 1.0)
        
        # Check frequency (approximately)
        # Count zero crossings in first 0.01 seconds
        test_samples = int(0.01 * self.config.sample_rate)
        test_tone = tone[:test_samples]
        zero_crossings = np.sum(np.diff(np.sign(test_tone)) != 0)
        expected_crossings = int(440.0 * 0.01 * 2)  # 2 crossings per period
        
        # Allow some tolerance
        self.assertLess(abs(zero_crossings - expected_crossings), 5)
    
    def test_waveform_types(self):
        """Test different waveform types"""
        waveforms = ['sine', 'square', 'sawtooth', 'triangle', 'noise']
        
        for waveform in waveforms:
            with self.subTest(waveform=waveform):
                tone = Synthesis.tone(
                    self.config,
                    frequency_hz=440.0,
                    duration_s=0.01,
                    waveform=waveform
                )
                self.assertEqual(len(tone), int(0.01 * self.config.sample_rate))
                self.assertLessEqual(np.max(np.abs(tone)), 1.0)
    
    def test_dsp_operations(self):
        """Test DSP operations"""
        # Create test signal
        signal = np.array([1.0, 0.5, 0.0, -0.5, -1.0])
        
        # Test clipping
        clipped = DSP.clip(signal)
        self.assertLessEqual(np.max(np.abs(clipped)), 1.0)
        
        # Test normalization
        normalized = DSP.normalize_peak(signal)
        self.assertAlmostEqual(np.max(np.abs(normalized)), 1.0, places=5)
        
        # Test mono conversion
        stereo_signal = np.array([[1.0, 0.5], [0.3, -0.2]])
        mono = DSP.as_float_mono(stereo_signal)
        expected = np.array([0.75, 0.05])  # average of each channel
        np.testing.assert_array_almost_equal(mono, expected)
        
        # Test stereo conversion
        mono_signal = np.array([0.5, -0.5])
        stereo = DSP.ensure_channels(mono_signal, 2)
        self.assertEqual(stereo.shape, (2, 2))
        
        # Test PCM16 conversion
        pcm16 = DSP.to_pcm16(signal)
        self.assertEqual(pcm16.dtype, np.int16)
    
    def test_dsp_effects(self):
        """Test DSP effects"""
        signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
        
        # Test overdrive
        overdriven = DSP.overdrive(signal, drive=2.0)
        self.assertEqual(len(overdriven), len(signal))
        
        # Test bitcrush
        crushed = DSP.bitcrush(signal, bits=8)
        self.assertEqual(len(crushed), len(signal))
        
        # Test ring modulation
        modulated = DSP.ring_mod(signal, sample_rate=44100, mod_freq=10.0)
        self.assertEqual(len(modulated), len(signal))
        
        # Test delay
        delayed = DSP.delay_feedforward(signal, sample_rate=44100, delay_s=0.1)
        self.assertGreater(len(delayed), len(signal))
    
    def test_adsr_envelope(self):
        """Test ADSR envelope generation"""
        frames = 1000
        sample_rate = 44100
        env = DSP.adsr_envelope(frames, sample_rate)
        
        self.assertEqual(len(env), frames)
        self.assertGreaterEqual(env[0], 0.0)  # Start at 0
        self.assertLessEqual(env[-1], 0.0)  # End at 0
        
        # Should have positive values in the middle
        self.assertGreater(np.max(env), 0.0)
    
    def test_signal_mixing(self):
        """Test signal mixing"""
        signal1 = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
        signal2 = np.sin(2 * np.pi * 554.37 * np.linspace(0, 0.1, 4410))
        
        mixed = Synthesis.mix([signal1, signal2])
        
        # Check length
        self.assertEqual(len(mixed), len(signal1))
        
        # Check that mixing doesn't cause clipping
        self.assertLessEqual(np.max(np.abs(mixed)), 1.0)
    
    def test_synthesizer_context_manager(self):
        """Test synthesizer as context manager"""
        with AudioSynthesizer(self.config) as synth:
            self.assertIsNotNone(synth)
            # Should be usable within context
        # Should close cleanly
    
    def test_pcm_rendering(self):
        """Test PCM byte rendering"""
        signal = np.array([0.5, -0.5, 1.0, -1.0])
        
        pcm_bytes, frames = self.synthesizer.render_pcm16_bytes(signal)
        
        self.assertIsInstance(pcm_bytes, bytes)
        self.assertEqual(frames, len(signal))
        
        # Should be convertible back to int16
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        self.assertEqual(len(pcm_array), frames * self.config.channels)
    
    def test_play_functionality(self):
        """Test play functionality"""
        signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
        
        # This should work even if audio hardware is unavailable
        # It should fall back to file output
        handle = self.synthesizer.play(signal, blocking=True)
        
        self.assertIsNotNone(handle)
        self.assertTrue(handle.wait(timeout=5.0))
    
    def test_play_with_effects(self):
        """Test playing with effects"""
        signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
        
        # Apply effects
        effects = [
            lambda x: DSP.overdrive(x, drive=2.0),
            lambda x: DSP.bitcrush(x, bits=8),
        ]
        
        handle = self.synthesizer.play(signal, effects=effects, blocking=True)
        
        self.assertIsNotNone(handle)
        self.assertTrue(handle.wait(timeout=5.0))
    
    def test_config_validation(self):
        """Test configuration validation"""
        # Valid config
        config = AudioConfig(sample_rate=48000, channels=1)
        self.assertEqual(config.sample_rate, 48000)
        self.assertEqual(config.channels, 1)
        
        # Invalid configs
        with self.assertRaises(ValueError):
            AudioConfig(sample_rate=0)
        
        with self.assertRaises(ValueError):
            AudioConfig(channels=3)
        
        with self.assertRaises(ValueError):
            AudioConfig(frames_per_buffer=0)
    
    def test_error_handling(self):
        """Test error handling"""
        # Test invalid signal
        with self.assertRaises(Exception):
            DSP.require_finite(np.array([1.0, np.nan, 2.0]))
        
        # Test invalid synthesis parameters
        with self.assertRaises(Exception):
            Synthesis.tone(self.config, frequency_hz=0.0, duration_s=0.1)
        
        with self.assertRaises(Exception):
            Synthesis.tone(self.config, frequency_hz=440.0, duration_s=0.0)

if __name__ == "__main__":
    unittest.main()

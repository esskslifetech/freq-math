#!/usr/bin/env python3
"""
Test cases for the audio synthesizer component
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import numpy as np
from audio_synthesizer import AudioSynthesizer

class TestAudioSynthesizer(unittest.TestCase):
    def setUp(self):
        self.synthesizer = AudioSynthesizer(sample_rate=44100)
    
    def test_generate_tone(self):
        """Test tone generation"""
        # Test sine wave
        tone = self.synthesizer.generate_tone(440.0, 0.1, waveform='sine')
        
        # Check length
        expected_samples = int(0.1 * 44100)
        self.assertEqual(len(tone), expected_samples)
        
        # Check amplitude range
        self.assertLessEqual(np.max(np.abs(tone)), 1.0)
        
        # Check frequency (approximately)
        # Count zero crossings in first 0.01 seconds
        test_samples = int(0.01 * 44100)
        test_tone = tone[:test_samples]
        zero_crossings = np.sum(np.diff(np.sign(test_tone)) != 0)
        expected_crossings = int(440.0 * 0.01 * 2)  # 2 crossings per period
        
        # Allow some tolerance
        self.assertLess(abs(zero_crossings - expected_crossings), 5)
    
    def test_waveform_types(self):
        """Test different waveform types"""
        waveforms = ['sine', 'square', 'sawtooth', 'triangle']
        
        for waveform in waveforms:
            tone = self.synthesizer.generate_tone(440.0, 0.01, waveform=waveform)
            self.assertEqual(len(tone), int(0.01 * 44100))
            self.assertLessEqual(np.max(np.abs(tone)), 1.0)
    
    def test_apply_effects(self):
        """Test audio effects"""
        # Generate a simple tone
        tone = self.synthesizer.generate_tone(440.0, 0.1)
        
        # Test gain
        gain_tone = self.synthesizer.apply_effects(tone, gain=0.5)
        self.assertAlmostEqual(np.max(np.abs(gain_tone)), 0.5, places=2)
        
        # Test fade in/out
        faded_tone = self.synthesizer.apply_effects(tone, fade_in=0.01, fade_out=0.01)
        
        # Check that fade starts near zero
        self.assertLess(abs(faded_tone[0]), 0.1)
        # Check that fade ends near zero
        self.assertLess(abs(faded_tone[-1]), 0.1)
    
    def test_stereo_conversion(self):
        """Test mono to stereo conversion"""
        mono_signal = self.synthesizer.generate_tone(440.0, 0.1)
        
        # Test center pan
        stereo = self.synthesizer.create_stereo_signal(mono_signal, pan=0.0)
        self.assertEqual(stereo.shape, (len(mono_signal), 2))
        np.testing.assert_array_equal(stereo[:, 0], stereo[:, 1])
        
        # Test left pan
        stereo_left = self.synthesizer.create_stereo_signal(mono_signal, pan=-1.0)
        self.assertGreater(np.max(np.abs(stereo_left[:, 0])), np.max(np.abs(stereo_left[:, 1])))
        
        # Test right pan
        stereo_right = self.synthesizer.create_stereo_signal(mono_signal, pan=1.0)
        self.assertGreater(np.max(np.abs(stereo_right[:, 1])), np.max(np.abs(stereo_right[:, 0])))
    
    def test_mix_signals(self):
        """Test signal mixing"""
        # Generate two different tones
        tone1 = self.synthesizer.generate_tone(440.0, 0.1)
        tone2 = self.synthesizer.generate_tone(554.37, 0.1)
        
        # Mix signals
        mixed = self.synthesizer.mix_signals([tone1, tone2])
        
        # Check length
        self.assertEqual(len(mixed), len(tone1))
        
        # Check that mixing doesn't cause clipping
        self.assertLessEqual(np.max(np.abs(mixed)), 1.0)
        
        # Test with weights
        weighted_mixed = self.synthesizer.mix_signals([tone1, tone2], weights=[0.7, 0.3])
        self.assertEqual(len(weighted_mixed), len(tone1))
        self.assertLessEqual(np.max(np.abs(weighted_mixed)), 1.0)
    
    def test_numpy_to_int16_conversion(self):
        """Test float to int16 conversion"""
        # Create test signal
        float_signal = np.array([1.0, 0.5, 0.0, -0.5, -1.0])
        int_signal = self.synthesizer.numpy_to_int16(float_signal)
        
        # Check data type
        self.assertEqual(int_signal.dtype, np.int16)
        
        # Check values (approximately)
        self.assertAlmostEqual(int_signal[0], 32767, delta=1)
        self.assertAlmostEqual(int_signal[2], 0, delta=1)
        self.assertAlmostEqual(int_signal[4], -32767, delta=1)

if __name__ == "__main__":
    unittest.main()

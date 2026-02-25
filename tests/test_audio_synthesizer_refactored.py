#!/usr/bin/env python3
"""
Test cases for refactored audio synthesizer component
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
    from audio_synthesizer import (
        AudioSynthesizer, AudioConfig, DSP, Synthesis, MusicTheory,
        WaveFileBackend, PyAudioBackend, WavExportOptions, WavWriter,
        AudioError, HardwareUnavailableError, InvalidSignalError, SerializationError
    )
    AUDIO_SYNTH_AVAILABLE = True
except ImportError as e:
    print(f"Audio synthesizer not available: {e}")
    AUDIO_SYNTH_AVAILABLE = False

class TestAudioConfig(unittest.TestCase):
    def test_default_config(self):
        """Test default configuration values"""
        config = AudioConfig()
        
        self.assertEqual(config.sample_rate, 44_100)
        self.assertEqual(config.channels, 2)
        self.assertEqual(config.frames_per_buffer, 512)
        self.assertEqual(config.bit_depth, 16)
        self.assertEqual(config.sample_width_bytes, 2)
        self.assertEqual(config.frame_width_bytes, 4)
    
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
        
        with self.assertRaises(ValueError):
            AudioConfig(bit_depth=24)

@unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "Audio synthesizer not available")
class TestDSP(unittest.TestCase):
    def test_require_finite(self):
        """Test finite signal validation"""
        # Valid signal
        valid = np.array([1.0, 0.5, -0.5])
        DSP.require_finite(valid)  # Should not raise
        
        # Invalid signal with NaN
        invalid = np.array([1.0, np.nan, -0.5])
        with self.assertRaises(InvalidSignalError):
            DSP.require_finite(invalid)
        
        # Invalid signal with Inf
        invalid = np.array([1.0, np.inf, -0.5])
        with self.assertRaises(InvalidSignalError):
            DSP.require_finite(invalid)
    
    def test_as_float_mono(self):
        """Test mono conversion"""
        # Mono input
        mono = np.array([1.0, 0.5, -0.5])
        result = DSP.as_float_mono(mono)
        np.testing.assert_array_equal(result, mono)
        
        # Stereo input
        stereo = np.array([[1.0, 0.5], [0.3, -0.2]])
        expected = np.array([0.75, 0.05])  # average of each channel
        result = DSP.as_float_mono(stereo)
        np.testing.assert_array_almost_equal(result, expected)
        
        # Invalid shape
        invalid = np.array([[[1.0, 0.5]]])
        with self.assertRaises(InvalidSignalError):
            DSP.as_float_mono(invalid)
    
    def test_ensure_channels(self):
        """Test channel ensuring"""
        mono = np.array([1.0, 0.5, -0.5])
        
        # Ensure mono
        result_mono = DSP.ensure_channels(mono, 1)
        self.assertEqual(result_mono.shape, (3,))
        
        # Ensure stereo
        result_stereo = DSP.ensure_channels(mono, 2)
        self.assertEqual(result_stereo.shape, (3, 2))
        
        # Test panning
        result_left = DSP.ensure_channels(mono, 2, pan=-1.0)
        result_right = DSP.ensure_channels(mono, 2, pan=1.0)
        
        # Left should have more energy in left channel
        self.assertGreater(np.max(np.abs(result_left[:, 0])), np.max(np.abs(result_left[:, 1])))
        # Right should have more energy in right channel
        self.assertGreater(np.max(np.abs(result_right[:, 1])), np.max(np.abs(result_right[:, 0])))
    
    def test_clip_and_normalize(self):
        """Test clipping and normalization"""
        signal = np.array([2.0, -2.0, 0.5, -0.5])
        
        # Clipping
        clipped = DSP.clip(signal)
        self.assertLessEqual(np.max(np.abs(clipped)), 1.0)
        
        # Normalization
        normalized = DSP.normalize_peak(signal)
        self.assertAlmostEqual(np.max(np.abs(normalized)), 1.0, places=5)
    
    def test_to_pcm16(self):
        """Test PCM16 conversion"""
        signal = np.array([1.0, 0.0, -1.0])
        pcm = DSP.to_pcm16(signal)
        
        self.assertEqual(pcm.dtype, np.int16)
        self.assertAlmostEqual(pcm[0] / 32767.0, 1.0, places=3)
        self.assertEqual(pcm[1], 0)
        self.assertAlmostEqual(pcm[2] / 32767.0, -1.0, places=3)
    
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
    
    def test_effects(self):
        """Test audio effects"""
        signal = np.array([0.5, -0.5, 1.0, -1.0])
        
        # Overdrive
        overdriven = DSP.overdrive(signal, drive=2.0)
        self.assertEqual(len(overdriven), len(signal))
        
        # Bitcrush
        crushed = DSP.bitcrush(signal, bits=4)
        self.assertEqual(len(crushed), len(signal))
        
        # Ring mod
        modulated = DSP.ring_mod(signal, sample_rate=44100, mod_freq=10.0)
        self.assertEqual(len(modulated), len(signal))
        
        # Delay
        delayed = DSP.delay_feedforward(signal, sample_rate=44100, delay_s=0.1)
        self.assertGreater(len(delayed), len(signal))

@unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "Audio synthesizer not available")
class TestSynthesis(unittest.TestCase):
    def setUp(self):
        self.config = AudioConfig(sample_rate=44100)
    
    def test_tone_generation(self):
        """Test basic tone generation"""
        tone = Synthesis.tone(self.config, frequency_hz=440.0, duration_s=0.1)
        
        expected_samples = int(0.1 * self.config.sample_rate)
        self.assertEqual(len(tone), expected_samples)
        self.assertTrue(np.all(np.isfinite(tone)))
        self.assertLessEqual(np.max(np.abs(tone)), 1.0)
    
    def test_waveform_types(self):
        """Test different waveform types"""
        waveforms = ['sine', 'square', 'sawtooth', 'triangle', 'noise']
        
        for waveform in waveforms:
            with self.subTest(waveform=waveform):
                tone = Synthesis.tone(self.config, frequency_hz=440.0, duration_s=0.01, waveform=waveform)
                self.assertEqual(len(tone), int(0.01 * self.config.sample_rate))
                self.assertTrue(np.all(np.isfinite(tone)))
    
    def test_signal_mixing(self):
        """Test signal mixing"""
        signal1 = np.array([0.5, -0.5, 0.3])
        signal2 = np.array([0.3, 0.2, -0.4])
        
        mixed = Synthesis.mix([signal1, signal2])
        
        # Should be normalized
        self.assertLessEqual(np.max(np.abs(mixed)), 1.0)
        self.assertEqual(len(mixed), max(len(signal1), len(signal2)))
    
    def test_invalid_parameters(self):
        """Test invalid parameter handling"""
        with self.assertRaises(InvalidSignalError):
            Synthesis.tone(self.config, frequency_hz=0.0, duration_s=0.1)
        
        with self.assertRaises(InvalidSignalError):
            Synthesis.tone(self.config, frequency_hz=440.0, duration_s=0.0)

@unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "Audio synthesizer not available")
class TestMusicTheory(unittest.TestCase):
    def test_note_to_frequency(self):
        """Test note to frequency conversion"""
        # A4 should be 440 Hz by default
        freq = MusicTheory.note_to_frequency("A4")
        self.assertAlmostEqual(freq, 440.0, places=1)
        
        # C4 (middle C)
        freq = MusicTheory.note_to_frequency("C4")
        self.assertAlmostEqual(freq, 261.63, places=1)
        
        # Sharp notes
        freq = MusicTheory.note_to_frequency("C#4")
        self.assertAlmostEqual(freq, 277.18, places=1)
        
        # Flat notes
        freq = MusicTheory.note_to_frequency("Db4")
        self.assertAlmostEqual(freq, 277.18, places=1)
    
    def test_custom_a4_frequency(self):
        """Test custom A4 frequency"""
        freq = MusicTheory.note_to_frequency("A4", a4_hz=442.0)
        self.assertAlmostEqual(freq, 442.0, places=1)
    
    def test_invalid_notes(self):
        """Test invalid note handling"""
        with self.assertRaises(ValueError):
            MusicTheory.note_to_frequency("")
        
        with self.assertRaises(ValueError):
            MusicTheory.note_to_frequency("H4")  # Invalid note
        
        with self.assertRaises(ValueError):
            MusicTheory.note_to_frequency("A")  # Missing octave
    
    def test_render_melody(self):
        """Test melody rendering"""
        config = AudioConfig(sample_rate=44100)
        notes = [("C4", 0.1), ("E4", 0.1), ("G4", 0.1)]
        
        melody = MusicTheory.render_melody(config, notes)
        
        # Should have 3 notes + 2 gaps
        expected_duration = 0.3 + 0.02  # 2 gaps of 0.01s each
        expected_samples = int(expected_duration * config.sample_rate)
        self.assertEqual(len(melody), expected_samples)

@unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "Audio synthesizer not available")
class TestWaveFileBackend(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.backend = WaveFileBackend(WavExportOptions(directory=Path(self.temp_dir)))
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_wav_export(self):
        """Test WAV file export"""
        config = AudioConfig(sample_rate=44100, channels=2)
        pcm_data = np.array([1000, -1000, 2000, -2000], dtype=np.int16)
        pcm_bytes = pcm_data.tobytes()
        frames = 2  # 2 stereo frames
        
        handle = self.backend.play_pcm16_interleaved(
            config=config,
            pcm_bytes=pcm_bytes,
            frames=frames
        )
        
        # Should complete immediately
        self.assertTrue(handle.wait(timeout=1.0))
        
        # Check file was created
        self.assertIsNotNone(handle.artifact_path)
        self.assertTrue(handle.artifact_path.exists())
        
        # Verify WAV file
        with wave.open(str(handle.artifact_path), 'rb') as wav:
            self.assertEqual(wav.getnchannels(), config.channels)
            self.assertEqual(wav.getsampwidth(), config.sample_width_bytes)
            self.assertEqual(wav.getframerate(), config.sample_rate)
    
    def test_unique_filenames(self):
        """Test unique filename generation"""
        config = AudioConfig()
        pcm_data = np.array([1000, -1000], dtype=np.int16)
        pcm_bytes = pcm_data.tobytes()
        frames = 1
        
        handle1 = self.backend.play_pcm16_interleaved(
            config=config, pcm_bytes=pcm_bytes, frames=frames
        )
        handle2 = self.backend.play_pcm16_interleaved(
            config=config, pcm_bytes=pcm_bytes, frames=frames
        )
        
        # Should have different filenames
        self.assertNotEqual(
            handle1.artifact_path.name,
            handle2.artifact_path.name
        )

class TestWavWriter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_write_pcm16(self):
        """Test PCM16 writing"""
        config = AudioConfig(sample_rate=44100, channels=2)
        pcm_data = np.array([1000, -1000, 2000, -2000], dtype=np.int16)
        file_path = Path(self.temp_dir) / "test.wav"
        
        WavWriter.write_pcm16(
            path=file_path,
            config=config,
            pcm16=pcm_data,
            channels=2
        )
        
        # Verify file exists and has correct properties
        self.assertTrue(file_path.exists())
        
        with wave.open(str(file_path), 'rb') as wav:
            self.assertEqual(wav.getnchannels(), 2)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 44100)
            
            # Read back and verify data
            data = wav.readframes(-1)
            read_pcm = np.frombuffer(data, dtype=np.int16)
            np.testing.assert_array_equal(read_pcm, pcm_data)
    
    def test_atomic_write(self):
        """Test atomic file writing"""
        config = AudioConfig()
        pcm_data = np.array([1000, -1000], dtype=np.int16)
        file_path = Path(self.temp_dir) / "test.wav"
        
        # Write file
        WavWriter.write_pcm16(
            path=file_path,
            config=config,
            pcm16=pcm_data,
            channels=1
        )
        
        # Should not have .tmp file
        self.assertFalse(file_path.with_suffix(file_path.suffix + ".tmp").exists())
        self.assertTrue(file_path.exists())

@unittest.skipUnless(AUDIO_SYNTH_AVAILABLE, "Audio synthesizer not available")
class TestAudioSynthesizer(unittest.TestCase):
    def setUp(self):
        self.config = AudioConfig(sample_rate=44100)
    
    def test_context_manager(self):
        """Test context manager behavior"""
        with AudioSynthesizer(self.config) as synth:
            self.assertIsNotNone(synth)
            # Should be usable within context
        # Should close cleanly
    
    def test_render_pcm16_bytes(self):
        """Test PCM16 byte rendering"""
        synth = AudioSynthesizer(self.config)
        signal = np.array([0.5, -0.5, 1.0, -1.0])
        
        pcm_bytes, frames = synth.render_pcm16_bytes(signal)
        
        self.assertIsInstance(pcm_bytes, bytes)
        self.assertEqual(frames, len(signal))
        
        # Should be convertible back to int16
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        self.assertEqual(len(pcm_array), frames * self.config.channels)
    
    def test_play_with_wave_backend(self):
        """Test playing with wave file backend"""
        backend = WaveFileBackend()
        synth = AudioSynthesizer(self.config, backend=backend)
        
        signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
        
        handle = synth.play(signal, blocking=True)
        
        self.assertTrue(handle.wait(timeout=5.0))
        self.assertIsNotNone(handle.artifact_path)
        self.assertTrue(handle.artifact_path.exists())
    
    def test_play_with_effects(self):
        """Test playing with effects"""
        backend = WaveFileBackend()
        synth = AudioSynthesizer(self.config, backend=backend)
        
        signal = np.sin(2 * np.pi * 440 * np.linspace(0, 0.1, 4410))
        
        # Apply effects
        effects = [
            lambda x: DSP.overdrive(x, drive=2.0),
            lambda x: DSP.bitcrush(x, bits=8),
        ]
        
        handle = synth.play(signal, effects=effects, blocking=True)
        
        self.assertTrue(handle.wait(timeout=5.0))
        self.assertIsNotNone(handle.artifact_path)

if __name__ == "__main__":
    unittest.main()

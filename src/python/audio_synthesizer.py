"""
audio_synthesizer.py
====================

A pure-Python audio synthesis toolkit built on NumPy.

Architecture
------------
- **Pure core**: DSP, Synthesis, MusicTheory, SignalAnalyzer — zero side effects.
- **Effect pipeline**: Composable ``EffectChain`` with typed ``Effect`` protocol.
- **Isolated I/O**: WavWriter, playback backends — all side effects behind contracts.
- **Facade**: ``AudioSynthesizer`` orchestrates pure → impure boundary.

Concurrency
-----------
- ``WaveFileBackend``: atomic writes with unique filenames → fully concurrent.
- ``PyAudioBackend``: RLock-guarded device access; sequential streams recommended.
- All pure functions are thread-safe by construction (no shared mutable state).

API Contracts
-------------
- ``AudioConfig``: immutable, validated at construction.
- ``FloatSignal``: ``NDArray[np.floating]`` in ``[-1, 1]`` (recommended).
- ``PCM16Array``: ``NDArray[np.int16]``, little-endian interleaved.
- All public errors derive from ``AudioError``.
"""

from __future__ import annotations

import contextlib
import enum
import functools
import logging
import math
import os
import struct
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Callable,
    Final,
    Iterable,
    Protocol,
    Sequence,
    runtime_checkable,
)

import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)

# Optional hardware dependency
try:
    import pyaudio  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    pyaudio = None

__all__ = [
    # Errors
    "AudioError",
    "HardwareUnavailableError",
    "InvalidSignalError",
    "SerializationError",
    # Config / types
    "AudioConfig",
    "FloatSignal",
    "PCM16Array",
    "WaveformType",
    "ScaleType",
    # Pure DSP
    "DSP",
    "Synthesis",
    "MusicTheory",
    "SignalAnalyzer",
    # Effects
    "Effect",
    "EffectChain",
    "Overdrive",
    "Bitcrush",
    "RingModulator",
    "FeedforwardDelay",
    "BiquadFilter",
    "Compressor",
    "Chorus",
    "SchroederReverb",
    "Tremolo",
    "FadeInOut",
    # Serialization
    "WavExportOptions",
    "WavWriter",
    # Playback
    "PlaybackStats",
    "PlaybackHandle",
    "AudioBackend",
    "WaveFileBackend",
    "PyAudioBackend",
    # Facade
    "AudioSynthesizer",
]

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

_PCM16_MAX: Final[float] = 32_767.0
_TWO_PI: Final[float] = 2.0 * math.pi
_DEFAULT_SAMPLE_RATE: Final[int] = 44_100
_DEFAULT_CHANNELS: Final[int] = 2
_DEFAULT_FRAMES_PER_BUFFER: Final[int] = 512
_DEFAULT_BIT_DEPTH: Final[int] = 16
_PLAYBACK_TIMEOUT_MARGIN_S: Final[float] = 1.0
_EPSILON: Final[float] = 1e-12
_A4_HZ: Final[float] = 440.0
_MIDI_A4: Final[int] = 69


# ═══════════════════════════════════════════════════════════════════════════════
# Errors (API Contracts)
# ═══════════════════════════════════════════════════════════════════════════════

class AudioError(Exception):
    """Base for all audio-module errors."""


class HardwareUnavailableError(AudioError):
    """Real-time audio hardware is unavailable or failed."""


class InvalidSignalError(AudioError):
    """Signal has wrong shape, NaN/Inf, or violates a DSP contract."""


class SerializationError(AudioError):
    """WAV / PCM serialization failed."""


# ═══════════════════════════════════════════════════════════════════════════════
# Types & Enums
# ═══════════════════════════════════════════════════════════════════════════════

FloatSignal = npt.NDArray[np.floating]
PCM16Array = npt.NDArray[np.int16]


class WaveformType(enum.Enum):
    """Supported oscillator waveforms."""
    SINE = "sine"
    SQUARE = "square"
    SAWTOOTH = "sawtooth"
    TRIANGLE = "triangle"
    NOISE = "noise"
    PULSE = "pulse"


class ScaleType(enum.Enum):
    """Common musical scales expressed as semitone interval patterns."""
    MAJOR = "major"
    MINOR = "minor"
    PENTATONIC_MAJOR = "pentatonic_major"
    PENTATONIC_MINOR = "pentatonic_minor"
    BLUES = "blues"
    CHROMATIC = "chromatic"
    DORIAN = "dorian"
    MIXOLYDIAN = "mixolydian"
    HARMONIC_MINOR = "harmonic_minor"


_SCALE_INTERVALS: Final[dict[ScaleType, tuple[int, ...]]] = {
    ScaleType.MAJOR: (0, 2, 4, 5, 7, 9, 11),
    ScaleType.MINOR: (0, 2, 3, 5, 7, 8, 10),
    ScaleType.PENTATONIC_MAJOR: (0, 2, 4, 7, 9),
    ScaleType.PENTATONIC_MINOR: (0, 3, 5, 7, 10),
    ScaleType.BLUES: (0, 3, 5, 6, 7, 10),
    ScaleType.CHROMATIC: tuple(range(12)),
    ScaleType.DORIAN: (0, 2, 3, 5, 7, 9, 10),
    ScaleType.MIXOLYDIAN: (0, 2, 4, 5, 7, 9, 10),
    ScaleType.HARMONIC_MINOR: (0, 2, 3, 5, 7, 8, 11),
}


class FilterType(enum.Enum):
    """Biquad filter topologies."""
    LOW_PASS = "low_pass"
    HIGH_PASS = "high_pass"
    BAND_PASS = "band_pass"
    NOTCH = "notch"


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration (immutable, validated)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class AudioConfig:
    """
    Immutable audio contract used across DSP, serialization, and playback.

    Invariants
    ----------
    - ``sample_rate > 0``
    - ``channels ∈ {1, 2}``
    - ``bit_depth == 16``  (PCM-16 end-to-end)
    - ``frames_per_buffer > 0``
    """
    sample_rate: int = _DEFAULT_SAMPLE_RATE
    channels: int = _DEFAULT_CHANNELS
    frames_per_buffer: int = _DEFAULT_FRAMES_PER_BUFFER
    bit_depth: int = _DEFAULT_BIT_DEPTH

    def __post_init__(self) -> None:
        _require(self.sample_rate > 0, "sample_rate must be > 0")
        _require(self.channels in (1, 2), "channels must be 1 or 2")
        _require(self.frames_per_buffer > 0, "frames_per_buffer must be > 0")
        _require(self.bit_depth == 16, "bit_depth must be 16 (PCM16)")

    @property
    def sample_width_bytes(self) -> int:
        """Bytes per single-channel sample (always 2 for PCM-16)."""
        return self.bit_depth // 8

    @property
    def frame_width_bytes(self) -> int:
        """Bytes per interleaved frame (e.g. 4 for stereo PCM-16)."""
        return self.channels * self.sample_width_bytes

    @property
    def nyquist_hz(self) -> float:
        """Nyquist frequency for this sample rate."""
        return self.sample_rate / 2.0

    def frames_for(self, duration_s: float) -> int:
        """Number of frames for a given duration, minimum 1."""
        return max(1, int(round(duration_s * self.sample_rate)))


# ═══════════════════════════════════════════════════════════════════════════════
# Internal Validation Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _require(condition: bool, message: str) -> None:
    """Compact precondition check; raises ``ValueError`` on failure."""
    if not condition:
        raise ValueError(message)


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")


def _as_f32(signal: FloatSignal) -> npt.NDArray[np.float32]:
    """Cast to contiguous float32 without unnecessary copy."""
    return np.ascontiguousarray(signal, dtype=np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# Pure DSP (side-effect free)
# ═══════════════════════════════════════════════════════════════════════════════

class DSP:
    """
    Pure DSP utilities.

    Every method is deterministic and free of side effects.
    All accept and return ``np.float32`` arrays.
    """

    __slots__ = ()

    # ── Validation ────────────────────────────────────────────────────────

    @staticmethod
    def require_finite(signal: FloatSignal) -> None:
        """Raise ``InvalidSignalError`` if any element is NaN or Inf."""
        if signal.size and not np.isfinite(signal).all():
            raise InvalidSignalError("Signal contains NaN or Inf.")

    # ── Channel Manipulation ──────────────────────────────────────────────

    @staticmethod
    def as_float_mono(signal: FloatSignal) -> npt.NDArray[np.float32]:
        """
        Downmix to mono ``(frames,)``.

        Accepts ``(frames,)`` or ``(frames, 2)``; stereo is averaged.
        """
        arr = _as_f32(signal)
        if arr.ndim == 1:
            out = arr
        elif arr.ndim == 2 and arr.shape[1] == 2:
            out = (arr[:, 0] + arr[:, 1]) * 0.5
        else:
            raise InvalidSignalError(f"Expected (n,) or (n,2), got {arr.shape}.")
        DSP.require_finite(out)
        return np.ascontiguousarray(out)

    @staticmethod
    def ensure_channels(
        signal: FloatSignal,
        channels: int,
        *,
        pan: float = 0.0,
    ) -> npt.NDArray[np.float32]:
        """
        Reshape signal to ``channels``.

        For mono→stereo: equal-power pan (``-1`` = hard left, ``+1`` = hard right).
        """
        _require(channels in (1, 2), "channels must be 1 or 2")
        arr = _as_f32(signal)
        DSP.require_finite(arr)

        if channels == 1:
            return DSP.as_float_mono(arr)

        # channels == 2
        if arr.ndim == 2 and arr.shape[1] == 2:
            return np.ascontiguousarray(arr)
        if arr.ndim != 1:
            raise InvalidSignalError(f"Expected (n,) or (n,2), got {arr.shape}.")

        pan_clamped = float(np.clip(pan, -1.0, 1.0))
        angle = (pan_clamped + 1.0) * (math.pi / 4.0)
        left_gain = math.cos(angle)
        right_gain = math.sin(angle)

        stereo = np.empty((arr.shape[0], 2), dtype=np.float32)
        stereo[:, 0] = arr * left_gain
        stereo[:, 1] = arr * right_gain
        return stereo

    # ── Amplitude Processing ──────────────────────────────────────────────

    @staticmethod
    def clip(
        signal: FloatSignal,
        lo: float = -1.0,
        hi: float = 1.0,
    ) -> npt.NDArray[np.float32]:
        """Hard-clip signal to ``[lo, hi]``."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        return np.clip(arr, lo, hi).astype(np.float32, copy=False)

    @staticmethod
    def normalize_peak(
        signal: FloatSignal,
        target_peak: float = 1.0,
    ) -> npt.NDArray[np.float32]:
        """Scale so that ``max(|signal|) == target_peak``."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        if peak < _EPSILON:
            return np.ascontiguousarray(arr)
        return np.ascontiguousarray(arr * (target_peak / peak))

    @staticmethod
    def normalize_rms(
        signal: FloatSignal,
        target_rms: float = 0.2,
    ) -> npt.NDArray[np.float32]:
        """Scale so that RMS equals ``target_rms``, then clip to ``[-1, 1]``."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
        if rms < _EPSILON:
            return np.ascontiguousarray(arr)
        scaled = arr * (target_rms / rms)
        return DSP.clip(scaled)

    @staticmethod
    def gain_db(signal: FloatSignal, db: float) -> npt.NDArray[np.float32]:
        """Apply gain in decibels. ``+6 dB ≈ ×2``, ``-6 dB ≈ ×0.5``."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        linear = 10.0 ** (db / 20.0)
        return np.ascontiguousarray(arr * np.float32(linear))

    # ── PCM Conversion ────────────────────────────────────────────────────

    @staticmethod
    def to_pcm16(signal: FloatSignal) -> PCM16Array:
        """
        Float ``[-1, 1]`` → little-endian ``int16``.

        Clips before conversion for safety.
        """
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        clipped = np.clip(arr, -1.0, 1.0)
        pcm = (clipped * _PCM16_MAX).astype("<i2", copy=False)
        return np.ascontiguousarray(pcm)

    @staticmethod
    def from_pcm16(pcm: PCM16Array) -> npt.NDArray[np.float32]:
        """Little-endian ``int16`` → float ``[-1, 1]``."""
        return np.asarray(pcm, dtype=np.float32) / _PCM16_MAX

    # ── Envelope ──────────────────────────────────────────────────────────

    @staticmethod
    def adsr_envelope(
        frames: int,
        sample_rate: int,
        *,
        attack_s: float = 0.01,
        decay_s: float = 0.05,
        sustain_level: float = 0.7,
        release_s: float = 0.08,
    ) -> npt.NDArray[np.float32]:
        """
        Generate an ADSR amplitude envelope of length ``frames``.

        Parameters
        ----------
        frames : int ≥ 0
        sample_rate : int > 0
        attack_s, decay_s, release_s : float ≥ 0
        sustain_level : float ∈ [0, 1]
        """
        _require(frames >= 0, "frames must be >= 0")
        _require_positive(sample_rate, "sample_rate")
        _require(
            min(attack_s, decay_s, release_s) >= 0,
            "attack_s/decay_s/release_s must be >= 0",
        )
        _require(0.0 <= sustain_level <= 1.0, "sustain_level must be in [0, 1]")

        if frames == 0:
            return np.empty(0, dtype=np.float32)

        a = min(int(round(attack_s * sample_rate)), frames)
        d = min(int(round(decay_s * sample_rate)), max(0, frames - a))
        r = min(int(round(release_s * sample_rate)), max(0, frames - a - d))
        s = max(0, frames - a - d - r)

        segments: list[npt.NDArray[np.float32]] = []
        if a:
            segments.append(np.linspace(0.0, 1.0, a, endpoint=False, dtype=np.float32))
        if d:
            segments.append(
                np.linspace(1.0, sustain_level, d, endpoint=False, dtype=np.float32)
            )
        if s:
            segments.append(np.full(s, sustain_level, dtype=np.float32))
        if r:
            segments.append(
                np.linspace(sustain_level, 0.0, r, endpoint=True, dtype=np.float32)
            )

        return np.concatenate(segments) if segments else np.empty(0, dtype=np.float32)

    @staticmethod
    def apply_envelope(
        signal: FloatSignal,
        envelope: npt.NDArray[np.float32],
    ) -> npt.NDArray[np.float32]:
        """Element-wise multiply signal by envelope. Lengths must match."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        if arr.shape[0] != envelope.shape[0]:
            raise InvalidSignalError(
                f"Envelope length {envelope.shape[0]} ≠ signal frames {arr.shape[0]}."
            )
        return np.ascontiguousarray(arr * envelope)

    # ── Resampling / Time Manipulation ────────────────────────────────────

    @staticmethod
    def resample(signal: FloatSignal, factor: float) -> npt.NDArray[np.float32]:
        """
        Time-stretch / pitch-shift via linear interpolation.

        ``factor > 1`` → longer (lower pitch), ``factor < 1`` → shorter (higher pitch).
        """
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        _require_positive(factor, "factor")
        if arr.size == 0:
            return arr
        new_len = max(1, int(round(arr.shape[0] * factor)))
        indices = np.linspace(0, arr.shape[0] - 1, new_len, dtype=np.float64)
        return np.interp(indices, np.arange(arr.shape[0]), arr).astype(
            np.float32, copy=False
        )

    @staticmethod
    def reverse(signal: FloatSignal) -> npt.NDArray[np.float32]:
        """Reverse the signal in time."""
        arr = _as_f32(signal)
        return np.ascontiguousarray(arr[::-1])

    @staticmethod
    def crossfade(
        a: FloatSignal,
        b: FloatSignal,
        overlap_frames: int,
    ) -> npt.NDArray[np.float32]:
        """
        Crossfade the tail of ``a`` into the head of ``b`` over ``overlap_frames``.

        Returns a new signal of length ``len(a) + len(b) - overlap_frames``.
        """
        arr_a = _as_f32(a)
        arr_b = _as_f32(b)
        DSP.require_finite(arr_a)
        DSP.require_finite(arr_b)
        overlap = min(overlap_frames, arr_a.shape[0], arr_b.shape[0])
        _require(overlap >= 0, "overlap_frames must be >= 0")

        if overlap == 0:
            return np.concatenate([arr_a, arr_b])

        fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
        fade_in = 1.0 - fade_out

        out_len = arr_a.shape[0] + arr_b.shape[0] - overlap
        out = np.empty(out_len, dtype=np.float32)
        out[: arr_a.shape[0] - overlap] = arr_a[:-overlap]
        out[arr_a.shape[0] - overlap : arr_a.shape[0]] = (
            arr_a[-overlap:] * fade_out + arr_b[:overlap] * fade_in
        )
        out[arr_a.shape[0] :] = arr_b[overlap:]
        return out


# ═══════════════════════════════════════════════════════════════════════════════
# Effect Protocol & Composable Chain
# ═══════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class Effect(Protocol):
    """
    Any callable ``(FloatSignal) → FloatSignal`` with a ``name`` attribute.

    Implementations must be **pure** (no side effects, deterministic given inputs).
    """

    @property
    def name(self) -> str: ...

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]: ...


@dataclass(frozen=True, slots=True)
class Overdrive:
    """Soft-clip distortion via ``tanh`` waveshaping."""

    drive: float = 3.0

    @property
    def name(self) -> str:
        return f"Overdrive(drive={self.drive})"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        if self.drive <= 0.0:
            return arr
        d = float(self.drive)
        return np.ascontiguousarray(np.tanh(arr * d) / np.float32(math.tanh(d)))


@dataclass(frozen=True, slots=True)
class Bitcrush:
    """Reduce amplitude resolution for lo-fi / chiptune textures."""

    bits: int = 8

    def __post_init__(self) -> None:
        _require(self.bits > 0, "bits must be > 0")

    @property
    def name(self) -> str:
        return f"Bitcrush(bits={self.bits})"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        levels = np.float32(2 ** self.bits - 1)
        crushed = np.round((np.clip(arr, -1.0, 1.0) + 1.0) * 0.5 * levels) / levels
        return np.ascontiguousarray(crushed * 2.0 - 1.0)


@dataclass(frozen=True, slots=True)
class RingModulator:
    """Multiply by a sine LFO — robot / tremolo / sci-fi textures."""

    sample_rate: int
    mod_freq: float = 30.0
    depth: float = 1.0

    @property
    def name(self) -> str:
        return f"RingMod(freq={self.mod_freq}, depth={self.depth})"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        _require_positive(self.sample_rate, "sample_rate")
        if self.mod_freq <= 0:
            return arr
        depth = float(np.clip(self.depth, 0.0, 1.0))
        t = np.arange(arr.shape[0], dtype=np.float32) / np.float32(self.sample_rate)
        modulator = np.sin(_TWO_PI * np.float32(self.mod_freq) * t, dtype=np.float32)
        return np.ascontiguousarray(arr * ((1.0 - depth) + depth * modulator))


@dataclass(frozen=True, slots=True)
class FeedforwardDelay:
    """Single-tap feedforward delay (no feedback — always stable)."""

    sample_rate: int
    delay_s: float = 0.25
    wet: float = 0.35

    @property
    def name(self) -> str:
        return f"Delay(delay={self.delay_s}s, wet={self.wet})"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        _require_positive(self.sample_rate, "sample_rate")
        if self.delay_s <= 0 or self.wet <= 0:
            return arr
        d = max(1, int(round(self.delay_s * self.sample_rate)))
        w = float(np.clip(self.wet, 0.0, 1.0))
        out = np.zeros(arr.shape[0] + d, dtype=np.float32)
        out[: arr.shape[0]] += arr
        out[d:] += arr * np.float32(w)
        return DSP.clip(out)


@dataclass(frozen=True, slots=True)
class BiquadFilter:
    """
    Second-order IIR (biquad) filter.

    Supports low-pass, high-pass, band-pass, and notch topologies.
    Coefficients computed via the Audio EQ Cookbook (Robert Bristow-Johnson).
    """

    sample_rate: int
    cutoff_hz: float
    filter_type: FilterType = FilterType.LOW_PASS
    q: float = 0.707  # Butterworth Q

    def __post_init__(self) -> None:
        _require_positive(self.sample_rate, "sample_rate")
        _require_positive(self.cutoff_hz, "cutoff_hz")
        _require_positive(self.q, "q")
        _require(
            self.cutoff_hz < self.sample_rate / 2.0,
            f"cutoff_hz ({self.cutoff_hz}) must be < Nyquist ({self.sample_rate / 2.0})",
        )

    @property
    def name(self) -> str:
        return f"Biquad({self.filter_type.value}, {self.cutoff_hz}Hz, Q={self.q})"

    def _coefficients(self) -> tuple[np.float64, ...]:
        """Return (b0, b1, b2, a0, a1, a2) per Audio EQ Cookbook."""
        w0 = _TWO_PI * self.cutoff_hz / self.sample_rate
        alpha = math.sin(w0) / (2.0 * self.q)
        cos_w0 = math.cos(w0)

        match self.filter_type:
            case FilterType.LOW_PASS:
                b0 = (1.0 - cos_w0) / 2.0
                b1 = 1.0 - cos_w0
                b2 = b0
            case FilterType.HIGH_PASS:
                b0 = (1.0 + cos_w0) / 2.0
                b1 = -(1.0 + cos_w0)
                b2 = b0
            case FilterType.BAND_PASS:
                b0 = alpha
                b1 = 0.0
                b2 = -alpha
            case FilterType.NOTCH:
                b0 = 1.0
                b1 = -2.0 * cos_w0
                b2 = 1.0

        a0 = 1.0 + alpha
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha
        return (b0, b1, b2, a0, a1, a2)

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        if arr.size == 0:
            return arr

        b0, b1, b2, a0, a1, a2 = self._coefficients()
        # Normalize
        b0 /= a0
        b1 /= a0
        b2 /= a0
        a1 /= a0
        a2 /= a0

        # Direct Form II Transposed — vectorized where possible, loop for IIR
        out = np.empty_like(arr)
        z1 = 0.0
        z2 = 0.0
        for i in range(arr.shape[0]):
            x = float(arr[i])
            y = b0 * x + z1
            z1 = b1 * x - a1 * y + z2
            z2 = b2 * x - a2 * y
            out[i] = y

        return np.ascontiguousarray(out)


@dataclass(frozen=True, slots=True)
class Compressor:
    """
    Simple feed-forward compressor with RMS detection.

    Parameters
    ----------
    threshold_db : Compression starts above this level (e.g. ``-20``).
    ratio : Compression ratio (e.g. ``4.0`` means 4:1).
    attack_ms : Envelope follower attack (ms).
    release_ms : Envelope follower release (ms).
    makeup_db : Post-compression gain.
    """

    sample_rate: int
    threshold_db: float = -20.0
    ratio: float = 4.0
    attack_ms: float = 5.0
    release_ms: float = 50.0
    makeup_db: float = 0.0

    def __post_init__(self) -> None:
        _require_positive(self.sample_rate, "sample_rate")
        _require(self.ratio >= 1.0, "ratio must be >= 1.0")

    @property
    def name(self) -> str:
        return (
            f"Compressor(thresh={self.threshold_db}dB, "
            f"ratio={self.ratio}:1, makeup={self.makeup_db}dB)"
        )

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        if arr.size == 0:
            return arr

        threshold_linear = 10.0 ** (self.threshold_db / 20.0)
        attack_coeff = math.exp(-1.0 / (self.attack_ms * 0.001 * self.sample_rate))
        release_coeff = math.exp(-1.0 / (self.release_ms * 0.001 * self.sample_rate))
        makeup_linear = 10.0 ** (self.makeup_db / 20.0)

        envelope = 0.0
        out = np.empty_like(arr)
        for i in range(arr.shape[0]):
            level = abs(float(arr[i]))
            coeff = attack_coeff if level > envelope else release_coeff
            envelope = coeff * envelope + (1.0 - coeff) * level

            if envelope > threshold_linear:
                gain_reduction = threshold_linear * (
                    (envelope / threshold_linear) ** (1.0 / self.ratio - 1.0)
                )
            else:
                gain_reduction = 1.0
            out[i] = arr[i] * gain_reduction * makeup_linear

        return np.ascontiguousarray(out)


@dataclass(frozen=True, slots=True)
class Chorus:
    """
    Modulated-delay chorus effect.

    Creates width by mixing in slightly detuned copies of the signal.
    """

    sample_rate: int
    rate_hz: float = 1.5
    depth_ms: float = 3.0
    wet: float = 0.5

    def __post_init__(self) -> None:
        _require_positive(self.sample_rate, "sample_rate")

    @property
    def name(self) -> str:
        return f"Chorus(rate={self.rate_hz}Hz, depth={self.depth_ms}ms)"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        n = arr.shape[0]
        if n == 0:
            return arr

        wet = float(np.clip(self.wet, 0.0, 1.0))
        max_delay_samples = int(self.depth_ms * 0.001 * self.sample_rate)
        if max_delay_samples < 1:
            return arr

        t = np.arange(n, dtype=np.float32) / np.float32(self.sample_rate)
        lfo = (np.sin(_TWO_PI * np.float32(self.rate_hz) * t) + 1.0) * 0.5
        delay_samples = (lfo * max_delay_samples).astype(np.float32)

        indices = np.arange(n, dtype=np.float32) - delay_samples
        indices = np.clip(indices, 0, n - 1)

        # Linear interpolation for sub-sample delay
        idx_floor = np.floor(indices).astype(int)
        idx_ceil = np.minimum(idx_floor + 1, n - 1)
        frac = indices - idx_floor.astype(np.float32)

        delayed = arr[idx_floor] * (1.0 - frac) + arr[idx_ceil] * frac
        return np.ascontiguousarray(arr * (1.0 - wet) + delayed * wet)


@dataclass(frozen=True, slots=True)
class SchroederReverb:
    """
    Schroeder reverb (4 comb filters + 2 all-pass filters).

    Simple but characteristic metallic reverb suitable for synthesis.
    """

    sample_rate: int
    room_scale: float = 0.7
    wet: float = 0.3
    damping: float = 0.5

    def __post_init__(self) -> None:
        _require_positive(self.sample_rate, "sample_rate")
        _require(0.0 <= self.room_scale <= 1.0, "room_scale must be in [0, 1]")
        _require(0.0 <= self.damping <= 1.0, "damping must be in [0, 1]")

    @property
    def name(self) -> str:
        return f"Reverb(room={self.room_scale}, wet={self.wet})"

    @staticmethod
    def _comb(
        signal: npt.NDArray[np.float32],
        delay: int,
        feedback: float,
        damping: float,
    ) -> npt.NDArray[np.float32]:
        n = signal.shape[0]
        out = np.zeros(n, dtype=np.float32)
        buf = np.zeros(delay, dtype=np.float32)
        damp_state = np.float32(0.0)
        idx = 0
        for i in range(n):
            delayed = buf[idx]
            damp_state = delayed * (1.0 - damping) + damp_state * damping
            buf[idx] = signal[i] + damp_state * feedback
            out[i] = delayed
            idx = (idx + 1) % delay
        return out

    @staticmethod
    def _allpass(
        signal: npt.NDArray[np.float32],
        delay: int,
        feedback: float = 0.5,
    ) -> npt.NDArray[np.float32]:
        n = signal.shape[0]
        out = np.zeros(n, dtype=np.float32)
        buf = np.zeros(delay, dtype=np.float32)
        idx = 0
        for i in range(n):
            delayed = buf[idx]
            buf[idx] = signal[i] + delayed * feedback
            out[i] = -signal[i] + delayed
            idx = (idx + 1) % delay
        return out

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        if arr.size == 0:
            return arr

        wet = float(np.clip(self.wet, 0.0, 1.0))
        sr_scale = self.sample_rate / 44100.0
        rs = self.room_scale

        # Classic Schroeder comb delays (tuned to avoid resonance alignment)
        comb_delays = [
            max(1, int(1557 * sr_scale * rs)),
            max(1, int(1617 * sr_scale * rs)),
            max(1, int(1491 * sr_scale * rs)),
            max(1, int(1422 * sr_scale * rs)),
        ]
        feedback = 0.84 * rs
        comb_sum = sum(
            self._comb(arr, d, feedback, self.damping) for d in comb_delays
        )
        comb_sum /= np.float32(len(comb_delays))

        # All-pass stages for diffusion
        ap_delays = [max(1, int(225 * sr_scale)), max(1, int(556 * sr_scale))]
        diffused = comb_sum
        for apd in ap_delays:
            diffused = self._allpass(diffused, apd, 0.5)

        mixed = arr * (1.0 - wet) + diffused * wet
        return DSP.clip(mixed)


@dataclass(frozen=True, slots=True)
class Tremolo:
    """Amplitude modulation via a low-frequency oscillator."""

    sample_rate: int
    rate_hz: float = 5.0
    depth: float = 0.5

    @property
    def name(self) -> str:
        return f"Tremolo(rate={self.rate_hz}Hz, depth={self.depth})"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        _require_positive(self.sample_rate, "sample_rate")
        depth = float(np.clip(self.depth, 0.0, 1.0))
        t = np.arange(arr.shape[0], dtype=np.float32) / np.float32(self.sample_rate)
        lfo = (1.0 - depth) + depth * (
            0.5 + 0.5 * np.sin(_TWO_PI * np.float32(self.rate_hz) * t)
        )
        return np.ascontiguousarray(arr * lfo)


@dataclass(frozen=True, slots=True)
class FadeInOut:
    """Apply linear fade-in and/or fade-out to signal edges."""

    sample_rate: int
    fade_in_s: float = 0.01
    fade_out_s: float = 0.01

    @property
    def name(self) -> str:
        return f"Fade(in={self.fade_in_s}s, out={self.fade_out_s}s)"

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        n = arr.shape[0]
        if n == 0:
            return arr

        out = arr.copy()
        fade_in = min(n, max(0, int(round(self.fade_in_s * self.sample_rate))))
        fade_out = min(n - fade_in, max(0, int(round(self.fade_out_s * self.sample_rate))))

        if fade_in > 0:
            out[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
        if fade_out > 0:
            out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
        return np.ascontiguousarray(out)


class EffectChain:
    """
    Composable, ordered sequence of ``Effect`` instances.

    Applying the chain runs each effect in order on the signal.
    Immutable once created; use ``append`` / ``prepend`` to derive new chains.
    """

    __slots__ = ("_effects",)

    def __init__(self, effects: Sequence[Effect] = ()) -> None:
        self._effects: tuple[Effect, ...] = tuple(effects)

    @property
    def effects(self) -> tuple[Effect, ...]:
        return self._effects

    def __len__(self) -> int:
        return len(self._effects)

    def __repr__(self) -> str:
        names = " → ".join(e.name for e in self._effects) or "(empty)"
        return f"EffectChain[{names}]"

    def append(self, effect: Effect) -> EffectChain:
        """Return a **new** chain with ``effect`` appended."""
        return EffectChain((*self._effects, effect))

    def prepend(self, effect: Effect) -> EffectChain:
        """Return a **new** chain with ``effect`` prepended."""
        return EffectChain((effect, *self._effects))

    def __call__(self, signal: FloatSignal) -> npt.NDArray[np.float32]:
        arr = _as_f32(signal)
        for fx in self._effects:
            arr = _as_f32(fx(arr))
            DSP.require_finite(arr)
        return arr


# ═══════════════════════════════════════════════════════════════════════════════
# Signal Analysis (pure)
# ═══════════════════════════════════════════════════════════════════════════════

class SignalAnalyzer:
    """Non-destructive signal measurements — all pure and side-effect free."""

    __slots__ = ()

    @staticmethod
    def peak(signal: FloatSignal) -> float:
        """Peak absolute amplitude."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        return float(np.max(np.abs(arr))) if arr.size else 0.0

    @staticmethod
    def rms(signal: FloatSignal) -> float:
        """Root-mean-square amplitude."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        return float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0

    @staticmethod
    def crest_factor(signal: FloatSignal) -> float:
        """Ratio of peak to RMS (headroom indicator). Returns 0 for silence."""
        rms_val = SignalAnalyzer.rms(signal)
        if rms_val < _EPSILON:
            return 0.0
        return SignalAnalyzer.peak(signal) / rms_val

    @staticmethod
    def peak_db(signal: FloatSignal) -> float:
        """Peak amplitude in dBFS (decibels relative to full scale)."""
        p = SignalAnalyzer.peak(signal)
        if p < _EPSILON:
            return -math.inf
        return 20.0 * math.log10(p)

    @staticmethod
    def rms_db(signal: FloatSignal) -> float:
        """RMS amplitude in dBFS."""
        r = SignalAnalyzer.rms(signal)
        if r < _EPSILON:
            return -math.inf
        return 20.0 * math.log10(r)

    @staticmethod
    def zero_crossing_rate(signal: FloatSignal) -> float:
        """Fraction of adjacent samples that cross zero (timbre / pitch hint)."""
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        if arr.size < 2:
            return 0.0
        crossings = np.sum(np.abs(np.diff(np.sign(arr))) > 0)
        return float(crossings) / (arr.size - 1)

    @staticmethod
    def spectral_centroid(signal: FloatSignal, sample_rate: int) -> float:
        """
        Frequency-domain 'center of mass' — correlates with perceived brightness.

        Returns frequency in Hz.
        """
        arr = _as_f32(signal)
        DSP.require_finite(arr)
        _require_positive(sample_rate, "sample_rate")
        if arr.size == 0:
            return 0.0

        spectrum = np.abs(np.fft.rfft(arr))
        freqs = np.fft.rfftfreq(arr.size, d=1.0 / sample_rate)
        total = float(np.sum(spectrum))
        if total < _EPSILON:
            return 0.0
        return float(np.sum(freqs * spectrum) / total)

    @staticmethod
    def duration_s(signal: FloatSignal, sample_rate: int) -> float:
        """Duration in seconds."""
        return signal.shape[0] / sample_rate if signal.size else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Synthesis (pure signal generators)
# ═══════════════════════════════════════════════════════════════════════════════

class Synthesis:
    """Signal generators — all pure and deterministic (given an optional RNG seed)."""

    __slots__ = ()

    @staticmethod
    def tone(
        config: AudioConfig,
        *,
        frequency_hz: float,
        duration_s: float,
        amplitude: float = 0.9,
        waveform: WaveformType | str = WaveformType.SINE,
        phase_rad: float = 0.0,
        pulse_width: float = 0.5,
        rng: np.random.Generator | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Generate a mono tone.

        Parameters
        ----------
        frequency_hz : float > 0
        duration_s : float > 0
        amplitude : float, peak amplitude
        waveform : WaveformType or str
        phase_rad : initial phase offset (radians)
        pulse_width : duty cycle for ``PULSE`` waveform ∈ (0, 1)
        rng : optional NumPy Generator for ``NOISE`` waveform
        """
        _require_positive(frequency_hz, "frequency_hz")
        _require_positive(duration_s, "duration_s")
        sr = config.sample_rate
        frames = config.frames_for(duration_s)

        t = np.arange(frames, dtype=np.float32) / np.float32(sr)
        phase = _TWO_PI * np.float32(frequency_hz) * t + np.float32(phase_rad)

        wf = WaveformType(waveform) if isinstance(waveform, str) else waveform

        match wf:
            case WaveformType.SINE:
                sig = np.sin(phase)
            case WaveformType.SQUARE:
                sig = np.sign(np.sin(phase))
            case WaveformType.SAWTOOTH:
                x = (t * np.float32(frequency_hz)) % 1.0
                sig = 2.0 * x - 1.0
            case WaveformType.TRIANGLE:
                x = (t * np.float32(frequency_hz)) % 1.0
                sig = 2.0 * np.abs(2.0 * x - 1.0) - 1.0
            case WaveformType.PULSE:
                pw = float(np.clip(pulse_width, 0.01, 0.99))
                x = (t * np.float32(frequency_hz)) % 1.0
                sig = np.where(x < pw, np.float32(1.0), np.float32(-1.0))
            case WaveformType.NOISE:
                g = rng if rng is not None else np.random.default_rng()
                sig = g.uniform(-1.0, 1.0, size=frames).astype(np.float32)

        return np.ascontiguousarray(sig.astype(np.float32, copy=False) * np.float32(amplitude))

    @staticmethod
    def chirp(
        config: AudioConfig,
        *,
        start_hz: float,
        end_hz: float,
        duration_s: float,
        amplitude: float = 0.9,
        method: str = "linear",
    ) -> npt.NDArray[np.float32]:
        """
        Frequency sweep from ``start_hz`` to ``end_hz``.

        Methods: ``"linear"`` or ``"logarithmic"``.
        """
        _require_positive(start_hz, "start_hz")
        _require_positive(end_hz, "end_hz")
        _require_positive(duration_s, "duration_s")
        frames = config.frames_for(duration_s)
        t = np.arange(frames, dtype=np.float64) / config.sample_rate

        if method == "logarithmic":
            k = (end_hz / start_hz) ** (1.0 / duration_s)
            phase = _TWO_PI * start_hz * (k**t - 1.0) / math.log(k)
        else:  # linear
            rate = (end_hz - start_hz) / duration_s
            phase = _TWO_PI * (start_hz * t + 0.5 * rate * t**2)

        sig = np.sin(phase).astype(np.float32, copy=False) * np.float32(amplitude)
        return np.ascontiguousarray(sig)

    @staticmethod
    def silence(config: AudioConfig, *, duration_s: float) -> npt.NDArray[np.float32]:
        """Generate silence."""
        _require_positive(duration_s, "duration_s")
        return np.zeros(config.frames_for(duration_s), dtype=np.float32)

    @staticmethod
    def pink_noise(
        config: AudioConfig,
        *,
        duration_s: float,
        amplitude: float = 0.9,
        rng: np.random.Generator | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Generate pink noise (1/f spectrum) via Voss–McCartney algorithm.

        Produces a more natural, less harsh noise than white noise.
        """
        _require_positive(duration_s, "duration_s")
        frames = config.frames_for(duration_s)
        g = rng if rng is not None else np.random.default_rng()

        num_rows = 16
        # Pad to next power of 2 for efficiency
        array = g.standard_normal((num_rows, frames)).astype(np.float32)
        # Each row is updated at 1/2^n the rate
        for row in range(1, num_rows):
            stride = 2**row
            mask = np.zeros(frames, dtype=np.float32)
            mask[::stride] = 1.0
            array[row] *= mask
            # Forward-fill
            for i in range(1, frames):
                if mask[i] == 0.0:
                    array[row, i] = array[row, i - 1]

        sig = np.sum(array, axis=0)
        sig = DSP.normalize_peak(sig, target_peak=amplitude)
        return np.ascontiguousarray(sig)

    @staticmethod
    def kick_drum(
        config: AudioConfig,
        *,
        duration_s: float = 0.3,
        amplitude: float = 0.95,
    ) -> npt.NDArray[np.float32]:
        """
        Synthesize a kick drum: pitch-swept sine + exponential decay.
        """
        _require_positive(duration_s, "duration_s")
        frames = config.frames_for(duration_s)
        t = np.arange(frames, dtype=np.float32) / np.float32(config.sample_rate)

        # Pitch envelope: 150 Hz → 40 Hz exponential sweep
        freq = 40.0 + 110.0 * np.exp(-30.0 * t)
        phase = _TWO_PI * np.cumsum(freq / config.sample_rate).astype(np.float32)
        sig = np.sin(phase)

        # Amplitude envelope: sharp attack, exponential decay
        env = np.exp(-8.0 * t).astype(np.float32)
        return np.ascontiguousarray(sig * env * np.float32(amplitude))

    @staticmethod
    def snare_drum(
        config: AudioConfig,
        *,
        duration_s: float = 0.2,
        amplitude: float = 0.9,
        rng: np.random.Generator | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Synthesize a snare drum: sine body + filtered noise burst.
        """
        _require_positive(duration_s, "duration_s")
        frames = config.frames_for(duration_s)
        t = np.arange(frames, dtype=np.float32) / np.float32(config.sample_rate)
        g = rng if rng is not None else np.random.default_rng()

        # Body: 200 Hz sine with fast decay
        body = np.sin(_TWO_PI * 200.0 * t) * np.exp(-20.0 * t)
        # Noise: white noise with medium decay
        noise = g.uniform(-1.0, 1.0, size=frames).astype(np.float32) * np.exp(-12.0 * t)

        sig = (body * 0.6 + noise * 0.4).astype(np.float32)
        return np.ascontiguousarray(DSP.normalize_peak(sig, target_peak=amplitude))

    @staticmethod
    def hihat(
        config: AudioConfig,
        *,
        duration_s: float = 0.08,
        amplitude: float = 0.7,
        rng: np.random.Generator | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Synthesize a hi-hat: high-frequency filtered noise with very fast decay.
        """
        _require_positive(duration_s, "duration_s")
        frames = config.frames_for(duration_s)
        t = np.arange(frames, dtype=np.float32) / np.float32(config.sample_rate)
        g = rng if rng is not None else np.random.default_rng()

        noise = g.uniform(-1.0, 1.0, size=frames).astype(np.float32)
        env = np.exp(-40.0 * t).astype(np.float32)
        sig = noise * env

        # Simple high-pass via first-difference approximation
        hp = np.diff(sig, prepend=np.float32(0.0))
        return np.ascontiguousarray(DSP.normalize_peak(hp, target_peak=amplitude))

    @staticmethod
    def mix(
        signals: Sequence[FloatSignal],
        weights: Sequence[float] | None = None,
    ) -> npt.NDArray[np.float32]:
        """Mix multiple signals by zero-padding shorter ones, then normalize peak."""
        if not signals:
            return np.zeros(0, dtype=np.float32)

        max_len = max(np.asarray(s).shape[0] for s in signals)
        wts = weights if weights is not None else [1.0] * len(signals)
        out = np.zeros(max_len, dtype=np.float32)

        for i, s in enumerate(signals):
            arr = _as_f32(s)
            DSP.require_finite(arr)
            w = float(wts[i]) if i < len(wts) else 1.0
            out[: arr.shape[0]] += arr * np.float32(w)

        return DSP.normalize_peak(out)

    @staticmethod
    def concatenate(
        signals: Sequence[FloatSignal],
        gap_s: float = 0.0,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
    ) -> npt.NDArray[np.float32]:
        """Concatenate signals with optional silence gaps."""
        if not signals:
            return np.zeros(0, dtype=np.float32)

        gap_frames = max(0, int(round(gap_s * sample_rate)))
        gap = np.zeros(gap_frames, dtype=np.float32) if gap_frames else None

        parts: list[npt.NDArray[np.float32]] = []
        for i, s in enumerate(signals):
            arr = _as_f32(s)
            DSP.require_finite(arr)
            parts.append(arr)
            if gap is not None and i < len(signals) - 1:
                parts.append(gap)

        return np.ascontiguousarray(np.concatenate(parts))


# ═══════════════════════════════════════════════════════════════════════════════
# Music Theory (pure)
# ═══════════════════════════════════════════════════════════════════════════════

class MusicTheory:
    """Musical helpers: note parsing, scale generation, melody/chord rendering."""

    __slots__ = ()

    _NOTE_INDEX: Final[dict[str, int]] = {
        "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4,
        "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9,
        "A#": 10, "BB": 10, "B": 11,
    }

    @staticmethod
    def note_to_midi(note: str) -> int:
        """
        Parse a note name (e.g. ``'A4'``, ``'C#5'``, ``'Db3'``) to MIDI number.

        Convention: ``C-1 = 0``, ``A4 = 69``.
        """
        _require(bool(note) and len(note) >= 2, "Invalid note (expected e.g. 'A4', 'C#5').")
        s = note.strip().upper()

        pitch = s[0]
        rest = s[1:]

        if rest and rest[0] in ("#", "B") and not rest[0].isdigit():
            # Handle flats: 'B' followed by a digit is ambiguous with note B
            # 'Bb3' → pitch='BB', rest='3' vs 'B3' → pitch='B', rest='3'
            if rest[0] == "#" or (rest[0] == "B" and len(rest) > 1 and rest[1:].lstrip("-").isdigit()):
                pitch += rest[0]
                rest = rest[1:]

        try:
            octave = int(rest)
        except ValueError as e:
            raise ValueError(f"Invalid octave in note '{note}'.") from e

        _require(pitch in MusicTheory._NOTE_INDEX, f"Unknown pitch class in '{note}'.")
        return (octave + 1) * 12 + MusicTheory._NOTE_INDEX[pitch]

    @staticmethod
    def midi_to_frequency(midi: int, *, a4_hz: float = _A4_HZ) -> float:
        """MIDI note number → frequency in Hz (12-TET)."""
        return float(a4_hz) * (2.0 ** ((midi - _MIDI_A4) / 12.0))

    @staticmethod
    def note_to_frequency(note: str, *, a4_hz: float = _A4_HZ) -> float:
        """Note name → frequency in Hz."""
        return MusicTheory.midi_to_frequency(MusicTheory.note_to_midi(note), a4_hz=a4_hz)

    @staticmethod
    def frequency_to_midi(freq_hz: float, *, a4_hz: float = _A4_HZ) -> float:
        """Frequency → MIDI note number (possibly fractional for microtuning)."""
        _require_positive(freq_hz, "freq_hz")
        return 12.0 * math.log2(freq_hz / a4_hz) + _MIDI_A4

    @staticmethod
    def scale_frequencies(
        root: str,
        scale: ScaleType = ScaleType.MAJOR,
        *,
        octaves: int = 1,
        a4_hz: float = _A4_HZ,
    ) -> list[float]:
        """
        Return frequencies for a scale starting at ``root``.

        Example: ``scale_frequencies("C4", ScaleType.MAJOR, octaves=2)``
        """
        _require_positive(octaves, "octaves")
        root_midi = MusicTheory.note_to_midi(root)
        intervals = _SCALE_INTERVALS[scale]
        freqs: list[float] = []
        for octave in range(octaves):
            for interval in intervals:
                midi = root_midi + octave * 12 + interval
                freqs.append(MusicTheory.midi_to_frequency(midi, a4_hz=a4_hz))
        # Add the octave-completing note
        freqs.append(MusicTheory.midi_to_frequency(root_midi + octaves * 12, a4_hz=a4_hz))
        return freqs

    @staticmethod
    def chord_frequencies(
        root: str,
        *,
        intervals: Sequence[int] = (0, 4, 7),
        a4_hz: float = _A4_HZ,
    ) -> list[float]:
        """
        Return frequencies for a chord.

        Default intervals ``(0, 4, 7)`` = major triad.
        Minor triad: ``(0, 3, 7)``. Dom7: ``(0, 4, 7, 10)``.
        """
        root_midi = MusicTheory.note_to_midi(root)
        return [
            MusicTheory.midi_to_frequency(root_midi + iv, a4_hz=a4_hz)
            for iv in intervals
        ]

    @staticmethod
    def render_chord(
        config: AudioConfig,
        root: str,
        *,
        intervals: Sequence[int] = (0, 4, 7),
        duration_s: float = 1.0,
        waveform: WaveformType | str = WaveformType.SINE,
        amplitude: float = 0.7,
    ) -> npt.NDArray[np.float32]:
        """Render a chord as a mixed signal."""
        freqs = MusicTheory.chord_frequencies(root, intervals=intervals)
        per_amp = amplitude / max(1, len(freqs))
        tones = [
            Synthesis.tone(config, frequency_hz=f, duration_s=duration_s,
                           amplitude=per_amp, waveform=waveform)
            for f in freqs
        ]
        return Synthesis.mix(tones)

    @staticmethod
    def render_melody(
        config: AudioConfig,
        notes: Sequence[tuple[str, float]],
        *,
        waveform: WaveformType | str = WaveformType.SINE,
        amplitude: float = 0.85,
        gap_s: float = 0.01,
    ) -> npt.NDArray[np.float32]:
        """
        Render a sequence of ``(note_name, duration_s)`` pairs.

        Each note gets an ADSR envelope and is separated by ``gap_s`` silence.
        """
        parts: list[npt.NDArray[np.float32]] = []
        silence = np.zeros(max(0, int(round(gap_s * config.sample_rate))), dtype=np.float32)

        for name, dur in notes:
            freq = MusicTheory.note_to_frequency(name)
            sig = Synthesis.tone(
                config, frequency_hz=freq, duration_s=dur,
                amplitude=amplitude, waveform=waveform,
            )
            env = DSP.adsr_envelope(sig.shape[0], config.sample_rate)
            sig = DSP.apply_envelope(sig, env)
            parts.append(sig)
            if silence.size:
                parts.append(silence)

        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.ascontiguousarray(np.concatenate(parts))

    @staticmethod
    def render_arpeggio(
        config: AudioConfig,
        root: str,
        *,
        intervals: Sequence[int] = (0, 4, 7),
        note_duration_s: float = 0.15,
        octaves: int = 2,
        direction: str = "up",
        waveform: WaveformType | str = WaveformType.SINE,
        amplitude: float = 0.8,
    ) -> npt.NDArray[np.float32]:
        """
        Render an arpeggio pattern.

        Directions: ``"up"``, ``"down"``, ``"updown"``.
        """
        root_midi = MusicTheory.note_to_midi(root)
        midi_notes: list[int] = []
        for octave in range(octaves):
            for iv in intervals:
                midi_notes.append(root_midi + octave * 12 + iv)
        midi_notes.append(root_midi + octaves * 12)

        match direction:
            case "down":
                midi_notes.reverse()
            case "updown":
                down = list(reversed(midi_notes[:-1]))
                midi_notes = midi_notes + down
            case _:  # "up" or default
                pass

        note_tuples = [
            (
                "",  # placeholder — we use freq directly below
                note_duration_s,
            )
            for _ in midi_notes
        ]

        parts: list[npt.NDArray[np.float32]] = []
        for midi in midi_notes:
            freq = MusicTheory.midi_to_frequency(midi)
            sig = Synthesis.tone(
                config, frequency_hz=freq, duration_s=note_duration_s,
                amplitude=amplitude, waveform=waveform,
            )
            env = DSP.adsr_envelope(sig.shape[0], config.sample_rate)
            parts.append(DSP.apply_envelope(sig, env))

        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.ascontiguousarray(np.concatenate(parts))

    @staticmethod
    def render_drum_pattern(
        config: AudioConfig,
        pattern: Sequence[str],
        *,
        bpm: float = 120.0,
        amplitude: float = 0.85,
        rng: np.random.Generator | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Render a drum pattern from a sequence of hit codes.

        Codes: ``"K"`` = kick, ``"S"`` = snare, ``"H"`` = hi-hat, ``"-"`` = rest.

        Each step is one beat (quarter-note at the given BPM).

        Example: ``["K", "H", "S", "H", "K", "H", "S", "H"]``
        """
        _require_positive(bpm, "bpm")
        beat_s = 60.0 / bpm
        g = rng if rng is not None else np.random.default_rng()

        parts: list[npt.NDArray[np.float32]] = []
        for code in pattern:
            beat_frames = config.frames_for(beat_s)
            step = np.zeros(beat_frames, dtype=np.float32)
            match code.upper():
                case "K":
                    hit = Synthesis.kick_drum(config, duration_s=min(beat_s, 0.3), amplitude=amplitude)
                case "S":
                    hit = Synthesis.snare_drum(config, duration_s=min(beat_s, 0.2), amplitude=amplitude, rng=g)
                case "H":
                    hit = Synthesis.hihat(config, duration_s=min(beat_s, 0.08), amplitude=amplitude * 0.7, rng=g)
                case _:
                    hit = None

            if hit is not None:
                n = min(hit.shape[0], beat_frames)
                step[:n] = hit[:n]
            parts.append(step)

        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.ascontiguousarray(np.concatenate(parts))

    @staticmethod
    def metronome(
        config: AudioConfig,
        *,
        bpm: float = 120.0,
        beats: int = 8,
        accent_first: bool = True,
    ) -> npt.NDArray[np.float32]:
        """
        Generate a metronome click track.

        Accented beat (first of each bar) uses a higher-pitched click.
        """
        _require_positive(bpm, "bpm")
        _require(beats > 0, "beats must be > 0")
        beat_s = 60.0 / bpm
        click_dur = min(0.02, beat_s * 0.5)

        click_hi = Synthesis.tone(config, frequency_hz=1500.0, duration_s=click_dur, amplitude=0.9)
        click_lo = Synthesis.tone(config, frequency_hz=1000.0, duration_s=click_dur, amplitude=0.7)

        env = DSP.adsr_envelope(
            click_hi.shape[0], config.sample_rate,
            attack_s=0.001, decay_s=0.005, sustain_level=0.0, release_s=0.005,
        )
        click_hi = DSP.apply_envelope(click_hi, env)
        env_lo = DSP.adsr_envelope(
            click_lo.shape[0], config.sample_rate,
            attack_s=0.001, decay_s=0.005, sustain_level=0.0, release_s=0.005,
        )
        click_lo = DSP.apply_envelope(click_lo, env_lo)

        beat_frames = config.frames_for(beat_s)
        parts: list[npt.NDArray[np.float32]] = []
        for i in range(beats):
            step = np.zeros(beat_frames, dtype=np.float32)
            click = click_hi if (accent_first and i == 0) else click_lo
            n = min(click.shape[0], beat_frames)
            step[:n] = click[:n]
            parts.append(step)

        return np.ascontiguousarray(np.concatenate(parts))


# ═══════════════════════════════════════════════════════════════════════════════
# Serialization (isolated side effects)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class WavExportOptions:
    """
    Options for WAV file export.

    ``make_unique=True`` appends timestamp + UUID for concurrency-safe writes.
    """

    directory: Path = field(default_factory=lambda: Path("."))
    filename_prefix: str = "output"
    make_unique: bool = True

    def resolve_path(self) -> Path:
        """Create directory if needed and return the target WAV path."""
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.make_unique:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            uid = uuid.uuid4().hex[:10]
            name = f"{self.filename_prefix}-{stamp}-{uid}.wav"
        else:
            name = f"{self.filename_prefix}.wav"
        return self.directory / name


class WavWriter:
    """Atomic WAV file writer (write-to-temp then rename)."""

    __slots__ = ()

    @staticmethod
    def write_pcm16(
        path: Path,
        *,
        config: AudioConfig,
        pcm16: PCM16Array,
        channels: int,
    ) -> None:
        """Write PCM-16 data to a WAV file atomically."""
        try:
            path = Path(path)
            tmp = path.with_suffix(path.suffix + ".tmp")
            with wave.open(str(tmp), "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(config.sample_width_bytes)
                wf.setframerate(config.sample_rate)
                wf.writeframes(pcm16.tobytes())
            os.replace(tmp, path)  # atomic on POSIX + Windows NTFS
        except Exception as e:
            # Clean up temp file on failure
            with contextlib.suppress(OSError):
                if tmp.exists():
                    tmp.unlink()
            raise SerializationError(f"Failed to write WAV '{path}': {e}") from e

    @staticmethod
    def read_pcm16(
        path: Path,
    ) -> tuple[AudioConfig, npt.NDArray[np.float32]]:
        """
        Read a WAV file and return ``(config, float_signal)``.

        Only PCM-16 files are supported.
        """
        try:
            with wave.open(str(path), "rb") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()

                if sample_width != 2:
                    raise SerializationError(
                        f"Only 16-bit WAV supported, got {sample_width * 8}-bit."
                    )

                raw = wf.readframes(n_frames)
        except SerializationError:
            raise
        except Exception as e:
            raise SerializationError(f"Failed to read WAV '{path}': {e}") from e

        config = AudioConfig(
            sample_rate=sample_rate,
            channels=channels,
            bit_depth=16,
        )
        pcm16 = np.frombuffer(raw, dtype="<i2")
        signal = DSP.from_pcm16(pcm16)

        if channels == 2:
            signal = signal.reshape(-1, 2)

        return config, signal


# ═══════════════════════════════════════════════════════════════════════════════
# Playback Backend Contracts (isolated side effects)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class PlaybackStats:
    """Immutable playback statistics."""

    frames: int
    duration_s: float


class PlaybackHandle:
    """
    Concurrency-safe handle for a single playback / export operation.

    Thread-safe: ``wait()``, ``stop()`` can be called from any thread.
    """

    __slots__ = ("_done", "_stop_fn", "_stats", "_artifact_path")

    def __init__(
        self,
        *,
        done: threading.Event,
        stop_fn: Callable[[], None],
        stats: PlaybackStats,
        artifact_path: Path | None = None,
    ) -> None:
        self._done = done
        self._stop_fn = stop_fn
        self._stats = stats
        self._artifact_path = artifact_path

    @property
    def stats(self) -> PlaybackStats:
        return self._stats

    @property
    def artifact_path(self) -> Path | None:
        """For file-backend runs, the produced WAV path."""
        return self._artifact_path

    @property
    def is_done(self) -> bool:
        return self._done.is_set()

    def stop(self) -> None:
        """Request stop and wait for completion."""
        self._stop_fn()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until done. Returns ``True`` if completed before timeout."""
        return self._done.wait(timeout)


@runtime_checkable
class AudioBackend(Protocol):
    """Contract for playback backends."""

    def play_pcm16_interleaved(
        self,
        *,
        config: AudioConfig,
        pcm_bytes: bytes,
        frames: int,
    ) -> PlaybackHandle: ...


class WaveFileBackend:
    """
    Always-available backend: exports PCM-16 WAV (atomic + unique by default).

    Safe for fully concurrent usage.
    """

    __slots__ = ("_export",)

    def __init__(self, export: WavExportOptions | None = None) -> None:
        self._export = export or WavExportOptions()

    def play_pcm16_interleaved(
        self,
        *,
        config: AudioConfig,
        pcm_bytes: bytes,
        frames: int,
    ) -> PlaybackHandle:
        done = threading.Event()
        path = self._export.resolve_path()

        pcm16 = np.frombuffer(pcm_bytes, dtype="<i2")
        expected_samples = frames * config.channels
        if pcm16.size != expected_samples:
            raise SerializationError(
                f"PCM sample count mismatch: expected {expected_samples}, got {pcm16.size}."
            )

        WavWriter.write_pcm16(path, config=config, pcm16=pcm16, channels=config.channels)
        done.set()

        stats = PlaybackStats(frames=frames, duration_s=frames / config.sample_rate)
        return PlaybackHandle(done=done, stop_fn=lambda: None, stats=stats, artifact_path=path)


class PyAudioBackend:
    """
    Real-time playback via PyAudio.

    Pre-chunks PCM bytes upfront to minimize per-callback allocation and GC pressure.

    **Not** hard real-time (Python GIL); best-effort low-latency.
    """

    __slots__ = ("_pa", "_lock", "_closed")

    def __init__(self) -> None:
        if pyaudio is None:
            raise HardwareUnavailableError("PyAudio is not installed.")
        self._pa = pyaudio.PyAudio()
        self._lock = threading.RLock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._pa.terminate()

    def play_pcm16_interleaved(
        self,
        *,
        config: AudioConfig,
        pcm_bytes: bytes,
        frames: int,
    ) -> PlaybackHandle:
        with self._lock:
            if self._closed:
                raise HardwareUnavailableError("PyAudioBackend is closed.")

            done = threading.Event()
            stop_event = threading.Event()

            bytes_per_chunk = config.frames_per_buffer * config.frame_width_bytes
            _require(bytes_per_chunk > 0, "Invalid buffer sizing.")

            # Pre-chunk: allocate all chunks upfront, zero-pad the last
            chunks: list[bytes] = []
            for start in range(0, len(pcm_bytes), bytes_per_chunk):
                chunk = pcm_bytes[start : start + bytes_per_chunk]
                if len(chunk) < bytes_per_chunk:
                    chunk += b"\x00" * (bytes_per_chunk - len(chunk))
                chunks.append(chunk)

            chunk_iter = iter(range(len(chunks)))

            def callback(in_data, frame_count, time_info, status_flags):
                if stop_event.is_set():
                    done.set()
                    return (b"\x00" * bytes_per_chunk, pyaudio.paComplete)

                idx = next(chunk_iter, None)
                if idx is None:
                    done.set()
                    return (b"\x00" * bytes_per_chunk, pyaudio.paComplete)

                return (chunks[idx], pyaudio.paContinue)

            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=config.channels,
                rate=config.sample_rate,
                output=True,
                frames_per_buffer=config.frames_per_buffer,
                stream_callback=callback,
            )

            def stop_fn() -> None:
                stop_event.set()
                with contextlib.suppress(Exception):
                    if stream.is_active():
                        stream.stop_stream()
                with contextlib.suppress(Exception):
                    stream.close()
                done.set()

            stream.start_stream()
            stats = PlaybackStats(frames=frames, duration_s=frames / config.sample_rate)
            return PlaybackHandle(done=done, stop_fn=stop_fn, stats=stats)


# ═══════════════════════════════════════════════════════════════════════════════
# Facade / Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class AudioSynthesizer(contextlib.AbstractContextManager["AudioSynthesizer"]):
    """
    Top-level orchestrator bridging pure DSP → impure playback / export.

    Pipeline::

        float signal → [EffectChain] → ensure channels → clip → PCM-16 → backend

    Concurrency
    -----------
    - ``WaveFileBackend``: fully concurrent (unique atomic writes).
    - ``PyAudioBackend``: sequential streams recommended (device-dependent).
    """

    __slots__ = ("_config", "_backend", "_lock", "_current_handle", "_default_chain")

    def __init__(
        self,
        config: AudioConfig | None = None,
        backend: AudioBackend | None = None,
        default_chain: EffectChain | None = None,
    ) -> None:
        self._config = config or AudioConfig()
        self._backend: AudioBackend = backend if backend is not None else self._auto_backend()
        self._lock = threading.RLock()
        self._current_handle: PlaybackHandle | None = None
        self._default_chain = default_chain or EffectChain()

    @property
    def config(self) -> AudioConfig:
        return self._config

    @property
    def default_chain(self) -> EffectChain:
        return self._default_chain

    @default_chain.setter
    def default_chain(self, chain: EffectChain) -> None:
        self._default_chain = chain

    def _auto_backend(self) -> AudioBackend:
        if pyaudio is None:
            logger.info("PyAudio unavailable → using WaveFileBackend.")
            return WaveFileBackend()
        try:
            return PyAudioBackend()
        except Exception:
            logger.exception("PyAudioBackend init failed → using WaveFileBackend.")
            return WaveFileBackend()

    def close(self) -> None:
        """Release backend resources."""
        with self._lock:
            if isinstance(self._backend, PyAudioBackend):
                self._backend.close()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ── Pure Compilation ──────────────────────────────────────────────────

    def render_pcm16_bytes(
        self,
        signal: FloatSignal,
        *,
        pan: float = 0.0,
        chain: EffectChain | None = None,
        effects: Iterable[Callable[[FloatSignal], FloatSignal]] = (),
    ) -> tuple[bytes, int]:
        """
        Pure compilation pipeline:
        ``signal → chain → ad-hoc effects → ensure channels → clip → PCM-16 bytes``

        Returns ``(pcm_bytes, frames)``.
        """
        arr = _as_f32(signal)
        DSP.require_finite(arr)

        # Apply effect chain (default or explicit)
        active_chain = chain if chain is not None else self._default_chain
        if active_chain:
            arr = active_chain(arr)

        # Apply any additional ad-hoc effects
        for fx in effects:
            arr = _as_f32(fx(arr))
            DSP.require_finite(arr)

        arr = DSP.ensure_channels(arr, self._config.channels, pan=pan)
        arr = DSP.clip(arr)

        pcm16 = DSP.to_pcm16(arr)
        frames = int(arr.shape[0])
        return (pcm16.tobytes(), frames)

    # ── Playback ──────────────────────────────────────────────────────────

    def play(
        self,
        signal: FloatSignal,
        *,
        pan: float = 0.0,
        chain: EffectChain | None = None,
        effects: Iterable[Callable[[FloatSignal], FloatSignal]] = (),
        blocking: bool = True,
        timeout_s: float | None = None,
    ) -> PlaybackHandle:
        """
        Play via backend (hardware if available, otherwise export WAV).

        If ``blocking=True`` and ``timeout_s is None``, waits for the natural
        duration plus a safety margin.
        """
        pcm_bytes, frames = self.render_pcm16_bytes(
            signal, pan=pan, chain=chain, effects=effects,
        )

        with self._lock:
            if self._current_handle is not None:
                self._current_handle.stop()
                self._current_handle = None

            handle = self._backend.play_pcm16_interleaved(
                config=self._config,
                pcm_bytes=pcm_bytes,
                frames=frames,
            )
            self._current_handle = handle

        if blocking:
            expected = frames / self._config.sample_rate
            timeout = timeout_s if timeout_s is not None else (
                expected + _PLAYBACK_TIMEOUT_MARGIN_S
            )
            if not handle.wait(timeout=timeout):
                handle.stop()
                raise HardwareUnavailableError("Playback timed out and was stopped.")

        return handle

    def stop_audio(self) -> None:
        """Stop any currently playing audio."""
        with self._lock:
            if self._current_handle is not None:
                self._current_handle.stop()
                self._current_handle = None

    # ── Convenience Shortcuts ─────────────────────────────────────────────

    def play_tone(
        self,
        frequency_hz: float,
        duration_s: float = 0.5,
        *,
        waveform: WaveformType | str = WaveformType.SINE,
        amplitude: float = 0.9,
        **play_kwargs,
    ) -> PlaybackHandle:
        """Quick tone playback."""
        sig = Synthesis.tone(
            self._config,
            frequency_hz=frequency_hz,
            duration_s=duration_s,
            waveform=waveform,
            amplitude=amplitude,
        )
        return self.play(sig, **play_kwargs)

    def play_note(
        self,
        note: str,
        duration_s: float = 0.5,
        *,
        waveform: WaveformType | str = WaveformType.SINE,
        **play_kwargs,
    ) -> PlaybackHandle:
        """Quick note playback (e.g. ``play_note("C4", 0.5)``)."""
        freq = MusicTheory.note_to_frequency(note)
        return self.play_tone(freq, duration_s, waveform=waveform, **play_kwargs)

    def play_chord(
        self,
        root: str,
        duration_s: float = 1.0,
        *,
        intervals: Sequence[int] = (0, 4, 7),
        waveform: WaveformType | str = WaveformType.SINE,
        **play_kwargs,
    ) -> PlaybackHandle:
        """Quick chord playback."""
        sig = MusicTheory.render_chord(
            self._config, root,
            intervals=intervals, duration_s=duration_s, waveform=waveform,
        )
        return self.play(sig, **play_kwargs)

    def play_melody(
        self,
        notes: Sequence[tuple[str, float]],
        *,
        waveform: WaveformType | str = WaveformType.SINE,
        **play_kwargs,
    ) -> PlaybackHandle:
        """Quick melody playback."""
        sig = MusicTheory.render_melody(
            self._config, notes, waveform=waveform,
        )
        return self.play(sig, **play_kwargs)

    def play_drum_pattern(
        self,
        pattern: Sequence[str],
        *,
        bpm: float = 120.0,
        **play_kwargs,
    ) -> PlaybackHandle:
        """Quick drum pattern playback."""
        sig = MusicTheory.render_drum_pattern(
            self._config, pattern, bpm=bpm,
        )
        return self.play(sig, **play_kwargs)

    def export_wav(
        self,
        signal: FloatSignal,
        path: Path | str,
        *,
        pan: float = 0.0,
        chain: EffectChain | None = None,
    ) -> Path:
        """
        Export signal to a WAV file at the given path (no playback).

        Returns the resolved path.
        """
        pcm_bytes, frames = self.render_pcm16_bytes(signal, pan=pan, chain=chain)
        resolved = Path(path)
        pcm16 = np.frombuffer(pcm_bytes, dtype="<i2")
        WavWriter.write_pcm16(
            resolved, config=self._config,
            pcm16=pcm16, channels=self._config.channels,
        )
        return resolved
#!/usr/bin/env python3
"""
freq_math_app.py
================

Freq-Math: A sophisticated mathematical equation sonifier.

Architecture
------------
- **Adapter layer**: Isolates calculator dependency behind a stable contract.
- **Domain models**: Frozen dataclasses for all cross-boundary data.
- **Service layer**: Concurrency-safe ``AudioWorker`` communicates via message queue.
- **Presentation**: GUI with MVC separation; pure logic extracted for testability.
- **CLI**: Full-featured command-line interface with structured output.

Concurrency
-----------
- Worker threads communicate exclusively via ``queue.Queue[WorkerMessage]``.
- Zero shared mutable state between GUI thread and workers.
- All cross-boundary payloads are immutable (frozen dataclasses or NumPy arrays).
"""

from __future__ import annotations

import argparse
import contextlib
import enum
import json
import logging
import math
import os
import queue
import struct
import sys
import threading
import time
import wave
from collections import deque

from src.python.dependency_bootstrap import ensure_dependencies

ensure_dependencies((("numpy", "numpy"), ("matplotlib", "matplotlib")))
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final, Protocol, Sequence, runtime_checkable

import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Lazy GUI imports (allow headless CLI usage)
# ═══════════════════════════════════════════════════════════════════════════════

_tk = None
_ttk = None
_messagebox = None
_filedialog = None
_scrolledtext = None
_Figure = None
_FigureCanvasTkAgg = None


def _import_gui_deps() -> None:
    """Import GUI dependencies lazily so CLI mode works headless."""
    global _tk, _ttk, _messagebox, _filedialog, _scrolledtext
    global _Figure, _FigureCanvasTkAgg
    import tkinter as tk_mod
    from tkinter import ttk as ttk_mod, messagebox as mb_mod
    from tkinter import filedialog as fd_mod, scrolledtext as st_mod
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as FCA
    from matplotlib.figure import Figure as Fig

    _tk = tk_mod
    _ttk = ttk_mod
    _messagebox = mb_mod
    _filedialog = fd_mod
    _scrolledtext = st_mod
    _Figure = Fig
    _FigureCanvasTkAgg = FCA


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

_APP_TITLE: Final[str] = "Freq-Math Sonifier"
_DEFAULT_SAMPLE_RATE: Final[int] = 44_100
_DEFAULT_DURATION_S: Final[float] = 2.0
_DEFAULT_FREQUENCY_HZ: Final[float] = 440.0
_DEFAULT_X_RANGE: Final[tuple[float, float]] = (0.0, 1.0)
_PLOT_MAX_POINTS: Final[int] = 2000
_MATH_PLOT_RESOLUTION: Final[int] = 500
_SPECTRUM_FFT_SIZE: Final[int] = 4096
_QUEUE_POLL_INTERVAL_MS: Final[int] = 40
_HISTORY_MAX_LEN: Final[int] = 25
_MIN_DURATION_S: Final[float] = 0.1
_MAX_DURATION_S: Final[float] = 30.0
_MIN_FREQUENCY_HZ: Final[float] = 20.0
_MAX_FREQUENCY_HZ: Final[float] = 8000.0
_PCM16_MAX: Final[float] = 32_767.0


# ═══════════════════════════════════════════════════════════════════════════════
# Calculator Adapter (dependency isolation)
# ═══════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class CalculatorPort(Protocol):
    """Stable contract the app depends on — isolates calculator internals."""

    @property
    def sample_rate(self) -> int: ...

    def compile_and_validate(self, equation: str) -> str | None:
        """Return ``None`` if valid, or an error message string."""
        ...

    def generate_math_array(
        self,
        equation: str,
        *,
        x_range: tuple[float, float],
        steps: int,
    ) -> npt.NDArray[np.float32]: ...

    def generate_audio_array(
        self,
        equation: str,
        *,
        duration_s: float,
        x_range: tuple[float, float],
        base_frequency_hz: float,
        mapping_mode: str,
    ) -> npt.NDArray[np.float32]: ...

    def get_equation_info(self, equation: str) -> dict[str, Any]: ...

    def stop_audio(self) -> None: ...

    def list_presets(self) -> dict[str, str]: ...

    def list_mapping_modes(self) -> tuple[str, ...]: ...


# ── Concrete adapter for real calculator ──────────────────────────────────

try:
    from src.python.freq_math_calculator import (
        FreqMathCalculator,
        MappingMode,
        MathSecurityError,
        BuiltinEquation,
    )
    _HAS_CALCULATOR = True
except ImportError:
    _HAS_CALCULATOR = False
    logger.warning(
        "freq_math_calculator not importable; using mock adapter."
    )

try:
    from src.python.audio_synthesizer import AudioSynthesizer, AudioConfig
    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False


class RealCalculatorAdapter:
    """
    Adapter wrapping ``FreqMathCalculator`` behind the stable ``CalculatorPort``.

    Translates between the app's vocabulary and the calculator's API.
    """

    __slots__ = ("_calc", "_synth")

    def __init__(self, sample_rate: int = _DEFAULT_SAMPLE_RATE) -> None:
        if not _HAS_CALCULATOR:
            raise ImportError("FreqMathCalculator is not available.")
        self._calc = FreqMathCalculator(sample_rate=sample_rate, audio_player=None)
        self._synth: AudioSynthesizer | None = None
        if _HAS_AUDIO:
            with contextlib.suppress(Exception):
                self._synth = AudioSynthesizer(
                    AudioConfig(sample_rate=sample_rate, channels=1),
                )

    @property
    def sample_rate(self) -> int:
        return self._calc.sample_rate

    def compile_and_validate(self, equation: str) -> str | None:
        try:
            self._calc.compile_equation(equation)
            return None
        except Exception as exc:
            return str(exc)

    def generate_math_array(
        self,
        equation: str,
        *,
        x_range: tuple[float, float],
        steps: int,
    ) -> npt.NDArray[np.float32]:
        return self._calc.generate_math_array(
            equation, x_range=x_range, steps=steps,
        )

    def generate_audio_array(
        self,
        equation: str,
        *,
        duration_s: float,
        x_range: tuple[float, float],
        base_frequency_hz: float,
        mapping_mode: str = "fm_sine",
    ) -> npt.NDArray[np.float32]:
        mode = MappingMode(mapping_mode)
        return self._calc.generate_audio_array(
            equation,
            duration_s=duration_s,
            x_range=x_range,
            base_frequency_hz=base_frequency_hz,
            mode=mode,
        )

    def get_equation_info(self, equation: str) -> dict[str, Any]:
        return self._calc.get_equation_info(equation)

    def stop_audio(self) -> None:
        if self._synth is not None:
            with contextlib.suppress(Exception):
                self._synth.stop_audio()

    def play_signal(
        self, audio: npt.NDArray[np.float32], *, blocking: bool = False,
    ) -> None:
        if self._synth is not None:
            self._synth.play(audio, blocking=blocking)

    def list_presets(self) -> dict[str, str]:
        return self._calc.list_presets()

    def list_mapping_modes(self) -> tuple[str, ...]:
        return tuple(m.value for m in MappingMode)


class MockCalculatorAdapter:
    """
    Fallback adapter when the real calculator module is unavailable.

    Generates plausible signals for UI testing without real DSP.
    """

    __slots__ = ("_sr",)

    def __init__(self, sample_rate: int = _DEFAULT_SAMPLE_RATE) -> None:
        self._sr = sample_rate

    @property
    def sample_rate(self) -> int:
        return self._sr

    def compile_and_validate(self, equation: str) -> str | None:
        return None if equation.strip() else "Equation is empty."

    def generate_math_array(
        self,
        equation: str,
        *,
        x_range: tuple[float, float],
        steps: int,
    ) -> npt.NDArray[np.float32]:
        x = np.linspace(x_range[0], x_range[1], steps, dtype=np.float32)
        return np.sin(2.0 * np.pi * x * 5.0).astype(np.float32)

    def generate_audio_array(
        self,
        equation: str,
        *,
        duration_s: float,
        x_range: tuple[float, float],
        base_frequency_hz: float,
        mapping_mode: str = "fm_sine",
    ) -> npt.NDArray[np.float32]:
        frames = max(1, int(round(duration_s * self._sr)))
        t = np.arange(frames, dtype=np.float32) / self._sr
        return (np.sin(2.0 * np.pi * base_frequency_hz * t) * 0.8).astype(
            np.float32
        )

    def get_equation_info(self, equation: str) -> dict[str, Any]:
        return {
            "equation": equation,
            "metadata": {"complexity_score": 0, "is_safe": True},
            "min_result": -1.0,
            "max_result": 1.0,
            "span": 2.0,
            "mean_result": 0.0,
            "rms_result": 0.707,
            "monotonic": False,
        }

    def stop_audio(self) -> None:
        pass

    def play_signal(
        self, audio: npt.NDArray[np.float32], *, blocking: bool = False,
    ) -> None:
        pass

    def list_presets(self) -> dict[str, str]:
        return dict(_BUILTIN_PRESETS)

    def list_mapping_modes(self) -> tuple[str, ...]:
        return ("fm_sine", "am_sine", "phase_distortion", "wavetable", "direct")


def create_calculator(
    sample_rate: int = _DEFAULT_SAMPLE_RATE,
) -> RealCalculatorAdapter | MockCalculatorAdapter:
    """Factory: real adapter if available, mock otherwise."""
    if _HAS_CALCULATOR:
        try:
            return RealCalculatorAdapter(sample_rate)
        except Exception:
            logger.exception("Real calculator init failed; using mock.")
    return MockCalculatorAdapter(sample_rate)


# ═══════════════════════════════════════════════════════════════════════════════
# Domain Models (immutable, validated)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class SynthesisParams:
    """
    Immutable payload for a synthesis request.

    Validated at construction — workers never receive invalid params.
    """

    equation: str
    duration_s: float = _DEFAULT_DURATION_S
    base_frequency_hz: float = _DEFAULT_FREQUENCY_HZ
    x_range: tuple[float, float] = _DEFAULT_X_RANGE
    mapping_mode: str = "fm_sine"

    def __post_init__(self) -> None:
        if not self.equation.strip():
            raise ValueError("Equation must not be empty.")
        if not (_MIN_DURATION_S <= self.duration_s <= _MAX_DURATION_S):
            raise ValueError(
                f"Duration must be in [{_MIN_DURATION_S}, {_MAX_DURATION_S}]."
            )
        if not (_MIN_FREQUENCY_HZ <= self.base_frequency_hz <= _MAX_FREQUENCY_HZ):
            raise ValueError(
                f"Frequency must be in [{_MIN_FREQUENCY_HZ}, {_MAX_FREQUENCY_HZ}]."
            )
        x0, x1 = self.x_range
        if not (math.isfinite(x0) and math.isfinite(x1)):
            raise ValueError("X-range endpoints must be finite.")
        if x0 == x1:
            raise ValueError("X-range endpoints must differ.")


class WorkerState(enum.Enum):
    """Finite-state labels for worker → GUI communication."""

    PROGRESS = enum.auto()
    MATH_READY = enum.auto()
    AUDIO_READY = enum.auto()
    PLAYING = enum.auto()
    FINISHED = enum.auto()
    ERROR = enum.auto()


@dataclass(frozen=True, slots=True)
class WorkerMessage:
    """Immutable message DTO crossing the thread boundary."""

    state: WorkerState
    payload: Any = None


@dataclass(frozen=True, slots=True)
class SignalStats:
    """Computed statistics for a generated signal."""

    frames: int
    duration_s: float
    peak: float
    rms: float
    crest_factor: float
    zero_crossing_rate: float

    @classmethod
    def from_signal(
        cls, signal: npt.NDArray[np.float32], sample_rate: int,
    ) -> SignalStats:
        n = signal.shape[0]
        duration = n / sample_rate if sample_rate > 0 else 0.0
        peak = float(np.max(np.abs(signal))) if n else 0.0
        rms = float(np.sqrt(np.mean(signal**2))) if n else 0.0
        crest = peak / rms if rms > 1e-12 else 0.0

        zcr = 0.0
        if n > 1:
            crossings = np.sum(np.abs(np.diff(np.sign(signal))) > 0)
            zcr = float(crossings) / (n - 1)

        return cls(
            frames=n,
            duration_s=duration,
            peak=peak,
            rms=rms,
            crest_factor=crest,
            zero_crossing_rate=zcr,
        )

    def format_report(self) -> str:
        peak_db = 20.0 * math.log10(self.peak) if self.peak > 1e-12 else -math.inf
        rms_db = 20.0 * math.log10(self.rms) if self.rms > 1e-12 else -math.inf
        return (
            f"Frames       : {self.frames:,}\n"
            f"Duration     : {self.duration_s:.3f} s\n"
            f"Peak         : {self.peak:.4f}  ({peak_db:+.1f} dBFS)\n"
            f"RMS          : {self.rms:.4f}  ({rms_db:+.1f} dBFS)\n"
            f"Crest Factor : {self.crest_factor:.2f}\n"
            f"ZCR          : {self.zero_crossing_rate:.4f}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Theming (softcoded)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Softcoded color palette — swap for light theme or custom branding."""

    bg: str = "#1e1e2e"
    surface: str = "#313244"
    fg: str = "#cdd6f4"
    fg_dim: str = "#6c7086"
    accent: str = "#89b4fa"
    accent_hover: str = "#74c7ec"
    success: str = "#a6e3a1"
    warning: str = "#f9e2af"
    error: str = "#f38ba8"
    plot_bg: str = "#181825"
    plot_grid: str = "#45475a"
    plot_line_math: str = "#89b4fa"
    plot_line_audio: str = "#a6e3a1"
    plot_line_spectrum: str = "#f9e2af"


DARK_THEME: Final[ThemeColors] = ThemeColors()

LIGHT_THEME: Final[ThemeColors] = ThemeColors(
    bg="#eff1f5",
    surface="#ccd0da",
    fg="#4c4f69",
    fg_dim="#9ca0b0",
    accent="#1e66f5",
    accent_hover="#2a6ef5",
    success="#40a02b",
    warning="#df8e1d",
    error="#d20f39",
    plot_bg="#e6e9ef",
    plot_grid="#bcc0cc",
    plot_line_math="#1e66f5",
    plot_line_audio="#40a02b",
    plot_line_spectrum="#df8e1d",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Presets
# ═══════════════════════════════════════════════════════════════════════════════

_BUILTIN_PRESETS: Final[tuple[tuple[str, str], ...]] = (
    ("Sine Wave", "sin(2*pi*x)"),
    ("FM Synthesis", "sin(2*pi*x*5 + 3*sin(2*pi*x*0.5))"),
    ("Exponential Decay", "exp(-5*x) * sin(2*pi*x*8)"),
    ("Harmonic Stack", "sin(2*pi*x) + sin(4*pi*x)/2 + sin(6*pi*x)/3"),
    ("Bell Curve", "exp(-((x-0.5)**2)/(2*0.01))"),
    ("Chirp Sweep", "sin(2*pi*x*x*10)"),
    ("Wave Packet", "exp(-((x-0.5)**2)*50) * sin(2*pi*x*20)"),
    ("Sawtooth", "2*(x % 1) - 1"),
    ("Triangle", "2*abs(2*(x % 1) - 1) - 1"),
    ("Pulse Train", "sin(2*pi*x) + 0.5*sin(4*pi*x) + 0.25*sin(6*pi*x)"),
    ("Sigmoid", "1 / (1 + exp(-10*(x - 0.5)))"),
    ("Damped Oscillation", "exp(-3*x) * sin(2*pi*x*12) * cos(pi*x)"),
    ("Interference", "sin(2*pi*x*7) + sin(2*pi*x*7.5)"),
    ("Rectified Sine", "abs(sin(2*pi*x*4))"),
    ("Staircase", "floor(x*8) / 8"),
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pure Utilities (side-effect free, testable)
# ═══════════════════════════════════════════════════════════════════════════════

def decimate_for_display(
    signal: npt.NDArray[np.float32],
    max_points: int = _PLOT_MAX_POINTS,
) -> npt.NDArray[np.float32]:
    """
    Reduce signal to at most ``max_points`` for responsive plotting.

    Uses min/max decimation to preserve visual peaks.
    """
    n = signal.shape[0]
    if n <= max_points:
        return signal

    chunk_size = n // (max_points // 2)
    if chunk_size < 2:
        return signal[:: max(1, n // max_points)]

    trimmed = n - (n % chunk_size)
    reshaped = signal[:trimmed].reshape(-1, chunk_size)
    mins = reshaped.min(axis=1)
    maxs = reshaped.max(axis=1)

    # Interleave min and max for faithful envelope
    decimated = np.empty(mins.size + maxs.size, dtype=np.float32)
    decimated[0::2] = mins
    decimated[1::2] = maxs
    return decimated


def compute_spectrum(
    signal: npt.NDArray[np.float32],
    sample_rate: int,
    fft_size: int = _SPECTRUM_FFT_SIZE,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """
    Compute magnitude spectrum in dB.

    Returns ``(frequencies_hz, magnitude_db)`` for the positive half.
    """
    n = min(signal.shape[0], fft_size)
    if n == 0:
        return np.zeros(0), np.zeros(0)

    windowed = signal[:n] * np.hanning(n).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(windowed, n=fft_size))
    freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)

    # To dB, floor at -120 dB
    magnitude_db = 20.0 * np.log10(np.maximum(spectrum, 1e-12))
    magnitude_db = np.maximum(magnitude_db, -120.0)

    return freqs, magnitude_db


def encode_pcm16_wav(
    signal: npt.NDArray[np.float32],
    sample_rate: int,
    path: Path,
) -> None:
    """
    Write a mono PCM-16 WAV file.

    Peak-normalizes to prevent clipping, uses atomic write via temp file.
    """
    peak = float(np.max(np.abs(signal))) if signal.size else 0.0
    if peak < 1e-12:
        normalized = signal
    else:
        normalized = signal / peak

    pcm16 = (np.clip(normalized, -1.0, 1.0) * _PCM16_MAX).astype("<i2")

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with wave.open(str(tmp_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def format_equation_report(info: dict[str, Any]) -> str:
    """Format equation analysis info into a human-readable report."""
    if "error" in info:
        return f"Analysis Error:\n{info['error']}"

    meta = info.get("metadata", {})
    lines = [
        "═══ Equation Analysis ═══",
        "",
        f"  Normalized : {info.get('normalized_equation', 'N/A')}",
        f"  Safe       : {'✓' if meta.get('is_safe') else '✗'}",
        f"  Complexity : {meta.get('complexity_score', 'N/A')}",
        "",
        "── Structure ──",
        f"  Operations : {', '.join(meta.get('operations', ())) or 'none'}",
        f"  Functions  : {', '.join(meta.get('functions', ())) or 'none'}",
        "",
        "── Numerical Probing ──",
        f"  Range      : [{info.get('min_result', 0):.6f}, "
        f"{info.get('max_result', 0):.6f}]",
        f"  Span       : {info.get('span', 0):.6f}",
        f"  Mean       : {info.get('mean_result', 0):.6f}",
        f"  RMS        : {info.get('rms_result', 0):.6f}",
        f"  Monotonic  : {'yes' if info.get('monotonic') else 'no'}",
    ]

    test_points = info.get("test_points", ())
    results = info.get("results", ())
    if test_points and results:
        lines.append("")
        lines.append("── Sample Values ──")
        for x_val, y_val in zip(test_points, results):
            lines.append(f"  f({x_val:.3f}) = {y_val:.6f}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Service Layer (concurrency-safe worker)
# ═══════════════════════════════════════════════════════════════════════════════

class AudioWorker(threading.Thread):
    """
    Background worker: generate math + audio signals, post results to queue.

    Communicates **exclusively** via ``WorkerMessage`` DTOs.
    Holds no reference to any GUI object.
    """

    __slots__ = ("_params", "_queue", "_calc", "_cancel")

    def __init__(
        self,
        params: SynthesisParams,
        msg_queue: queue.Queue[WorkerMessage],
        calculator: RealCalculatorAdapter | MockCalculatorAdapter,
    ) -> None:
        super().__init__(daemon=True, name="AudioWorker")
        self._params = params
        self._queue = msg_queue
        self._calc = calculator
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            self._post(WorkerState.PROGRESS, 10)

            # ── Validate ──
            err = self._calc.compile_and_validate(self._params.equation)
            if err:
                self._post(WorkerState.ERROR, f"Compilation failed:\n{err}")
                return

            if self._cancel.is_set():
                return

            self._post(WorkerState.PROGRESS, 20)

            # ── Generate math signal (for plotting) ──
            math_signal = self._calc.generate_math_array(
                self._params.equation,
                x_range=self._params.x_range,
                steps=_MATH_PLOT_RESOLUTION,
            )
            self._post(WorkerState.MATH_READY, math_signal)
            self._post(WorkerState.PROGRESS, 40)

            if self._cancel.is_set():
                return

            # ── Generate audio ──
            audio_signal = self._calc.generate_audio_array(
                self._params.equation,
                duration_s=self._params.duration_s,
                x_range=self._params.x_range,
                base_frequency_hz=self._params.base_frequency_hz,
                mapping_mode=self._params.mapping_mode,
            )
            self._post(WorkerState.AUDIO_READY, audio_signal)
            self._post(WorkerState.PROGRESS, 80)

            if self._cancel.is_set():
                return

            # ── Play audio (best-effort) ──
            self._post(WorkerState.PLAYING, None)
            if hasattr(self._calc, "play_signal"):
                try:
                    self._calc.play_signal(audio_signal, blocking=False)
                except Exception:
                    logger.debug("Playback unavailable; signal generated only.")

            # ── Wait for playback duration ──
            deadline = time.monotonic() + self._params.duration_s
            while time.monotonic() < deadline:
                if self._cancel.is_set():
                    return
                time.sleep(0.05)

            self._post(WorkerState.PROGRESS, 100)
            self._post(WorkerState.FINISHED, None)

        except Exception as exc:
            logger.error("Worker failed: %s", exc, exc_info=True)
            self._post(WorkerState.ERROR, str(exc))

    def _post(self, state: WorkerState, payload: Any = None) -> None:
        self._queue.put(WorkerMessage(state=state, payload=payload))


# ═══════════════════════════════════════════════════════════════════════════════
# Plot Manager (extracted for testability and SRP)
# ═══════════════════════════════════════════════════════════════════════════════

class PlotManager:
    """
    Manages the three-subplot figure: math function, audio waveform, spectrum.

    Performance strategy:
    - Pre-allocated ``Line2D`` objects — ``set_data()`` mutations, never ``ax.clear()``.
    - Min/max decimation for large audio signals.
    - ``draw_idle()`` for non-blocking canvas refresh.
    """

    __slots__ = (
        "_fig",
        "_ax_math",
        "_ax_audio",
        "_ax_spectrum",
        "_line_math",
        "_line_audio",
        "_line_spectrum",
        "_canvas",
        "_colors",
        "_sample_rate",
    )

    def __init__(
        self,
        parent_widget: Any,
        colors: ThemeColors,
        sample_rate: int,
    ) -> None:
        self._colors = colors
        self._sample_rate = sample_rate

        self._fig = _Figure(figsize=(10, 8), facecolor=colors.bg)
        self._fig.subplots_adjust(hspace=0.45, top=0.96, bottom=0.06)

        self._ax_math = self._fig.add_subplot(311, facecolor=colors.plot_bg)
        self._ax_audio = self._fig.add_subplot(312, facecolor=colors.plot_bg)
        self._ax_spectrum = self._fig.add_subplot(313, facecolor=colors.plot_bg)

        axes_config: list[tuple[Any, str, str, str, str]] = [
            (self._ax_math, "Mathematical Function", "x", "f(x)", colors.plot_line_math),
            (self._ax_audio, "Audio Waveform", "Time (s)", "Amplitude", colors.plot_line_audio),
            (self._ax_spectrum, "Frequency Spectrum", "Frequency (Hz)", "Magnitude (dB)", colors.plot_line_spectrum),
        ]

        lines = []
        for ax, title, xlabel, ylabel, color in axes_config:
            ax.set_title(title, color=colors.fg, fontsize=10, pad=6)
            ax.set_xlabel(xlabel, color=colors.fg_dim, fontsize=8)
            ax.set_ylabel(ylabel, color=colors.fg_dim, fontsize=8)
            ax.tick_params(colors=colors.fg_dim, labelsize=7)
            ax.grid(True, alpha=0.2, color=colors.plot_grid, linewidth=0.5)
            for spine in ax.spines.values():
                spine.set_color(colors.surface)
            (line,) = ax.plot([], [], color=color, linewidth=1.5, antialiased=True)
            lines.append(line)

        self._line_math, self._line_audio, self._line_spectrum = lines

        self._ax_math.set_xlim(0, 1)
        self._ax_math.set_ylim(-1.1, 1.1)
        self._ax_audio.set_xlim(0, 2)
        self._ax_audio.set_ylim(-1.1, 1.1)
        self._ax_spectrum.set_xlim(20, sample_rate / 2)
        self._ax_spectrum.set_ylim(-120, 0)
        self._ax_spectrum.set_xscale("log")

        self._canvas = _FigureCanvasTkAgg(self._fig, master=parent_widget)
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
        self._canvas.draw()

    @property
    def widget(self) -> Any:
        return self._canvas.get_tk_widget()

    def update_math(
        self,
        x: npt.NDArray[np.float32],
        y: npt.NDArray[np.float32],
    ) -> None:
        """Update the math-function subplot."""
        self._line_math.set_data(x, y)
        self._ax_math.relim()
        self._ax_math.autoscale_view()
        self._canvas.draw_idle()

    def update_audio(
        self,
        audio: npt.NDArray[np.float32],
        duration_s: float,
    ) -> None:
        """Update the audio waveform subplot with decimated data."""
        decimated = decimate_for_display(audio)
        t = np.linspace(0, duration_s, decimated.shape[0])
        self._line_audio.set_data(t, decimated)
        self._ax_audio.relim()
        self._ax_audio.autoscale_view()
        self._canvas.draw_idle()

    def update_spectrum(
        self,
        audio: npt.NDArray[np.float32],
    ) -> None:
        """Compute and display the frequency spectrum."""
        freqs, mag_db = compute_spectrum(audio, self._sample_rate)
        if freqs.size == 0:
            return
        self._line_spectrum.set_data(freqs, mag_db)
        self._ax_spectrum.set_xlim(20, self._sample_rate / 2)
        self._ax_spectrum.set_ylim(float(np.min(mag_db)) - 5, float(np.max(mag_db)) + 5)
        self._canvas.draw_idle()

    def clear_all(self) -> None:
        """Reset all plots to empty state."""
        for line in (self._line_math, self._line_audio, self._line_spectrum):
            line.set_data([], [])
        self._canvas.draw_idle()


# ═══════════════════════════════════════════════════════════════════════════════
# GUI (presentation layer)
# ═══════════════════════════════════════════════════════════════════════════════

class FreqMathGUI:
    """
    Main application window.

    Responsibilities:
    - Build and manage widgets.
    - Dispatch user actions to the service layer.
    - Poll the message queue for worker results.
    - Update plots and status indicators.

    Holds zero mutable references to the worker thread.
    """

    __slots__ = (
        "_root",
        "_colors",
        "_calc",
        "_msg_queue",
        "_worker",
        "_is_playing",
        "_current_audio",
        "_history",
        # Widgets
        "_equation_entry",
        "_preset_var",
        "_duration_var",
        "_freq_var",
        "_x_start_var",
        "_x_end_var",
        "_mapping_var",
        "_history_listbox",
        "_status_label",
        "_stats_label",
        "_progress_var",
        "_progress_bar",
        "_plots",
        "_validation_label",
        "_synth_btn",
    )

    def __init__(
        self,
        root: Any,
        *,
        colors: ThemeColors = DARK_THEME,
        calculator: RealCalculatorAdapter | MockCalculatorAdapter | None = None,
    ) -> None:
        self._root = root
        self._colors = colors
        self._calc = calculator or create_calculator()
        self._msg_queue: queue.Queue[WorkerMessage] = queue.Queue()
        self._worker: AudioWorker | None = None
        self._is_playing = False
        self._current_audio: npt.NDArray[np.float32] | None = None
        self._history: deque[str] = deque(maxlen=_HISTORY_MAX_LEN)

        self._root.title(f"🎵 {_APP_TITLE}")
        self._root.geometry("1500x950")
        self._root.minsize(1000, 700)
        self._root.configure(bg=colors.bg)

        self._setup_styles()
        self._build_ui()
        self._bind_shortcuts()
        self._poll_queue()

    # ── Style ─────────────────────────────────────────────────────────────

    def _setup_styles(self) -> None:
        c = self._colors
        style = _ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=c.bg)
        style.configure("TLabelframe", background=c.bg, foreground=c.fg)
        style.configure(
            "TLabelframe.Label", background=c.bg, foreground=c.fg,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "TLabel", background=c.bg, foreground=c.fg, font=("Segoe UI", 9),
        )
        style.configure(
            "Title.TLabel", background=c.bg, foreground=c.accent,
            font=("Segoe UI", 18, "bold"),
        )
        style.configure(
            "Dim.TLabel", background=c.bg, foreground=c.fg_dim,
            font=("Segoe UI", 8),
        )
        style.configure(
            "Stats.TLabel", background=c.bg, foreground=c.fg_dim,
            font=("Consolas", 8),
        )
        style.configure(
            "Valid.TLabel", background=c.bg, foreground=c.success,
            font=("Segoe UI", 8),
        )
        style.configure(
            "Invalid.TLabel", background=c.bg, foreground=c.error,
            font=("Segoe UI", 8),
        )
        style.configure(
            "Action.TButton",
            background=c.surface, foreground=c.accent,
            font=("Segoe UI", 9, "bold"), borderwidth=0, padding=6,
        )
        style.map(
            "Action.TButton",
            background=[("active", c.accent)],
            foreground=[("active", c.bg)],
        )
        style.configure(
            "Stop.TButton",
            background=c.surface, foreground=c.error,
            font=("Segoe UI", 9, "bold"), borderwidth=0, padding=6,
        )
        style.map(
            "Stop.TButton",
            background=[("active", c.error)],
            foreground=[("active", c.bg)],
        )

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        c = self._colors

        # Header
        header = _ttk.Frame(self._root)
        header.pack(fill="x", padx=20, pady=(12, 4))
        _ttk.Label(header, text=f"🎵 {_APP_TITLE}", style="Title.TLabel").pack(
            side="left",
        )
        _ttk.Label(
            header,
            text="Ctrl+Enter: Synthesize  ·  Ctrl+S: Export  ·  Escape: Stop",
            style="Dim.TLabel",
        ).pack(side="right")

        # Main content
        main = _ttk.Frame(self._root)
        main.pack(fill="both", expand=True, padx=16, pady=4)

        left = _ttk.Frame(main)
        left.pack(side="left", fill="y", padx=(0, 12))

        right = _ttk.Frame(main)
        right.pack(side="right", fill="both", expand=True)

        self._build_input_panel(left)
        self._build_params_panel(left)
        self._build_history_panel(left)
        self._build_stats_panel(left)

        self._plots = PlotManager(right, c, self._calc.sample_rate)

        self._build_status_bar()

    def _build_input_panel(self, parent: Any) -> None:
        c = self._colors
        frame = _ttk.LabelFrame(parent, text="Equation")
        frame.pack(fill="x", pady=(0, 10), ipadx=8, ipady=6)

        # Presets
        preset_row = _ttk.Frame(frame)
        preset_row.pack(fill="x", pady=(2, 6))
        _ttk.Label(preset_row, text="Preset:").pack(side="left", padx=4)

        preset_names = ["Custom"] + [name for name, _ in _BUILTIN_PRESETS]
        presets_from_calc = self._calc.list_presets()
        for name, eq in presets_from_calc.items():
            if name not in preset_names:
                preset_names.append(name)

        self._preset_var = _tk.StringVar(value="Custom")
        combo = _ttk.Combobox(
            preset_row, textvariable=self._preset_var,
            values=preset_names, state="readonly", width=22,
        )
        combo.pack(side="left", fill="x", expand=True, padx=4)
        combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # Equation entry
        _ttk.Label(frame, text="f(x) =").pack(anchor="w", padx=4)
        self._equation_entry = _ttk.Entry(frame, font=("Consolas", 12), width=36)
        self._equation_entry.insert(0, _BUILTIN_PRESETS[0][1])
        self._equation_entry.pack(fill="x", padx=4, pady=4)
        self._equation_entry.bind("<KeyRelease>", self._on_equation_changed)

        # Validation indicator
        self._validation_label = _ttk.Label(frame, text="", style="Valid.TLabel")
        self._validation_label.pack(anchor="w", padx=4)

        # Action buttons
        btn_frame = _ttk.Frame(frame)
        btn_frame.pack(fill="x", padx=4, pady=(4, 2))

        self._synth_btn = _ttk.Button(
            btn_frame, text="▶ Synthesize", command=self._on_synthesize,
            style="Action.TButton",
        )
        self._synth_btn.pack(side="left", padx=2, expand=True, fill="x")

        _ttk.Button(
            btn_frame, text="⏹ Stop", command=self._on_stop,
            style="Stop.TButton",
        ).pack(side="left", padx=2, expand=True, fill="x")

        btn_frame2 = _ttk.Frame(frame)
        btn_frame2.pack(fill="x", padx=4, pady=(2, 2))

        _ttk.Button(
            btn_frame2, text="ℹ Analyze", command=self._on_analyze,
            style="Action.TButton",
        ).pack(side="left", padx=2, expand=True, fill="x")

        _ttk.Button(
            btn_frame2, text="💾 Export WAV", command=self._on_export,
            style="Action.TButton",
        ).pack(side="left", padx=2, expand=True, fill="x")

    def _build_params_panel(self, parent: Any) -> None:
        frame = _ttk.LabelFrame(parent, text="Parameters")
        frame.pack(fill="x", pady=(0, 10), ipadx=8, ipady=6)

        self._duration_var = self._make_slider(
            frame, "Duration (s):", _MIN_DURATION_S, _MAX_DURATION_S,
            _DEFAULT_DURATION_S, precision=1,
        )
        self._freq_var = self._make_slider(
            frame, "Base Freq (Hz):", _MIN_FREQUENCY_HZ, _MAX_FREQUENCY_HZ,
            _DEFAULT_FREQUENCY_HZ, precision=0,
        )

        # Mapping mode
        mode_row = _ttk.Frame(frame)
        mode_row.pack(fill="x", pady=4)
        _ttk.Label(mode_row, text="Mapping:").pack(side="left", padx=4)
        modes = self._calc.list_mapping_modes()
        self._mapping_var = _tk.StringVar(value=modes[0] if modes else "fm_sine")
        _ttk.Combobox(
            mode_row, textvariable=self._mapping_var,
            values=list(modes), state="readonly", width=18,
        ).pack(side="left", fill="x", expand=True, padx=4)

        # Domain
        domain_row = _ttk.Frame(frame)
        domain_row.pack(fill="x", pady=4)
        _ttk.Label(domain_row, text="Domain [x₀, x₁]:").pack(anchor="w", padx=4)
        entry_row = _ttk.Frame(frame)
        entry_row.pack(fill="x")
        self._x_start_var = _tk.DoubleVar(value=_DEFAULT_X_RANGE[0])
        self._x_end_var = _tk.DoubleVar(value=_DEFAULT_X_RANGE[1])
        _ttk.Entry(entry_row, textvariable=self._x_start_var, width=10).pack(
            side="left", padx=4,
        )
        _ttk.Label(entry_row, text="to").pack(side="left")
        _ttk.Entry(entry_row, textvariable=self._x_end_var, width=10).pack(
            side="left", padx=4,
        )

    def _build_history_panel(self, parent: Any) -> None:
        c = self._colors
        frame = _ttk.LabelFrame(parent, text="History")
        frame.pack(fill="both", expand=True, pady=(0, 10), ipadx=8, ipady=6)

        self._history_listbox = _tk.Listbox(
            frame,
            bg=c.surface, fg=c.fg,
            selectbackground=c.accent, selectforeground=c.bg,
            font=("Consolas", 9), borderwidth=0, activestyle="none",
        )
        self._history_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self._history_listbox.bind("<<ListboxSelect>>", self._on_history_select)

    def _build_stats_panel(self, parent: Any) -> None:
        frame = _ttk.LabelFrame(parent, text="Signal Statistics")
        frame.pack(fill="x", pady=(0, 10), ipadx=8, ipady=6)
        self._stats_label = _ttk.Label(
            frame, text="No signal generated yet.", style="Stats.TLabel",
            justify="left",
        )
        self._stats_label.pack(anchor="w", padx=4, pady=4)

    def _build_status_bar(self) -> None:
        bar = _ttk.Frame(self._root)
        bar.pack(fill="x", side="bottom", padx=16, pady=(4, 10))

        self._status_label = _ttk.Label(
            bar, text="Ready", style="Dim.TLabel",
        )
        self._status_label.pack(side="left")

        self._progress_var = _tk.DoubleVar(value=0)
        self._progress_bar = _ttk.Progressbar(
            bar, variable=self._progress_var, maximum=100, length=280,
        )
        self._progress_bar.pack(side="right", padx=(10, 0))

        # Attribution text in the right bottom corner
        attribution_label = _ttk.Label(
            bar, text="This project is made by K-S (Kanishk Soni)", style="Dim.TLabel",
        )
        attribution_label.pack(side="right", padx=(0, 10))

    # ── Widget Helpers ────────────────────────────────────────────────────

    def _make_slider(
        self,
        parent: Any,
        label: str,
        from_: float,
        to: float,
        default: float,
        precision: int = 1,
    ) -> _tk.DoubleVar:
        """Create a labeled slider with live value display."""
        container = _ttk.Frame(parent)
        container.pack(fill="x", pady=3)

        _ttk.Label(container, text=label).pack(anchor="w", padx=4)

        row = _ttk.Frame(container)
        row.pack(fill="x")

        var = _tk.DoubleVar(value=default)
        fmt = f"{{:.{precision}f}}"
        value_label = _ttk.Label(row, text=fmt.format(default), width=8)

        slider = _ttk.Scale(
            row, from_=from_, to=to, variable=var, orient="horizontal",
        )
        slider.pack(side="left", fill="x", expand=True, padx=4)
        value_label.pack(side="right", padx=4)

        def _on_change(*_: Any) -> None:
            value_label.config(text=fmt.format(var.get()))

        slider.configure(command=_on_change)
        return var

    # ── Event Handlers ────────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        self._root.bind("<Control-Return>", lambda _: self._on_synthesize())
        self._root.bind("<Control-s>", lambda _: self._on_export())
        self._root.bind("<Escape>", lambda _: self._on_stop())
        self._equation_entry.bind("<Return>", lambda _: self._on_synthesize())
        self._root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _on_preset_selected(self, _event: Any = None) -> None:
        name = self._preset_var.get()
        preset_map = dict(_BUILTIN_PRESETS)
        preset_map.update(self._calc.list_presets())
        if name in preset_map:
            self._equation_entry.delete(0, _tk.END)
            self._equation_entry.insert(0, preset_map[name])
            self._validate_equation()

    def _on_equation_changed(self, _event: Any = None) -> None:
        self._validate_equation()

    def _validate_equation(self) -> None:
        """Real-time validation feedback as the user types."""
        equation = self._equation_entry.get().strip()
        if not equation:
            self._validation_label.config(text="", style="Dim.TLabel")
            return

        err = self._calc.compile_and_validate(equation)
        if err is None:
            self._validation_label.config(text="✓ valid", style="Valid.TLabel")
        else:
            short_err = err[:80] + "…" if len(err) > 80 else err
            self._validation_label.config(
                text=f"✗ {short_err}", style="Invalid.TLabel",
            )

    def _on_synthesize(self) -> None:
        if self._is_playing:
            return

        equation = self._equation_entry.get().strip()
        if not equation:
            _messagebox.showwarning("Validation", "Equation field is empty.")
            return

        try:
            params = SynthesisParams(
                equation=equation,
                duration_s=self._duration_var.get(),
                base_frequency_hz=self._freq_var.get(),
                x_range=(self._x_start_var.get(), self._x_end_var.get()),
                mapping_mode=self._mapping_var.get(),
            )
        except ValueError as exc:
            _messagebox.showwarning("Parameter Error", str(exc))
            return

        self._push_history(equation)
        self._is_playing = True
        self._status_label.config(text="Compiling & generating…")
        self._progress_var.set(0)
        self._synth_btn.state(["disabled"])

        # Cancel any lingering worker
        if self._worker is not None:
            self._worker.cancel()

        self._worker = AudioWorker(params, self._msg_queue, self._calc)
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        self._calc.stop_audio()
        self._reset_state("Stopped")

    def _on_analyze(self) -> None:
        equation = self._equation_entry.get().strip()
        if not equation:
            return

        info = self._calc.get_equation_info(equation)
        report = format_equation_report(info)

        win = _tk.Toplevel(self._root)
        win.title("Equation Analysis")
        win.geometry("480x420")
        win.configure(bg=self._colors.bg)

        text = _scrolledtext.ScrolledText(
            win, font=("Consolas", 10), wrap="word",
            bg=self._colors.surface, fg=self._colors.fg,
            insertbackground=self._colors.fg, borderwidth=0,
        )
        text.pack(fill="both", expand=True, padx=12, pady=12)
        text.insert("1.0", report)
        text.config(state="disabled")

    def _on_export(self) -> None:
        if self._current_audio is None:
            _messagebox.showinfo("Export", "Generate a signal first.")
            return

        path_str = _filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV Audio", "*.wav")],
            title="Export WAV",
        )
        if not path_str:
            return

        try:
            encode_pcm16_wav(
                self._current_audio,
                self._calc.sample_rate,
                Path(path_str),
            )
            _messagebox.showinfo(
                "Export Complete", f"Saved to:\n{path_str}",
            )
        except Exception as exc:
            _messagebox.showerror("Export Failed", str(exc))

    def _on_history_select(self, _event: Any = None) -> None:
        sel = self._history_listbox.curselection()
        if sel:
            idx = sel[0]
            items = list(self._history)
            if 0 <= idx < len(items):
                self._equation_entry.delete(0, _tk.END)
                self._equation_entry.insert(0, items[idx])
                self._validate_equation()

    def _on_closing(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        self._calc.stop_audio()
        self._root.destroy()

    # ── Queue Polling ─────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        """Non-blocking main-thread loop consuming worker messages."""
        try:
            while True:
                msg: WorkerMessage = self._msg_queue.get_nowait()
                match msg.state:
                    case WorkerState.PROGRESS:
                        self._progress_var.set(msg.payload)
                    case WorkerState.MATH_READY:
                        self._update_math_plot(msg.payload)
                    case WorkerState.AUDIO_READY:
                        self._current_audio = msg.payload
                        self._update_audio_plots(msg.payload)
                        self._update_stats(msg.payload)
                    case WorkerState.PLAYING:
                        self._status_label.config(text="Playing…")
                    case WorkerState.FINISHED:
                        self._reset_state("Complete")
                    case WorkerState.ERROR:
                        _messagebox.showerror("Error", str(msg.payload))
                        self._reset_state("Error")
        except queue.Empty:
            pass
        finally:
            self._root.after(_QUEUE_POLL_INTERVAL_MS, self._poll_queue)

    # ── State Updates ─────────────────────────────────────────────────────

    def _reset_state(self, status: str) -> None:
        self._is_playing = False
        self._progress_var.set(0)
        self._status_label.config(text=status)
        self._synth_btn.state(["!disabled"])

    def _update_math_plot(self, math_signal: npt.NDArray[np.float32]) -> None:
        x_start = self._x_start_var.get()
        x_end = self._x_end_var.get()
        x = np.linspace(x_start, x_end, math_signal.shape[0], dtype=np.float32)
        self._plots.update_math(x, math_signal)

    def _update_audio_plots(self, audio: npt.NDArray[np.float32]) -> None:
        duration = self._duration_var.get()
        self._plots.update_audio(audio, duration)
        self._plots.update_spectrum(audio)

    def _update_stats(self, audio: npt.NDArray[np.float32]) -> None:
        stats = SignalStats.from_signal(audio, self._calc.sample_rate)
        self._stats_label.config(text=stats.format_report())

    def _push_history(self, equation: str) -> None:
        if equation in self._history:
            self._history.remove(equation)
        self._history.appendleft(equation)
        self._history_listbox.delete(0, _tk.END)
        for eq in self._history:
            self._history_listbox.insert(_tk.END, eq)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def run_cli(args: argparse.Namespace) -> int:
    """Execute CLI mode. Returns exit code."""
    calc = create_calculator(sample_rate=args.sample_rate)

    equation = args.equation
    x_range = (args.x_start, args.x_end)

    # ── Info mode ──
    if args.info:
        info = calc.get_equation_info(equation)
        report = format_equation_report(info)
        print(report)
        return 0 if "error" not in info else 1

    # ── Validate ──
    err = calc.compile_and_validate(equation)
    if err:
        logger.error("Compilation failed: %s", err)
        return 1

    # ── Generate ──
    logger.info(
        "Generating: equation=%r duration=%.2fs freq=%.1fHz mode=%s",
        equation, args.duration, args.frequency, args.mode,
    )

    try:
        audio = calc.generate_audio_array(
            equation,
            duration_s=args.duration,
            x_range=x_range,
            base_frequency_hz=args.frequency,
            mapping_mode=args.mode,
        )
    except Exception as exc:
        logger.error("Generation failed: %s", exc)
        return 1

    stats = SignalStats.from_signal(audio, calc.sample_rate)
    logger.info("Generated %d frames (%.3fs)", stats.frames, stats.duration_s)

    # ── Export ──
    if args.output:
        path = Path(args.output)
        try:
            encode_pcm16_wav(audio, calc.sample_rate, path)
            logger.info("Exported to: %s", path)
        except Exception as exc:
            logger.error("Export failed: %s", exc)
            return 1

    # ── Play ──
    if not args.no_play and hasattr(calc, "play_signal"):
        logger.info("Playing…")
        try:
            calc.play_signal(audio, blocking=True)
        except Exception:
            logger.info("Playback unavailable; use --output to export.")

    # ── Stats ──
    if args.stats:
        print(stats.format_report())

    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="freq-math",
        description="Freq-Math: Mathematical equation sonifier.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  %(prog)s "sin(2*pi*x*5)" --duration 3 --output tone.wav\n'
            '  %(prog)s "exp(-3*x)*sin(10*pi*x)" --mode am_sine --stats\n'
            "  %(prog)s --gui\n"
        ),
    )
    parser.add_argument(
        "equation", nargs="?", help="Mathematical equation to sonify",
    )
    parser.add_argument(
        "-d", "--duration", type=float, default=_DEFAULT_DURATION_S,
        help=f"Duration in seconds (default: {_DEFAULT_DURATION_S})",
    )
    parser.add_argument(
        "-f", "--frequency", type=float, default=_DEFAULT_FREQUENCY_HZ,
        help=f"Base frequency in Hz (default: {_DEFAULT_FREQUENCY_HZ})",
    )
    parser.add_argument(
        "--x-start", type=float, default=_DEFAULT_X_RANGE[0],
        help=f"Domain start (default: {_DEFAULT_X_RANGE[0]})",
    )
    parser.add_argument(
        "--x-end", type=float, default=_DEFAULT_X_RANGE[1],
        help=f"Domain end (default: {_DEFAULT_X_RANGE[1]})",
    )
    parser.add_argument(
        "-m", "--mode", default="fm_sine",
        choices=["fm_sine", "am_sine", "phase_distortion", "wavetable", "direct"],
        help="Audio mapping mode (default: fm_sine)",
    )
    parser.add_argument(
        "-o", "--output", type=str, default=None,
        help="Output WAV file path",
    )
    parser.add_argument(
        "-i", "--info", action="store_true",
        help="Print equation analysis and exit",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print signal statistics after generation",
    )
    parser.add_argument(
        "--no-play", action="store_true",
        help="Skip audio playback (useful with --output)",
    )
    parser.add_argument(
        "--sample-rate", type=int, default=_DEFAULT_SAMPLE_RATE,
        help=f"Sample rate in Hz (default: {_DEFAULT_SAMPLE_RATE})",
    )
    parser.add_argument(
        "-g", "--gui", action="store_true",
        help="Launch the graphical interface",
    )
    return parser


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Application entry point. Returns exit code."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui or not args.equation:
        _import_gui_deps()
        logger.info("Launching GUI…")
        root = _tk.Tk()
        FreqMathGUI(root)
        root.mainloop()
        return 0

    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
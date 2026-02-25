"""
freq_math_calculator.py
=======================

A safe, extensible math-to-audio engine.

Architecture
------------
- **Pure core**: ``EquationPreprocessor``, ``AstSafetyPolicy``, ``NumpyAstEvaluator``,
  ``EquationAnalyzer``, ``AudioPhaseMapper`` — zero side effects.
- **Composable transforms**: ``MathTransform`` protocol + ``TransformChain``.
- **Isolated I/O**: Audio playback via injected ``AudioPlayerProtocol``.
- **Facade**: ``FreqMathCalculator`` orchestrates pure → impure boundary.

Security
--------
Every user equation passes through:

1. ``EquationPreprocessor`` — tokenize, normalize, insert implicit multiplication.
2. ``ast.parse(mode="eval")`` — Python's own parser (no ``eval``).
3. ``AstSafetyPolicy`` — whitelist of AST node types, names, functions, constants.
4. ``NumpyAstEvaluator`` — direct AST interpretation into NumPy ufuncs.

No ``eval()`` / ``exec()`` / ``compile()`` of user strings ever occurs.

Concurrency
-----------
- Compilation is LRU-cached behind an ``RLock``.
- ``CompiledEquation`` is immutable (frozen dataclass).
- All evaluation / generation is pure → thread-safe by construction.
- Side-effect playback is behind an optional, injectable protocol.
"""

from __future__ import annotations

import ast
import enum
import logging
import math
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import (
    Callable,
    Final,
    Iterable,
    Mapping,
    Protocol,
    Sequence,
    runtime_checkable,
)

import numpy as np
import numpy.typing as npt

logger = logging.getLogger(__name__)

FloatArray = npt.NDArray[np.floating]

__all__ = [
    # Errors
    "FreqMathError",
    "MathSecurityError",
    "MathEvaluationError",
    "MathDomainError",
    # Config / types
    "CompilationLimits",
    "GenerationLimits",
    "MathParameters",
    "EquationMetadata",
    "AnalysisResult",
    "CompiledEquation",
    "MappingMode",
    # Pure core
    "EquationPreprocessor",
    "AstSafetyPolicy",
    "NumpyAstEvaluator",
    "EquationAnalyzer",
    "AudioPhaseMapper",
    # Transforms
    "MathTransform",
    "TransformChain",
    "HarmonicOvertones",
    "WaveFold",
    "Quantize",
    "SmoothStep",
    "Invert",
    "TimeStretch",
    "PhaseDistort",
    # Generators
    "LissajousGenerator",
    "FractalNoiseGenerator",
    "HarmonicSeriesGenerator",
    # Playback protocol
    "AudioPlayerProtocol",
    # Facade
    "FreqMathCalculator",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

_TWO_PI: Final[float] = 2.0 * math.pi
_DEFAULT_SAMPLE_RATE: Final[int] = 44_100
_DEFAULT_MAX_AST_NODES: Final[int] = 500
_DEFAULT_MAX_CONSTANT_ABS: Final[float] = 1e9
_DEFAULT_MAX_POWER_ABS: Final[float] = 128.0
_DEFAULT_MAX_STEPS: Final[int] = 5_000_000
_DEFAULT_MAX_DURATION_S: Final[float] = 60.0
_EPSILON: Final[float] = 1e-12
_COMPILE_CACHE_SIZE: Final[int] = 512

# Default probe points for equation analysis
_DEFAULT_PROBE_POINTS: Final[tuple[float, ...]] = (
    0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Errors (API Contracts)
# ═══════════════════════════════════════════════════════════════════════════════

class FreqMathError(Exception):
    """Base for all freq-math errors."""


class MathSecurityError(FreqMathError):
    """Equation contains forbidden syntax, names, or exceeds complexity limits."""


class MathEvaluationError(FreqMathError):
    """Evaluation failed or produced invalid results."""


class MathDomainError(FreqMathError):
    """Input domain / configuration would cause unsafe resource usage."""


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class MappingMode(enum.Enum):
    """How a math signal maps onto audio."""
    FM_SINE = "fm_sine"
    AM_SINE = "am_sine"
    PHASE_DISTORTION = "phase_distortion"
    WAVETABLE = "wavetable"
    DIRECT = "direct"


class BuiltinEquation(enum.Enum):
    """Curated preset equations for quick exploration."""
    SINE = "sin(2*pi*x)"
    CHIRP = "sin(2*pi*x*x*10)"
    BELL_CURVE = "exp(-((x-0.5)**2)/(2*0.01))"
    SAWTOOTH = "2*(x % 1) - 1"
    TRIANGLE = "2*abs(2*(x % 1) - 1) - 1"
    SQUARE = "sign(sin(2*pi*x))"
    PULSE = "sin(2*pi*x) + 0.5*sin(4*pi*x) + 0.25*sin(6*pi*x)"
    NOISE_MODULATED = "sin(2*pi*x*10) * exp(-3*x)"
    DECAY = "exp(-5*x) * sin(2*pi*x*8)"
    WAVEPACKET = "exp(-((x-0.5)**2)*50) * sin(2*pi*x*20)"
    HARMONIC_STACK = "sin(2*pi*x) + sin(4*pi*x)/2 + sin(6*pi*x)/3"
    FM_WOBBLE = "sin(2*pi*x*5 + 3*sin(2*pi*x*0.5))"
    HYPERBOLIC = "1 / (1 + exp(-10*(x-0.5)))"


# ═══════════════════════════════════════════════════════════════════════════════
# Internal Validation Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")


def _require_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise MathDomainError(f"{name} must be finite, got {value}")


def _sanitize_array(arr: FloatArray) -> FloatArray:
    """Replace NaN/Inf with safe defaults."""
    return np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)


def _peak_normalize(arr: FloatArray) -> FloatArray:
    """Scale so peak absolute value is 1.0 (no-op for silence)."""
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    if peak < _EPSILON:
        return arr
    return arr / np.float32(peak)


# ═══════════════════════════════════════════════════════════════════════════════
# Immutable Configuration Objects
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class CompilationLimits:
    """
    Safety limits for AST validation.

    Invariants
    ----------
    - ``max_ast_nodes > 0``
    - ``max_constant_abs > 0``
    - ``max_power_abs > 0``
    """
    max_ast_nodes: int = _DEFAULT_MAX_AST_NODES
    max_constant_abs: float = _DEFAULT_MAX_CONSTANT_ABS
    max_power_abs: float = _DEFAULT_MAX_POWER_ABS

    def __post_init__(self) -> None:
        _require(self.max_ast_nodes > 0, "max_ast_nodes must be > 0")
        _require(self.max_constant_abs > 0, "max_constant_abs must be > 0")
        _require(self.max_power_abs > 0, "max_power_abs must be > 0")


@dataclass(frozen=True, slots=True)
class GenerationLimits:
    """
    Prevent accidental huge allocations.

    Invariants
    ----------
    - ``max_steps > 0``
    - ``max_duration_s > 0``
    """
    max_steps: int = _DEFAULT_MAX_STEPS
    max_duration_s: float = _DEFAULT_MAX_DURATION_S

    def __post_init__(self) -> None:
        _require(self.max_steps > 0, "max_steps must be > 0")
        _require(self.max_duration_s > 0, "max_duration_s must be > 0")


@dataclass(frozen=True, slots=True)
class MathParameters:
    """
    Soft-configurable parameters injectable into equations.

    Users reference these by name inside expressions (e.g. ``A*sin(f*x)``).
    """
    A: float = 0.5
    f: float = 440.0
    alpha: float = 0.1
    beta: float = 0.1
    l: float = 0.1

    def as_dict(self) -> dict[str, float]:
        return {
            "A": self.A,
            "f": self.f,
            "alpha": self.alpha,
            "beta": self.beta,
            "l": self.l,
        }


@dataclass(frozen=True, slots=True)
class EquationMetadata:
    """Static analysis of a compiled equation."""
    equation: str
    operations: tuple[str, ...]
    functions: tuple[str, ...]
    complexity_score: int
    is_safe: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "equation": self.equation,
            "operations": self.operations,
            "functions": self.functions,
            "complexity_score": self.complexity_score,
            "is_safe": self.is_safe,
        }


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Numerical probing results for a compiled equation."""
    equation: str
    test_points: tuple[float, ...]
    results: tuple[float, ...]
    min_result: float
    max_result: float
    span: float
    mean_result: float
    rms_result: float
    monotonic: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "equation": self.equation,
            "test_points": self.test_points,
            "results": self.results,
            "min_result": self.min_result,
            "max_result": self.max_result,
            "span": self.span,
            "mean_result": self.mean_result,
            "rms_result": self.rms_result,
            "monotonic": self.monotonic,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Tokenizer
# ═══════════════════════════════════════════════════════════════════════════════

class _TokenKind(enum.Enum):
    NUM = "num"
    NAME = "name"
    OP = "op"
    LPAR = "lpar"
    RPAR = "rpar"
    COMMA = "comma"


@dataclass(frozen=True, slots=True)
class _Token:
    kind: _TokenKind
    value: str


class _Tokenizer:
    """
    Lexes a math expression string into a flat token stream.

    Handles numbers (int, float, scientific notation), names,
    operators, parentheses, and commas.  Silently skips formatting
    characters like ``{}``, ``:``, ``[]``.
    """

    __slots__ = ()

    _SKIP_CHARS: Final[frozenset[str]] = frozenset("{}:[]")
    _SIMPLE_OPS: Final[frozenset[str]] = frozenset("+-*/=%")

    @classmethod
    def tokenize(cls, expr: str) -> list[_Token]:
        tokens: list[_Token] = []
        i, n = 0, len(expr)

        while i < n:
            ch = expr[i]

            if ch.isspace():
                i += 1
                continue

            if ch in cls._SKIP_CHARS:
                i += 1
                continue

            if ch in cls._SIMPLE_OPS:
                tokens.append(_Token(_TokenKind.OP, ch))
                i += 1
                continue

            if ch == "(":
                tokens.append(_Token(_TokenKind.LPAR, ch))
                i += 1
                continue

            if ch == ")":
                tokens.append(_Token(_TokenKind.RPAR, ch))
                i += 1
                continue

            if ch == ",":
                tokens.append(_Token(_TokenKind.COMMA, ch))
                i += 1
                continue

            # Double-star power operator
            if ch == "*" and i + 1 < n and expr[i + 1] == "*":
                tokens.append(_Token(_TokenKind.OP, "**"))
                i += 2
                continue

            # Numeric literal (int / float / scientific)
            if ch.isdigit() or (ch == "." and i + 1 < n and expr[i + 1].isdigit()):
                j = cls._scan_number(expr, i, n)
                tokens.append(_Token(_TokenKind.NUM, expr[i:j]))
                i = j
                continue

            # Identifier
            if ch.isalpha() or ch == "_":
                j = i + 1
                while j < n and (expr[j].isalnum() or expr[j] == "_"):
                    j += 1
                tokens.append(_Token(_TokenKind.NAME, expr[i:j]))
                i = j
                continue

            raise MathSecurityError(f"Unsupported character '{ch}' in equation.")

        return tokens

    @staticmethod
    def _scan_number(expr: str, start: int, length: int) -> int:
        """Return the index one past the end of a numeric literal."""
        j = start + 1
        while j < length and (expr[j].isdigit() or expr[j] == "."):
            j += 1
        # Scientific notation: e.g. 1.5e-3
        if j < length and expr[j] in ("e", "E"):
            k = j + 1
            if k < length and expr[k] in ("+", "-"):
                k += 1
            if k < length and expr[k].isdigit():
                k += 1
                while k < length and expr[k].isdigit():
                    k += 1
                j = k
        return j


# ═══════════════════════════════════════════════════════════════════════════════
# Preprocessing (pure)
# ═══════════════════════════════════════════════════════════════════════════════

class EquationPreprocessor:
    """
    Converts human math notation into a strict Python-expression subset.

    Pipeline::

        raw string
        → strip LHS of ``=``
        → normalize unicode (``×÷−^``)
        → normalize aliases (``t→x``, ``lambda→l``)
        → tokenize → insert implicit ``*`` → rejoin
        → validate parentheses / basic syntax
    """

    _UNICODE_MAP: Final[dict[str, str]] = {
        "×": "*", "∗": "*", "·": "*",
        "÷": "/",
        "−": "-", "–": "-", "—": "-",
        "^": "**",
        "²": "**2", "³": "**3",
        "π": "pi",
    }

    __slots__ = ("_allowed_functions",)

    def __init__(self, *, allowed_functions: frozenset[str]) -> None:
        self._allowed_functions = allowed_functions

    def preprocess(self, equation: str) -> str:
        """
        Return a normalized, implicit-multiplication-inserted expression string.

        Raises ``MathSecurityError`` on empty input or invalid syntax.
        """
        if not isinstance(equation, str) or not equation.strip():
            raise MathSecurityError("Equation must be a non-empty string.")

        expr = self._collapse_whitespace(equation)
        expr = self._strip_lhs(expr)
        expr = self._normalize_unicode(expr)
        expr = self._normalize_aliases(expr)
        expr = self._insert_implicit_multiplication(expr)
        self._validate_parentheses(expr)
        self._validate_basic_syntax(expr)
        return expr

    # ── Internal Steps ────────────────────────────────────────────────────

    @staticmethod
    def _collapse_whitespace(expr: str) -> str:
        return re.sub(r"\s+", " ", expr.strip().replace("\n", " ").replace("\r", " "))

    @staticmethod
    def _strip_lhs(expr: str) -> str:
        """If ``y(t) = ...`` or ``f(x)=...``, take RHS."""
        if "=" in expr:
            _, rhs = expr.split("=", 1)
            return rhs.strip()
        return expr

    def _normalize_unicode(self, expr: str) -> str:
        for src, dst in self._UNICODE_MAP.items():
            expr = expr.replace(src, dst)
        return expr

    @staticmethod
    def _normalize_aliases(expr: str) -> str:
        # ``t`` → ``x``  (common time variable)
        expr = re.sub(r"\bt\b", "x", expr)
        # ``lambda`` → ``l``  (reserved keyword avoidance)
        expr = re.sub(r"\blambda\b", "l", expr)
        # Normalize case-prefixed function names: ``Csin`` → ``sin``
        expr = re.sub(
            r"[Cc](sin|cos|tan|exp|log|sqrt|abs)\b",
            lambda m: m.group(1).lower(),
            expr,
            flags=re.IGNORECASE,
        )
        return expr

    def _insert_implicit_multiplication(self, expr: str) -> str:
        """
        Insert ``*`` between adjacent tokens where multiplication is implied.

        ``2pi`` → ``2*pi``  ·  ``2(x)`` → ``2*(x)``  ·  ``)(`` → ``)*(``.
        Does **not** insert between a known function name and ``(``.
        """
        tokens = _Tokenizer.tokenize(expr)
        if not tokens:
            raise MathSecurityError("Equation is empty after tokenization.")

        result: list[_Token] = [tokens[0]]
        for prev, cur in zip(tokens, tokens[1:]):
            if self._needs_implicit_star(prev, cur):
                result.append(_Token(_TokenKind.OP, "*"))
            result.append(cur)

        return "".join(tok.value for tok in result)

    def _needs_implicit_star(self, prev: _Token, cur: _Token) -> bool:
        """True if an implicit ``*`` should be inserted between ``prev`` and ``cur``."""
        value_kinds: frozenset[_TokenKind] = frozenset(
            {_TokenKind.NUM, _TokenKind.NAME, _TokenKind.RPAR}
        )
        value_start_kinds: frozenset[_TokenKind] = frozenset(
            {_TokenKind.NUM, _TokenKind.NAME, _TokenKind.LPAR}
        )

        if prev.kind not in value_kinds or cur.kind not in value_start_kinds:
            return False

        # Function call: ``sin(`` — no implicit star
        if (
            prev.kind == _TokenKind.NAME
            and cur.kind == _TokenKind.LPAR
            and prev.value.lower() in self._allowed_functions
        ):
            return False

        return True

    @staticmethod
    def _validate_parentheses(expr: str) -> None:
        depth = 0
        for ch in expr:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth < 0:
                raise MathSecurityError(
                    "Unbalanced parentheses: extra closing parenthesis."
                )
        if depth != 0:
            raise MathSecurityError(
                "Unbalanced parentheses: missing closing parenthesis."
            )

    @staticmethod
    def _validate_basic_syntax(expr: str) -> None:
        if "()" in expr:
            raise MathSecurityError(
                "Empty parentheses '()' are not allowed."
            )
        for bad in ("**)", "*)", "(**", "(*", "//", "%%"):
            if bad in expr:
                raise MathSecurityError(
                    f"Invalid syntax pattern '{bad}' detected."
                )


# ═══════════════════════════════════════════════════════════════════════════════
# AST Safety Policy (pure)
# ═══════════════════════════════════════════════════════════════════════════════

class AstSafetyPolicy:
    """
    Whitelist-based AST validator.

    Rejects attribute access, subscripts, comprehensions, assignments,
    imports, lambdas, f-strings, starred expressions — everything except
    the minimal expression subset needed for safe math.
    """

    _ALLOWED_NODE_TYPES: Final[tuple[type[ast.AST], ...]] = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Constant,
        ast.Load,
        ast.Tuple,
        # Operators
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
        ast.UAdd, ast.USub,
    )

    __slots__ = ("_allowed_names", "_allowed_functions", "_limits")

    def __init__(
        self,
        *,
        allowed_names: frozenset[str],
        allowed_functions: frozenset[str],
        limits: CompilationLimits,
    ) -> None:
        self._allowed_names = allowed_names
        self._allowed_functions = allowed_functions
        self._limits = limits

    def validate(self, tree: ast.AST) -> None:
        """Raise ``MathSecurityError`` if the AST violates any policy rule."""
        nodes = list(ast.walk(tree))
        self._check_complexity(nodes)

        called_names = self._collect_called_function_names(nodes)

        for node in nodes:
            self._check_node_type(node)
            self._check_call(node)
            self._check_constant(node)
            self._check_power(node)

        # Name check (exclude names that resolved as function calls)
        for node in nodes:
            if isinstance(node, ast.Name) and node.id.lower() not in called_names:
                self._check_name(node)

    # ── Individual Checks ─────────────────────────────────────────────────

    def _check_complexity(self, nodes: list[ast.AST]) -> None:
        if len(nodes) > self._limits.max_ast_nodes:
            raise MathSecurityError(
                f"Expression too complex ({len(nodes)} nodes, "
                f"limit {self._limits.max_ast_nodes})."
            )

    def _check_node_type(self, node: ast.AST) -> None:
        if not isinstance(node, self._ALLOWED_NODE_TYPES):
            raise MathSecurityError(
                f"Unsupported syntax: {type(node).__name__}. "
                "Only basic mathematical operations are allowed."
            )

    def _check_call(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            return
        if not isinstance(node.func, ast.Name):
            raise MathSecurityError(
                "Only direct function calls (e.g. sin(x)) are allowed."
            )
        if node.func.id.lower() not in self._allowed_functions:
            raise MathSecurityError(
                f"Unknown function: '{node.func.id}'. "
                f"Available: {', '.join(sorted(self._allowed_functions))}"
            )

    def _check_constant(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Constant):
            return
        if not isinstance(node.value, (int, float)):
            raise MathSecurityError("Only int/float constants are allowed.")
        if abs(float(node.value)) > self._limits.max_constant_abs:
            raise MathSecurityError(
                f"Constant magnitude {abs(node.value)} exceeds limit "
                f"{self._limits.max_constant_abs}."
            )

    def _check_power(self, node: ast.AST) -> None:
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Pow):
            return
        if isinstance(node.right, ast.Constant) and isinstance(
            node.right.value, (int, float)
        ):
            if abs(float(node.right.value)) > self._limits.max_power_abs:
                raise MathSecurityError(
                    f"Power exponent {abs(node.right.value)} exceeds limit "
                    f"{self._limits.max_power_abs}."
                )

    def _check_name(self, node: ast.Name) -> None:
        lower = node.id.lower()
        if lower not in self._allowed_names and lower not in self._allowed_functions:
            variables = sorted(self._allowed_names - self._allowed_functions)
            raise MathSecurityError(
                f"Unknown variable: '{node.id}'. "
                f"Available: {', '.join(variables)}"
            )

    def _collect_called_function_names(
        self, nodes: list[ast.AST],
    ) -> frozenset[str]:
        """Return lowercased names of identifiers used as function calls."""
        names: set[str] = set()
        for node in nodes:
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
            ):
                names.add(node.func.id.lower())
        return frozenset(names)


# ═══════════════════════════════════════════════════════════════════════════════
# NumPy AST Evaluator (pure — no eval())
# ═══════════════════════════════════════════════════════════════════════════════

class NumpyAstEvaluator:
    """
    Interprets a validated AST directly into NumPy ufunc calls.

    Each AST node maps to exactly one NumPy operation on the full array,
    giving vectorized throughput without ever touching Python's ``eval``.
    """

    _BIN_OPS: Final[Mapping[type[ast.operator], Callable]] = {
        ast.Add:  np.add,
        ast.Sub:  np.subtract,
        ast.Mult: np.multiply,
        ast.Div:  np.true_divide,
        ast.Mod:  np.mod,
        ast.Pow:  np.power,
    }

    _UNARY_OPS: Final[Mapping[type[ast.unaryop], Callable]] = {
        ast.UAdd: np.positive,
        ast.USub: np.negative,
    }

    _FUNCS: Final[Mapping[str, Callable]] = {
        # Trigonometric
        "sin":   np.sin,
        "cos":   np.cos,
        "tan":   np.tan,
        "asin":  np.arcsin,
        "acos":  np.arccos,
        "atan":  np.arctan,
        # Hyperbolic
        "sinh":  np.sinh,
        "cosh":  np.cosh,
        "tanh":  np.tanh,
        # Exponential / logarithmic
        "exp":   np.exp,
        "log":   np.log,
        "log2":  np.log2,
        "log10": np.log10,
        # Power / root
        "sqrt":  np.sqrt,
        "cbrt":  np.cbrt,
        # Rounding / magnitude
        "abs":   np.abs,
        "sign":  np.sign,
        "floor": np.floor,
        "ceil":  np.ceil,
        "round": np.round,
        # Two-argument elementwise
        "min":   np.minimum,
        "max":   np.maximum,
        "atan2": np.arctan2,
        # Special
        "sinc":  np.sinc,
    }

    # Names that require exactly 2 arguments
    _BINARY_FUNCS: Final[frozenset[str]] = frozenset({"min", "max", "atan2"})

    # ── Default Environment Variables ─────────────────────────────────────

    _SINGLE_LETTER_DEFAULTS: Final[dict[str, float]] = {
        letter: 1.0
        for letter in "abcdghjkmnpqrsuvwz"
    }
    _EXTRA_DEFAULTS: Final[dict[str, float]] = {
        "omega": 1.0, "phi": 0.5, "theta": 0.0,
        "D": 1.0, "E": math.e, "S": 1.0,
        "partial": 0.5, "phi_b": 0.25,
        "random": 0.5,  # fixed for reproducibility
    }

    @classmethod
    def build_environment(
        cls,
        x: object,
        params: MathParameters,
    ) -> dict[str, object]:
        """Construct the name→value mapping for evaluation."""
        env: dict[str, object] = {
            **cls._SINGLE_LETTER_DEFAULTS,
            **cls._EXTRA_DEFAULTS,
            **params.as_dict(),
            "x": x,
            "t": x,
            "y": x,
            "pi": math.pi,
            "e": math.e,
            "tau": _TWO_PI,
        }
        return env

    @classmethod
    def evaluate(
        cls,
        tree: ast.Expression,
        *,
        x: object,
        params: MathParameters,
    ) -> object:
        """
        Evaluate a validated AST against ``x`` (scalar or array) and ``params``.

        Returns a sanitized scalar or NumPy array (NaN→0, ±Inf→±1).
        """
        env = cls.build_environment(x, params)
        with np.errstate(all="ignore"):
            result = cls._eval_node(tree.body, env)
        return cls._sanitize_result(result)

    # ── Recursive Node Interpreter ────────────────────────────────────────

    @classmethod
    def _eval_node(cls, node: ast.AST, env: Mapping[str, object]) -> object:
        match node:
            case ast.Constant(value=v):
                return float(v)

            case ast.Name(id=name):
                try:
                    return env[name]
                except KeyError as exc:
                    raise MathEvaluationError(
                        f"Unknown identifier: '{name}'"
                    ) from exc

            case ast.UnaryOp(op=op, operand=operand):
                fn = cls._UNARY_OPS.get(type(op))
                if fn is None:
                    raise MathEvaluationError(
                        f"Unsupported unary op: {type(op).__name__}"
                    )
                return fn(cls._eval_node(operand, env))

            case ast.BinOp(left=left, op=op, right=right):
                fn = cls._BIN_OPS.get(type(op))
                if fn is None:
                    raise MathEvaluationError(
                        f"Unsupported binary op: {type(op).__name__}"
                    )
                return fn(cls._eval_node(left, env), cls._eval_node(right, env))

            case ast.Call(func=ast.Name(id=name), args=args):
                fn = cls._FUNCS.get(name.lower())
                if fn is None:
                    raise MathEvaluationError(f"Unsupported function: '{name}'")
                evaluated_args = [cls._eval_node(a, env) for a in args]
                if name.lower() in cls._BINARY_FUNCS and len(evaluated_args) != 2:
                    raise MathEvaluationError(
                        f"'{name}' requires exactly 2 arguments."
                    )
                return fn(*evaluated_args)

            case ast.Tuple(elts=elements):
                return np.array([cls._eval_node(e, env) for e in elements])

            case _:
                raise MathEvaluationError(
                    f"Unsupported AST node: {type(node).__name__}"
                )

    @staticmethod
    def _sanitize_result(result: object) -> object:
        if isinstance(result, np.ndarray):
            return np.nan_to_num(result, nan=0.0, posinf=1.0, neginf=-1.0)
        if isinstance(result, (int, float, np.floating, np.integer)):
            val = float(result)
            return 0.0 if not math.isfinite(val) else val
        raise MathEvaluationError(
            f"Unsupported result type: {type(result).__name__}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Compiled Equation (immutable)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class CompiledEquation:
    """
    Immutable compiled equation ready for repeated evaluation.

    Constructed only through ``FreqMathCalculator.compile_equation``.
    """
    source: str
    tree: ast.Expression
    metadata: EquationMetadata

    def evaluate_array(
        self,
        x: FloatArray,
        *,
        params: MathParameters,
    ) -> FloatArray:
        """Evaluate over an array of x-values (vectorized)."""
        result = NumpyAstEvaluator.evaluate(self.tree, x=x, params=params)
        return np.asarray(result, dtype=np.float32)

    def evaluate_scalar(
        self,
        x: float,
        *,
        params: MathParameters,
    ) -> float:
        """Evaluate at a single x-value."""
        result = NumpyAstEvaluator.evaluate(self.tree, x=float(x), params=params)
        if isinstance(result, np.ndarray):
            if result.size != 1:
                raise MathEvaluationError(
                    f"Scalar evaluation produced array of size {result.size}."
                )
            return float(result.item())
        return float(result)


# ═══════════════════════════════════════════════════════════════════════════════
# MathTransform Protocol & Composable Chain
# ═══════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class MathTransform(Protocol):
    """
    Pure ``FloatArray → FloatArray`` transform with a ``name``.

    Applied post-evaluation to shape the math signal before audio mapping.
    """

    @property
    def name(self) -> str: ...

    def __call__(self, signal: FloatArray) -> FloatArray: ...


@dataclass(frozen=True, slots=True)
class HarmonicOvertones:
    """
    Add harmonic overtones at integer multiples of the base signal's
    implied fundamental period, with amplitude rolloff.

    ``harmonics=3`` adds partials at 2×, 3×, 4× with 1/n rolloff.
    """
    harmonics: int = 3
    rolloff: float = 1.0

    def __post_init__(self) -> None:
        _require(self.harmonics >= 0, "harmonics must be >= 0")

    @property
    def name(self) -> str:
        return f"HarmonicOvertones(n={self.harmonics}, rolloff={self.rolloff})"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        if self.harmonics == 0 or arr.size == 0:
            return arr
        result = arr.copy()
        for h in range(2, self.harmonics + 2):
            # Resample signal to h× speed via linear interpolation
            indices = np.linspace(0, arr.size - 1, arr.size, dtype=np.float64) * h
            indices = indices % arr.size
            idx_floor = np.floor(indices).astype(int) % arr.size
            idx_ceil = (idx_floor + 1) % arr.size
            frac = (indices - np.floor(indices)).astype(np.float32)
            overtone = arr[idx_floor] * (1.0 - frac) + arr[idx_ceil] * frac
            amplitude = 1.0 / (h ** self.rolloff)
            result += overtone * np.float32(amplitude)
        return _peak_normalize(result)


@dataclass(frozen=True, slots=True)
class WaveFold:
    """
    Wavefolding distortion: folds signal back when it exceeds ``[-threshold, threshold]``.

    Creates rich harmonic content from simple waveforms.
    ``iterations`` controls fold density.
    """
    threshold: float = 0.7
    iterations: int = 2

    def __post_init__(self) -> None:
        _require(self.threshold > 0, "threshold must be > 0")
        _require(self.iterations >= 1, "iterations must be >= 1")

    @property
    def name(self) -> str:
        return f"WaveFold(thresh={self.threshold}, iter={self.iterations})"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32).copy()
        t = np.float32(self.threshold)
        for _ in range(self.iterations):
            # Triangle-wave fold: reflect at ±threshold
            arr = np.abs(np.mod(arr + t, 4.0 * t) - 2.0 * t) - t
        return _peak_normalize(arr)


@dataclass(frozen=True, slots=True)
class Quantize:
    """
    Quantize signal amplitude to ``levels`` discrete steps.

    Musical analogue of bitcrush for math signals.
    """
    levels: int = 16

    def __post_init__(self) -> None:
        _require(self.levels >= 2, "levels must be >= 2")

    @property
    def name(self) -> str:
        return f"Quantize(levels={self.levels})"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        # Normalize to [0, 1], quantize, then back to original range
        lo, hi = float(np.min(arr)), float(np.max(arr))
        span = hi - lo
        if span < _EPSILON:
            return arr
        normalized = (arr - lo) / span
        quantized = np.round(normalized * (self.levels - 1)) / (self.levels - 1)
        return np.ascontiguousarray(quantized * span + lo)


@dataclass(frozen=True, slots=True)
class SmoothStep:
    """
    Apply a Hermite smoothstep (S-curve) to the normalized signal.

    ``order=1``: basic smoothstep.  ``order=2``: smoother (Ken Perlin's).
    """
    order: int = 1

    def __post_init__(self) -> None:
        _require(self.order in (1, 2), "order must be 1 or 2")

    @property
    def name(self) -> str:
        return f"SmoothStep(order={self.order})"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        # Map to [0, 1]
        lo, hi = float(np.min(arr)), float(np.max(arr))
        span = hi - lo
        if span < _EPSILON:
            return arr
        t = np.clip((arr - lo) / span, 0.0, 1.0)
        if self.order == 1:
            s = t * t * (3.0 - 2.0 * t)
        else:
            s = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
        return np.ascontiguousarray(s * span + lo)


@dataclass(frozen=True, slots=True)
class Invert:
    """Flip the signal upside-down around its midpoint."""

    @property
    def name(self) -> str:
        return "Invert"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        return np.ascontiguousarray(-arr)


@dataclass(frozen=True, slots=True)
class TimeStretch:
    """
    Stretch or compress the signal in time via linear interpolation.

    ``factor > 1`` → slower, ``factor < 1`` → faster.
    Output length is preserved; content wraps around.
    """
    factor: float = 1.0

    def __post_init__(self) -> None:
        _require(self.factor > 0, "factor must be > 0")

    @property
    def name(self) -> str:
        return f"TimeStretch(factor={self.factor})"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        n = arr.size
        if n == 0 or self.factor == 1.0:
            return arr
        indices = (np.arange(n, dtype=np.float64) * self.factor) % n
        idx_floor = np.floor(indices).astype(int) % n
        idx_ceil = (idx_floor + 1) % n
        frac = (indices - np.floor(indices)).astype(np.float32)
        return np.ascontiguousarray(
            arr[idx_floor] * (1.0 - frac) + arr[idx_ceil] * frac
        )


@dataclass(frozen=True, slots=True)
class PhaseDistort:
    """
    Phase distortion synthesis transform.

    Warps the time axis non-linearly to create harmonic-rich waveforms
    from simple sources (inspired by Casio CZ synthesis).
    """
    amount: float = 0.5

    def __post_init__(self) -> None:
        _require(0.0 <= self.amount <= 1.0, "amount must be in [0, 1]")

    @property
    def name(self) -> str:
        return f"PhaseDistort(amount={self.amount})"

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        n = arr.size
        if n == 0 or self.amount < _EPSILON:
            return arr
        # Non-linear time warp: compress first half, stretch second half
        t = np.linspace(0.0, 1.0, n, dtype=np.float64)
        a = self.amount
        warped = np.where(
            t < 0.5,
            t * (1.0 + a) / (1.0),
            0.5 * (1.0 + a) + (t - 0.5) * (1.0 - a),
        )
        warped = np.clip(warped, 0.0, 1.0)
        indices = warped * (n - 1)
        idx_floor = np.floor(indices).astype(int)
        idx_ceil = np.minimum(idx_floor + 1, n - 1)
        frac = (indices - idx_floor).astype(np.float32)
        return np.ascontiguousarray(
            arr[idx_floor] * (1.0 - frac) + arr[idx_ceil] * frac
        )


class TransformChain:
    """
    Immutable, ordered sequence of ``MathTransform`` instances.

    Applying the chain runs each transform in order.
    Use ``append`` / ``prepend`` to derive new chains.
    """

    __slots__ = ("_transforms",)

    def __init__(self, transforms: Sequence[MathTransform] = ()) -> None:
        self._transforms: tuple[MathTransform, ...] = tuple(transforms)

    @property
    def transforms(self) -> tuple[MathTransform, ...]:
        return self._transforms

    def __len__(self) -> int:
        return len(self._transforms)

    def __repr__(self) -> str:
        names = " → ".join(t.name for t in self._transforms) or "(empty)"
        return f"TransformChain[{names}]"

    def append(self, transform: MathTransform) -> TransformChain:
        return TransformChain((*self._transforms, transform))

    def prepend(self, transform: MathTransform) -> TransformChain:
        return TransformChain((transform, *self._transforms))

    def __call__(self, signal: FloatArray) -> FloatArray:
        arr = np.asarray(signal, dtype=np.float32)
        for tx in self._transforms:
            arr = np.asarray(tx(arr), dtype=np.float32)
        return arr


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis (pure)
# ═══════════════════════════════════════════════════════════════════════════════

class EquationAnalyzer:
    """Static and numerical analysis of compiled equations."""

    _OP_SYMBOLS: Final[dict[type, str]] = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*",
        ast.Div: "/", ast.Pow: "^", ast.Mod: "%",
    }

    __slots__ = ()

    @classmethod
    def metadata(
        cls,
        source: str,
        tree: ast.Expression,
        *,
        allowed_functions: frozenset[str],
    ) -> EquationMetadata:
        """Extract static metadata from a parsed AST."""
        ops: set[str] = set()
        funcs: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                sym = cls._OP_SYMBOLS.get(type(node.op))
                if sym:
                    ops.add(sym)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                lower = node.func.id.lower()
                if lower in allowed_functions:
                    funcs.add(lower)

        node_count = sum(1 for _ in ast.walk(tree))
        complexity = len(ops) + 2 * len(funcs) + node_count

        return EquationMetadata(
            equation=source,
            operations=tuple(sorted(ops)),
            functions=tuple(sorted(funcs)),
            complexity_score=complexity,
            is_safe=True,
        )

    @staticmethod
    def probe_bounds(
        compiled: CompiledEquation,
        *,
        params: MathParameters,
        points: Sequence[float] = _DEFAULT_PROBE_POINTS,
    ) -> AnalysisResult:
        """Evaluate at sample points and compute summary statistics."""
        xs = tuple(float(p) for p in points)
        ys = tuple(compiled.evaluate_scalar(x, params=params) for x in xs)
        mn = min(ys) if ys else 0.0
        mx = max(ys) if ys else 0.0
        mean_val = sum(ys) / len(ys) if ys else 0.0
        rms_val = math.sqrt(sum(y * y for y in ys) / len(ys)) if ys else 0.0

        # Check monotonicity
        diffs = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)] if len(ys) > 1 else []
        is_monotonic = (
            all(d >= 0 for d in diffs) or all(d <= 0 for d in diffs)
        ) if diffs else True

        return AnalysisResult(
            equation=compiled.source,
            test_points=xs,
            results=ys,
            min_result=mn,
            max_result=mx,
            span=mx - mn,
            mean_result=mean_val,
            rms_result=rms_val,
            monotonic=is_monotonic,
        )

    @staticmethod
    def compare_equations(
        equations: Sequence[CompiledEquation],
        *,
        params: MathParameters,
        points: Sequence[float] = _DEFAULT_PROBE_POINTS,
    ) -> list[AnalysisResult]:
        """Probe multiple equations at the same points for comparison."""
        return [
            EquationAnalyzer.probe_bounds(eq, params=params, points=points)
            for eq in equations
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# Audio Phase Mapper (pure)
# ═══════════════════════════════════════════════════════════════════════════════

class AudioPhaseMapper:
    """
    Maps a math signal to audio via several synthesis strategies.

    All methods are pure, deterministic, and return contiguous float32 arrays.
    """

    __slots__ = ()

    @staticmethod
    def _validate_common(
        math_signal: FloatArray,
        sample_rate: int,
        base_frequency_hz: float,
    ) -> npt.NDArray[np.float32]:
        """Common validation and sanitization for all mapping modes."""
        _require_positive(sample_rate, "sample_rate")
        _require_positive(base_frequency_hz, "base_frequency_hz")
        x = np.asarray(math_signal, dtype=np.float32)
        if x.ndim != 1:
            raise MathEvaluationError("math_signal must be 1-D.")
        if x.size == 0:
            return np.zeros(0, dtype=np.float32)
        if not np.isfinite(x).all():
            x = _sanitize_array(x)
        return x

    @staticmethod
    def fm_sine(
        math_signal: FloatArray,
        *,
        base_frequency_hz: float,
        sample_rate: int,
        deviation: float = 0.5,
        normalize: bool = True,
    ) -> npt.NDArray[np.float32]:
        """
        Frequency-modulation mapping.

        ``f_inst[n] = base_freq × (1 + deviation × signal[n])``
        ``phase[n]  = 2π × cumsum(f_inst) / sample_rate``
        ``output[n] = sin(phase[n])``
        """
        x = AudioPhaseMapper._validate_common(
            math_signal, sample_rate, base_frequency_hz,
        )
        if x.size == 0:
            return x
        _require(deviation >= 0, "deviation must be >= 0")

        if normalize:
            x = _peak_normalize(x)

        inst_freq = np.float32(base_frequency_hz) * (1.0 + x * np.float32(deviation))
        inst_freq = np.maximum(inst_freq, np.float32(1.0))

        phase = _TWO_PI * np.cumsum(inst_freq, dtype=np.float64) / sample_rate
        return np.sin(phase).astype(np.float32, copy=False)

    @staticmethod
    def am_sine(
        math_signal: FloatArray,
        *,
        base_frequency_hz: float,
        sample_rate: int,
        depth: float = 0.8,
        normalize: bool = True,
    ) -> npt.NDArray[np.float32]:
        """
        Amplitude-modulation mapping.

        ``carrier[n] = sin(2π × base_freq × n / sr)``
        ``output[n]  = carrier[n] × (1 - depth + depth × signal[n])``
        """
        x = AudioPhaseMapper._validate_common(
            math_signal, sample_rate, base_frequency_hz,
        )
        if x.size == 0:
            return x
        depth = float(np.clip(depth, 0.0, 1.0))

        if normalize:
            x = _peak_normalize(x)
        # Map signal to [0, 1] for envelope
        envelope = (x + 1.0) * 0.5

        t = np.arange(x.size, dtype=np.float64) / sample_rate
        carrier = np.sin(_TWO_PI * base_frequency_hz * t).astype(np.float32)
        modulated = carrier * ((1.0 - depth) + depth * envelope)
        return np.ascontiguousarray(modulated)

    @staticmethod
    def phase_distortion(
        math_signal: FloatArray,
        *,
        base_frequency_hz: float,
        sample_rate: int,
        normalize: bool = True,
    ) -> npt.NDArray[np.float32]:
        """
        Phase-distortion mapping (Casio CZ–inspired).

        Uses the math signal as a phase transfer function applied to a
        linearly-advancing carrier phase.
        """
        x = AudioPhaseMapper._validate_common(
            math_signal, sample_rate, base_frequency_hz,
        )
        if x.size == 0:
            return x
        if normalize:
            x = _peak_normalize(x)

        t = np.arange(x.size, dtype=np.float64) / sample_rate
        linear_phase = (_TWO_PI * base_frequency_hz * t) % _TWO_PI
        # Use math signal to warp phase
        warped = linear_phase + x.astype(np.float64) * math.pi
        return np.sin(warped).astype(np.float32, copy=False)

    @staticmethod
    def wavetable(
        math_signal: FloatArray,
        *,
        base_frequency_hz: float,
        sample_rate: int,
    ) -> npt.NDArray[np.float32]:
        """
        Wavetable mapping: treat the math signal as one cycle of a waveform,
        then read it back at ``base_frequency_hz`` using interpolation.
        """
        x = AudioPhaseMapper._validate_common(
            math_signal, sample_rate, base_frequency_hz,
        )
        if x.size == 0:
            return x
        table = _peak_normalize(x)
        table_len = table.size

        total_frames = x.size
        t = np.arange(total_frames, dtype=np.float64)
        phase = (t * base_frequency_hz / sample_rate) % 1.0
        indices = phase * table_len

        idx_floor = np.floor(indices).astype(int) % table_len
        idx_ceil = (idx_floor + 1) % table_len
        frac = (indices - np.floor(indices)).astype(np.float32)

        return np.ascontiguousarray(
            table[idx_floor] * (1.0 - frac) + table[idx_ceil] * frac
        )

    @staticmethod
    def direct(
        math_signal: FloatArray,
        *,
        base_frequency_hz: float = 1.0,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        normalize: bool = True,
    ) -> npt.NDArray[np.float32]:
        """
        Direct mapping: use the math signal as audio samples directly.

        Useful when the equation already represents a waveform.
        """
        x = np.asarray(math_signal, dtype=np.float32)
        if x.ndim != 1:
            raise MathEvaluationError("math_signal must be 1-D.")
        x = _sanitize_array(x)
        if normalize and x.size:
            x = _peak_normalize(x)
        return np.clip(x, -1.0, 1.0).astype(np.float32, copy=False)

    @classmethod
    def map_signal(
        cls,
        math_signal: FloatArray,
        *,
        mode: MappingMode,
        base_frequency_hz: float,
        sample_rate: int,
        deviation: float = 0.5,
        normalize: bool = True,
    ) -> npt.NDArray[np.float32]:
        """Dispatch to the appropriate mapping strategy."""
        match mode:
            case MappingMode.FM_SINE:
                return cls.fm_sine(
                    math_signal,
                    base_frequency_hz=base_frequency_hz,
                    sample_rate=sample_rate,
                    deviation=deviation,
                    normalize=normalize,
                )
            case MappingMode.AM_SINE:
                return cls.am_sine(
                    math_signal,
                    base_frequency_hz=base_frequency_hz,
                    sample_rate=sample_rate,
                    depth=deviation,
                    normalize=normalize,
                )
            case MappingMode.PHASE_DISTORTION:
                return cls.phase_distortion(
                    math_signal,
                    base_frequency_hz=base_frequency_hz,
                    sample_rate=sample_rate,
                    normalize=normalize,
                )
            case MappingMode.WAVETABLE:
                return cls.wavetable(
                    math_signal,
                    base_frequency_hz=base_frequency_hz,
                    sample_rate=sample_rate,
                )
            case MappingMode.DIRECT:
                return cls.direct(
                    math_signal,
                    base_frequency_hz=base_frequency_hz,
                    sample_rate=sample_rate,
                    normalize=normalize,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Pure Generators (fun features)
# ═══════════════════════════════════════════════════════════════════════════════

class LissajousGenerator:
    """
    Generate Lissajous-curve-derived audio signals.

    Lissajous figures arise from two perpendicular sinusoids:
    ``x(t) = sin(a·t + δ)``, ``y(t) = sin(b·t)``.
    We use the x-component as the audio signal.
    """

    __slots__ = ()

    @staticmethod
    def generate(
        *,
        sample_rate: int,
        duration_s: float,
        freq_a: float = 3.0,
        freq_b: float = 2.0,
        delta: float = 0.0,
        amplitude: float = 0.9,
    ) -> npt.NDArray[np.float32]:
        """
        Parameters
        ----------
        freq_a, freq_b : Frequency ratio parameters (not Hz — Hz is derived
                         by multiplying with 100 internally).
        delta : Phase offset in radians.
        """
        _require_positive(sample_rate, "sample_rate")
        _require_positive(duration_s, "duration_s")
        frames = max(1, int(round(duration_s * sample_rate)))
        t = np.arange(frames, dtype=np.float64) / sample_rate

        base = 100.0  # Hz multiplier
        sig = np.sin(_TWO_PI * freq_a * base * t + delta).astype(np.float32)
        modulator = np.sin(_TWO_PI * freq_b * base * t).astype(np.float32)

        # Combine into a single signal using ring modulation
        combined = (sig * 0.6 + sig * modulator * 0.4) * np.float32(amplitude)
        return np.ascontiguousarray(combined)


class FractalNoiseGenerator:
    """
    Generate fractal Brownian motion noise (fBm) via octave summation.

    Produces organic, natural textures useful as modulation sources.
    """

    __slots__ = ()

    @staticmethod
    def generate(
        *,
        sample_rate: int,
        duration_s: float,
        octaves: int = 6,
        lacunarity: float = 2.0,
        persistence: float = 0.5,
        amplitude: float = 0.9,
        rng: np.random.Generator | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Parameters
        ----------
        octaves : Number of noise layers to sum.
        lacunarity : Frequency multiplier per octave.
        persistence : Amplitude multiplier per octave.
        """
        _require_positive(sample_rate, "sample_rate")
        _require_positive(duration_s, "duration_s")
        _require(octaves >= 1, "octaves must be >= 1")
        _require_positive(lacunarity, "lacunarity")

        frames = max(1, int(round(duration_s * sample_rate)))
        g = rng or np.random.default_rng()

        signal = np.zeros(frames, dtype=np.float64)
        freq_scale = 1.0
        amp_scale = 1.0

        for _ in range(octaves):
            # Band-limited noise: generate at freq_scale, interpolate up
            layer_size = max(2, int(frames / freq_scale))
            raw = g.standard_normal(layer_size)
            # Upsample via interpolation
            indices = np.linspace(0, layer_size - 1, frames, dtype=np.float64)
            layer = np.interp(indices, np.arange(layer_size), raw)
            signal += layer * amp_scale

            freq_scale *= lacunarity
            amp_scale *= persistence

        result = _peak_normalize(signal.astype(np.float32))
        return np.ascontiguousarray(result * np.float32(amplitude))


class HarmonicSeriesGenerator:
    """
    Generate audio from a harmonic series with configurable amplitudes.

    The harmonic series is the foundation of musical timbre; different
    amplitude profiles produce different tonal colors.
    """

    __slots__ = ()

    @staticmethod
    def generate(
        *,
        sample_rate: int,
        duration_s: float,
        fundamental_hz: float = 220.0,
        num_harmonics: int = 8,
        amplitude_profile: str = "inverse",
        amplitude: float = 0.9,
    ) -> npt.NDArray[np.float32]:
        """
        Parameters
        ----------
        amplitude_profile :
            ``"inverse"``  → 1/n (sawtooth-like).
            ``"inverse_odd"`` → 1/n for odd harmonics only (clarinet-like).
            ``"inverse_square"`` → 1/n² (mellow/organ-like).
            ``"equal"`` → all harmonics at equal amplitude (harsh/buzzy).
            ``"exponential"`` → exp(-0.5·n) (bell-like).
        """
        _require_positive(sample_rate, "sample_rate")
        _require_positive(duration_s, "duration_s")
        _require_positive(fundamental_hz, "fundamental_hz")
        _require(num_harmonics >= 1, "num_harmonics must be >= 1")

        frames = max(1, int(round(duration_s * sample_rate)))
        t = np.arange(frames, dtype=np.float64) / sample_rate
        signal = np.zeros(frames, dtype=np.float64)

        for n in range(1, num_harmonics + 1):
            match amplitude_profile:
                case "inverse":
                    amp = 1.0 / n
                case "inverse_odd":
                    if n % 2 == 0:
                        continue
                    amp = 1.0 / n
                case "inverse_square":
                    amp = 1.0 / (n * n)
                case "equal":
                    amp = 1.0
                case "exponential":
                    amp = math.exp(-0.5 * n)
                case _:
                    amp = 1.0 / n

            freq = fundamental_hz * n
            if freq > sample_rate / 2.0:
                break  # Skip above Nyquist
            signal += amp * np.sin(_TWO_PI * freq * t)

        result = _peak_normalize(signal.astype(np.float32))
        return np.ascontiguousarray(result * np.float32(amplitude))


# ═══════════════════════════════════════════════════════════════════════════════
# Audio Player Protocol (side-effect contract)
# ═══════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class AudioPlayerProtocol(Protocol):
    """
    Minimal protocol for injecting audio playback.

    Keeps the calculator pure-testable: provide a mock or file-writer in tests.
    """

    def play(self, signal: FloatArray, *, blocking: bool = True) -> object: ...


# Best-effort import of the audio synthesizer module
try:
    from .audio_synthesizer import (  # type: ignore[import-untyped]
        AudioSynthesizer as _AudioSynthesizer,
        AudioConfig as _AudioConfig,
        DSP as _DSP,
    )
except Exception:  # pragma: no cover
    _AudioSynthesizer = None
    _AudioConfig = None
    _DSP = None


# ═══════════════════════════════════════════════════════════════════════════════
# Facade / Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class FreqMathCalculator:
    """
    High-level facade orchestrating:

    1. Preprocess + compile equations safely.
    2. Evaluate to math arrays (pure).
    3. Apply optional ``TransformChain`` (pure).
    4. Map to audio via ``AudioPhaseMapper`` (pure).
    5. Optionally play / export via injected backend (side-effect).

    Thread Safety
    -------------
    - Compilation is LRU-cached behind an ``RLock``.
    - ``CompiledEquation`` is immutable.
    - All evaluation / generation is pure → concurrent-safe by construction.
    - Side-effect playback is behind an optional, injectable protocol.

    Examples
    --------
    >>> calc = FreqMathCalculator(sample_rate=44100)
    >>> audio = calc.generate_audio_array("sin(2*pi*x*5)", duration_s=1.0)
    >>> audio.shape
    (44100,)
    """

    _ALLOWED_FUNCTIONS: Final[frozenset[str]] = frozenset(NumpyAstEvaluator._FUNCS.keys())

    _ALLOWED_NAMES: Final[frozenset[str]] = frozenset({
        "x", "pi", "e", "tau",
        # MathParameters fields
        "A", "f", "alpha", "beta", "l",
        # Common variable names
        "t", "omega", "phi", "theta", "D", "k", "n", "m",
        "c", "a", "b", "d", "g", "h", "j", "p", "q", "r",
        "s", "u", "v", "w", "y", "z", "E", "S",
        "partial", "random", "phi_b",
    }) | _ALLOWED_FUNCTIONS

    __slots__ = (
        "sample_rate",
        "_compilation_limits",
        "_generation_limits",
        "_default_params",
        "_policy",
        "_preprocessor",
        "_compile_lock",
        "_audio_player",
        "_default_transform_chain",
    )

    def __init__(
        self,
        *,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        compilation_limits: CompilationLimits = CompilationLimits(),
        generation_limits: GenerationLimits = GenerationLimits(),
        default_params: MathParameters = MathParameters(),
        audio_player: AudioPlayerProtocol | None = None,
        default_transform_chain: TransformChain | None = None,
    ) -> None:
        _require_positive(sample_rate, "sample_rate")

        self.sample_rate = int(sample_rate)
        self._compilation_limits = compilation_limits
        self._generation_limits = generation_limits
        self._default_params = default_params
        self._default_transform_chain = default_transform_chain or TransformChain()

        self._policy = AstSafetyPolicy(
            allowed_names=self._ALLOWED_NAMES,
            allowed_functions=self._ALLOWED_FUNCTIONS,
            limits=self._compilation_limits,
        )
        self._preprocessor = EquationPreprocessor(
            allowed_functions=self._ALLOWED_FUNCTIONS,
        )

        self._compile_lock = threading.RLock()
        self._audio_player = audio_player or self._try_default_audio_player()

    @property
    def default_params(self) -> MathParameters:
        return self._default_params

    @property
    def default_transform_chain(self) -> TransformChain:
        return self._default_transform_chain

    @default_transform_chain.setter
    def default_transform_chain(self, chain: TransformChain) -> None:
        self._default_transform_chain = chain

    def _try_default_audio_player(self) -> AudioPlayerProtocol | None:
        if _AudioSynthesizer is None or _AudioConfig is None:
            logger.info("AudioSynthesizer unavailable; pure-render mode.")
            return None
        try:
            synth = _AudioSynthesizer(
                _AudioConfig(sample_rate=self.sample_rate),
            )
            if isinstance(synth, AudioPlayerProtocol):
                return synth
            logger.info("AudioSynthesizer does not match protocol; pure-render mode.")
            return None
        except Exception:
            logger.exception("Audio backend init failed; pure-render mode.")
            return None

    # ── Compilation ───────────────────────────────────────────────────────

    def compile_equation(self, equation: str) -> CompiledEquation:
        """
        Preprocess and compile a user equation string.

        Returns an immutable ``CompiledEquation`` safe for concurrent evaluation.
        Raises ``MathSecurityError`` on invalid / unsafe input.
        """
        normalized = self._preprocessor.preprocess(equation)
        return self._compile_cached(normalized)

    @lru_cache(maxsize=_COMPILE_CACHE_SIZE)
    def _compile_cached(self, normalized_equation: str) -> CompiledEquation:
        with self._compile_lock:
            try:
                tree = ast.parse(normalized_equation, mode="eval")
            except SyntaxError as exc:
                raise MathSecurityError(
                    f"Malformed equation syntax: {exc}"
                ) from exc

            if not isinstance(tree, ast.Expression):
                raise MathSecurityError("Only single expressions are allowed.")

            self._policy.validate(tree)
            meta = EquationAnalyzer.metadata(
                normalized_equation, tree,
                allowed_functions=self._ALLOWED_FUNCTIONS,
            )
            return CompiledEquation(
                source=normalized_equation, tree=tree, metadata=meta,
            )

    # ── Pure Generation ───────────────────────────────────────────────────

    def generate_math_array(
        self,
        equation: str,
        *,
        x_range: tuple[float, float] = (0.0, 1.0),
        steps: int,
        params: MathParameters | None = None,
        transform_chain: TransformChain | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Evaluate ``equation`` over a linspace and return a float32 array.

        Optionally applies a ``TransformChain`` post-evaluation.
        """
        _require(steps > 0, "steps must be > 0")
        if steps > self._generation_limits.max_steps:
            raise MathDomainError(
                f"steps ({steps}) exceeds limit ({self._generation_limits.max_steps})."
            )

        x0, x1 = float(x_range[0]), float(x_range[1])
        _require_finite(x0, "x_range[0]")
        _require_finite(x1, "x_range[1]")
        if x0 == x1:
            raise MathDomainError("x_range endpoints must differ.")

        compiled = self.compile_equation(equation)
        x = np.linspace(x0, x1, steps, dtype=np.float32)
        p = params or self._default_params

        y = compiled.evaluate_array(x, params=p)

        # Handle scalar-constant equations (broadcast to full array)
        if y.shape != x.shape:
            if np.isscalar(y) or (isinstance(y, np.ndarray) and y.size == 1):
                y = np.full_like(x, float(np.asarray(y).item()))
            else:
                raise MathEvaluationError(
                    f"Equation produced shape {y.shape}, expected {x.shape}."
                )

        y = _sanitize_array(y)

        # Apply transform chain
        chain = transform_chain if transform_chain is not None else self._default_transform_chain
        if chain:
            y = chain(y)

        return np.ascontiguousarray(y, dtype=np.float32)

    def generate_audio_array(
        self,
        equation: str,
        *,
        duration_s: float = 2.0,
        x_range: tuple[float, float] = (0.0, 1.0),
        base_frequency_hz: float = 440.0,
        deviation: float = 0.5,
        mode: MappingMode = MappingMode.FM_SINE,
        params: MathParameters | None = None,
        transform_chain: TransformChain | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Evaluate equation → apply transforms → map to audio.

        Returns a float32 audio signal ready for playback or export.
        """
        _require_positive(duration_s, "duration_s")
        if duration_s > self._generation_limits.max_duration_s:
            raise MathDomainError(
                f"duration_s ({duration_s}) exceeds limit "
                f"({self._generation_limits.max_duration_s})."
            )

        steps = max(1, int(round(duration_s * self.sample_rate)))
        math_signal = self.generate_math_array(
            equation,
            x_range=x_range,
            steps=steps,
            params=params,
            transform_chain=transform_chain,
        )

        return AudioPhaseMapper.map_signal(
            math_signal,
            mode=mode,
            base_frequency_hz=base_frequency_hz,
            sample_rate=self.sample_rate,
            deviation=deviation,
        )

    def generate_from_preset(
        self,
        preset: BuiltinEquation,
        *,
        duration_s: float = 2.0,
        base_frequency_hz: float = 440.0,
        mode: MappingMode = MappingMode.FM_SINE,
        params: MathParameters | None = None,
    ) -> npt.NDArray[np.float32]:
        """Generate audio from a ``BuiltinEquation`` preset."""
        return self.generate_audio_array(
            preset.value,
            duration_s=duration_s,
            base_frequency_hz=base_frequency_hz,
            mode=mode,
            params=params,
        )

    # ── Side Effects (optional) ───────────────────────────────────────────

    def evaluate_and_play(
        self,
        equation: str,
        *,
        duration_s: float = 2.0,
        x_range: tuple[float, float] = (0.0, 1.0),
        base_frequency_hz: float = 440.0,
        deviation: float = 0.5,
        mode: MappingMode = MappingMode.FM_SINE,
        params: MathParameters | None = None,
        transform_chain: TransformChain | None = None,
        blocking: bool = True,
    ) -> npt.NDArray[np.float32]:
        """
        Generate audio and play it through the injected backend.

        Always returns the generated audio array, even if playback fails.
        """
        audio = self.generate_audio_array(
            equation,
            duration_s=duration_s,
            x_range=x_range,
            base_frequency_hz=base_frequency_hz,
            deviation=deviation,
            mode=mode,
            params=params,
            transform_chain=transform_chain,
        )

        if self._audio_player is None:
            logger.info("No audio backend; returning array only.")
            return audio

        # Best-effort ADSR envelope for anti-click
        audio = self._apply_anti_click_envelope(audio)

        try:
            self._audio_player.play(audio, blocking=blocking)
        except Exception:
            logger.exception("Audio playback failed; returning array only.")

        return audio

    def _apply_anti_click_envelope(
        self, audio: npt.NDArray[np.float32],
    ) -> npt.NDArray[np.float32]:
        """Best-effort fade-in/out to prevent clicks."""
        if _DSP is None or audio.size == 0:
            return audio
        try:
            env = _DSP.adsr_envelope(audio.shape[0], self.sample_rate)
            return _DSP.apply_envelope(audio, env)
        except Exception:
            return audio

    # ── Polyphonic / Fun Features ─────────────────────────────────────────

    def create_polyphonic_chord(
        self,
        equation: str,
        *,
        duration_s: float = 2.0,
        root_frequency_hz: float = 220.0,
        ratios: Sequence[float] = (1.0, 1.25, 1.5, 1.875),
        deviation: float = 0.35,
        mode: MappingMode = MappingMode.FM_SINE,
        params: MathParameters | None = None,
        blocking: bool = False,
    ) -> npt.NDArray[np.float32]:
        """
        Render multiple FM voices at harmonic ratios and mix them.

        Default ratios ``(1, 5/4, 3/2, 15/8)`` give a major-seventh chord.
        Pure generation; plays if backend exists.
        """
        voices: list[npt.NDArray[np.float32]] = [
            self.generate_audio_array(
                equation,
                duration_s=duration_s,
                base_frequency_hz=root_frequency_hz * float(r),
                deviation=deviation,
                mode=mode,
                params=params,
            )
            for r in ratios
        ]

        mixed = _mix_signals(voices)

        if self._audio_player is not None:
            try:
                self._audio_player.play(mixed, blocking=blocking)
            except Exception:
                logger.exception("Chord playback failed.")

        return mixed

    def create_evolving_texture(
        self,
        equation: str,
        *,
        duration_s: float = 4.0,
        base_frequency_hz: float = 220.0,
        num_layers: int = 4,
        freq_spread: float = 1.02,
        mode: MappingMode = MappingMode.FM_SINE,
        params: MathParameters | None = None,
    ) -> npt.NDArray[np.float32]:
        """
        Create a slowly-evolving texture by layering slightly-detuned voices.

        Each layer is offset by ``freq_spread`` factor, creating beating patterns.
        """
        _require(num_layers >= 1, "num_layers must be >= 1")
        voices: list[npt.NDArray[np.float32]] = []
        for i in range(num_layers):
            detune = freq_spread ** (i - num_layers / 2.0)
            voices.append(
                self.generate_audio_array(
                    equation,
                    duration_s=duration_s,
                    base_frequency_hz=base_frequency_hz * detune,
                    mode=mode,
                    params=params,
                )
            )
        return _mix_signals(voices)

    def create_harmonic_sweep(
        self,
        *,
        duration_s: float = 3.0,
        fundamental_hz: float = 110.0,
        max_harmonics: int = 16,
        amplitude: float = 0.9,
    ) -> npt.NDArray[np.float32]:
        """
        Additive synthesis sweep: harmonics fade in one by one over the duration.

        Creates a brightening effect — like an orchestral crescendo.
        """
        _require_positive(duration_s, "duration_s")
        _require(max_harmonics >= 1, "max_harmonics must be >= 1")
        frames = max(1, int(round(duration_s * self.sample_rate)))
        t = np.arange(frames, dtype=np.float64) / self.sample_rate
        signal = np.zeros(frames, dtype=np.float64)

        for n in range(1, max_harmonics + 1):
            freq = fundamental_hz * n
            if freq > self.sample_rate / 2.0:
                break
            # Each harmonic fades in at a different time
            fade_start = (n - 1) / max_harmonics * duration_s
            fade_env = np.clip((t - fade_start) / (duration_s * 0.1), 0.0, 1.0)
            harm_amp = fade_env / n
            signal += harm_amp * np.sin(_TWO_PI * freq * t)

        result = _peak_normalize(signal.astype(np.float32))
        return np.ascontiguousarray(result * np.float32(amplitude))

    # ── Analysis / Introspection ──────────────────────────────────────────

    def get_equation_info(
        self,
        equation: str,
        *,
        params: MathParameters | None = None,
    ) -> dict[str, object]:
        """
        Return a dict of metadata + numerical probing for the equation.

        Returns ``{"error": "..."}`` on any failure.
        """
        try:
            compiled = self.compile_equation(equation)
            p = params or self._default_params
            analysis = EquationAnalyzer.probe_bounds(compiled, params=p)
            return {
                **analysis.as_dict(),
                "normalized_equation": compiled.source,
                "metadata": compiled.metadata.as_dict(),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def analyze_equation_structure(
        self,
        equation: str,
    ) -> dict[str, object]:
        """Return static structure metadata for an equation."""
        try:
            compiled = self.compile_equation(equation)
            return compiled.metadata.as_dict()
        except Exception as exc:
            return {"error": str(exc)}

    def list_presets(self) -> dict[str, str]:
        """Return all ``BuiltinEquation`` presets as ``{name: equation}``."""
        return {preset.name: preset.value for preset in BuiltinEquation}

    def list_functions(self) -> tuple[str, ...]:
        """Return all available function names."""
        return tuple(sorted(self._ALLOWED_FUNCTIONS))

    def list_variables(self) -> tuple[str, ...]:
        """Return all available variable names."""
        return tuple(sorted(self._ALLOWED_NAMES - self._ALLOWED_FUNCTIONS))

    # Properties for compatibility with main.py GUI
    @property
    def math_evaluator(self):
        """Provide access to math evaluator for GUI compatibility."""
        class _MathEvaluatorWrapper:
            def __init__(self, calculator):
                self.calculator = calculator
            
            def evaluate(self, equation, x):
                """Evaluate equation at point x, compatible with GUI interface."""
                try:
                    # Convert x to numpy array if it's a scalar
                    if np.isscalar(x):
                        x = np.array([x])
                    
                    # Compile and evaluate the equation
                    compiled = self.calculator.compile_equation(equation)
                    result = compiled.evaluate_array(x, params=self.calculator._default_params)
                    
                    # Return scalar if input was scalar
                    if result.size == 1:
                        return float(result[0])
                    return result
                except Exception:
                    # Fallback for any errors
                    return np.sin(x)
        
        return _MathEvaluatorWrapper(self)

    @property
    def audio_synthesizer(self):
        """Provide access to audio synthesizer for GUI compatibility."""
        return self._audio_player


# ═══════════════════════════════════════════════════════════════════════════════
# Module-Level Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _mix_signals(signals: Sequence[FloatArray]) -> npt.NDArray[np.float32]:
    """Mix multiple signals (zero-pad shorter ones, peak-normalize)."""
    if not signals:
        return np.zeros(0, dtype=np.float32)
    max_len = max(np.asarray(s).shape[0] for s in signals)
    out = np.zeros(max_len, dtype=np.float32)
    for s in signals:
        arr = np.asarray(s, dtype=np.float32)
        out[: arr.shape[0]] += arr
    return _peak_normalize(out)
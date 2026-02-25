#!/usr/bin/env python3
"""
Test cases for FreqMathCalculator component
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import numpy as np
from freq_math_calculator import (
    FreqMathCalculator, 
    MathSecurityError, 
    MathEvaluationError,
    MathDomainError,
    MathParameters,
    CompilationLimits,
    GenerationLimits,
    EquationPreprocessor,
    AstSafetyPolicy,
    CompiledEquation,
    AudioPhaseMapper
)

class TestMathParameters(unittest.TestCase):
    def test_default_parameters(self):
        """Test default parameter values"""
        params = MathParameters()
        self.assertEqual(params.A, 0.5)
        self.assertEqual(params.f, 440.0)
        self.assertEqual(params.alpha, 0.1)
        self.assertEqual(params.beta, 0.1)
        self.assertEqual(params.l, 0.1)
    
    def test_parameter_conversion(self):
        """Test parameter to dict conversion"""
        params = MathParameters(A=0.8, f=880.0)
        param_dict = params.as_dict()
        expected = {"A": 0.8, "f": 880.0, "alpha": 0.1, "beta": 0.1, "l": 0.1}
        self.assertEqual(param_dict, expected)

class TestEquationPreprocessor(unittest.TestCase):
    def setUp(self):
        self.preprocessor = EquationPreprocessor(allowed_functions=['sin', 'cos', 'exp', 'log'])
    
    def test_basic_expressions(self):
        """Test basic expression preprocessing"""
        cases = [
            ("sin(x)", "sin(x)"),
            ("2*x", "2*x"),
            ("x^2", "x**2"),
            ("3x", "3*x"),
            ("x2", "x*2"),
        ]
        
        for input_expr, expected in cases:
            with self.subTest(input_expr=input_expr):
                result = self.preprocessor.preprocess(input_expr)
                self.assertEqual(result, expected)
    
    def test_function_notation(self):
        """Test function notation preprocessing"""
        cases = [
            ("y = sin(x)", "sin(x)"),
            ("f(t) = cos(t)", "cos(x)"),
            ("y(x) = 2*x + 1", "2*x + 1"),
        ]
        
        for input_expr, expected in cases:
            with self.subTest(input_expr=input_expr):
                result = self.preprocessor.preprocess(input_expr)
                self.assertEqual(result, expected)
    
    def test_unicode_normalization(self):
        """Test Unicode operator normalization"""
        cases = [
            ("2×x", "2*x"),
            ("x÷2", "x/2"),
            ("x−1", "x-1"),
            ("x^2", "x**2"),
        ]
        
        for input_expr, expected in cases:
            with self.subTest(input_expr=input_expr):
                result = self.preprocessor.preprocess(input_expr)
                self.assertEqual(result, expected)
    
    def test_implicit_multiplication(self):
        """Test implicit multiplication insertion"""
        cases = [
            ("2(x+1)", "2*(x+1)"),
            ("(x+1)(x-1)", "(x+1)*(x-1)"),
            ("sin(x)cos(x)", "sin(x)*cos(x)"),
            ("2pi", "2*pi"),
        ]
        
        for input_expr, expected in cases:
            with self.subTest(input_expr=input_expr):
                result = self.preprocessor.preprocess(input_expr)
                self.assertEqual(result, expected)
    
    def test_invalid_expressions(self):
        """Test invalid expression handling"""
        with self.assertRaises(MathSecurityError):
            self.preprocessor.preprocess("")
        
        with self.assertRaises(MathSecurityError):
            self.preprocessor.preprocess("   ")

class TestAstSafetyPolicy(unittest.TestCase):
    def setUp(self):
        self.limits = CompilationLimits()
        self.policy = AstSafetyPolicy(
            allowed_names=['x', 'pi', 'e'],
            allowed_functions=['sin', 'cos'],
            limits=self.limits
        )
    
    def test_allowed_expressions(self):
        """Test that allowed expressions pass validation"""
        import ast
        
        valid_expressions = [
            "sin(x)",
            "cos(x) + sin(x)",
            "x + pi",
            "2*x + e",
        ]
        
        for expr in valid_expressions:
            with self.subTest(expr=expr):
                tree = ast.parse(expr, mode='eval')
                try:
                    self.policy.validate(tree)
                except MathSecurityError:
                    self.fail(f"Valid expression {expr} was rejected")
    
    def test_forbidden_nodes(self):
        """Test that forbidden AST nodes are rejected"""
        import ast
        
        forbidden_expressions = [
            "x[0]",  # subscript
            "x.attr",  # attribute
            "lambda x: x",  # lambda
            "[1, 2, 3]",  # list
            "{'x': 1}",  # dict
        ]
        
        for expr in forbidden_expressions:
            with self.subTest(expr=expr):
                tree = ast.parse(expr, mode='eval')
                with self.assertRaises(MathSecurityError):
                    self.policy.validate(tree)
    
    def test_forbidden_names(self):
        """Test that forbidden names are rejected"""
        import ast
        
        forbidden_expressions = [
            "forbidden_func(x)",
            "forbidden_var + x",
        ]
        
        for expr in forbidden_expressions:
            with self.subTest(expr=expr):
                tree = ast.parse(expr, mode='eval')
                with self.assertRaises(MathSecurityError):
                    self.policy.validate(tree)
    
    def test_constant_limits(self):
        """Test constant magnitude limits"""
        import ast
        
        # Should pass
        tree = ast.parse("1000", mode='eval')
        self.policy.validate(tree)
        
        # Should fail (too large)
        tree = ast.parse("1e10", mode='eval')
        with self.assertRaises(MathSecurityError):
            self.policy.validate(tree)

class TestAudioPhaseMapper(unittest.TestCase):
    def test_fm_sine_basic(self):
        """Test basic FM sine synthesis"""
        sample_rate = 44100
        math_signal = np.array([0.0, 0.5, 1.0, -0.5, -1.0])
        
        audio = AudioPhaseMapper.fm_sine(
            math_signal,
            base_frequency_hz=440.0,
            sample_rate=sample_rate,
            deviation=0.5
        )
        
        # Check output properties
        self.assertEqual(len(audio), len(math_signal))
        self.assertTrue(np.all(np.isfinite(audio)))
        self.assertLessEqual(np.max(np.abs(audio)), 1.0)
    
    def test_fm_sine_normalization(self):
        """Test FM synthesis with normalization"""
        sample_rate = 44100
        math_signal = np.array([2.0, -2.0, 1.5, -1.5])
        
        # With normalization
        audio_norm = AudioPhaseMapper.fm_sine(
            math_signal,
            base_frequency_hz=440.0,
            sample_rate=sample_rate,
            normalize=True
        )
        
        # Without normalization
        audio_no_norm = AudioPhaseMapper.fm_sine(
            math_signal,
            base_frequency_hz=440.0,
            sample_rate=sample_rate,
            normalize=False
        )
        
        # Normalized should have smaller amplitude
        self.assertLess(np.max(np.abs(audio_norm)), np.max(np.abs(audio_no_norm)))
    
    def test_fm_sine_immutable(self):
        """Test immutable flag"""
        math_signal = np.array([0.0, 0.5, 1.0])
        
        audio = AudioPhaseMapper.fm_sine(
            math_signal,
            base_frequency_hz=440.0,
            sample_rate=44100,
            immutable=True
        )
        
        self.assertFalse(audio.flags.writeable)
    
    def test_fm_sine_error_handling(self):
        """Test error handling for invalid inputs"""
        math_signal = np.array([0.0, 0.5, 1.0])
        
        # Invalid sample rate
        with self.assertRaises(ValueError):
            AudioPhaseMapper.fm_sine(math_signal, base_frequency_hz=440.0, sample_rate=0)
        
        # Invalid base frequency
        with self.assertRaises(ValueError):
            AudioPhaseMapper.fm_sine(math_signal, base_frequency_hz=0.0, sample_rate=44100)
        
        # Invalid deviation
        with self.assertRaises(ValueError):
            AudioPhaseMapper.fm_sine(math_signal, base_frequency_hz=440.0, sample_rate=44100, deviation=-0.1)

class TestFreqMathCalculator(unittest.TestCase):
    def setUp(self):
        self.calculator = FreqMathCalculator()
    
    def test_compilation(self):
        """Test equation compilation"""
        compiled = self.calculator.compile_equation("sin(x)")
        
        self.assertIsInstance(compiled, CompiledEquation)
        self.assertEqual(compiled.source, "sin(x)")
        self.assertTrue(compiled.metadata.is_safe)
    
    def test_generate_math_array(self):
        """Test math array generation"""
        result = self.calculator.generate_math_array("sin(x)", steps=100)
        
        self.assertEqual(len(result), 100)
        self.assertTrue(np.all(np.isfinite(result)))
        
        # Test specific values
        expected_first = np.sin(0.0)
        self.assertAlmostEqual(result[0], expected_first, places=5)
    
    def test_generate_audio_array(self):
        """Test audio array generation"""
        audio = self.calculator.generate_audio_array("sin(x)", duration_s=0.1)
        
        expected_samples = int(0.1 * self.calculator.sample_rate)
        self.assertEqual(len(audio), expected_samples)
        self.assertTrue(np.all(np.isfinite(audio)))
        self.assertLessEqual(np.max(np.abs(audio)), 1.0)
    
    def test_custom_parameters(self):
        """Test custom math parameters"""
        params = MathParameters(A=0.8, f=880.0)
        result = self.calculator.generate_math_array("A*sin(x)", steps=10, params=params)
        
        # Should use custom A value
        expected_first = 0.8 * np.sin(0.0)
        self.assertAlmostEqual(result[0], expected_first, places=5)
    
    def test_equation_info(self):
        """Test equation analysis"""
        info = self.calculator.get_equation_info("sin(x) + cos(x)")
        
        self.assertIn("equation", info)
        self.assertIn("metadata", info)
        self.assertIn("min_result", info)
        self.assertIn("max_result", info)
        self.assertEqual(info["equation"], "sin(x) + cos(x)")
    
    def test_polyphonic_chord(self):
        """Test polyphonic chord generation"""
        chord = self.calculator.create_polyphonic_chord("sin(x)", duration_s=0.1)
        
        expected_samples = int(0.1 * self.calculator.sample_rate)
        self.assertEqual(len(chord), expected_samples)
        self.assertTrue(np.all(np.isfinite(chord)))
    
    def test_domain_limits(self):
        """Test domain limit enforcement"""
        # Too many steps
        with self.assertRaises(MathDomainError):
            self.calculator.generate_math_array("sin(x)", steps=10_000_000)
        
        # Too long duration
        with self.assertRaises(MathDomainError):
            self.calculator.generate_audio_array("sin(x)", duration_s=120.0)
    
    def test_security_validation(self):
        """Test security validation"""
        dangerous_expressions = [
            "__import__('os')",
            "eval('1+1')",
            "open('file.txt')",
            "exec('print(1)')",
        ]
        
        for expr in dangerous_expressions:
            with self.subTest(expr=expr):
                with self.assertRaises(MathSecurityError):
                    self.calculator.compile_equation(expr)

if __name__ == "__main__":
    unittest.main()

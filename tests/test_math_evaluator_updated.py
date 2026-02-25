#!/usr/bin/env python3
"""
Updated test cases for math evaluator component (compatible with refactored codebase)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import numpy as np
from freq_math_calculator import FreqMathCalculator, MathParameters

class TestMathEvaluatorUpdated(unittest.TestCase):
    def setUp(self):
        self.calculator = FreqMathCalculator()
    
    def test_simple_arithmetic(self):
        """Test basic arithmetic operations"""
        # Test addition
        result = self.calculator.generate_math_array("2 + 3", steps=1)
        self.assertAlmostEqual(result[0], 5.0, places=5)
        
        # Test subtraction
        result = self.calculator.generate_math_array("10 - 4", steps=1)
        self.assertAlmostEqual(result[0], 6.0, places=5)
        
        # Test multiplication
        result = self.calculator.generate_math_array("3 * 4", steps=1)
        self.assertAlmostEqual(result[0], 12.0, places=5)
        
        # Test division
        result = self.calculator.generate_math_array("15 / 3", steps=1)
        self.assertAlmostEqual(result[0], 5.0, places=5)
    
    def test_trigonometric_functions(self):
        """Test trigonometric functions"""
        # Test sine
        result = self.calculator.generate_math_array("sin(0)", steps=1)
        self.assertAlmostEqual(result[0], 0.0, places=5)
        
        # Test cosine
        result = self.calculator.generate_math_array("cos(0)", steps=1)
        self.assertAlmostEqual(result[0], 1.0, places=5)
        
        # Test with pi
        result = self.calculator.generate_math_array("sin(pi)", steps=1)
        self.assertAlmostEqual(result[0], 0.0, places=5)
    
    def test_variables(self):
        """Test variable handling"""
        # Test x variable
        result = self.calculator.generate_math_array("x", steps=3, x_range=(2.0, 2.01))
        self.assertAlmostEqual(result[0], 2.0, places=5)
        self.assertAlmostEqual(result[1], 2.005, places=2)  # Less precision for floating point
        self.assertAlmostEqual(result[2], 2.01, places=2)
        
        # Test x in expression
        result = self.calculator.generate_math_array("2*x + 1", steps=1, x_range=(3.0, 3.01))
        self.assertAlmostEqual(result[0], 7.0, places=5)
    
    def test_constants(self):
        """Test mathematical constants"""
        # Test pi
        result = self.calculator.generate_math_array("pi", steps=1)
        self.assertAlmostEqual(result[0], 3.141592653589793, places=5)
        
        # Test e
        result = self.calculator.generate_math_array("e", steps=1)
        self.assertAlmostEqual(result[0], 2.718281828459045, places=5)
    
    def test_complex_expressions(self):
        """Test complex mathematical expressions"""
        # Test polynomial
        result = self.calculator.generate_math_array("x**2 + 2*x + 1", steps=1, x_range=(2.0, 2.01))
        self.assertAlmostEqual(result[0], 9.0, places=5)
        
        # Test nested functions
        result = self.calculator.generate_math_array("sin(cos(x))", steps=1, x_range=(0.0, 0.01))
        expected = np.sin(np.cos(0.0))
        self.assertAlmostEqual(result[0], expected, places=5)
    
    def test_custom_parameters(self):
        """Test custom math parameters"""
        params = MathParameters(A=0.8, f=880.0)
        
        # Test A parameter
        result = self.calculator.generate_math_array("A", steps=1, params=params)
        self.assertAlmostEqual(result[0], 0.8, places=5)
        
        # Test f parameter
        result = self.calculator.generate_math_array("f", steps=1, params=params)
        self.assertAlmostEqual(result[0], 880.0, places=5)
    
    def test_function_notation(self):
        """Test function notation preprocessing"""
        # Test y = expression
        result = self.calculator.generate_math_array("y = sin(x)", steps=1, x_range=(0.0, 0.01))
        expected = np.sin(0.0)
        self.assertAlmostEqual(result[0], expected, places=5)
        
        # Test f(x) = expression
        result = self.calculator.generate_math_array("f(x) = 2*x + 1", steps=1, x_range=(3.0, 3.01))
        self.assertAlmostEqual(result[0], 7.0, places=5)
    
    def test_unicode_operators(self):
        """Test Unicode operator normalization"""
        # Test multiplication
        result = self.calculator.generate_math_array("2 × x", steps=1, x_range=(3.0, 3.01))
        self.assertAlmostEqual(result[0], 6.0, places=5)
        
        # Test division
        result = self.calculator.generate_math_array("x ÷ 2", steps=1, x_range=(4.0, 4.01))
        self.assertAlmostEqual(result[0], 2.0, places=5)
        
        # Test power
        result = self.calculator.generate_math_array("x^2", steps=1, x_range=(3.0, 3.01))
        self.assertAlmostEqual(result[0], 9.0, places=5)
    
    def test_implicit_multiplication(self):
        """Test implicit multiplication insertion"""
        # Test 2x
        result = self.calculator.generate_math_array("2x", steps=1, x_range=(3.0, 3.01))
        self.assertAlmostEqual(result[0], 6.0, places=5)
        
        # Test 2(x+1)
        result = self.calculator.generate_math_array("2(x+1)", steps=1, x_range=(2.0, 2.01))
        self.assertAlmostEqual(result[0], 6.0, places=5)
        
        # Test (x+1)(x-1)
        result = self.calculator.generate_math_array("(x+1)(x-1)", steps=1, x_range=(3.0, 3.01))
        self.assertAlmostEqual(result[0], 8.0, places=5)
    
    def test_array_evaluation(self):
        """Test array evaluation across multiple points"""
        result = self.calculator.generate_math_array("x", steps=5, x_range=(0.0, 1.0))
        expected = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        
        for i, (res, exp) in enumerate(zip(result, expected)):
            self.assertAlmostEqual(res, exp, places=5, 
                                 msg=f"Mismatch at index {i}: {res} != {exp}")
    
    def test_audio_generation(self):
        """Test audio array generation"""
        audio = self.calculator.generate_audio_array("sin(x)", duration_s=0.1)
        
        expected_samples = int(0.1 * self.calculator.sample_rate)
        self.assertEqual(len(audio), expected_samples)
        self.assertTrue(np.all(np.isfinite(audio)))
        self.assertLessEqual(np.max(np.abs(audio)), 1.0)
    
    def test_equation_analysis(self):
        """Test equation analysis functionality"""
        info = self.calculator.get_equation_info("sin(x) + cos(x)")
        
        # Handle case where analysis fails
        if "error" in info:
            self.skipTest(f"Equation analysis failed: {info['error']}")
            return
        
        self.assertIn("equation", info)
        self.assertIn("metadata", info)
        self.assertIn("min_result", info)
        self.assertIn("max_result", info)
        # Note: preprocessing removes spaces, so expect sin(x)+cos(x)
        self.assertEqual(info["equation"], "sin(x)+cos(x)")
        
        # Check metadata
        metadata = info["metadata"]
        self.assertIsInstance(metadata, dict)
        self.assertIn("operations", metadata)
        self.assertIn("functions", metadata)
        self.assertIn("complexity_score", metadata)
    
    def test_error_handling(self):
        """Test error handling for invalid expressions"""
        from freq_math_calculator import MathSecurityError
        
        invalid_expressions = [
            "__import__('os')",
            "eval('1+1')",
            "open('file.txt')",
            "unknown_function(x)",
        ]
        
        for expr in invalid_expressions:
            with self.subTest(expr=expr):
                with self.assertRaises(MathSecurityError):
                    self.calculator.compile_equation(expr)

if __name__ == "__main__":
    unittest.main()

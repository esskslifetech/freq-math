#!/usr/bin/env python3
"""
Test cases for the math evaluator component
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
from freq_math_calculator import FreqMathCalculator
import numpy as np

class TestMathEvaluator(unittest.TestCase):
    def setUp(self):
        self.calculator = FreqMathCalculator()
    
    def test_simple_arithmetic(self):
        """Test basic arithmetic operations"""
        if not self.calculator.math_evaluator:
            self.skipTest("C++ bindings not available")
        
        # Test addition
        result = self.calculator.math_evaluator.evaluate("2 + 3", 0)
        self.assertAlmostEqual(result, 5.0, places=5)
        
        # Test subtraction
        result = self.calculator.math_evaluator.evaluate("10 - 4", 0)
        self.assertAlmostEqual(result, 6.0, places=5)
        
        # Test multiplication
        result = self.calculator.math_evaluator.evaluate("3 * 4", 0)
        self.assertAlmostEqual(result, 12.0, places=5)
        
        # Test division
        result = self.calculator.math_evaluator.evaluate("15 / 3", 0)
        self.assertAlmostEqual(result, 5.0, places=5)
    
    def test_trigonometric_functions(self):
        """Test trigonometric functions"""
        if not self.calculator.math_evaluator:
            self.skipTest("C++ bindings not available")
        
        # Test sine
        result = self.calculator.math_evaluator.evaluate("sin(0)", 0)
        self.assertAlmostEqual(result, 0.0, places=5)
        
        # Test cosine
        result = self.calculator.math_evaluator.evaluate("cos(0)", 0)
        self.assertAlmostEqual(result, 1.0, places=5)
        
        # Test with pi
        result = self.calculator.math_evaluator.evaluate("sin(pi)", 0)
        self.assertAlmostEqual(result, 0.0, places=5)
    
    def test_variables(self):
        """Test variable handling"""
        if not self.calculator.math_evaluator:
            self.skipTest("C++ bindings not available")
        
        # Test x variable
        result = self.calculator.math_evaluator.evaluate("x", 2.5)
        self.assertAlmostEqual(result, 2.5, places=5)
        
        # Test x in expression
        result = self.calculator.math_evaluator.evaluate("2*x + 1", 3)
        self.assertAlmostEqual(result, 7.0, places=5)
    
    def test_constants(self):
        """Test mathematical constants"""
        if not self.calculator.math_evaluator:
            self.skipTest("C++ bindings not available")
        
        # Test pi
        result = self.calculator.math_evaluator.evaluate("pi", 0)
        self.assertAlmostEqual(result, 3.14159265358979323846, places=5)
        
        # Test e
        result = self.calculator.math_evaluator.evaluate("e", 0)
        self.assertAlmostEqual(result, 2.71828182845904523536, places=5)
    
    def test_complex_expressions(self):
        """Test complex mathematical expressions"""
        if not self.calculator.math_evaluator:
            self.skipTest("C++ bindings not available")
        
        # Test polynomial
        result = self.calculator.math_evaluator.evaluate("x^2 + 2*x + 1", 2)
        self.assertAlmostEqual(result, 9.0, places=5)
        
        # Test nested functions
        result = self.calculator.math_evaluator.evaluate("sin(cos(x))", 0)
        expected = np.sin(np.cos(0))
        self.assertAlmostEqual(result, expected, places=5)
    
    def test_evaluate_range(self):
        """Test range evaluation"""
        if not self.calculator.math_evaluator:
            self.skipTest("C++ bindings not available")
        
        results = self.calculator.math_evaluator.evaluate_range("x", 0, 1, 5)
        expected = [0.0, 0.25, 0.5, 0.75, 1.0]
        
        for i, (result, exp) in enumerate(zip(results, expected)):
            self.assertAlmostEqual(result, exp, places=5, 
                                 msg=f"Mismatch at index {i}: {result} != {exp}")

if __name__ == "__main__":
    unittest.main()

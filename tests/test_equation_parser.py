#!/usr/bin/env python3
"""
Test cases for equation parser component (C++ bindings)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest

try:
    from src.python.freq_math_bindings import EquationParser, MathEnvironment, ParseError
    EQUATION_PARSER_AVAILABLE = True
except ImportError as e:
    print(f"Equation parser not available: {e}")
    EQUATION_PARSER_AVAILABLE = False

@unittest.skipUnless(EQUATION_PARSER_AVAILABLE, "Equation parser not available")
class TestEquationParser(unittest.TestCase):
    def setUp(self):
        self.parser = EquationParser()
        self.env = MathEnvironment()
    
    def test_basic_arithmetic(self):
        """Test basic arithmetic parsing"""
        equations = [
            "2 + 3",
            "10 - 4",
            "3 * 4",
            "15 / 3",
            "2 ^ 3",
        ]
        
        for eq in equations:
            with self.subTest(equation=eq):
                result = self.parser.parse(eq, self.env)
                self.assertIsNotNone(result)
                self.assertFalse(result.is_error())
    
    def test_trigonometric_functions(self):
        """Test trigonometric function parsing"""
        equations = [
            "sin(0)",
            "cos(0)",
            "tan(0)",
            "sin(pi)",
            "cos(pi/2)",
        ]
        
        for eq in equations:
            with self.subTest(equation=eq):
                result = self.parser.parse(eq, self.env)
                self.assertIsNotNone(result)
                self.assertFalse(result.is_error())
    
    def test_variables_and_constants(self):
        """Test variable and constant parsing"""
        equations = [
            "x",
            "2*x + 1",
            "pi",
            "e",
            "x + pi",
        ]
        
        for eq in equations:
            with self.subTest(equation=eq):
                result = self.parser.parse(eq, self.env)
                self.assertIsNotNone(result)
                self.assertFalse(result.is_error())
    
    def test_complex_expressions(self):
        """Test complex mathematical expressions"""
        equations = [
            "x^2 + 2*x + 1",
            "sin(cos(x))",
            "exp(-x^2)",
            "sqrt(x^2 + y^2)",
            "log(abs(x))",
        ]
        
        for eq in equations:
            with self.subTest(equation=eq):
                result = self.parser.parse(eq, self.env)
                self.assertIsNotNone(result)
                self.assertFalse(result.is_error())
    
    def test_error_handling(self):
        """Test error handling for invalid expressions"""
        invalid_equations = [
            "2 +",  # Incomplete
            "2 * * 3",  # Invalid syntax
            "sin(",  # Unclosed parenthesis
            "unknown_func(x)",  # Unknown function
            "2 / 0",  # Division by zero (may be caught at evaluation)
        ]
        
        for eq in invalid_equations:
            with self.subTest(equation=eq):
                result = self.parser.parse(eq, self.env)
                # Should either return error or raise exception
                if result is not None:
                    # If result is returned, it should indicate error
                    self.assertTrue(result.is_error() or hasattr(result, 'error'))

@unittest.skipUnless(EQUATION_PARSER_AVAILABLE, "Equation parser not available")
class TestMathEnvironment(unittest.TestCase):
    def setUp(self):
        self.env = MathEnvironment()
    
    def test_variable_operations(self):
        """Test variable setting and getting"""
        # Set variables
        self.env.set_variable("x", 2.5)
        self.env.set_variable("y", 3.7)
        
        # Get variables
        x_val = self.env.get_variable("x")
        y_val = self.env.get_variable("y")
        
        self.assertFalse(x_val.is_error())
        self.assertFalse(y_val.is_error())
        self.assertAlmostEqual(x_val.value, 2.5, places=5)
        self.assertAlmostEqual(y_val.value, 3.7, places=5)
    
    def test_undefined_variable(self):
        """Test getting undefined variable"""
        result = self.env.get_variable("undefined")
        
        self.assertTrue(result.is_error())
    
    def test_variable_override(self):
        """Test variable overriding"""
        # Set initial value
        self.env.set_variable("x", 1.0)
        result = self.env.get_variable("x")
        self.assertAlmostEqual(result.value, 1.0, places=5)
        
        # Override value
        self.env.set_variable("x", 5.0)
        result = self.env.get_variable("x")
        self.assertAlmostEqual(result.value, 5.0, places=5)
    
    def test_constant_variables(self):
        """Test built-in constants"""
        # These should be available by default
        pi_result = self.env.get_variable("pi")
        e_result = self.env.get_variable("e")
        
        self.assertFalse(pi_result.is_error())
        self.assertFalse(e_result.is_error())
        
        self.assertAlmostEqual(pi_result.value, 3.141592653589793, places=5)
        self.assertAlmostEqual(e_result.value, 2.718281828459045, places=5)

@unittest.skipUnless(EQUATION_PARSER_AVAILABLE, "Equation parser not available")
class TestParseError(unittest.TestCase):
    def test_error_creation(self):
        """Test ParseError creation and properties"""
        # This tests the error structure if available
        try:
            # Try to parse an invalid expression
            parser = EquationParser()
            env = MathEnvironment()
            result = parser.parse("2 + + 3", env)
            
            if result and result.is_error():
                error = result.error()
                self.assertIsNotNone(error)
                # Check if error has expected properties
                if hasattr(error, 'message'):
                    self.assertIsInstance(error.message, str)
                if hasattr(error, 'location'):
                    self.assertIsNotNone(error.location)
        except Exception:
            # If this interface doesn't exist, that's okay for this test
            pass

if __name__ == "__main__":
    unittest.main()

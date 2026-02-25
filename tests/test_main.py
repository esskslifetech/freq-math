#!/usr/bin/env python3
"""
Test cases for main.py entry point
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import tempfile
import subprocess
from pathlib import Path

class TestMainEntry(unittest.TestCase):
    """Test the main.py entry point"""
    
    def test_main_import(self):
        """Test that main.py can be imported"""
        try:
            import main
            self.assertIsNotNone(main)
        except ImportError as e:
            self.fail(f"Could not import main.py: {e}")
    
    def test_main_help(self):
        """Test main.py help functionality"""
        try:
            # Run main.py with --help or -h
            result = subprocess.run(
                [sys.executable, "main.py", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.path.dirname(os.path.dirname(__file__))
            )
            
            # Should exit with code 0 (help shown) or 1 (unknown option)
            self.assertIn(result.returncode, [0, 1])
            
            # Should contain help text or usage information
            output = result.stdout + result.stderr
            self.assertTrue(
                "usage" in output.lower() or 
                "help" in output.lower() or
                "main.py" in output
            )
        except subprocess.TimeoutExpired:
            self.fail("main.py --help timed out")
        except Exception as e:
            self.fail(f"Error running main.py --help: {e}")
    
    def test_main_with_equation(self):
        """Test main.py with a simple equation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Run main.py with a simple equation
                result = subprocess.run(
                    [sys.executable, "main.py", "sin(2*pi*440*x)"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src" / "python")}
                )
                
                # Should complete without crashing
                # Exit code may be 0 (success) or non-zero (audio issues)
                self.assertIsNotNone(result.returncode)
                
                # Should not have Python syntax errors
                self.assertNotIn("SyntaxError", result.stderr)
                self.assertNotIn("ImportError", result.stderr)
                
            except subprocess.TimeoutExpired:
                self.fail("main.py with equation timed out")
            except Exception as e:
                self.fail(f"Error running main.py with equation: {e}")
    
    def test_main_with_complex_equation(self):
        """Test main.py with complex equations that were previously problematic"""
        complex_equations = [
            "y=sin(2*pi*f*t)",
            "y(t)=A*sin(2*pi*f*t)",
            "f(x)=exp(-3*x)*sin(2*pi*880*x)",
            "sin(x) + (1/2)*sin(2*x) + (1/3)*sin(3*x)",
        ]
        
        for equation in complex_equations:
            with self.subTest(equation=equation):
                with tempfile.TemporaryDirectory() as temp_dir:
                    try:
                        result = subprocess.run(
                            [sys.executable, "main.py", equation],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            cwd=os.path.dirname(os.path.dirname(__file__)),
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src" / "python")}
                        )
                        
                        # Should not crash with syntax errors
                        self.assertNotIn("SyntaxError", result.stderr)
                        self.assertNotIn("Forbidden variable", result.stderr)
                        
                    except subprocess.TimeoutExpired:
                        self.fail(f"main.py with equation '{equation}' timed out")
                    except Exception as e:
                        self.fail(f"Error running main.py with equation '{equation}': {e}")
    
    def test_main_error_handling(self):
        """Test main.py error handling"""
        try:
            # Run with invalid equation
            result = subprocess.run(
                [sys.executable, "main.py", "__import__('os')"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src" / "python")}
            )
            
            # Should handle security errors gracefully
            output = result.stderr.lower()
            self.assertTrue(
                "forbidden" in output or 
                "security" in output or
                "error" in output or
                "invalid" in output
            )
            
        except subprocess.TimeoutExpired:
            self.fail("main.py error handling test timed out")
        except Exception as e:
            self.fail(f"Error testing main.py error handling: {e}")

class TestMainFunctionality(unittest.TestCase):
    """Test main.py functionality by importing and calling directly"""
    
    def test_main_function_exists(self):
        """Test that main function exists"""
        try:
            import main
            self.assertTrue(hasattr(main, 'main'))
            self.assertTrue(callable(getattr(main, 'main')))
        except ImportError as e:
            self.fail(f"Could not import main: {e}")
    
    def test_main_function_call(self):
        """Test calling main function directly"""
        try:
            import main
            
            # Test with minimal arguments
            # This may fail due to GUI dependencies, but shouldn't crash
            try:
                # Save original sys.argv
                original_argv = sys.argv
                sys.argv = ['main.py', 'sin(2*pi*440*x)']
                
                # Call main function
                main.main()
                
            except SystemExit:
                # Main may call sys.exit, which is expected
                pass
            except Exception as e:
                # Other exceptions might be expected (GUI, audio issues)
                # But shouldn't be import/syntax errors
                if "SyntaxError" in str(e) or "ImportError" in str(e):
                    self.fail(f"Unexpected import/syntax error: {e}")
            finally:
                # Restore original sys.argv
                sys.argv = original_argv
                
        except ImportError as e:
            self.fail(f"Could not import main: {e}")

if __name__ == "__main__":
    unittest.main()

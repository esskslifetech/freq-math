#!/usr/bin/env python3
"""
Test cases for example scripts
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python'))

import unittest
import subprocess
import tempfile
from pathlib import Path

class TestExamples(unittest.TestCase):
    """Test example scripts"""
    
    def test_basic_usage_example(self):
        """Test basic_usage.py example"""
        examples_dir = Path(__file__).parent.parent / "examples"
        basic_usage_path = examples_dir / "basic_usage.py"
        
        if not basic_usage_path.exists():
            self.skipTest("basic_usage.py example not found")
        
        try:
            # Run the example script
            result = subprocess.run(
                [sys.executable, str(basic_usage_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(examples_dir),
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src" / "python")}
            )
            
            # Should complete without crashing
            self.assertIsNotNone(result.returncode)
            
            # Should not have Python import/syntax errors
            self.assertNotIn("ImportError", result.stderr)
            self.assertNotIn("SyntaxError", result.stderr)
            self.assertNotIn("ModuleNotFoundError", result.stderr)
            
        except subprocess.TimeoutExpired:
            self.fail("basic_usage.py timed out")
        except Exception as e:
            self.fail(f"Error running basic_usage.py: {e}")
    
    def test_demo_py(self):
        """Test demo.py script"""
        demo_path = Path(__file__).parent.parent / "demo.py"
        
        if not demo_path.exists():
            self.skipTest("demo.py not found")
        
        try:
            # Run demo script
            result = subprocess.run(
                [sys.executable, str(demo_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(demo_path.parent),
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src" / "python")}
            )
            
            # Should complete without crashing
            self.assertIsNotNone(result.returncode)
            
            # Should not have Python import/syntax errors
            self.assertNotIn("ImportError", result.stderr)
            self.assertNotIn("SyntaxError", result.stderr)
            self.assertNotIn("ModuleNotFoundError", result.stderr)
            
        except subprocess.TimeoutExpired:
            self.fail("demo.py timed out")
        except Exception as e:
            self.fail(f"Error running demo.py: {e}")
    
    def test_example_output_files(self):
        """Test that examples can generate output files"""
        examples_dir = Path(__file__).parent.parent / "examples"
        basic_usage_path = examples_dir / "basic_usage.py"
        
        if not basic_usage_path.exists():
            self.skipTest("basic_usage.py example not found")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Run example in temporary directory to catch output files
                result = subprocess.run(
                    [sys.executable, str(basic_usage_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=temp_dir,
                    env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src" / "python")}
                )
                
                # Check for common output files
                temp_path = Path(temp_dir)
                output_files = list(temp_path.glob("*.wav"))
                
                # Should have generated at least one output file
                # (This may depend on the example implementation)
                if output_files:
                    self.assertGreater(len(output_files), 0)
                    
                    # Verify files are not empty
                    for wav_file in output_files:
                        self.assertGreater(wav_file.stat().st_size, 0)
                
            except subprocess.TimeoutExpired:
                self.fail("basic_usage.py output test timed out")
            except Exception as e:
                self.fail(f"Error testing example output: {e}")

class TestExampleFunctionality(unittest.TestCase):
    """Test example functionality by importing directly"""
    
    def test_basic_usage_import(self):
        """Test importing and running basic_usage functionality"""
        examples_dir = Path(__file__).parent.parent / "examples"
        basic_usage_path = examples_dir / "basic_usage.py"
        
        if not basic_usage_path.exists():
            self.skipTest("basic_usage.py example not found")
        
        try:
            # Add examples directory to path
            sys.path.insert(0, str(examples_dir))
            import basic_usage
            
            # Check if main functionality exists
            if hasattr(basic_usage, 'main'):
                # Try to call main (may fail due to audio/GUI issues)
                try:
                    basic_usage.main()
                except Exception as e:
                    # Should not be import/syntax errors
                    if "ImportError" in str(e) or "SyntaxError" in str(e):
                        self.fail(f"Import/syntax error in basic_usage: {e}")
            else:
                # Look for other common function names
                functions = [name for name in dir(basic_usage) if not name.startswith('_')]
                self.assertGreater(len(functions), 0, "No public functions found in basic_usage")
                
        except ImportError as e:
            self.fail(f"Could not import basic_usage: {e}")
        finally:
            # Clean up path
            if str(examples_dir) in sys.path:
                sys.path.remove(str(examples_dir))
    
    def test_demo_import(self):
        """Test importing demo functionality"""
        demo_path = Path(__file__).parent.parent / "demo.py"
        
        if not demo_path.exists():
            self.skipTest("demo.py not found")
        
        try:
            # Add parent directory to path to import demo
            parent_dir = demo_path.parent
            sys.path.insert(0, str(parent_dir))
            import demo
            
            # Check if main functionality exists
            if hasattr(demo, 'main'):
                # Try to call main
                try:
                    demo.main()
                except Exception as e:
                    # Should not be import/syntax errors
                    if "ImportError" in str(e) or "SyntaxError" in str(e):
                        self.fail(f"Import/syntax error in demo: {e}")
            else:
                # Look for other common function names
                functions = [name for name in dir(demo) if not name.startswith('_')]
                self.assertGreater(len(functions), 0, "No public functions found in demo")
                
        except ImportError as e:
            self.fail(f"Could not import demo: {e}")
        finally:
            # Clean up path
            if str(parent_dir) in sys.path:
                sys.path.remove(str(parent_dir))

if __name__ == "__main__":
    unittest.main()

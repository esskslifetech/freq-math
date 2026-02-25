#!/usr/bin/env python3
"""
Run all tests for the Freq-Math project
"""

import sys
import os
import unittest
import time
from pathlib import Path

# Add src/python to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

def discover_and_run_tests():
    """Discover and run all test files"""
    # Get the tests directory
    tests_dir = Path(__file__).parent
    
    # Discover all test files
    test_files = list(tests_dir.glob("test_*.py"))
    
    if not test_files:
        print("No test files found!")
        return False
    
    print(f"Found {len(test_files)} test files:")
    for test_file in sorted(test_files):
        print(f"  - {test_file.name}")
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Load tests from each file
    for test_file in sorted(test_files):
        try:
            # Convert file path to module name
            module_name = test_file.stem
            
            # Import the module
            if module_name in sys.modules:
                # Reload if already imported
                import importlib
                importlib.reload(sys.modules[module_name])
            else:
                # Import new module
                __import__(module_name)
            
            # Load tests from module
            module_suite = loader.loadTestsFromName(module_name)
            suite.addTest(module_suite)
            
        except Exception as e:
            print(f"Warning: Could not load tests from {test_file.name}: {e}")
            continue
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    start_time = time.time()
    result = runner.run(suite)
    end_time = time.time()
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Tests completed in {end_time - start_time:.2f} seconds")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    if result.failures:
        print(f"\nFailures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
    
    if result.errors:
        print(f"\nErrors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n{'PASS' if success else 'FAIL'}")
    print('='*60)
    
    return success

def run_specific_test(test_name):
    """Run a specific test file or test method"""
    tests_dir = Path(__file__).parent
    
    # Check if it's a test file
    test_file = tests_dir / f"test_{test_name}.py"
    if test_file.exists():
        module_name = test_file.stem
        suite = unittest.TestLoader().loadTestsFromName(module_name)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return len(result.failures) == 0 and len(result.errors) == 0
    
    # Check if it's a specific test method
    for test_file in tests_dir.glob("test_*.py"):
        try:
            module_name = test_file.stem
            if module_name in sys.modules:
                import importlib
                importlib.reload(sys.modules[module_name])
            else:
                __import__(module_name)
            
            # Try to load specific test
            suite = unittest.TestLoader().loadTestsFromName(f"{module_name}.{test_name}")
            if suite.countTestCases() > 0:
                runner = unittest.TextTestRunner(verbosity=2)
                result = runner.run(suite)
                return len(result.failures) == 0 and len(result.errors) == 0
        except Exception:
            continue
    
    print(f"Could not find test: {test_name}")
    return False

def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1]
        success = run_specific_test(test_name)
    else:
        # Run all tests
        success = discover_and_run_tests()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

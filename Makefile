# Makefile for Freq-Math project

.PHONY: all build clean test install run-examples help test-all test-math test-audio test-integration test-main test-examples test-cpp

# Default target
all: build

# Build C++ components and Python bindings
build:
	@echo "Building Freq-Math..."
	mkdir -p build
	cd build && cmake .. && make
	@echo "Build complete!"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build
	rm -f src/python/freq_math_bindings*.so
	rm -f tests/__pycache__/*.pyc
	rm -rf tests/__pycache__
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	@echo "Clean complete!"

# Install Python dependencies
install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Dependencies installed!"

# Run all tests
test-all:
	@echo "Running all tests..."
	cd tests && python3 run_all_tests.py

# Run specific test categories
test-math:
	@echo "Running math evaluator tests..."
	cd tests && python3 test_math_evaluator_updated.py

test-audio:
	@echo "Running audio synthesizer tests..."
	cd tests && python3 test_audio_synthesizer_updated.py

test-integration:
	@echo "Running integration tests..."
	cd tests && python3 test_integration.py

test-main:
	@echo "Running main entry point tests..."
	cd tests && python3 test_main.py

test-examples:
	@echo "Running example tests..."
	cd tests && python3 test_examples.py

test-cpp:
	@echo "Running C++ binding tests..."
	cd tests && python3 test_equation_parser.py test_math_evaluator_cpp.py test_audio_mapper.py

# Run original tests (for backward compatibility)
test:
	@echo "Running original tests..."
	cd tests && python3 test_math_evaluator.py
	cd tests && python3 test_audio_synthesizer.py

# Run specific test file
test-specific:
	@if [ -z "$(TEST_NAME)" ]; then \
		echo "Usage: make test-specific TEST_NAME=test_name"; \
		exit 1; \
	fi
	@echo "Running specific test: $(TEST_NAME)"
	cd tests && python3 run_all_tests.py $(TEST_NAME)

# Run examples
run-examples:
	@echo "Running example scripts..."
	cd examples && python3 basic_usage.py
	cd .. && python3 demo.py

# Continuous integration target
ci: build test-all
	@echo "CI pipeline completed successfully!"

# Development targets
dev-test: build test-all
	@echo "Development test cycle completed!"

dev-quick: build
	@echo "Running quick tests..."
	cd tests && python3 test_math_evaluator_updated.py -v

# Coverage target (if coverage package is available)
coverage:
	@echo "Running tests with coverage..."
	cd tests && python3 -m coverage run run_all_tests.py && python3 -m coverage report

# Help target
help:
	@echo "Freq-Math Makefile Targets:"
	@echo ""
	@echo "Build targets:"
	@echo "  all          - Build C++ components and Python bindings"
	@echo "  build        - Same as all"
	@echo ""
	@echo "Test targets:"
	@echo "  test-all     - Run all tests"
	@echo "  test         - Run original tests (backward compatibility)"
	@echo "  test-math    - Run math evaluator tests"
	@echo "  test-audio   - Run audio synthesizer tests"
	@echo "  test-integration - Run integration tests"
	@echo "  test-main    - Run main entry point tests"
	@echo "  test-examples - Run example tests"
	@echo "  test-cpp     - Run C++ binding tests"
	@echo "  test-specific TEST_NAME=name - Run specific test"
	@echo ""
	@echo "Utility targets:"
	@echo "  install      - Install Python dependencies"
	@echo "  clean        - Clean build artifacts and cache files"
	@echo "  run-examples - Run example scripts"
	@echo "  ci           - Full CI pipeline (build + test-all)"
	@echo "  dev-test     - Build and run all tests (development)"
	@echo "  dev-quick     - Build and run quick tests (development)"
	@echo "  coverage     - Run tests with coverage report"
	@echo "  help         - Show this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make test-all                    # Run all tests"
	@echo "  make test-specific TEST_NAME=test_math_evaluator_updated  # Run specific test"
	@echo "  make dev-test                    # Build and test (development cycle)"

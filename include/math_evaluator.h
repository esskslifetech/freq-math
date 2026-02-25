#pragma once

#include "equation_parser.h"
#include <vector>
#include <string>
#include "expected.h"
#include <span>

namespace freq_math {

// ============================================================================
// 1. ERROR HANDLING CONTRACTS
// ============================================================================

// Strongly typed evaluation error with contextual messages
struct EvalError {
    std::string message;
};

// ============================================================================
// 2. COMPILED DOMAIN MODEL (Value Semantics, Zero Pointers)
// ============================================================================

// CompiledExpression represents pre-compiled RPN (Reverse Polish Notation) bytecode.
// By compiling once, we can execute the expression millions of times with zero parsing overhead.
class CompiledExpression {
public:
    // Explicit constructor prevents accidental implicit conversions
    explicit CompiledExpression(std::vector<Token> rpn_bytecode) noexcept
        : bytecode_(std::move(rpn_bytecode)) {}

    // C++20 std::span provides a high-performance, bounds-safe view over the bytecode
    [[nodiscard]] std::span<const Token> bytecode() const noexcept { 
        return bytecode_; 
    }

private:
    std::vector<Token> bytecode_;
};

// ============================================================================
// 3. THE COMPILER (Shunting-Yard Algorithm to Bytecode)
// ============================================================================

class MathCompiler {
public:
    // Pure static scope. Cannot be instantiated.
    MathCompiler() = delete;

    // Pure Function: Compiles infix tokens to RPN bytecode.
    // 100% Thread-Safe. Throws no exceptions.
    [[nodiscard("Compilation result must be checked for syntax errors")]] 
    static freq_math::expected<CompiledExpression, EvalError> 
    compile(std::span<const Token> infix_tokens) noexcept;

private:
    // Hardcoded empirical rules for mathematical precedence
    [[nodiscard]] static constexpr int get_precedence(std::string_view op) noexcept {
        if (op == "^" || op == "_neg_") return 3;
        if (op == "*" || op == "/") return 2;
        if (op == "+" || op == "-") return 1;
        return 0;
    }

    [[nodiscard]] static constexpr bool is_right_associative(std::string_view op) noexcept {
        return op == "^" || op == "_neg_";
    }
};

// ============================================================================
// 4. THE VIRTUAL MACHINE (Stateless Evaluator)
// ============================================================================

class MathEvaluator {
public:
    // Pure static scope. No hidden instance state.
    MathEvaluator() = delete;

    // 1. Single Point Execution:
    // 100% Thread-Safe execution of bytecode. 
    // Environment is injected (Isolating side effects).
    [[nodiscard]] static freq_math::expected<double, EvalError> 
    evaluate(const CompiledExpression& expr, 
             double x, 
             const MathEnvironment& env) noexcept;

    // 2. Linear Range Execution:
    // HIGH PERFORMANCE: Evaluates a linear range (start to end).
    // Internally utilizes C++17/23 std::execution::par_unseq to distribute workload across CPU cores.
    [[nodiscard]] static freq_math::expected<std::vector<double>, EvalError> 
    evaluate_range(const CompiledExpression& expr, 
                   double start, double end, size_t steps, 
                   const MathEnvironment& env) noexcept;

    // 3. FUN/USEFUL FEATURE - Arbitrary Batch Execution:
    // Evaluates an arbitrary, non-linear array of X values.
    // Extremely useful for applying an equation to an existing audio buffer or physics dataset.
    [[nodiscard]] static freq_math::expected<std::vector<double>, EvalError> 
    evaluate_batch(const CompiledExpression& expr, 
                   std::span<const double> x_values, 
                   const MathEnvironment& env) noexcept;
};

} // namespace freq_math
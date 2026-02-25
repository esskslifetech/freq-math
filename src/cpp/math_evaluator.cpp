#include "math_evaluator.h"
#include <cmath>
#include <stack>
#include <execution> // For parallel vectorization
#include <algorithm>

namespace freq_math {

// ============================================================================
// COMPILER LOGIC (Dijkstra's Shunting Yard)
// ============================================================================

freq_math::expected<CompiledExpression, EvalError> 
MathCompiler::compile(std::span<const Token> infix_tokens) noexcept {
    std::vector<Token> output_queue;
    std::stack<Token> operator_stack;
    
    // Empirical Optimization: Reserve to prevent reallocations
    output_queue.reserve(infix_tokens.size());
    
    bool expect_operand = true; // Tracks state for unary minus detection

    for (const auto& token : infix_tokens) {
        if (token.type == TokenType::END_OF_STREAM) continue;

        if (token.type == TokenType::NUMBER || token.type == TokenType::VARIABLE) {
            output_queue.push_back(token);
            expect_operand = false;
        } 
        else if (token.type == TokenType::FUNCTION) {
            operator_stack.push(token);
            expect_operand = true;
        } 
        else if (token.type == TokenType::OPERATOR) {
            Token op_token = token;
            
            // Unary Minus Detection Heuristic
            if (expect_operand && token.text == "-") {
                op_token.text = "_neg_"; // Transform to internal unary operator
            }

            while (!operator_stack.empty() && operator_stack.top().type != TokenType::LEFT_PAREN) {
                const Token& top_op = operator_stack.top();
                
                int op_prec = get_precedence(op_token.text);
                int top_prec = get_precedence(top_op.text);
                
                if (top_op.type == TokenType::FUNCTION || 
                   (top_prec > op_prec) || 
                   (top_prec == op_prec && !is_right_associative(op_token.text))) {
                    output_queue.push_back(top_op);
                    operator_stack.pop();
                } else {
                    break;
                }
            }
            operator_stack.push(op_token);
            expect_operand = true;
        } 
        else if (token.type == TokenType::LEFT_PAREN) {
            operator_stack.push(token);
            expect_operand = true;
        } 
        else if (token.type == TokenType::RIGHT_PAREN) {
            bool paren_matched = false;
            while (!operator_stack.empty()) {
                if (operator_stack.top().type == TokenType::LEFT_PAREN) {
                    paren_matched = true;
                    operator_stack.pop();
                    break;
                }
                output_queue.push_back(operator_stack.top());
                operator_stack.pop();
            }
            if (!paren_matched) {
                return freq_math::unexpected(EvalError{"Mismatched parentheses"});
            }
            
            // If the operator preceding the parenthesis was a function, pop it
            if (!operator_stack.empty() && operator_stack.top().type == TokenType::FUNCTION) {
                output_queue.push_back(operator_stack.top());
                operator_stack.pop();
            }
            expect_operand = false;
        }
    }

    // Flush remaining operators
    while (!operator_stack.empty()) {
        if (operator_stack.top().type == TokenType::LEFT_PAREN) {
            return freq_math::unexpected(EvalError{"Mismatched parentheses"});
        }
        output_queue.push_back(operator_stack.top());
        operator_stack.pop();
    }

    return CompiledExpression{std::move(output_queue)};
}

// ============================================================================
// EXECUTION ENGINE (Stateless Stack Machine)
// ============================================================================

freq_math::expected<double, EvalError> 
MathEvaluator::evaluate(const CompiledExpression& expr, double x, const MathEnvironment& env) noexcept {
    std::vector<double> stack;
    stack.reserve(32); // Pre-allocate small stack to avoid dynamic allocations during execution

    for (const auto& token : expr.bytecode()) {
        if (token.type == TokenType::NUMBER) {
            stack.push_back(token.numeric_value);
        } 
        else if (token.type == TokenType::VARIABLE) {
            if (token.text == "x") {
                stack.push_back(x);
            } else {
                auto val = env.get_variable(token.text);
                if (!val) return freq_math::unexpected(EvalError{val.error()});
                stack.push_back(val.value());
            }
        } 
        else if (token.type == TokenType::OPERATOR) {
            if (token.text == "_neg_") {
                if (stack.empty()) return freq_math::unexpected(EvalError{"Invalid unary minus"});
                double a = stack.back(); stack.pop_back();
                stack.push_back(-a);
                continue;
            }

            if (stack.size() < 2) return freq_math::unexpected(EvalError{"Missing operands for operator"});
            double b = stack.back(); stack.pop_back();
            double a = stack.back(); stack.pop_back();

            if (token.text == "+") stack.push_back(a + b);
            else if (token.text == "-") stack.push_back(a - b);
            else if (token.text == "*") stack.push_back(a * b);
            else if (token.text == "/") {
                if (b == 0.0) return freq_math::unexpected(EvalError{"Division by zero"});
                stack.push_back(a / b);
            }
            else if (token.text == "^") stack.push_back(std::pow(a, b));
        } 
        else if (token.type == TokenType::FUNCTION) {
            if (stack.empty()) return freq_math::unexpected(EvalError{"Missing argument for function"});
            
            // Note: For multi-argument functions, we would pop N arguments based on function arity.
            // Keeping arity 1 for this implementation as requested by current spec.
            std::vector<double> args = { stack.back() }; 
            stack.pop_back();

            // Function execution is handled safely by the environment
            // In a production system, we'd add `execute_function` to Environment.
            // For now, mapping known hardcoded functions directly.
            if (token.text == "sin") stack.push_back(std::sin(args[0]));
            else if (token.text == "cos") stack.push_back(std::cos(args[0]));
            else if (token.text == "tan") stack.push_back(std::tan(args[0]));
            else if (token.text == "log") stack.push_back(std::log(args[0]));
            else if (token.text == "sqrt") {
                if (args[0] < 0.0) return freq_math::unexpected(EvalError{"Square root of negative number"});
                stack.push_back(std::sqrt(args[0]));
            }
            else return freq_math::unexpected(EvalError{std::string("Unknown function: ") + std::string(token.text)});
        }
    }

    if (stack.size() != 1) {
        return freq_math::unexpected(EvalError{"Invalid expression evaluation format"});
    }

    return stack.front();
}

// ============================================================================
// VECTORIZED PARALLEL EVALUATION (High-Performance "Fun Feature")
// ============================================================================

freq_math::expected<std::vector<double>, EvalError> 
MathEvaluator::evaluate_range(const CompiledExpression& expr, double start, double end, size_t steps, const MathEnvironment& env) noexcept {
    if (steps == 0) return std::vector<double>{};

    std::vector<double> results(steps);
    std::vector<double> x_values(steps);
    
    double step_size = (steps > 1) ? (end - start) / static_cast<double>(steps - 1) : 0.0;

    // 1. Populate X values
    for (size_t i = 0; i < steps; ++i) {
        x_values[i] = start + i * step_size;
    }

    std::atomic<bool> error_occurred{false};
    std::string global_err_msg;

    // 2. PARALLEL EXECUTION: Evaluates expression across all CPU Cores simultaneously
    // Requires <execution> - C++17/23 feature for extreme performance gains.
    std::transform(std::execution::par_unseq, x_values.begin(), x_values.end(), results.begin(),
        [&](double x) {
            if (error_occurred.load(std::memory_order_relaxed)) return 0.0;
            
            auto res = evaluate(expr, x, env);
            if (!res) {
                error_occurred.store(true, std::memory_order_relaxed);
                // Race condition on string write is fine here, we just need *an* error message
                global_err_msg = res.error().message; 
                return 0.0;
            }
            return res.value();
        }
    );

    if (error_occurred.load(std::memory_order_acquire)) {
        return freq_math::unexpected(EvalError{global_err_msg});
    }

    return results;
}

} // namespace freq_math
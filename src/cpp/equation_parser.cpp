#include "equation_parser.h"
#include <cctype>
#include <charconv>
#include <cmath>
#include <mutex>

namespace freq_math {

// ============================================================================
// ENVIRONMENT IMPLEMENTATION (Concurrency & Softcoding)
// ============================================================================

MathEnvironment::MathEnvironment() {
    // Hardcoded empirical constants (Soft-coded registration)
    set_variable("pi", std::numbers::pi);
    set_variable("e",  std::numbers::e);

    // Dynamic Function Registration
    register_function("sin",  1, [](const auto& args) { return std::sin(args[0]); });
    register_function("cos",  1, [](const auto& args) { return std::cos(args[0]); });
    register_function("tan",  1, [](const auto& args) { return std::tan(args[0]); });
    register_function("sqrt", 1, [](const auto& args) { return std::sqrt(args[0]); });
    register_function("abs",  1, [](const auto& args) { return std::abs(args[0]); });
    
    // Fun Feature: Multi-arity support (e.g., min, max)
    register_function("max",  2, [](const auto& args) { return std::max(args[0], args[1]); });
}

void MathEnvironment::set_variable(std::string_view name, double value) {
    std::unique_lock lock(rw_mutex_); // Write lock
    variables_[std::string(name)] = value;
}

freq_math::expected<double, std::string> MathEnvironment::get_variable(std::string_view name) const {
    std::shared_lock lock(rw_mutex_); // Concurrent Read lock
    auto it = variables_.find(std::string(name));
    if (it != variables_.end()) {
        return it->second;
    }
    return freq_math::unexpected("Undefined variable: " + std::string(name));
}

void MathEnvironment::register_function(std::string_view name, size_t arity, MathFunction func) {
    std::unique_lock lock(rw_mutex_);
    functions_[std::string(name)] = FuncDescriptor{arity, std::move(func)};
}

bool MathEnvironment::is_function(std::string_view name) const {
    std::shared_lock lock(rw_mutex_);
    return functions_.contains(std::string(name));
}

// ============================================================================
// PARSER IMPLEMENTATION (Stateless, Zero-Allocation Lexing)
// ============================================================================

freq_math::expected<std::vector<Token>, ParseError> 
EquationParser::parse(std::string_view equation, const MathEnvironment& env) noexcept {
    std::vector<Token> tokens;
    // Pre-allocate to prevent vector reallocations (empirical performance optimization)
    tokens.reserve(equation.length() / 2); 
    
    size_t pos = 0;
    TokenType last_token_type = TokenType::END_OF_STREAM; // For implicit multiplication

    while (pos < equation.length()) {
        char c = equation[pos];

        // 1. Skip Whitespace
        if (std::isspace(static_cast<unsigned char>(c))) {
            pos++;
            continue;
        }

        // 2. Numbers (High-performance std::from_chars)
        if (std::isdigit(static_cast<unsigned char>(c)) || c == '.') {
            size_t start_pos = pos;
            
            // Advance to end of number boundaries
            while (pos < equation.length() && 
                  (std::isdigit(static_cast<unsigned char>(equation[pos])) || equation[pos] == '.' || equation[pos] == 'e' || equation[pos] == 'E')) {
                pos++;
            }

            std::string_view num_str = equation.substr(start_pos, pos - start_pos);
            double value = 0.0;
            
            // C++17/23 Fast non-throwing conversion
            auto [ptr, ec] = std::from_chars(num_str.data(), num_str.data() + num_str.length(), value);
            
            if (ec != std::errc()) {
                return freq_math::unexpected(ParseError{{1, static_cast<uint32_t>(start_pos), 1}, "Invalid numeric format"});
            }

            tokens.push_back(Token{TokenType::NUMBER, num_str, value});
            last_token_type = TokenType::NUMBER;
            continue;
        }

        // 3. Identifiers (Variables / Functions)
        if (is_identifier_start(c)) {
            size_t start_pos = pos;
            while (pos < equation.length() && is_identifier_part(equation[pos])) {
                pos++;
            }

            std::string_view identifier = equation.substr(start_pos, pos - start_pos);

            // FUN FEATURE: Implicit Multiplication check (e.g., "2x" -> "2 * x")
            if (last_token_type == TokenType::NUMBER) {
                tokens.push_back(Token{TokenType::OPERATOR, "*", 0.0});
            }

            TokenType type = env.is_function(identifier) ? TokenType::FUNCTION : TokenType::VARIABLE;
            tokens.push_back(Token{type, identifier, 0.0});
            last_token_type = type;
            continue;
        }

        // 4. Operators
        if (is_operator(c)) {
            tokens.push_back(Token{TokenType::OPERATOR, equation.substr(pos, 1), 0.0});
            last_token_type = TokenType::OPERATOR;
            pos++;
            continue;
        }

        // 5. Parentheses
        if (c == '(') {
            // Implicit Multiplication: e.g., "2(x)" -> "2 * (x)"
            if (last_token_type == TokenType::NUMBER || last_token_type == TokenType::VARIABLE || last_token_type == TokenType::RIGHT_PAREN) {
                tokens.push_back(Token{TokenType::OPERATOR, "*", 0.0});
            }
            tokens.push_back(Token{TokenType::LEFT_PAREN, equation.substr(pos, 1), 0.0});
            last_token_type = TokenType::LEFT_PAREN;
            pos++;
            continue;
        }

        if (c == ')') {
            tokens.push_back(Token{TokenType::RIGHT_PAREN, equation.substr(pos, 1), 0.0});
            last_token_type = TokenType::RIGHT_PAREN;
            pos++;
            continue;
        }

        // 6. Unknown Character
        return freq_math::unexpected(ParseError{{1, static_cast<uint32_t>(pos), 1}, std::string("Unexpected character: ") + c});
    }

    tokens.push_back(Token{TokenType::END_OF_STREAM, "", 0.0});
    return tokens;
}

} // namespace freq_math
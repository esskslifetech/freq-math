#pragma once

#include <string_view>
#include <vector>
#include "expected.h"
#include <string>
#include <unordered_map>
#include <shared_mutex>
#include <functional>
#include <cstdint>

namespace freq_math {

// ============================================================================
// 1. DOMAIN MODELS (Highly Optimized, Cache-Friendly)
// ============================================================================

// Explicit underlying type for predictable memory layout
enum class TokenType : uint8_t {
    NUMBER,
    VARIABLE,
    OPERATOR,
    FUNCTION,
    LEFT_PAREN,
    RIGHT_PAREN,
    END_OF_STREAM
};

// Fun/Useful Feature: IDE-grade source tracking for pinpoint error reporting
struct SourceLocation {
    uint32_t line{1};
    uint32_t column{1};
    uint32_t length{0};
};

// The Token contains NO heap allocations (std::string removed).
// Passed by value effortlessly.
struct Token {
    TokenType type;
    std::string_view text;      // O(1) string referencing
    double numeric_value{0.0};  // Only populated if type == NUMBER
    SourceLocation location{};

    // Helper for downstream compiler logic
    [[nodiscard]] constexpr bool is_operator() const noexcept {
        return type == TokenType::OPERATOR;
    }
};

// Strongly typed error yielding exact location and human-readable message
struct ParseError {
    SourceLocation location;
    std::string message;
};

// ============================================================================
// 2. ISOLATED SIDE EFFECTS (The Environment)
// ============================================================================

// Function signature definition (Soft-coding function logic)
using MathFunction = std::function<double(const std::vector<double>&)>;

// MathEnvironment strictly decouples variables/functions from the Lexer.
// Built for Highest Concurrency Safety (Readers-Writer Locks).
class MathEnvironment {
public:
    MathEnvironment();

    // Mutators (Write Locks)
    void set_variable(std::string_view name, double value);
    void register_function(std::string_view name, size_t arity, MathFunction func);

    // Accessors (Concurrent Read Locks)
    [[nodiscard]] freq_math::expected<double, std::string> get_variable(std::string_view name) const;
    [[nodiscard]] bool is_function(std::string_view name) const;

private:
    mutable std::shared_mutex rw_mutex_; // Beyond in-memory safety mapping
    std::unordered_map<std::string, double> variables_;
    
    struct FuncDescriptor {
        size_t arity;
        MathFunction impl;
    };
    std::unordered_map<std::string, FuncDescriptor> functions_;
};

// ============================================================================
// 3. THE LEXICAL ANALYZER (100% Stateless & Pure)
// ============================================================================

class EquationParser {
public:
    // Deleted constructors enforce that this class cannot be instantiated.
    // It is a pure namespace-like scope for static lexical operations.
    EquationParser() = delete;

    // Pure function: Compiles a string into tokens.
    // Requires the environment ONLY to distinguish Variables from Functions.
    // Throws NO exceptions. 100% Thread-Safe.
    [[nodiscard("Always check parsing results for syntax errors")]] 
    static freq_math::expected<std::vector<Token>, ParseError> 
    parse(std::string_view equation, const MathEnvironment& env) noexcept;

private:
    // Isolated logic gates (Hardcoded lexical rules)
    [[nodiscard]] static constexpr bool is_operator(char c) noexcept {
        return c == '+' || c == '-' || c == '*' || c == '/' || c == '^';
    }

    [[nodiscard]] static constexpr bool is_identifier_start(char c) noexcept {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
    }

    [[nodiscard]] static constexpr bool is_identifier_part(char c) noexcept {
        return is_identifier_start(c) || (c >= '0' && c <= '9');
    }
};

} // namespace freq_math
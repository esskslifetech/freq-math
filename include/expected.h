#pragma once

#include <variant>
#include <string>
#include <vector>

namespace freq_math {

template<typename E>
class unexpected {
private:
    E value_;
public:
    unexpected(E&& value) : value_(std::move(value)) {}
    unexpected(const E& value) : value_(value) {}
    
    const E& value() const { return value_; }
    E& value() { return value_; }
};

template<typename T, typename E>
class expected {
private:
    std::variant<T, E> value_;

public:
    expected(T&& value) : value_(std::move(value)) {}
    expected(const T& value) : value_(value) {}
    expected(unexpected<E>&& error) : value_(std::move(error.value())) {}
    expected(const unexpected<E>& error) : value_(error.value()) {}
    
    bool has_value() const { return std::holds_alternative<T>(value_); }
    explicit operator bool() const { return has_value(); }
    
    T& value() { return std::get<T>(value_); }
    const T& value() const { return std::get<T>(value_); }
    
    E& error() { return std::get<E>(value_); }
    const E& error() const { return std::get<E>(value_); }
    
    T& operator*() { return value(); }
    const T& operator*() const { return value(); }
    
    T* operator->() { return &value(); }
    const T* operator->() const { return &value(); }
};

} // namespace freq_math


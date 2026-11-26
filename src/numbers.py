"""Точные числа в виде целого коэффициента и степени десяти."""

from dataclasses import dataclass
from decimal import (
    MAX_EMAX, MIN_EMIN, Context, Decimal, DecimalException, DivisionByZero,
    Inexact, InvalidOperation, Overflow,
)

from lark import Token

from .errors import located_error


@dataclass(frozen=True)
class Number:
    """Целый коэффициент без конечных нулей и произвольный показатель."""

    coefficient: Decimal
    power: int

    def leading_power(self) -> int:
        """Вернуть степень первого разряда ненулевого числа."""
        return self.power + self.coefficient.adjusted()


ZERO = Number(Decimal(0), 0)


def normalized(value: Decimal, power: int = 0) -> Number:
    """Перенести десятичный сдвиг и конечные нули в показатель."""
    if not value:
        return ZERO
    sign, digits, shift = value.as_tuple()
    end = len(digits)
    while not digits[end - 1]:
        end -= 1
    coefficient = Decimal((sign, digits[:end], 0))
    return Number(coefficient, power + shift + len(digits) - end)


def read_power(text: str) -> int:
    """Прочитать показатель произвольной длины в пределах объёма ввода."""
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return int(Decimal(text))


def read_number(token: Token) -> Number:
    """Разобрать мантиссу и показатель независимо друг от друга."""
    mantissa, _, power = token.lower().partition("e")
    value = Decimal(mantissa)
    return normalized(value, read_power(power)) if value else ZERO


def align(left: Number, right: Number) -> tuple[Context, Decimal, Decimal, int]:
    """Выровнять коэффициенты для точной операции Decimal."""
    power = min(left.power, right.power)
    high = max(left.leading_power(), right.leading_power())
    precision = high - power + 2
    context = Context(
        prec=precision, Emin=MIN_EMIN, Emax=MAX_EMAX,
        traps=[Inexact, InvalidOperation, Overflow, DivisionByZero],
    )
    first = context.scaleb(left.coefficient, left.power - power)
    second = context.scaleb(right.coefficient, right.power - power)
    return context, first, second, power


def add(left: Number, right: Number) -> Number:
    """Сложить числа, сохранив все десятичные разряды результата."""
    if not left.coefficient:
        return right
    if not right.coefficient:
        return left
    context, first, second, power = align(left, right)
    return normalized(context.add(first, second), power)


def subtract(left: Number, right: Number) -> Number:
    """Вычесть правый операнд через точное сложение."""
    if not right.coefficient:
        return left
    return add(left, Number(right.coefficient.copy_negate(), right.power))


def power_remainder(left: Number, right: Number) -> Number:
    """Вычислить остаток от масштабирования без разворачивания степени."""
    dividend = int(left.coefficient)
    divisor = int(right.coefficient)
    factor = pow(10, left.power - right.power, abs(divisor))
    remainder = ((dividend % divisor) * factor) % divisor
    return normalized(Decimal(remainder), right.power)


def modulo(left: Number, right: Number) -> Number:
    """Вычислить остаток со знаком делителя."""
    if not left.coefficient:
        return ZERO
    if left.power > right.power:
        return power_remainder(left, right)
    if left.leading_power() < right.leading_power():
        negative = left.coefficient.is_signed()
        same_sign = negative == right.coefficient.is_signed()
        return left if same_sign else add(left, right)
    context, first, second, power = align(left, right)
    remainder = context.remainder(first, second)
    if remainder and remainder.is_signed() != second.is_signed():
        remainder = context.add(remainder, second)
    return normalized(remainder, power)


OPERATIONS = {"+": add, "-": subtract, "mod": modulo}


def calculate(token: Token, left: object, right: object) -> Number:
    """Применить двоичную операцию или сообщить об ошибке вычисления."""
    try:
        operation = OPERATIONS[token]
    except KeyError:
        message = f"неизвестная операция {str(token)!r}. Доступны +, - и mod"
        raise located_error(message, token.line, token.column) from None
    if not isinstance(left, Number) or not isinstance(right, Number):
        message = f"операция {str(token)!r} принимает два числа"
        raise located_error(message, token.line, token.column)
    if token == "mod" and not right.coefficient:
        raise located_error("остаток от деления на ноль",
                            token.line, token.column)
    try:
        return operation(left, right)
    except (DecimalException, OverflowError, ValueError):
        message = "точное вычисление выходит за возможности Decimal"
        raise located_error(message, token.line, token.column) from None

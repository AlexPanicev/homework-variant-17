"""Точная десятичная арифметика учебного языка."""

from decimal import (
    Context, Decimal, DecimalException, DivisionByZero, Inexact,
    InvalidOperation, Overflow,
)
from operator import add, sub

from lark import Token

from .errors import located_error


MAX_POWER = 4096
CALCULATION_CONTEXT = Context(
    prec=2 * MAX_POWER + 2,
    Emin=-MAX_POWER,
    Emax=MAX_POWER + 1,
    traps=[DivisionByZero, Inexact, InvalidOperation, Overflow],
)
RANGE_ERROR = f"число выходит за диапазон десятичных разрядов ±{MAX_POWER}"


def modulo(left: Decimal, right: Decimal) -> Decimal:
    """Вернуть остаток со знаком делителя при округлении частного вниз."""
    remainder = left % right
    if remainder and remainder.is_signed() != right.is_signed():
        return remainder + right
    return remainder


OPERATIONS = {"+": add, "-": sub, "mod": modulo}


def normalize(value: Decimal) -> Decimal:
    """Удалить незначащие нули и проверить разряды ненулевого числа."""
    number = value.normalize()
    if not number:
        return Decimal(0)
    if number.adjusted() > MAX_POWER or number.as_tuple().exponent < -MAX_POWER:
        raise InvalidOperation
    return number


def read_number(token: Token) -> Decimal:
    """Преобразовать целый операнд или число с экспонентой без округления."""
    try:
        return normalize(Decimal(token))
    except DecimalException:
        mantissa, _, _ = token.lower().partition("e")
        if not any(char.isdecimal() and int(char) for char in mantissa):
            return Decimal(0)
        raise located_error(RANGE_ERROR, token.line, token.column) from None


def calculate(token: Token, left: object, right: object) -> Decimal:
    """Применить двоичную операцию или сообщить об ошибке вычисления."""
    try:
        operation = OPERATIONS[token]
    except KeyError:
        message = f"неизвестная операция {str(token)!r}. Доступны +, - и mod"
        raise located_error(message, token.line, token.column) from None
    if not isinstance(left, Decimal) or not isinstance(right, Decimal):
        message = f"операция {str(token)!r} принимает два числа"
        raise located_error(message, token.line, token.column)
    if token == "mod" and not right:
        raise located_error("остаток от деления на ноль",
                            token.line, token.column)
    try:
        return normalize(operation(left, right))
    except DecimalException:
        raise located_error(RANGE_ERROR, token.line, token.column) from None

"""Синтаксический разбор Lark и сообщения об ошибках ввода."""

from functools import cache
from pathlib import Path

from lark import Lark, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedToken

from .errors import ConfigError, located_error


EXPECTED_TOKENS = {
    "$END": "конец ввода",
    "INTEGER": "целое число",
    "NAME": "имя",
    "NUMBER": "число с экспонентой",
    "SYMBOL_OP": "`+` или `-`",
    "_ARRAY_OPEN": "`<<`",
    "_ARRAY_CLOSE": "`>>`",
    "_ARROW": "`=>`",
    "_ASSIGN": "`:=`",
    "_COMMA": "`,`",
    "_DEF": "`def`",
    "_EXPR_OPEN": "`!(`",
    "_MAP_OPEN": "`{`",
    "_MAP_CLOSE": "`}`",
    "_PAREN_OPEN": "`(`",
    "_PAREN_CLOSE": "`)`",
    "_SEMICOLON": "`;`",
}
PREVIEW_LENGTH = 32


@cache
def grammar() -> Lark:
    """Загрузить грамматику один раз для всех разборов в процессе."""
    path = Path(__file__).with_name("grammar.lark")
    return Lark(
        path.read_text(encoding="utf-8"),
        start="document",
        parser="lalr",
        lexer="contextual",
        propagate_positions=True,
        maybe_placeholders=False,
    )


def parse(source: str) -> Tree:
    """Вернуть дерево разбора или сообщить о месте синтаксической ошибки."""
    source = source.removeprefix("\ufeff").replace("\r\n", "\n")
    source = source.replace("\r", "\n")
    try:
        return grammar().parse(source)
    except UnexpectedToken as error:
        raise token_error(source, error) from None
    except UnexpectedCharacters as error:
        raise character_error(source, error) from None


def expected_message(terminals: set[str]) -> str:
    """Преобразовать имена терминалов Lark в подсказку о синтаксисе."""
    labels = sorted(EXPECTED_TOKENS.get(name, name) for name in terminals)
    return ". Ожидалось: " + ", ".join(labels) if labels else ""


def token_error(source: str, error: UnexpectedToken) -> ConfigError:
    """Сформировать сообщение о неожиданной лексеме или конце ввода."""
    expected = expected_message(error.accepts or error.expected)
    if error.token.type == "$END":
        line = source.count("\n") + 1
        column = len(source) - source.rfind("\n")
        return located_error("неожиданный конец ввода" + expected,
                             line, column)
    excerpt = error.token[:PREVIEW_LENGTH]
    message = f"неожиданная лексема {excerpt!r}" + expected
    return located_error(message, error.line, error.column)


def character_error(source: str, error: UnexpectedCharacters) -> ConfigError:
    """Отличить незакрытый комментарий от прочих ошибок лексики."""
    index = error.pos_in_stream
    if source.startswith("%{", index):
        message = "многострочный комментарий должен заканчиваться на %}"
    else:
        expected = expected_message(error.allowed or set())
        message = f"недопустимый символ {source[index]!r}" + expected
    return located_error(message, error.line, error.column)

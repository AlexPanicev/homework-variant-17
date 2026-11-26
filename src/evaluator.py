"""Вычисление констант и построение значения из дерева Lark."""

from dataclasses import dataclass
from decimal import Decimal

from lark import Token, v_args
from lark.tree import Meta
from lark.visitors import Transformer_NonRecursive

from .errors import located_error
from .numbers import calculate, read_number


MAX_CONTAINER_DEPTH = 64
type Data = Decimal | list[Data] | dict[str, Data]


@dataclass(frozen=True)
class Value:
    """Готовое значение и глубина вложенных в него контейнеров."""

    data: Data
    depth: int = 0


def container(meta: Meta, data: Data, depth: int) -> Value:
    """Проверить глубину перед передачей структуры в сериализатор YAML."""
    if depth > MAX_CONTAINER_DEPTH:
        message = f"глубина коллекций превышает {MAX_CONTAINER_DEPTH}"
        raise located_error(message, meta.line, meta.column)
    return Value(data, depth)


class Evaluator(Transformer_NonRecursive):
    """Обойти дерево в порядке исходного текста, начиная с дочерних узлов."""

    def __init__(self):
        """Создать таблицу объявлений для одного документа."""
        super().__init__()
        self.constants: dict[str, Value] = {}

    def document(self, children):
        """Вернуть данные единственного корневого значения."""
        return children[-1].data

    @v_args(inline=True)
    def definition(self, name: Token, value: Value) -> None:
        """Сохранить вычисленное значение под новым именем."""
        if name in self.constants:
            message = f"константа {str(name)!r} уже объявлена"
            raise located_error(message, name.line, name.column)
        self.constants[str(name)] = value

    @v_args(inline=True)
    def expression(self, value: Value) -> Value:
        """Вернуть значение тела префиксного выражения."""
        return value

    @v_args(inline=True)
    def reference(self, name: Token) -> Value:
        """Найти значение ранее объявленной константы."""
        try:
            return self.constants[name]
        except KeyError:
            message = f"константа {str(name)!r} ещё не объявлена"
            raise located_error(message, name.line, name.column) from None

    @v_args(inline=True)
    def number(self, token: Token) -> Value:
        """Преобразовать числовую лексему в десятичное значение."""
        return Value(read_number(token))

    @v_args(inline=True)
    def arithmetic(self, op: Token, left: Value, right: Value) -> Value:
        """Вычислить сложение, вычитание или остаток."""
        return Value(calculate(op, left.data, right.data))

    @v_args(meta=True)
    def array(self, meta: Meta, members: list[Value]) -> Value:
        """Собрать элементы массива и проверить глубину."""
        depth = max((item.depth for item in members), default=0) + 1
        return container(meta, [item.data for item in members], depth)

    @v_args(inline=True)
    def pair(self, name: Token, value: Value) -> tuple[Token, Value]:
        """Передать ключ вместе с его позицией и значением."""
        return name, value

    @v_args(meta=True)
    def mapping(self, meta: Meta, pairs: list[tuple[Token, Value]]) -> Value:
        """Собрать словарь, отклоняя повторяющиеся ключи."""
        result: dict[str, Data] = {}
        depth = 0
        for key, value in pairs:
            if key in result:
                message = f"ключ {str(key)!r} уже есть в словаре"
                raise located_error(message, key.line, key.column)
            result[str(key)] = value.data
            depth = max(depth, value.depth)
        return container(meta, result, depth + 1)

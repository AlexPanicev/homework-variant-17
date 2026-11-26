"""Вычисление констант и построение значения из дерева Lark."""

from lark import Token, v_args
from lark.visitors import Transformer_NonRecursive

from .errors import located_error
from .numbers import Number, calculate, read_number


type Data = Number | list[Data] | dict[str, Data]


class Evaluator(Transformer_NonRecursive):
    """Обойти дерево в порядке исходного текста, начиная с дочерних узлов."""

    def __init__(self):
        """Создать таблицу объявлений для одного документа."""
        super().__init__()
        self.constants: dict[str, Data] = {}

    def document(self, children):
        """Вернуть данные единственного корневого значения."""
        return children[-1]

    @v_args(inline=True)
    def definition(self, name: Token, value: Data) -> None:
        """Сохранить вычисленное значение под новым именем."""
        if name in self.constants:
            message = f"константа {str(name)!r} уже объявлена"
            raise located_error(message, name.line, name.column)
        self.constants[str(name)] = value

    @v_args(inline=True)
    def expression(self, value: Data) -> Data:
        """Вернуть значение тела префиксного выражения."""
        return value

    @v_args(inline=True)
    def reference(self, name: Token) -> Data:
        """Найти значение ранее объявленной константы."""
        try:
            return self.constants[name]
        except KeyError:
            message = f"константа {str(name)!r} ещё не объявлена"
            raise located_error(message, name.line, name.column) from None

    @v_args(inline=True)
    def number(self, token: Token) -> Number:
        """Преобразовать числовую лексему в десятичное значение."""
        return read_number(token)

    @v_args(inline=True)
    def arithmetic(self, op: Token, left: Data, right: Data) -> Number:
        """Вычислить сложение, вычитание или остаток."""
        return calculate(op, left, right)

    def array(self, members: list[Data]) -> list[Data]:
        """Вернуть вычисленные элементы массива в исходном порядке."""
        return members

    @v_args(inline=True)
    def pair(self, name: Token, value: Data) -> tuple[Token, Data]:
        """Передать ключ вместе с его позицией и значением."""
        return name, value

    def mapping(self, pairs: list[tuple[Token, Data]]) -> dict[str, Data]:
        """Собрать словарь, отклоняя повторяющиеся ключи."""
        result: dict[str, Data] = {}
        for key, value in pairs:
            if key in result:
                message = f"ключ {str(key)!r} уже есть в словаре"
                raise located_error(message, key.line, key.column)
            result[str(key)] = value
        return result

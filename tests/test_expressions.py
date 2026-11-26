"""Тесты объявлений и точного вычисления константных выражений."""

import unittest
from decimal import Decimal, localcontext

import yaml

from src.errors import ConfigError
from src.translator import translate


class ExpressionTests(unittest.TestCase):
    """Проверки функций языка и ошибок вычисления."""

    def test_literal_from_assignment(self):
        """Вычислить образец !(+ имя 1) с целым операндом."""
        source = "def base := 1.25e0; { result => !(+ base 1) }"
        self.assertEqual(yaml.safe_load(translate(source)), {"result": 2.25})

    def test_add_and_subtract_exactly(self):
        """Сохранить десятичную точность и порядок операндов."""
        source = "<< !(+ 1e-1 2e-1), !(- -1.5e0 0.25e0), !(- 1 +3) >>"
        output = translate(source)
        self.assertIn("3.0e-1", output)
        self.assertEqual(yaml.safe_load(output), [0.3, -1.75, -2])

    def test_nested_arithmetic_and_declarations(self):
        """Вычислить оба вида вложенных групп и значение новой константы."""
        source = "def a := !(+ 2 (- 20 3)); def b := !(mod a 3);"
        source += "!(+ !(- a b) !(mod 7 4))"
        self.assertEqual(yaml.safe_load(translate(source)), 21)

    def test_modulo_with_all_signs_and_fractions(self):
        """Проверить знак делителя и нулевой остаток."""
        cases = {
            "5 3": 2, "-5 3": 1, "5 -3": -1, "-5 -3": -2,
            "5.75e0 1.5e0": 1.25, "-5.75e0 1.5e0": 0.25,
            "0 -3": 0, "-6 3": 0,
        }
        for operands, expected in cases.items():
            with self.subTest(operands=operands):
                result = yaml.safe_load(translate(f"!(mod {operands})"))
                self.assertEqual(result, expected)

    def test_lexical_keywords_can_be_identifiers(self):
        """Различить имя def, имя mod и операции по их позиции."""
        source = "def def := 1e0; def mod := 3e0; {def => !(mod mod def)}"
        self.assertEqual(yaml.safe_load(translate(source)), {"def": 0})
        self.assertEqual(yaml.safe_load(translate("def mod := 3e0; !(mod)")),
                         3)

    def test_collection_constants_and_aliases(self):
        """Подставить массив и словарь целиком и сохранить общие ссылки."""
        source = (
            "def items := <<1e0, 2e0>>; def config := {list => !(items)};"
            "{outer => !(config), also => !(items)}"
        )
        result = yaml.safe_load(translate(source))
        self.assertEqual(result, {"outer": {"list": [1, 2]}, "also": [1, 2]})
        self.assertIs(result["outer"]["list"], result["also"])

    def test_declarations_not_in_output(self):
        """Вернуть корень без объявлений и сбросить контекст между вызовами."""
        self.assertEqual(yaml.safe_load(translate("def a := 1e0; {}")), {})
        with self.assertRaisesRegex(ConfigError, "ещё не объявлена"):
            translate("!(a)")

    def test_invalid_declaration_syntax(self):
        """Отклонить неверные знаки, пропуски и объявления внутри корня."""
        cases = (
            "def a = 1e0; {}", "def a := 1e0 {}", "def a := ; {}",
            "def a := 1e0;", "def a1 := 1e0; {}", "{} def a := 1e0;",
            "defa := 1e0; {}", "{a=> def b := 1e0;}",
        )
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ConfigError):
                translate(text)

    def test_unknown_forward_and_self_references(self):
        """Доступны только объявления, обработанные ранее."""
        cases = (
            "!(+ a 1)", "def a := !(b); def b := 1e0; {}", "def a := !(a); {}"
        )
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ConfigError, "ещё не объявлена"):
                    translate(text)

    def test_duplicate_constant_position(self):
        """Указать имя повторно объявленной константы."""
        source = "def a := 1e0;\ndef a := 2e0;\n{}"
        with self.assertRaisesRegex(ConfigError, r"строка 2, столбец 5.*уже"):
            translate(source)

    def test_invalid_operations_or_arity(self):
        """Отклонить неизвестный оператор, лишние и недостающие операнды."""
        cases = (
            "!()", "!(+)", "!(+ 1)", "!(- 1 2 3)", "!(mod 1)",
            "!(mod 1 2 3)", "!(mul 1 2)", "!(* 1 2)",
            "!(mod(1, 2))", "!(+ 1, 2)", "!(+ 1 2", "!(+ 1.0 2)",
        )
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ConfigError):
                translate(text)

    def test_undefined_operator_message(self):
        """Назвать неизвестную операцию и её позицию."""
        with self.assertRaisesRegex(ConfigError, r"столбец 3.*операция 'mul'"):
            translate("!(mul 1 2)")

    def test_modulo_by_zero(self):
        """Проверить ноль в литерале и вычисленном делителе."""
        for right in ("0", "-0e5", "(- 2 2)"):
            with self.subTest(right=right):
                with self.assertRaisesRegex(ConfigError, "деления на ноль"):
                    translate(f"!(mod 1 {right})")

    def test_reject_collection_operands(self):
        """Проверить типы операндов для каждой арифметической операции."""
        for declaration in ("{}", "<<>>"):
            for op in ("+", "-", "mod"):
                with self.subTest(declaration=declaration, op=op):
                    with self.assertRaisesRegex(ConfigError, "два числа"):
                        translate(f"def a := {declaration}; !({op} 1 a)")

    def test_no_rounding_in_wide_result(self):
        """Удержать все разряды при вычитании на краях диапазона."""
        with localcontext() as outer_context:
            outer_context.prec = 2
            output = translate("!(- 1e4097 1e-4097)")
        number = Decimal(output.splitlines()[0])
        self.assertEqual(number.as_tuple().digits, (9,) * 8194)
        self.assertEqual(number.as_tuple().exponent, -4097)

    def test_addition_beyond_previous_power_boundary(self):
        """Сохранить лишний старший разряд при сложении."""
        output = translate("!(+ 9e4096 9e4096)")
        self.assertEqual(yaml.safe_load(output), 18 * 10 ** 4096)

    def test_very_large_powers_cancel_exactly(self):
        """Вычислить ноль для равных чисел за диапазоном Decimal."""
        power = "2" * 40
        output = translate(f"!(- 1.5e{power} 1.5e{power})")
        self.assertEqual(output.splitlines()[0], "0")
        self.assertEqual(translate("!(- 0 0)").splitlines()[0], "0")
        self.assertEqual(yaml.safe_load(output), 0)

    def test_modulo_with_very_large_power(self):
        """Вычислить остаток без разворачивания огромного делимого."""
        output = translate("<<!(mod -1e100000000 3), !(mod 1e100000000 -3)>>")
        self.assertEqual(yaml.safe_load(output), [2, -2])

    def test_wide_intermediate_result_cancels_exactly(self):
        """Сохранить единицу после операции с 5 000 001 разрядом."""
        output = translate("!(- !(+ 1e5000000 1) 1e5000000)")
        self.assertEqual(yaml.safe_load(output), 1)

    def test_precision_outside_decimal_capabilities_is_reported(self):
        """Сообщить о невозможной для Decimal длине коэффициента."""
        power = "9" * 30
        with self.assertRaisesRegex(ConfigError, "возможности Decimal"):
            translate(f"!(+ 1e{power} 1)")

    def test_deep_collection_constant_keeps_aliases(self):
        """Подставить глубокую коллекцию в два поля как общее значение."""
        depth = 65
        nested = "<<" * depth + "0e0" + ">>" * depth
        source = f"def deep := {nested}; {{left => !(deep), right => !(deep)}}"
        result = yaml.safe_load(translate(source))
        self.assertIs(result["left"], result["right"])
        value = result["left"]
        for _ in range(depth):
            value, = value
        self.assertEqual(value, 0)

    def test_deep_arithmetic_uses_no_python_recursion(self):
        """Вычислить цепочку вложенных выражений глубже лимита Python."""
        depth = 2000
        source = "!(+ " * depth + "0" + " 1)" * depth
        self.assertEqual(yaml.safe_load(translate(source)), depth)

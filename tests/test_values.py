"""Тесты чисел, комментариев, коллекций и их представления в YAML."""

import unittest
from decimal import Decimal

import yaml

from src.errors import ConfigError
from src.translator import translate


class ValueTests(unittest.TestCase):
    """Проверки преобразования всех типов и границ грамматики."""

    def test_exponent_literals(self):
        """Прочитать все формы знака, мантиссы и экспоненты."""
        cases = {
            "008e0": 8,
            "+13.5e-1": 1.35,
            "-1.0E+2": -100,
            "5.e-1": 0.5,
            "3e+03": 3000,
            "-0E-3": 0,
            "١٢.٣e١": 123,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(yaml.safe_load(translate(text)), expected)

    def test_require_exponent_in_values(self):
        """Отклонить записи чисел вне формата задания."""
        cases = (
            "1", "+1", "1.0", ".5e0", "1e", "1e+", "1.e-",
            "--1e0", "1_0e1", "1e0.0", "nan", "inf", "0x2", "'1e0'",
            "<<1>>", "{foo => 1.0}", "def x := 1; !(x)",
        )
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ConfigError):
                translate(text)

    def test_arrays_and_mappings_at_each_level(self):
        """Сохранить пустые и вложенные коллекции обоих типов."""
        source = "{foo => << {}, <<2e0>>, {BAR => <<>>}, >>, _ => {},}"
        result = {"foo": [{}, [2], {"BAR": []}], "_": {}}
        self.assertEqual(yaml.safe_load(translate(source)), result)
        self.assertEqual(yaml.safe_load(translate("<< {X => 3e0} >>")),
                         [{"X": 3}])

    def test_preserve_string_keys(self):
        """Сохранить регистр и ключи, похожие на YAML-литералы."""
        names = ["on", "off", "true", "FALSE", "Null", "yes", "no", "y", "N"]
        source = "{" + ", ".join(f"{name} => 1e0" for name in names) + "}"
        output = translate(source)
        self.assertEqual(list(yaml.safe_load(output)), names)
        self.assertIn("'y':", output)
        self.assertIn("'N':", output)

    def test_quote_mixed_case_yaml_literals(self):
        """Сохранить имена при регистронезависимом чтении YAML-литералов."""
        names = (
            "NuLl", "nUlL", "YeS", "yEs", "nO", "TrUe", "FaLsE", "oN", "OfF"
        )
        source = "{" + ", ".join(f"{key}=>1e0" for key in names) + "}"
        output = translate(source)
        self.assertEqual(list(yaml.safe_load(output)), list(names))
        for key in names:
            with self.subTest(key=key):
                self.assertIn(f"'{key}':", output)

    def test_comments_inside_all_tokens_of_document(self):
        """Разрешить комментарии между лексемами и после корня без LF."""
        source = """%{ || } >> %} def || объявление
seed := %{ ignored
<< %} 4e0;
{value => !(+ %{ арифметика %} seed || правый операнд ниже
1), || запятая перед закрывающей скобкой допустима
}|| конец"""
        self.assertEqual(yaml.safe_load(translate(source)), {"value": 5})

    def test_malformed_containers(self):
        """Отклонить пропуски значений и разделителей в коллекциях."""
        cases = (
            "<<", "<<,>>", "<<1e0,,2e0>>", "<<1e0 2e0>>", "<<1e0 > >",
            "{,}", "{a: 1e0}", "{a => }", "{a => 1e0", "{a => 1e0,,}",
            "{a => 1e0 b => 2e0}", "{a => {b => <<1e0}}",
        )
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ConfigError):
                translate(text)

    def test_invalid_names(self):
        """Отклонить цифры, дефисы и нелатинские буквы в именах."""
        names = ("9a", "a9", "a-b", "абв", "aé", ".n", "a!n", "'a'")
        for name in names:
            with self.subTest(name=name), self.assertRaises(ConfigError):
                translate(f"{{ {name} => 1e0 }}")

    def test_reject_duplicate_mapping_keys_at_second_key(self):
        """Сообщить позицию повторного ключа во вложенном словаре."""
        source = "<< { a => 1e0,\n a => 2e0 } >>"
        with self.assertRaisesRegex(ConfigError, r"строка 2, столбец 2.*ключ"):
            translate(source)
        self.assertEqual(yaml.safe_load(translate("{a=>1e0,A=>2e0}")),
                         {"a": 1, "A": 2})

    def test_collection_with_sixty_five_levels(self):
        """Сохранить все 65 уровней массива в загружаемом YAML."""
        depth = 65
        source = "<<" * depth + "1e0" + ">>" * depth
        value = yaml.safe_load(translate(source))
        for _ in range(depth):
            value, = value
        self.assertEqual(value, 1)

    def test_deep_collection_serializes_with_explicit_stack(self):
        """Проверить события YAML для вложенных массивов глубиной 1500."""
        depth = 1500
        source = "<<" * depth + "{leaf => 1e0}" + ">>" * depth
        events = list(yaml.parse(translate(source)))
        opened = sum(isinstance(event, yaml.SequenceStartEvent)
                     for event in events)
        closed = sum(isinstance(event, yaml.SequenceEndEvent)
                     for event in events)
        self.assertEqual(opened, depth)
        self.assertEqual(closed, depth)
        leaves = [event.value for event in events
                  if isinstance(event, yaml.ScalarEvent)]
        self.assertEqual(leaves, ["leaf", "1"])

    def test_deep_mappings_use_compact_yaml_if_indentation_exceeds_size(self):
        """Записать 3000 уровней словаря без квадратичного числа отступов."""
        depth = 3000
        source = "{key => " * depth + "1e0" + "}" * depth
        output = translate(source)
        events = list(yaml.parse(output))
        mappings = [event for event in events
                    if isinstance(event, yaml.MappingStartEvent)]
        self.assertEqual(len(mappings), depth)
        self.assertTrue(all(event.flow_style for event in mappings))
        scalar_values = [event.value for event in events
                         if isinstance(event, yaml.ScalarEvent)]
        self.assertEqual(scalar_values, ["key"] * depth + ["1"])

    def test_yaml_text_keeps_tiny_and_large_literals(self):
        """Проверить разряды в самом документе, включая малые экспоненты."""
        small = translate("1e-4097").splitlines()[0]
        large = yaml.safe_load(translate("1e4097"))
        self.assertEqual(Decimal(small), Decimal("1e-4097"))
        self.assertEqual(large, 10 ** 4097)

    def test_zero_with_exponent_outside_decimal_range(self):
        """Свести нулевую мантиссу к нулю при любой длине экспоненты."""
        power = "9" * 30
        cases = (f"0e{power}", f"-000.E-{power}", f"+٠.０e+{power}")
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(yaml.safe_load(translate(source)), 0)

    def test_nonzero_powers_outside_decimal_range(self):
        """Сохранить точную экспоненту даже за диапазоном Decimal."""
        for power in ("9" * 30, "-" + "9" * 30, "9" * 4400):
            with self.subTest(length=len(power), negative=power[:1] == "-"):
                node = yaml.compose(translate(f"1.25e{power}"))
                suffix = power if power.startswith("-") else "+" + power
                self.assertEqual(node.value, "1.25e" + suffix)
                self.assertEqual(node.tag, "tag:yaml.org,2002:float")

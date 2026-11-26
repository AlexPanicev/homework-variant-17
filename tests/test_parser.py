"""Тесты дерева разбора и позиций синтаксических ошибок."""

import unittest

from src.errors import ConfigError
from src.parser import parse


class ParserTests(unittest.TestCase):
    """Проверки грамматики отдельно от вычисления выражений."""

    def test_definition_and_root(self):
        """Разобрать объявление, вложенный словарь и массив."""
        tree = parse("def rate := +2.E-1; { a => << !(+ rate 1), {} >> }")
        self.assertEqual(tree.data, "document")
        self.assertEqual(
            [child.data for child in tree.children], ["definition", "mapping"]
        )

    def test_comments_and_multiple_lines(self):
        """Считать CRLF и CR переводами строки, пропустить комментарии."""
        tree = parse("\ufeff|| header\r\n%{ a\rb %}\r\n<<1e0>>|| tail")
        self.assertEqual(tree.children[0].meta.line, 4)

    def test_missing_value_at_eof(self):
        """Сообщить позицию конца ввода после комментария и перевода строки."""
        with self.assertRaisesRegex(ConfigError, r"строка 2, столбец 1"):
            parse("def a := 1e0;|| comment\n")

    def test_unterminated_comment(self):
        """Указать начало незакрытого комментария."""
        with self.assertRaisesRegex(ConfigError, r"строка 2, столбец 1.*%}"):
            parse("{}\n%{ missing")

    def test_trailing_text_is_invalid(self):
        """Потребовать завершения документа после корневого значения."""
        for source in ("<<>> {}", "{}?"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ConfigError, "конец ввода"):
                    parse(source)

    def test_adjacent_operands_need_boundaries(self):
        """Отклонить слитные числа, имена и ключевое слово."""
        for source in ("!(+ 1e0+2e0)", "!(+ 1e0a)", "deffoo := 1e0; {}"):
            with self.subTest(source=source), self.assertRaises(ConfigError):
                parse(source)

    def test_missing_separator_after_operator(self):
        """Предложить пробел, если оператор примыкает к имени операнда."""
        diagnostic = "от операнда пробелом"
        for operator in ("+", "-"):
            with self.subTest(operator=operator):
                with self.assertRaisesRegex(ConfigError, diagnostic):
                    parse(f"!({operator}base 1)")

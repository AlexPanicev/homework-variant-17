"""Проверки штатного запуска, потоков и кодов завершения."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

from src.main import INPUT_ERROR, IO_ERROR, MAX_INPUT_BYTES


RUNNER = Path(__file__).resolve().parents[1] / "run.sh"
TIMEOUT = 20


def run_cli(source: bytes, *args: str) -> subprocess.CompletedProcess:
    """Запустить скрипт из другого каталога и перехватить оба потока."""
    return subprocess.run(
        [str(RUNNER), *args],
        input=source,
        cwd=RUNNER.parent.parent,
        env={**os.environ, "PYTHON": sys.executable},
        capture_output=True,
        timeout=TIMEOUT,
        check=False,
    )


class CliTests(unittest.TestCase):
    """Проверки CLI как отдельного процесса."""

    def test_returns_only_yaml_on_success(self):
        """Принять UTF-8 с BOM и CRLF без служебных строк в выводе."""
        source = "\ufeff|| комментарий\r\n{port => 8e3}\r\n".encode()
        result = run_cli(source)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout, b"port: 8000\n")

    def test_empty_and_comment_only_inputs(self):
        """Отклонить документы без корня и сообщить о конце ввода."""
        for text in (b"", b" \t\n", b"|| comment", b"%{ comment %}"):
            with self.subTest(text=text):
                result = run_cli(text)
                self.assertEqual(result.returncode, INPUT_ERROR)
                self.assertEqual(result.stdout, b"")
                self.assertIn("конец ввода", result.stderr.decode())

    def test_errors_leave_stdout_empty(self):
        """Проверить оба вида ошибок на полноценном документе."""
        cases = {
            b"{a=>1e0, b=>?}": "недопустимый символ",
            b"<<1e0, !(mod 3 0)>>": "деления на ноль",
        }
        for text, message in cases.items():
            with self.subTest(text=text):
                result = run_cli(text)
                self.assertEqual(result.returncode, INPUT_ERROR)
                self.assertEqual(result.stdout, b"")
                self.assertIn(message, result.stderr.decode())
                self.assertNotIn(b"Traceback", result.stderr)

    def test_invalid_utf8(self):
        """Объяснить ошибку кодировки с номером байта."""
        result = run_cli(b"{}\n\xff")
        self.assertEqual(result.returncode, INPUT_ERROR)
        self.assertEqual(result.stdout, b"")
        self.assertIn("UTF-8, байт 4", result.stderr.decode())

    def test_input_limit(self):
        """Принять ввод на границе размера и отклонить следующий байт."""
        prefix = b"{}||"
        source = prefix + b"x" * (MAX_INPUT_BYTES - len(prefix))
        result = run_cli(source)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(yaml.safe_load(result.stdout), {})
        result = run_cli(source + b"x")
        self.assertEqual(result.returncode, INPUT_ERROR)
        self.assertEqual(result.stdout, b"")
        self.assertIn("вход превышает", result.stderr.decode())

    def test_output_limit(self):
        """Остановить большой вывод до передачи каких-либо байтов в stdout."""
        values = b",".join([b"!(big)"] * 1100)
        result = run_cli(b"def big := 1e4096; <<" + values + b">>")
        self.assertEqual(result.returncode, INPUT_ERROR)
        self.assertEqual(result.stdout, b"")
        self.assertIn("результат YAML превышает", result.stderr.decode())

    def test_help_and_unknown_option(self):
        """Показать помощь и отклонить неподдерживаемый параметр."""
        result = run_cli(b"", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"stdin", result.stdout)
        self.assertEqual(result.stderr, b"")
        result = run_cli(b"{}", "--unknown")
        self.assertEqual(result.returncode, INPUT_ERROR)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"--unknown", result.stderr)

    def test_broken_output(self):
        """Обработать закрытый выходной канал без трассировки."""
        with subprocess.Popen(
            [str(RUNNER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env={**os.environ, "PYTHON": sys.executable},
        ) as process:
            process.stdout.close()
            process.stdin.write(b"{}")
            process.stdin.close()
            self.assertEqual(process.wait(timeout=TIMEOUT), IO_ERROR)
            diagnostic = process.stderr.read()
            self.assertNotIn(b"Traceback", diagnostic)
            self.assertNotIn(b"Exception ignored", diagnostic)

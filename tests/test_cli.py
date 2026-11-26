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


def run_cli(source: bytes, *args: str,
            prelude: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    """Запустить скрипт из другого каталога и перехватить оба потока."""
    return subprocess.run(
        [*prelude, str(RUNNER), *args],
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
        literal = b"7" * 4097 + b"e0"
        source = b"def big := " + literal + b"; <<" + values + b">>"
        result = run_cli(source)
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
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHON": sys.executable},
        ) as process:
            process.stdout.close()
            process.stdin.write(b"{}")
            process.stdin.close()
            self.assertEqual(process.wait(timeout=TIMEOUT), IO_ERROR)
            diagnostic = process.stderr.read()
            self.assertNotIn(b"Traceback", diagnostic)
            self.assertNotIn(b"Exception ignored", diagnostic)

    def test_closed_stderr(self):
        """Вернуть код ошибки и сохранить stdout при закрытом stderr."""
        prelude = ("sh", "-c", 'exec "$@" 2>&-', "sh")
        for source, args in ((b"?", ()), (b"{}", ("--unknown",))):
            with self.subTest(source=source, args=args):
                result = run_cli(source, *args, prelude=prelude)
                self.assertEqual(result.returncode, INPUT_ERROR)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")
        result = run_cli(b"{}", prelude=prelude)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(yaml.safe_load(result.stdout), {})

    def test_closed_stdin(self):
        """Сообщить о закрытом stdin без трассировки."""
        prelude = ("sh", "-c", 'exec "$@" <&-', "sh")
        result = run_cli(b"", prelude=prelude)
        self.assertEqual(result.returncode, IO_ERROR)
        self.assertEqual(result.stdout, b"")
        self.assertIn("поток stdin недоступен", result.stderr.decode())
        self.assertNotIn(b"Traceback", result.stderr)

    def test_closed_stdout(self):
        """Считать сбой записи YAML или справки ошибкой ввода-вывода."""
        prelude = ("sh", "-c", 'exec "$@" >&-', "sh")
        for args in ((), ("--help",)):
            with self.subTest(args=args):
                result = run_cli(b"{}", *args, prelude=prelude)
                self.assertEqual(result.returncode, IO_ERROR)
                self.assertEqual(result.stdout, b"")
                self.assertIn("выходной поток недоступен",
                              result.stderr.decode())
                self.assertNotIn(b"Traceback", result.stderr)

    def test_broken_error_output(self):
        """Сохранить код 2 при записи ошибки в канал без читателя."""
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            result = subprocess.run(
                [str(RUNNER)], input=b"?", stdout=subprocess.PIPE,
                stderr=write_fd, env={**os.environ, "PYTHON": sys.executable},
                timeout=TIMEOUT, check=False,
            )
        finally:
            os.close(write_fd)
        self.assertEqual(result.returncode, INPUT_ERROR)
        self.assertEqual(result.stdout, b"")

    def check_example(self, filename: str, expected: dict):
        """Сверить YAML предметного примера с ожидаемой структурой."""
        path = RUNNER.with_name("examples") / filename
        result = run_cli(path.read_bytes())
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        self.assertEqual(yaml.safe_load(result.stdout), expected)

    def test_telemetry_example(self):
        """Проверить интервалы опроса и каналы датчиков."""
        self.check_example("telemetry.cfg", {
            "polling": {"period_seconds": 2.5, "delayed_seconds": 3.5},
            "channels": [0, 1, 7],
        })

    def test_museum_example(self):
        """Проверить вместимость группы и расписание экскурсий."""
        self.check_example("museum.cfg", {
            "group": {"capacity": 24, "reserve": 20},
            "session_hours": [10, 14, 16],
            "cancelled": [],
        })

    def test_warehouse_example(self):
        """Проверить остаток после упаковки и добавленный резерв."""
        self.check_example("warehouse.cfg", {
            "batch": {"units": 53, "box_size": 10, "loose_units": 3},
            "buffer": 5,
        })

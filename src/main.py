"""Точка входа для чтения stdin и записи YAML в stdout."""

import argparse
import sys
from contextlib import suppress
from typing import TextIO

from .errors import ConfigError


MAX_INPUT_BYTES = 1024 * 1024
INPUT_ERROR = 2
IO_ERROR = 1
INTERRUPTED = 130


def read_source() -> str:
    """Прочитать вход в UTF-8 с ограничением на размер."""
    if sys.stdin is None:
        raise OSError("поток stdin недоступен")
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ConfigError("вход превышает 1 МиБ")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        position = error.start + 1
        raise ConfigError(f"ожидался текст UTF-8, байт {position}") from None


def write_text(stream: TextIO | None, text: str) -> None:
    """Записать текст и закрыть поток при сбое записи или сброса буфера."""
    if stream is None:
        raise OSError("выходной поток недоступен")
    try:
        stream.write(text)
        stream.flush()
    except OSError:
        with suppress(OSError):
            stream.close()
        raise


def report_error(message: str, status: int) -> int:
    """Передать диагностику в stderr и сохранить код даже при сбое записи."""
    with suppress(OSError):
        write_text(sys.stderr, message + "\n")
    return status


class CliArguments(argparse.ArgumentParser):
    """Справка и ошибки вызова со строго раздельными потоками."""

    def print_help(self, file: TextIO | None = None) -> None:
        """Записать справку в stdout или в переданный поток."""
        stream = sys.stdout if file is None else file
        write_text(stream, self.format_help())

    def error(self, message: str) -> None:
        """Направить ошибку вызова в stderr и завершиться с кодом 2."""
        text = f"{self.format_usage()}{self.prog}: error: {message}"
        self.exit(report_error(text, INPUT_ERROR))


def main() -> int:
    """Разобрать параметры и вернуть код завершения для оболочки."""
    parser = CliArguments(
        prog="run.sh",
        description="Преобразует конфигурацию варианта 17 из stdin в YAML.",
    )
    try:
        parser.parse_args()
        from .translator import translate

        write_text(sys.stdout, translate(read_source()))
    except ConfigError as error:
        return report_error(f"Ошибка: {error}", INPUT_ERROR)
    except ModuleNotFoundError as error:
        if error.name not in {"lark", "yaml"}:
            raise
        return report_error("Установите зависимости из requirements.txt.",
                            IO_ERROR)
    except OSError as error:
        return report_error(f"Ошибка ввода-вывода: {error}", IO_ERROR)
    except KeyboardInterrupt:
        return report_error("Прервано.", INTERRUPTED)
    return 0


if __name__ == "__main__":
    sys.exit(main())

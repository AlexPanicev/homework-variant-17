"""Точка входа для чтения stdin и записи YAML в stdout."""

import argparse
import sys
from contextlib import suppress

from .errors import ConfigError


MAX_INPUT_BYTES = 1024 * 1024
INPUT_ERROR = 2
IO_ERROR = 1
INTERRUPTED = 130


def read_source() -> str:
    """Прочитать вход в UTF-8 с ограничением на размер."""
    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ConfigError("вход превышает 1 МиБ")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        position = error.start + 1
        raise ConfigError(f"ожидался текст UTF-8, байт {position}") from None


def write_result(output: str) -> None:
    """Записать результат и обработать недоступный выходной поток."""
    try:
        sys.stdout.write(output)
        sys.stdout.flush()
    except OSError:
        with suppress(OSError):
            sys.stdout.close()
        raise


def main() -> int:
    """Разобрать параметры и вернуть код завершения для оболочки."""
    parser = argparse.ArgumentParser(
        prog="run.sh",
        description="Преобразует конфигурацию варианта 17 из stdin в YAML.",
    )
    parser.parse_args()
    try:
        from .translator import translate

        write_result(translate(read_source()))
    except ConfigError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return INPUT_ERROR
    except ModuleNotFoundError as error:
        if error.name not in {"lark", "yaml"}:
            raise
        print("Установите зависимости из requirements.txt.", file=sys.stderr)
        return IO_ERROR
    except OSError as error:
        print(f"Ошибка ввода-вывода: {error}", file=sys.stderr)
        return IO_ERROR
    except KeyboardInterrupt:
        print("Прервано.", file=sys.stderr)
        return INTERRUPTED
    return 0


if __name__ == "__main__":
    sys.exit(main())

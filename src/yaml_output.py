"""Сериализация результата без преобразования Decimal в двоичный float."""

from decimal import Decimal
from io import StringIO

import yaml

from .errors import ConfigError
from .evaluator import Data


MAX_OUTPUT_MIB = 4
MAX_OUTPUT_CHARS = MAX_OUTPUT_MIB * 1024 * 1024
TAG_PREFIX = "tag:yaml.org,2002:"


def ensure_output_size(characters: int) -> None:
    """Остановить сериализацию до превышения допустимого размера YAML."""
    if characters > MAX_OUTPUT_CHARS:
        raise ConfigError(f"результат YAML превышает {MAX_OUTPUT_MIB} МиБ")


class OutputBuffer(StringIO):
    """Собрать YAML целиком и ограничить размер результата."""

    def write(self, text: str) -> int:
        """Остановить сериализацию до превышения лимита."""
        ensure_output_size(self.tell() + len(text))
        return super().write(text)


class ConfigDumper(yaml.SafeDumper):
    """Сериализатор YAML для десятичных чисел и строковых ключей."""

    scalar_chars = 0

    def represent_scalar(self, tag, value, style=None):
        """Ограничить объём скаляров ещё при построении узлов YAML."""
        self.scalar_chars += len(value)
        ensure_output_size(self.scalar_chars)
        return super().represent_scalar(tag, value, style)

    def ignore_aliases(self, data) -> bool:
        """Записывать каждое число отдельно и сохранять ссылки коллекций."""
        return isinstance(data, Decimal) or super().ignore_aliases(data)


def represent_number(dumper: ConfigDumper, value: Decimal):
    """Записать целое или десятичное число с его точным значением."""
    if value == value.to_integral_value():
        return dumper.represent_scalar(TAG_PREFIX + "int", format(value, "f"))
    coefficient, exponent = format(value, "e").split("e")
    if "." not in coefficient:
        coefficient += ".0"
    return dumper.represent_scalar(
        TAG_PREFIX + "float", f"{coefficient}e{exponent}"
    )


def represent_key(dumper: ConfigDumper, key: str):
    """Сохранить строки y и n в YAML 1.1, а также ключи вроде true и on."""
    style = "'" if key.lower() in {"y", "n"} else None
    return dumper.represent_scalar(TAG_PREFIX + "str", key, style=style)


ConfigDumper.add_representer(Decimal, represent_number)
ConfigDumper.add_representer(str, represent_key)


def dump_config(value: Data) -> str:
    """Вернуть один документ YAML с ключами в порядке исходника."""
    with OutputBuffer() as output:
        yaml.dump(value, output, Dumper=ConfigDumper, sort_keys=False)
        return output.getvalue()

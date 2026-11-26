"""Диагностика, которую CLI может показать без трассировки Python."""


class ConfigError(ValueError):
    """Ошибка во входной конфигурации."""


def located_error(message: str, line: int, column: int) -> ConfigError:
    """Привязать сообщение к строке и столбцу исходного текста."""
    return ConfigError(f"строка {line}, столбец {column}: {message}")

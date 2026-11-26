"""Объединение разбора, вычислений и вывода YAML."""

from lark.exceptions import VisitError

from .errors import ConfigError
from .evaluator import Evaluator
from .parser import parse
from .yaml_output import dump_config


def translate(source: str) -> str:
    """Преобразовать учебную конфигурацию в один документ YAML."""
    tree = parse(source)
    try:
        value = Evaluator().transform(tree)
    except VisitError as error:
        if isinstance(error.orig_exc, (ConfigError, MemoryError)):
            raise error.orig_exc from None
        raise
    return dump_config(value)

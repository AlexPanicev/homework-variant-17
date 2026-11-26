"""Объединение разбора, вычислений и вывода YAML."""

from decimal import localcontext

from lark.exceptions import VisitError

from .errors import ConfigError
from .evaluator import Evaluator
from .numbers import CALCULATION_CONTEXT
from .parser import parse
from .yaml_output import dump_config


def translate(source: str) -> str:
    """Преобразовать учебную конфигурацию в один документ YAML."""
    tree = parse(source)
    with localcontext(CALCULATION_CONTEXT):
        try:
            value = Evaluator().transform(tree)
        except VisitError as error:
            if isinstance(error.orig_exc, ConfigError):
                raise error.orig_exc from None
            raise
        return dump_config(value)

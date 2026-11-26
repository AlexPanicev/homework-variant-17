"""Запись YAML через события PyYAML и явный стек коллекций."""

from decimal import Decimal
from io import StringIO
from typing import Iterator

import yaml

from .errors import ConfigError
from .evaluator import Data
from .limits import MAX_OUTPUT_CHARS, MAX_OUTPUT_MIB
from .numbers import Number


TAG_PREFIX = "tag:yaml.org,2002:"
AMBIGUOUS_KEYS = {"y", "n", "yes", "no", "true", "false", "on", "off", "null"}
type Pending = list[Data | str | yaml.Event]


class OutputLimitError(ConfigError):
    """Размер текущей записи YAML превысил допустимый объём."""


class OutputBuffer(StringIO):
    """Собрать YAML целиком, контролируя размер результата."""

    def write(self, text: str) -> int:
        """Остановить эмиттер до превышения размера вывода."""
        if self.tell() + len(text) > MAX_OUTPUT_CHARS:
            message = f"результат YAML превышает {MAX_OUTPUT_MIB} МиБ"
            raise OutputLimitError(message)
        return super().write(text)


def number_event(value: Number) -> yaml.ScalarEvent:
    """Записать точное число с подходящим числовым тегом YAML."""
    digits = format(value.coefficient, "f")
    if value.power >= 0 and len(digits) + value.power <= MAX_OUTPUT_CHARS:
        text = digits + "0" * value.power
        return yaml.ScalarEvent(None, TAG_PREFIX + "int", (True, False), text)
    sign = "-" if value.coefficient.is_signed() else ""
    digits = digits.removeprefix("-")
    exponent = format(Decimal(value.leading_power()), "+f")
    text = f"{sign}{digits[0]}.{digits[1:] or '0'}e{exponent}"
    return yaml.ScalarEvent(None, TAG_PREFIX + "float", (True, False), text)


def key_event(key: str) -> yaml.ScalarEvent:
    """Кавычками защитить ключи, похожие на логические значения и null."""
    style = "'" if key.lower() in AMBIGUOUS_KEYS else None
    return yaml.ScalarEvent(None, TAG_PREFIX + "str", (True, True), key,
                            style=style)


def collection_anchors(root: Data) -> dict[int, str | None]:
    """Назначить якоря объектам, которые встречаются повторно."""
    anchors = {}
    next_anchor = 1
    pending = [root]
    while pending:
        item = pending.pop()
        if not isinstance(item, (list, dict)):
            continue
        identity = id(item)
        if identity in anchors:
            if anchors[identity] is None:
                anchors[identity] = f"id{next_anchor:03d}"
                next_anchor += 1
            continue
        anchors[identity] = None
        members = item if isinstance(item, list) else item.values()
        pending.extend(reversed(members))
    return anchors


def open_collection(value: list[Data] | dict[str, Data],
                    anchor: str | None, pending: Pending,
                    compact: bool) -> yaml.Event:
    """Поставить содержимое и конец коллекции в стек событий."""
    if isinstance(value, list):
        pending.append(yaml.SequenceEndEvent())
        pending.extend(reversed(value))
        return yaml.SequenceStartEvent(anchor, TAG_PREFIX + "seq", True,
                                       flow_style=compact)
    pending.append(yaml.MappingEndEvent())
    for key, member in reversed(value.items()):
        pending.extend((member, key))
    return yaml.MappingStartEvent(anchor, TAG_PREFIX + "map", True,
                                  flow_style=compact)


def node_events(root: Data, compact: bool) -> Iterator[yaml.Event]:
    """Обойти значения и ссылки без вызовов в глубину Python."""
    anchors = collection_anchors(root)
    emitted = set()
    pending: Pending = [root]
    while pending:
        value = pending.pop()
        if isinstance(value, yaml.Event):
            yield value
        elif isinstance(value, Number):
            yield number_event(value)
        elif isinstance(value, str):
            yield key_event(value)
        else:
            anchor = anchors[id(value)]
            if anchor is not None and anchor in emitted:
                yield yaml.AliasEvent(anchor)
                continue
            if anchor is not None:
                emitted.add(anchor)
            yield open_collection(value, anchor, pending, compact)


def document_events(root: Data, compact: bool) -> Iterator[yaml.Event]:
    """Окружить события корневого значения границами документа."""
    yield yaml.StreamStartEvent()
    yield yaml.DocumentStartEvent()
    yield from node_events(root, compact)
    yield yaml.DocumentEndEvent()
    yield yaml.StreamEndEvent()


def render(value: Data, compact: bool) -> str:
    """Записать YAML в выбранной форме до лимита объёма."""
    width = MAX_OUTPUT_CHARS if compact else None
    with OutputBuffer() as output:
        events = document_events(value, compact)
        yaml.emit(events, output, Dumper=yaml.SafeDumper, width=width)
        return output.getvalue()


def dump_config(value: Data) -> str:
    """При нехватке места для отступов попробовать компактный YAML."""
    try:
        return render(value, compact=False)
    except OutputLimitError:
        pass
    return render(value, compact=True)

"""Запись YAML через события PyYAML и явный стек коллекций."""

import sys
from decimal import Decimal
from typing import Iterator

import yaml

from .evaluator import Data
from .numbers import Number


TAG_PREFIX = "tag:yaml.org,2002:"
AMBIGUOUS_KEYS = {"y", "n", "yes", "no", "true", "false", "on", "off", "null"}
INDENT = 2
READABLE_WIDTH = 80
type Pending = list[Data | str | yaml.Event]


def scientific_text(value: Number, digits: str) -> str:
    """Сформировать точную экспоненциальную запись для YAML."""
    sign = "-" if value.coefficient.is_signed() else ""
    digits = digits.removeprefix("-")
    exponent = format(Decimal(value.leading_power()), "+f")
    return f"{sign}{digits[0]}.{digits[1:] or '0'}e{exponent}"


def number_event(value: Number) -> yaml.ScalarEvent:
    """Выбрать точную десятичную или короткую экспоненциальную запись."""
    digits = format(value.coefficient, "f")
    fraction = value.power < 0
    reader_digits = sys.int_info.default_max_str_digits
    long_padding = value.power > 0 and value.leading_power() >= reader_digits
    if fraction or long_padding:
        scientific = scientific_text(value, digits)
        if fraction or len(scientific) < len(digits) + value.power:
            return yaml.ScalarEvent(
                None, TAG_PREFIX + "float", (True, False), scientific
            )
    text = digits + "0" * value.power
    return yaml.ScalarEvent(None, TAG_PREFIX + "int", (True, False), text)


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


def node_events(root: Data) -> Iterator[yaml.Event]:
    """Обойти значения и ссылки без вызовов в глубину Python."""
    anchors = collection_anchors(root)
    emitted = set()
    pending: Pending = [root]
    depth = 0
    while pending:
        value = pending.pop()
        if isinstance(value, yaml.Event):
            depth -= 1
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
            compact = depth * INDENT >= READABLE_WIDTH
            yield open_collection(value, anchor, pending, compact)
            depth += 1


def document_events(root: Data) -> Iterator[yaml.Event]:
    """Окружить события корневого значения границами документа."""
    yield yaml.StreamStartEvent()
    yield yaml.DocumentStartEvent()
    yield from node_events(root)
    yield yaml.DocumentEndEvent()
    yield yaml.StreamEndEvent()


def dump_config(value: Data) -> str:
    """Собрать полный YAML из событий, сохраняя отступы читабельными."""
    return yaml.emit(document_events(value), Dumper=yaml.SafeDumper,
                     indent=INDENT, width=sys.maxsize)

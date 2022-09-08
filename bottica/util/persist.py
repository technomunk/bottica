"""Easy data persistence using runtime inspection."""

import json
from inspect import isawaitable
from typing import Any, Callable, TypeAlias, get_type_hints

from .deserializers import DEFAULT_DESERIALIZERS
from .serializers import DEFAULT_SERIALIZERS


class _Persistent:
    """Sentinel type for PERSISTENT annotation"""

    __slots__ = ()


Serializer = Callable[[Any], Any]
Deserializer = Callable[[Any, dict], Any]
# Mark a value as persistent, ie one that should be serialized.
PERSISTENT = _Persistent()


# I know what I'm doing :anger:
# pylint: disable=dangerous-default-value
def marshall(
    obj: object,
    *,
    serializers: dict[type | TypeAlias, Serializer] = {},
) -> dict:
    """Take any fields annotated as persistent and make sure they are serializeable."""
    data = {}

    hints = get_type_hints(obj, include_extras=True)
    for field, hint in hints.items():
        if PERSISTENT not in getattr(hint, "__metadata__", ()):
            continue
        field_type = getattr(hint, "__origin__", hint)
        if serializer := serializers.get(field_type) or DEFAULT_SERIALIZERS.get(field_type):
            data[field] = serializer(getattr(obj, field))
        else:
            data[field] = getattr(obj, field)

    return data


async def unmarshall(
    data: dict,
    obj: object,
    *,
    deserializers: dict[type | TypeAlias, Deserializer] = {},
    deserializer_opts: dict = {},
):
    """Read data from provided serialized dictionary into given object."""
    hints = get_type_hints(obj, include_extras=True)
    for field, hint in hints.items():
        if field not in data:
            continue
        if PERSISTENT not in getattr(hint, "__metadata__", ()):
            continue

        field_type = getattr(hint, "__origin__", hint)
        if deserializer := deserializers.get(field_type) or DEFAULT_DESERIALIZERS.get(field_type):
            value = deserializer(data[field], deserializer_opts)
            if isawaitable(value):
                await value
            setattr(obj, field, value)
        else:
            setattr(obj, field, data[field])


def persist(
    obj: object,
    filename: str,
    *,
    serializers: dict[type | TypeAlias, Serializer] = {},
):
    """
    Save data from given object to the provided file.
    The data can later be restored from the file.
    """
    with open(filename, "w", encoding="utf8") as file:
        json.dump(marshall(obj, serializers=serializers), file)


async def restore(
    filename: str,
    obj: object,
    *,
    deserializers: dict[type | TypeAlias, Deserializer] = {},
    deserializer_opts: dict = {},
):
    """
    Restore saved data from provided file.
    """
    with open(filename, "r", encoding="utf8") as file:
        data = json.load(file)

    await unmarshall(data, obj, deserializers=deserializers, deserializer_opts=deserializer_opts)

"""Customized `command` decorator with additional functionality."""

from importlib import import_module
from typing import Any, Callable, Iterable, Optional, Type, get_type_hints

from discord.ext.commands import Command
from discord.ext.commands import command as discord_command
from discord.ext.commands.core import MISSING


# Optimized data holder
# pylint: disable=too-few-public-methods
class Description:
    """Description of a command parameter that can be used in conjunction with typing.Annotated."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value


# pylint: disable=dangerous-default-value
def command(
    name: str = MISSING,
    cls: Type[Command[Any, ..., Any]] = MISSING,
    descriptions: dict[str, str] = {},
    **attrs: Any,
) -> Any:
    def parameterized_decorator(func: Callable) -> Command[Any, ..., Any]:
        command_ = discord_command(name, cls, **attrs)(func)
        for param_name, description in descriptions.items():
            param = command_.params.get(param_name)
            if not param:
                raise ValueError(f"Parameter '{param_name}' does not exist in {command_.name}")

            command_.params[param_name] = param.replace(description=description)

        return command_

    return parameterized_decorator


def _add_parameter_descriptions(command_: Command[Any, ..., Any], func: Callable):
    hints = get_type_hints(
        func,
        globalns=vars(import_module(func.__module__)),
        include_extras=True,
    )

    for param_name, hint in hints.items():
        description = _find_description(getattr(hint, "__metadata__", []))
        if not description:
            continue

        param = command_.params.get(param_name)
        if not param:
            raise ValueError(f"Parameter '{param_name}' does not exist in {func.__name__}")

        command_.params[param_name] = param.replace(description=description.value)


def _find_description(hints: Iterable[object]) -> Optional[Description]:
    for hint in hints:
        if isinstance(hint, Description):
            return hint

    return None

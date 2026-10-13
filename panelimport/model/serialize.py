"""Strict conversion between dataclasses and JSON-compatible structures.

The project file is the direct serialization of the model dataclasses, so loading must
reproduce exactly what was saved and reject anything it does not understand.
"""

from __future__ import annotations

import dataclasses
import enum
import types
import typing
from typing import Any


class SerializationError(ValueError):
    pass


def to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, float) and obj != obj:  # NaN is not valid JSON
        raise SerializationError("NaN cannot be serialized")
    return obj


def from_jsonable(tp: Any, data: Any, path: str = "$") -> Any:
    if tp is Any:
        return data
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    if origin is typing.Union or origin is types.UnionType:
        if data is None:
            if type(None) in args:
                return None
            raise SerializationError(f"{path}: null is not allowed")
        errors = []
        for arg in args:
            if arg is type(None):
                continue
            try:
                return from_jsonable(arg, data, path)
            except SerializationError as exc:
                errors.append(str(exc))
        raise SerializationError("; ".join(errors) or f"{path}: no matching type")

    if origin is typing.Literal:
        if data not in args:
            raise SerializationError(f"{path}: {data!r} is not one of {list(args)}")
        return data

    if dataclasses.is_dataclass(tp):
        if not isinstance(data, dict):
            raise SerializationError(f"{path}: expected an object for {tp.__name__}")
        hints = typing.get_type_hints(tp)
        fields = [f for f in dataclasses.fields(tp) if f.init]
        names = {f.name for f in fields}
        unknown = set(data) - names
        if unknown:
            raise SerializationError(f"{path}: unknown keys {sorted(unknown)}")
        kwargs = {}
        for f in fields:
            if f.name in data:
                kwargs[f.name] = from_jsonable(hints[f.name], data[f.name], f"{path}.{f.name}")
            elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                raise SerializationError(f"{path}: missing key '{f.name}'")
        return tp(**kwargs)

    if origin in (list, typing.List):
        if not isinstance(data, list):
            raise SerializationError(f"{path}: expected a list")
        (item_tp,) = args or (Any,)
        return [from_jsonable(item_tp, v, f"{path}[{i}]") for i, v in enumerate(data)]

    if origin in (tuple, typing.Tuple):
        if not isinstance(data, list):
            raise SerializationError(f"{path}: expected a list")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(from_jsonable(args[0], v, f"{path}[{i}]") for i, v in enumerate(data))
        if len(args) != len(data):
            raise SerializationError(f"{path}: expected {len(args)} items")
        return tuple(from_jsonable(a, v, f"{path}[{i}]") for i, (a, v) in enumerate(zip(args, data)))

    if origin in (dict, typing.Dict):
        if not isinstance(data, dict):
            raise SerializationError(f"{path}: expected an object")
        _key_tp, val_tp = args or (str, Any)
        return {str(k): from_jsonable(val_tp, v, f"{path}.{k}") for k, v in data.items()}

    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        try:
            return tp(data)
        except ValueError as exc:
            raise SerializationError(f"{path}: {exc}") from None

    if tp is float:
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            raise SerializationError(f"{path}: expected a number")
        return float(data)
    if tp is int:
        if isinstance(data, bool) or not isinstance(data, int):
            raise SerializationError(f"{path}: expected an integer")
        return data
    if tp is bool:
        if not isinstance(data, bool):
            raise SerializationError(f"{path}: expected true/false")
        return data
    if tp is str:
        if not isinstance(data, str):
            raise SerializationError(f"{path}: expected a string")
        return data
    raise SerializationError(f"{path}: unsupported type {tp!r}")

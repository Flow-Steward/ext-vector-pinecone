"""Bounded JSON and primitive validation with safe public errors."""

import json


class Failure(Exception):
    def __init__(self, code, message, *, dispatched=False):
        super().__init__(message)
        self.code = code
        self.dispatched = dispatched


def require(condition, message, *, code="invalid_payload"):
    if not condition:
        raise Failure(code, message)


def text(value, name, maximum=65536, *, nonempty=False):
    require(isinstance(value, str), f"{name} must be text.")
    require(len(value.encode("utf-8")) <= maximum and "\x00" not in value, f"Invalid {name}.")
    require(not nonempty or bool(value.strip()), f"{name} must be nonempty.")
    return value


def integer(value, name, low, high):
    require(
        type(value) is int and low <= value <= high,
        f"{name} must be an integer from {low} to {high}.",
    )
    return value


def bounded_json(value, limit=256 * 1024):
    try:
        require(
            len(json.dumps(value, allow_nan=False).encode()) <= limit, "JSON exceeds byte limit."
        )
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise Failure("invalid_payload", "Bounded valid JSON is required.") from exc

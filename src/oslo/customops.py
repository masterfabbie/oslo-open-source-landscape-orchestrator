"""Custom operations: definitions, parameter values and the arguments for the host agent.

A custom operation runs a script that is configured in operations.d of the host agent
(``Name:``, ``Command:`` with placeholders such as ``$[SAPSYSTEMNAME]`` or
``$[PARAM-KRNLREL]``). The tool passes context parameters named as in LaMa, filled from the
inventory, and the parameters defined here as ``PARAM-<name>``.

Confirmed with a real host agent: arguments arrive as KEY=value; arguments that are not
passed are left out of the command line, so the following ones move up. As in LaMa, an
optional parameter left empty is not passed; scripts with positional arguments have to
cope with that (optional parameters last, or a default value).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import BUILT_IN_KEYS
from .customspec import CustomSpec, ParameterSpec
from .filters import TYPE_VALUES
from .models import CustomOperation, CustomOperationParameter, OperationTemplate
from .users import ROLE_ORDER

TARGETS = ("INSTANCE", "SYSTEM", "HOST")
ORDERINGS = ("parallel", "roles", "sequential")
PARAMETER_TYPES = ("STRING", "INTEGER", "BOOLEAN")
# Values end up in a command line run as root; without an own pattern only these are allowed.
DEFAULT_STRING_PATTERN = r"[A-Za-z0-9._-]*"
MAX_VALUE_LENGTH = 1024  # the host agent cuts parameter values after 1024 characters
KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
NAME_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9_]{0,63}")
AGENT_OPERATION_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")


class CustomOperationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ParameterError(ValueError):
    """Parameter values that do not fit the definition; ``problems`` maps name -> text."""

    def __init__(self, problems: dict[str, str]) -> None:
        super().__init__("; ".join(f"{name}: {text}" for name, text in problems.items()))
        self.problems = problems


# --- values ---------------------------------------------------------------------------------


def parameter_values(spec: CustomSpec, given: Mapping[str, str | bool | int]) -> dict[str, str]:
    """Check values against the definition; returns PARAM-<name> -> value for the host agent.

    A parameter that is not given at all gets its default value (the web form is prefilled
    with it). Booleans are passed as "true"/"false". An empty optional value is not passed.
    """
    problems: dict[str, str] = {}
    result: dict[str, str] = {}
    for parameter in spec.parameters:
        raw = given.get(parameter.name, parameter.default)
        if parameter.type == "BOOLEAN":
            value = "true" if raw in (True, "true", "on", "1", "yes") else "false"
            result[f"PARAM-{parameter.name}"] = value
            continue
        value = "" if raw is None else str(raw).strip()
        if not value:
            if parameter.required:
                problems[parameter.name] = "required"
            continue
        if len(value) > MAX_VALUE_LENGTH:
            problems[parameter.name] = f"at most {MAX_VALUE_LENGTH} characters"
            continue
        if parameter.type == "INTEGER" and not re.fullmatch(r"-?\d+", value):
            problems[parameter.name] = "not an integer"
            continue
        if parameter.type == "STRING":
            pattern = parameter.pattern or DEFAULT_STRING_PATTERN
            if not re.fullmatch(pattern, value):
                problems[parameter.name] = f"does not match {pattern}"
                continue
        result[f"PARAM-{parameter.name}"] = value
    if problems:
        raise ParameterError(problems)
    return result


# --- definitions ----------------------------------------------------------------------------


def _check_definition(
    key: str,
    name: str,
    agent_operation: str,
    target: str,
    instance_types: list[str],
    ordering: str,
    role: str,
    timeout_seconds: int,
) -> None:
    if not KEY_PATTERN.fullmatch(key) or key in BUILT_IN_KEYS:
        raise CustomOperationError(
            "operation_key", "Key: lowercase letters, digits and _, not a built-in operation"
        )
    if not name.strip() or len(name) > 128:
        raise CustomOperationError("operation_name", "The operation needs a name")
    if not AGENT_OPERATION_PATTERN.fullmatch(agent_operation):
        raise CustomOperationError(
            "operation_agent", "Host agent operation: letters, digits, '.', '_' and '-'"
        )
    if target not in TARGETS or ordering not in ORDERINGS:
        raise CustomOperationError("invalid_input", "Unknown target or ordering")
    if any(t not in TYPE_VALUES for t in instance_types):
        raise CustomOperationError("invalid_input", "Unknown instance type")
    if role not in {r.value for r in ROLE_ORDER}:
        raise CustomOperationError("invalid_input", "Unknown role")
    if not 10 <= timeout_seconds <= 86400:
        raise CustomOperationError("invalid_input", "Timeout: 10 to 86400 seconds")


async def save_operation(
    session: AsyncSession,
    operation: CustomOperation | None,
    *,
    key: str,
    name: str,
    description: str | None,
    agent_operation: str,
    target: str,
    instance_types: list[str],
    ordering: str,
    role: str,
    mass: bool,
    timeout_seconds: int,
    locks: bool = True,
    standalone: bool = True,
) -> CustomOperation:
    """Create (``operation`` None) or change a custom operation. The caller commits."""
    key, agent_operation = key.strip(), agent_operation.strip()
    _check_definition(
        key, name, agent_operation, target, instance_types, ordering, role, timeout_seconds
    )
    taken = await session.scalar(select(CustomOperation.id).where(CustomOperation.key == key))
    template = await session.scalar(
        select(OperationTemplate.id).where(OperationTemplate.key == key)
    )
    if template is not None or (taken is not None and (operation is None or taken != operation.id)):
        raise CustomOperationError("operation_key_taken", f"An operation {key} already exists")
    if operation is None:
        operation = CustomOperation(created_at=datetime.now(UTC), parameters=[])
        session.add(operation)
    operation.key = key
    operation.name = name.strip()
    operation.description = (description or "").strip() or None
    operation.agent_operation = agent_operation
    operation.target = target
    operation.instance_types = ",".join(t for t in TYPE_VALUES if t in instance_types)
    operation.ordering = ordering
    operation.role = role
    operation.mass = mass
    operation.locks = locks
    operation.standalone = standalone
    operation.timeout_seconds = timeout_seconds
    await session.flush()
    return operation


def _check_parameter(
    name: str, label: str, type: str, default: str | None, pattern: str | None
) -> None:
    if not NAME_PATTERN.fullmatch(name):
        raise CustomOperationError(
            "parameter_name", "Name: capital letters, digits and _, e.g. KRNLREL"
        )
    if not label.strip():
        raise CustomOperationError("parameter_label", "The parameter needs a display name")
    if type not in PARAMETER_TYPES:
        raise CustomOperationError("invalid_input", "Unknown parameter type")
    if pattern:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise CustomOperationError("parameter_pattern", f"Invalid pattern: {exc}") from exc
    if default:
        probe = ParameterSpec(name, label, type, False, None, pattern, None)
        spec = CustomSpec(0, "", None, "x", "HOST", (), "parallel", 60, (probe,))
        try:
            parameter_values(spec, {name: default})
        except ParameterError as exc:
            raise CustomOperationError(
                "parameter_default", f"The default value does not fit: {exc}"
            ) from exc


async def save_parameter(
    session: AsyncSession,
    operation: CustomOperation,
    parameter: CustomOperationParameter | None,
    *,
    name: str,
    label: str,
    type: str,
    required: bool,
    default: str | None,
    pattern: str | None,
    help: str | None,
) -> CustomOperationParameter:
    """Add (``parameter`` None) or change a parameter. The caller commits."""
    name = name.strip().upper()
    default = (default or "").strip() or None
    pattern = (pattern or "").strip() or None
    _check_parameter(name, label, type, default, pattern)
    if any(p.name == name and p is not parameter for p in operation.parameters):
        raise CustomOperationError("parameter_taken", f"A parameter {name} already exists")
    if parameter is None:
        position = max((p.position for p in operation.parameters), default=0) + 1
        parameter = CustomOperationParameter(position=position)
        operation.parameters.append(parameter)
    parameter.name = name
    parameter.label = label.strip()
    parameter.type = type
    parameter.required = required and type != "BOOLEAN"
    parameter.default = default
    parameter.pattern = pattern if type == "STRING" else None
    parameter.help = (help or "").strip() or None
    await session.flush()
    return parameter

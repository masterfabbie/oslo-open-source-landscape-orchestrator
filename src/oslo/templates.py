"""Operation templates: define and check them, and the parameter values of a run.

A template is a graph of operations of the catalog (built-in or custom): a step starts when
its predecessors have finished, independent steps run in parallel, like an operation template
in LaMa. Each step runs on fixed targets or on the "$selection" of the run, has its own
parameter values (fixed, or asked for at the start) and its own behavior on error. Only
admins define templates (like custom operations); running one needs its role, which is at
least the highest role of its steps.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .catalog import BUILT_IN_KEYS, Catalog, OperationDef
from .customops import KEY_PATTERN, ParameterError, parameter_values
from .models import CustomOperation, OperationTemplate, TemplateStep
from .operations import NotAssignedError, TargetNotFoundError, TargetType, lock_scope
from .templatespec import (
    ON_ERROR,
    SEPARATOR,
    STEP_TARGETS,
    StepSpec,
    TemplateSpec,
    cycle,
    parallel_pairs,
)
from .users import ROLE_ORDER, Role

MAX_STEPS = 50
MAX_STEP_TARGETS = 100


class TemplateError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def key_taken(session: AsyncSession, key: str, *, template_id: int | None = None) -> bool:
    """Templates and custom operations share one key space (both are catalog operations)."""
    if await session.scalar(select(CustomOperation.id).where(CustomOperation.key == key)):
        return True
    taken = await session.scalar(select(OperationTemplate.id).where(OperationTemplate.key == key))
    return taken is not None and taken != template_id


def _check_values(position: int, operation: OperationDef, values: dict[str, str], ask: list[str]):
    """Format of the given values; a required parameter needs a value unless it is asked for
    at the start."""
    if operation.custom is None:
        if values or ask:
            raise TemplateError("template_step", f"Step {position}: takes no parameters")
        return
    names = {p.name for p in operation.custom.parameters}
    if unknown := (set(values) | set(ask)) - names:
        raise TemplateError(
            "template_step", f"Step {position}: unknown parameters {sorted(unknown)}"
        )
    for p in operation.custom.parameters:
        if p.required and p.name not in ask and not values.get(p.name) and not p.default:
            raise TemplateError(
                "template_step",
                f"Step {position}: {p.label} needs a value or must be asked for at the start",
            )
    loose = replace(
        operation.custom,
        parameters=tuple(replace(p, required=False) for p in operation.custom.parameters),
    )
    try:
        parameter_values(loose, {k: v for k, v in values.items() if v != ""})
    except ParameterError as exc:
        raise TemplateError("template_step", f"Step {position}: {exc}") from exc


async def save_template(
    session: AsyncSession,
    catalog: Catalog,
    template: OperationTemplate | None,
    *,
    key: str,
    name: str,
    description: str | None,
    role: str,
    steps: Sequence[Mapping],
) -> OperationTemplate:
    """Create (``template`` None) or replace a template with its steps. The caller commits.

    ``steps``: dicts with ``position`` (number of the step, unique), ``operation`` (catalog
    key), ``target_type``, ``targets`` (fixed ids; empty: the selection), ``after``
    (positions of the predecessors), ``parameters`` (name -> value), ``ask`` (names asked for
    at the start) and ``on_error``.
    """
    key, name = key.strip(), name.strip()
    if not KEY_PATTERN.fullmatch(key) or key in BUILT_IN_KEYS:
        raise TemplateError(
            "template_key", "Key: lowercase letters, digits and _, not a built-in operation"
        )
    if await key_taken(session, key, template_id=template.id if template else None):
        raise TemplateError("template_key_taken", f"An operation {key} already exists")
    if not name or len(name) > 128:
        raise TemplateError("template_name", "The template needs a name")
    if role not in {r.value for r in ROLE_ORDER}:
        raise TemplateError("invalid_input", "Unknown role")
    if not steps:
        raise TemplateError("template_no_steps", "A template needs at least one step")
    if len(steps) > MAX_STEPS:
        raise TemplateError("invalid_input", f"At most {MAX_STEPS} steps")

    known = {op.key: op for op in catalog.steps()}
    positions = [int(step.get("position") or index) for index, step in enumerate(steps, 1)]
    if len(set(positions)) != len(positions) or min(positions) < 1:
        raise TemplateError("invalid_input", "Step numbers must be unique and positive")
    needed = Role.VIEWER
    checked: list[StepSpec] = []
    for position, step in zip(positions, steps, strict=True):
        operation = known.get(str(step.get("operation", "")))
        target_type = str(step.get("target_type") or "")
        if operation is None:
            raise TemplateError(
                "template_step", f"Step {position}: no operation {step.get('operation')}"
            )
        if target_type not in STEP_TARGETS or TargetType(target_type) not in operation.targets:
            raise TemplateError(
                "template_step", f"Step {position}: {operation.key} does not run on {target_type}"
            )
        targets = tuple(dict.fromkeys(int(t) for t in step.get("targets") or ()))
        if len(targets) > MAX_STEP_TARGETS:
            raise TemplateError("invalid_input", f"Step {position}: too many targets")
        after = tuple(dict.fromkeys(int(a) for a in step.get("after") or ()))
        if missing := [a for a in after if a not in positions or a == position]:
            raise TemplateError("template_step", f"Step {position}: unknown predecessors {missing}")
        on_error = str(step.get("on_error") or "stop")
        if on_error not in ON_ERROR or (on_error == "stop_and_start" and target_type == "HOST"):
            raise TemplateError("invalid_input", f"Step {position}: unknown behavior on error")
        values = {str(k): str(v) for k, v in dict(step.get("parameters") or {}).items()}
        ask = list(dict.fromkeys(str(a) for a in step.get("ask") or ()))
        _check_values(position, operation, values, ask)
        if ROLE_ORDER.index(operation.role) > ROLE_ORDER.index(needed):
            needed = operation.role
        checked.append(
            StepSpec(
                position=position,
                operation=operation.key,
                kind=operation.kind.value,
                target_type=target_type,
                targets=targets,
                after=after,
                on_error=on_error,
                parameters=values,
                ask=tuple(ask),
                custom=operation.custom,
            )
        )
    if ROLE_ORDER.index(Role(role)) < ROLE_ORDER.index(needed):
        raise TemplateError("template_role", f"The steps need at least the role {needed.value}")
    if (found := cycle(checked)) is not None:
        raise TemplateError(
            "template_cycle", "The steps wait for each other: " + " → ".join(map(str, found))
        )
    selection = {s.target_type for s in checked if s.on_selection}
    if len(selection) > 1:
        raise TemplateError(
            "template_selection", "Steps on the selection must all run on the same target type"
        )
    await _check_targets(session, checked)
    await _check_parallel(session, checked)

    if template is None:
        template = OperationTemplate(created_at=datetime.now(UTC), steps=[], mass=False)
        session.add(template)
    template.key = key
    template.name = name
    template.description = (description or "").strip() or None
    template.target = next(iter(selection), "")
    template.role = role
    template.steps.clear()
    await session.flush()
    for step in sorted(checked, key=lambda s: s.position):
        template.steps.append(
            TemplateStep(
                position=step.position,
                operation=step.operation,
                target_type=step.target_type,
                targets=json.dumps(list(step.targets)),
                after=json.dumps(list(step.after)),
                parameters=json.dumps(step.parameters),
                ask=json.dumps(list(step.ask)),
                on_error=step.on_error,
            )
        )
    await session.flush()
    return template


async def _check_targets(session: AsyncSession, steps: list[StepSpec]) -> None:
    for step in steps:
        if step.targets:
            try:
                await lock_scope(session, TargetType(step.target_type), list(step.targets))
            except (TargetNotFoundError, NotAssignedError) as exc:
                raise TemplateError("template_step", f"Step {step.position}: {exc}") from exc


async def _check_parallel(session: AsyncSession, steps: list[StepSpec]) -> None:
    """Two locking steps that may run at the same time must not touch the same system or
    host. Two steps on the selection always would; a step on the selection and one with
    fixed targets wait for each other at run time if they meet."""
    scopes: dict[int, tuple[set[int], set[int]]] = {}
    for a, b in parallel_pairs(steps):
        if not (a.locks and b.locks):
            continue
        if a.on_selection and b.on_selection:
            overlap = True
        elif a.on_selection or b.on_selection:
            continue
        else:
            for step in (a, b):
                if step.position not in scopes:
                    scopes[step.position] = await lock_scope(
                        session, TargetType(step.target_type), list(step.targets)
                    )
            (systems_a, hosts_a), (systems_b, hosts_b) = scopes[a.position], scopes[b.position]
            overlap = bool(systems_a & systems_b or hosts_a & hosts_b)
        if overlap:
            raise TemplateError(
                "template_parallel",
                f"Steps {a.position} and {b.position} may run at the same time on the same "
                "targets and both lock them; connect them or choose other targets",
            )


def template_values(
    spec: TemplateSpec, given: Mapping[str, str | int | bool]
) -> dict[str, dict[str, str]]:
    """Values of a run per step (position -> PARAM-<name> -> value), checked like those of
    custom operations. ``given`` uses "<position>.<NAME>" and may only set the parameters
    asked for at the start; the others keep the template's value, then the default."""
    result: dict[str, dict[str, str]] = {}
    problems: dict[str, str] = {}
    allowed = {p.name for p in spec.run_parameters()}
    if unknown := sorted(set(given) - allowed):
        raise ParameterError({name: "Fixed in the template" for name in unknown})
    for step in spec.steps:
        if step.custom is None:
            continue
        prefix = f"{step.position}{SEPARATOR}"
        values: dict[str, str | int | bool] = {k: v for k, v in step.parameters.items() if v != ""}
        values |= {k[len(prefix) :]: v for k, v in given.items() if k.startswith(prefix)}
        try:
            result[str(step.position)] = parameter_values(step.custom, values)
        except ParameterError as exc:
            problems |= {f"{prefix}{name}": text for name, text in exc.problems.items()}
    if problems:
        raise ParameterError(problems)
    return result


async def steps_using(session: AsyncSession, operation: str) -> list[str]:
    """Names of the templates that use an operation, e.g. before deleting it."""
    rows = await session.scalars(
        select(OperationTemplate.name)
        .join(TemplateStep, TemplateStep.template_id == OperationTemplate.id)
        .where(TemplateStep.operation == operation)
        .distinct()
    )
    return sorted(rows)

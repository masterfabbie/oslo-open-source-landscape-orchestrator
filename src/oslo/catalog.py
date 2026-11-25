"""Catalog of the operations the tool offers.

Each operation is described once: which targets it applies to, which role it needs and
whether it may run as a mass operation. Menus, mass operations and the API are built from
this catalog. Besides the built-in operations it holds the custom operations defined by an
admin (see customops.py); they run scripts configured in the host agent's operations.d,
like LaMa's custom operations, and appear everywhere without further changes. Operation
templates (chains of the other operations, templates.py) are part of it as well.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .customspec import CustomSpec, ParameterSpec, spec_applies
from .models import CustomOperation, Instance, OperationTemplate
from .operations import OperationKind, TargetType
from .templatespec import StepSpec, TemplateSpec
from .users import Role, has_role


@dataclass(frozen=True)
class OperationDef:
    key: str
    kind: OperationKind
    targets: frozenset[TargetType]
    role: Role
    mass: bool = True
    # Stops or restarts something; shown in red.
    danger: bool = False
    custom: CustomSpec | None = None
    # An operation template: a graph of the other operations (templatespec.py).
    template: TemplateSpec | None = None
    # False: only as a step of a template, not in menus, the landscape or schedules.
    standalone: bool = True
    # Menu in the landscape: "Kernel" or "Automation/Kernel"; built-in ones use translation
    # keys ("cat.instance_agent"); empty for the main buttons (start, stop, restart,
    # discovery) and for custom operations without a category ("More").
    category: str = ""

    @property
    def name(self) -> str | None:
        if self.template is not None:
            return self.template.name
        return self.custom.name if self.custom else None

    def label_key(self, target: str) -> str:
        """Translation key, e.g. "op.start_system"; for custom operations and templates their
        name, which the translation returns unchanged."""
        if self.template is not None:
            return self.template.name
        if self.custom is not None:
            return self.custom.name
        return f"op.{self.key}_system" if target == TargetType.SYSTEM else f"op.{self.key}"

    def applies_to(self, instance: Instance | None) -> bool:
        """Whether an instance has one of the instance types of a custom operation."""
        if self.custom is None or instance is None:
            return True
        return spec_applies(self.custom, instance)


_SYSTEM_AND_INSTANCE = frozenset({TargetType.SYSTEM, TargetType.INSTANCE})
INSTANCE_AGENT = "cat.instance_agent"
OSLO_CATEGORY = "cat.oslo"
MAX_CATEGORY_PART = 40


class CategoryError(ValueError):
    pass


def check_category(text: str | None) -> str:
    """A category as stored: at most two levels separated by "/", e.g. "Automation/Kernel";
    spaces around the levels are removed. Raises CategoryError."""
    if not text or not text.strip():
        return ""
    parts = [" ".join(part.split()) for part in text.split("/")]
    if len(parts) > 2:
        raise CategoryError("A category has at most two levels, e.g. Automation/Kernel")
    if any(not part or len(part) > MAX_CATEGORY_PART for part in parts):
        raise CategoryError(f"Each level of a category has 1 to {MAX_CATEGORY_PART} characters")
    if any(part.startswith("cat.") for part in parts):
        raise CategoryError("Categories starting with 'cat.' are reserved")
    return "/".join(parts)

_INSTANCE = frozenset({TargetType.INSTANCE})

BUILT_IN: tuple[OperationDef, ...] = (
    OperationDef("start", OperationKind.START, _SYSTEM_AND_INSTANCE, Role.OPERATOR),
    OperationDef("stop", OperationKind.STOP, _SYSTEM_AND_INSTANCE, Role.OPERATOR, danger=True),
    OperationDef(
        "restart", OperationKind.RESTART, _SYSTEM_AND_INSTANCE, Role.OPERATOR, danger=True
    ),
    OperationDef(
        "discover", OperationKind.DISCOVER, frozenset({TargetType.HOST}), Role.CONFIGURATOR
    ),
    # The instance agent (sapstartsrv) through the host agent.
    OperationDef(
        "register", OperationKind.REGISTER, _INSTANCE, Role.OPERATOR, category=INSTANCE_AGENT
    ),
    OperationDef(
        "unregister",
        OperationKind.UNREGISTER,
        _INSTANCE,
        Role.OPERATOR,
        danger=True,
        category=INSTANCE_AGENT,
    ),
    OperationDef(
        "reregister",
        OperationKind.REREGISTER,
        _INSTANCE,
        Role.OPERATOR,
        danger=True,
        category=INSTANCE_AGENT,
    ),
    # Installs the active OSLO operations bundle into operations.d (bundles.py).
    OperationDef(
        "update_bundle",
        OperationKind.UPDATE_BUNDLE,
        frozenset({TargetType.HOST}),
        Role.ADMIN,
        category=OSLO_CATEGORY,
    ),
)
BUILT_IN_KEYS = frozenset(op.key for op in BUILT_IN)
# Kept for code that only needs the built-in operations.
CATALOG = BUILT_IN


def spec_of(operation: CustomOperation) -> CustomSpec:
    return CustomSpec(
        id=operation.id,
        name=operation.name,
        description=operation.description,
        agent_operation=operation.agent_operation,
        target=operation.target,
        instance_types=tuple(t for t in operation.instance_types.split(",") if t),
        ordering=operation.ordering,
        timeout_seconds=operation.timeout_seconds,
        locks=operation.locks,
        parameters=tuple(
            ParameterSpec(p.name, p.label, p.type, p.required, p.default, p.pattern, p.help)
            for p in operation.parameters
        ),
    )


def definition_of(operation: CustomOperation) -> OperationDef:
    return OperationDef(
        key=operation.key,
        kind=OperationKind.CUSTOM,
        targets=frozenset({TargetType(operation.target)}),
        role=Role(operation.role),
        mass=operation.mass,
        custom=spec_of(operation),
        standalone=operation.standalone,
        category=operation.category or "",
    )


def template_spec(
    template: OperationTemplate, known: dict[str, OperationDef]
) -> TemplateSpec | None:
    """None if a step uses an operation that no longer exists."""
    steps = []
    for step in template.steps:
        operation = known.get(step.operation)
        if (
            operation is None
            or operation.template is not None
            or step.target_type not in operation.targets
        ):
            return None
        steps.append(
            StepSpec(
                position=step.position,
                operation=step.operation,
                kind=operation.kind.value,
                target_type=step.target_type,
                targets=tuple(json.loads(step.targets or "[]")),
                after=tuple(json.loads(step.after or "[]")),
                on_error=step.on_error,
                parameters=json.loads(step.parameters or "{}"),
                ask=tuple(json.loads(step.ask or "[]")),
                custom=operation.custom,
            )
        )
    return TemplateSpec(
        id=template.id,
        key=template.key,
        name=template.name,
        description=template.description,
        selection=template.target or None,
        steps=tuple(steps),
    )


def template_definition(
    template: OperationTemplate, known: dict[str, OperationDef]
) -> OperationDef | None:
    spec = template_spec(template, known)
    if spec is None:
        return None
    # A dialog template runs on the selection (one run for all selected targets); a
    # template with fixed targets only has no target in the landscape.
    return OperationDef(
        key=template.key,
        kind=OperationKind.TEMPLATE,
        targets=frozenset({TargetType(spec.selection)}) if spec.selection else frozenset(),
        role=Role(template.role),
        mass=True,
        template=spec,
        category=template.category or "",
    )


class Catalog:
    """The built-in operations plus the custom operations of one application.

    The custom operations are read from the database at startup and after each change.
    """

    def __init__(self) -> None:
        self._custom: tuple[OperationDef, ...] = ()
        self._templates: tuple[OperationDef, ...] = ()

    async def reload(self, session: AsyncSession) -> None:
        rows = await session.scalars(select(CustomOperation).order_by(CustomOperation.name))
        self._custom = tuple(definition_of(op) for op in rows)
        known = {op.key: op for op in BUILT_IN + self._custom}
        templates = await session.scalars(
            select(OperationTemplate).order_by(OperationTemplate.name)
        )
        self._templates = tuple(
            d for d in (template_definition(t, known) for t in templates) if d is not None
        )

    def all(self) -> tuple[OperationDef, ...]:
        return BUILT_IN + self._custom + self._templates

    def steps(self) -> tuple[OperationDef, ...]:
        """Operations a template may use as a step: all but templates."""
        return BUILT_IN + self._custom

    def get(self, key: str) -> OperationDef | None:
        return next((op for op in self.all() if op.key == key), None)

    def for_target(
        self, target: TargetType | str, user=None, *, mass: bool = False, instance=None
    ) -> list[OperationDef]:
        """Operations for a target type that run on their own (not only as template steps);
        with ``user`` only those the user may run, with ``instance`` only those that apply to
        its instance type."""
        return [
            op
            for op in self.all()
            if target in op.targets
            and op.standalone
            and (not mass or op.mass)
            and (user is None or has_role(user, op.role))
            and op.applies_to(instance)
        ]


_BUILT_IN_CATALOG = Catalog()


def get(key: str) -> OperationDef | None:
    """A built-in operation."""
    return _BUILT_IN_CATALOG.get(key)


def for_target(target: TargetType | str, user=None, *, mass: bool = False) -> list[OperationDef]:
    """Built-in operations for a target type."""
    return _BUILT_IN_CATALOG.for_target(target, user, mass=mass)

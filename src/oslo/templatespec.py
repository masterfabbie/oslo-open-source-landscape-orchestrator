"""Description of an operation template: steps with their targets, run as a graph.

A step starts when all its predecessors (``after``) have finished; steps without a path
between them run in parallel, like the steps of an operation template in LaMa. Each step
runs on fixed targets or on the "$selection" chosen when the template starts (a dialog
template, started from the landscape). Kept free of the catalog and the runner, which both
use it. A snapshot of the template (``TemplateSpec.to_dict``) is stored with each activity
that runs it, so later changes do not affect running templates.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .customspec import CustomSpec, ParameterSpec

ON_ERROR = ("stop", "continue", "stop_and_start")
STEP_TARGETS = ("INSTANCE", "SYSTEM", "HOST")
BUILT_IN_NAMES = {
    "START": "Start",
    "STOP": "Stop",
    "RESTART": "Restart",
    "DISCOVER": "Discovery",
    "REGISTER": "Register instance agent",
    "UNREGISTER": "Unregister instance agent",
    "REREGISTER": "Re-register instance agent",
    "UPDATE_BUNDLE": "Update OSLO operations",
}
# Parameters of a step are passed in a run as "<position>.<NAME>", e.g. "3.KRNLREL".
SEPARATOR = "."
SELECTION = "$selection"


@dataclass(frozen=True)
class StepSpec:
    position: int
    operation: str  # key of a built-in or custom operation
    kind: str  # START, STOP, RESTART, DISCOVER or CUSTOM
    target_type: str  # INSTANCE, SYSTEM or HOST
    # Fixed targets; empty: the selection of the run.
    targets: tuple[int, ...] = ()
    # Positions of the steps that must have finished first.
    after: tuple[int, ...] = ()
    on_error: str = "stop"
    # Values of the custom operation's parameters (name -> value).
    parameters: dict[str, str] = field(default_factory=dict)
    # Names of parameters asked for when the template starts.
    ask: tuple[str, ...] = ()
    custom: CustomSpec | None = None

    @property
    def on_selection(self) -> bool:
        return not self.targets

    @property
    def locks(self) -> bool:
        return self.custom.locks if self.custom else True

    @property
    def name(self) -> str:
        """For the (English) log: the custom operation's name or e.g. "Stop"."""
        return self.custom.name if self.custom else BUILT_IN_NAMES.get(self.kind, self.operation)

    def label_key(self) -> str:
        """For the interface: a translation key like "op.stop_system", or the custom
        operation's name, which the translation returns unchanged."""
        if self.custom:
            return self.custom.name
        if self.target_type == "SYSTEM":
            return f"op.{self.operation}_system"
        return f"op.{self.operation}"

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "operation": self.operation,
            "kind": self.kind,
            "target_type": self.target_type,
            "targets": list(self.targets),
            "after": list(self.after),
            "on_error": self.on_error,
            "parameters": dict(self.parameters),
            "ask": list(self.ask),
            "custom": self.custom.to_dict() if self.custom else None,
        }

    @classmethod
    def from_dict(cls, data: dict, legacy_target: str = "SYSTEM") -> StepSpec:
        """Snapshots from before migration 0008 were chains on the template's target, with
        every parameter asked for."""
        custom = CustomSpec.from_dict(data["custom"]) if data.get("custom") else None
        position = data["position"]
        legacy = "target_type" not in data
        return cls(
            position=position,
            operation=data["operation"],
            kind=data["kind"],
            target_type=legacy_target if legacy else data["target_type"],
            targets=tuple(data.get("targets") or ()),
            after=((position - 1,) if position > 1 else ())
            if legacy
            else tuple(data.get("after") or ()),
            on_error=data.get("on_error", "stop"),
            parameters=dict(data.get("parameters") or {}),
            ask=tuple(p.name for p in custom.parameters) if legacy and custom else tuple(
                data.get("ask") or ()
            ),
            custom=custom,
        )

    def run_parameters(self) -> list[ParameterSpec]:
        """The parameters a run asks for, named "<position>.<NAME>", with the template's
        values as defaults."""
        if self.custom is None:
            return []
        return [
            ParameterSpec(
                name=f"{self.position}{SEPARATOR}{p.name}",
                label=f"{self.position}. {self.custom.name}: {p.label}",
                type=p.type,
                required=p.required,
                default=self.parameters.get(p.name, p.default),
                pattern=p.pattern,
                help=p.help,
            )
            for p in self.custom.parameters
            if p.name in self.ask
        ]


@dataclass(frozen=True)
class TemplateSpec:
    id: int
    key: str
    name: str
    description: str | None
    # Type of the selection the steps without fixed targets run on; None: none needed.
    selection: str | None
    steps: tuple[StepSpec, ...]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "selection": self.selection,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TemplateSpec:
        legacy = data.get("target") if "selection" not in data else None
        return cls(
            id=data["id"],
            key=data["key"],
            name=data["name"],
            description=data.get("description"),
            selection=legacy or data.get("selection"),
            steps=tuple(StepSpec.from_dict(s, legacy or "SYSTEM") for s in data["steps"]),
        )

    def step(self, position: int) -> StepSpec:
        return next(s for s in self.steps if s.position == position)

    def run_parameters(self) -> list[ParameterSpec]:
        return [p for step in self.steps for p in step.run_parameters()]


def cycle(steps: Iterable[StepSpec]) -> list[int] | None:
    """Positions forming a cycle of predecessors, or None."""
    after = {s.position: s.after for s in steps}
    state: dict[int, int] = {}  # 1: on the path, 2: done
    path: list[int] = []

    def visit(position: int) -> list[int] | None:
        state[position] = 1
        path.append(position)
        for previous in after.get(position, ()):
            if state.get(previous) == 1:
                return path[path.index(previous) :]
            if previous not in state and (found := visit(previous)):
                return found
        path.pop()
        state[position] = 2
        return None

    for position in after:
        if position not in state and (found := visit(position)):
            return found
    return None


def ancestors(steps: Iterable[StepSpec]) -> dict[int, set[int]]:
    """position -> all steps that finish before it starts (for a graph without cycles)."""
    after = {s.position: s.after for s in steps}
    result: dict[int, set[int]] = {}

    def of(position: int) -> set[int]:
        if position not in result:
            result[position] = set()
            for previous in after.get(position, ()):
                result[position] |= {previous} | of(previous)
        return result[position]

    for position in after:
        of(position)
    return result


def parallel_pairs(steps: Iterable[StepSpec]) -> list[tuple[StepSpec, StepSpec]]:
    """Pairs of steps that may run at the same time: neither comes before the other."""
    steps = list(steps)
    before = ancestors(steps)
    return [
        (a, b)
        for i, a in enumerate(steps)
        for b in steps[i + 1 :]
        if a.position not in before[b.position] and b.position not in before[a.position]
    ]

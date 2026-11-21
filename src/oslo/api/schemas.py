"""Request and response models of the REST API. Passwords are never returned."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class HostCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    hostagent_port: int | None = Field(default=None, ge=1, le=65535)
    https: bool = False
    verify_tls: bool = True
    sapcontrol_port_offset: int = Field(default=0, ge=0, le=15000)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1)


class HostUpdate(BaseModel):
    """Connection data; omitted fields stay unchanged. hostagent_port 0 means the default."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    hostagent_port: int | None = Field(default=None, ge=0, le=65535)
    https: bool | None = None
    verify_tls: bool | None = None
    sapcontrol_port_offset: int | None = Field(default=None, ge=0, le=15000)


class InstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    sid_id: int
    sid: str = Field(validation_alias=AliasChoices("sid_name", "sid"))
    # None while the instance is not assigned to a system.
    system_id: int | None
    number: str
    # SID/number, with the instance hostname if SID/number exist on several hosts.
    label: str
    # database, central, application or agent; agents are left out of system operations.
    role: str
    hostname: str
    sap_version_info: str | None
    features: str | None
    # Translation key of the instance type, e.g. "itype.abap".
    type_key: str | None = None
    start_priority: str | None
    last_status: str
    status_checked_at: datetime | None


class InstanceListOut(InstanceOut):
    # For an unassigned instance: the system that already holds instances of its SID.
    suggested_system_id: int | None = None


class DatabaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    name: str
    type: str
    instance_name: str | None
    vendor: str | None
    release: str | None
    last_status: str
    status_checked_at: datetime | None


class HostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    hostagent_port: int | None
    https: bool
    verify_tls: bool
    sapcontrol_port_offset: int
    username: str | None
    has_credentials: bool
    os_name: str | None
    os_version: str | None
    cpu_count: int | None
    memory_kb: int | None
    reachable: bool | None
    last_error: str | None
    last_discovery_at: datetime | None
    # E.g. "7.22 PL72", read at the last discovery.
    hostagent_version: str | None
    # E.g. ["dev", "sla=1"].
    tags: list[str] = Field(validation_alias=AliasChoices("tag_list", "tags"))


class HostDetail(HostOut):
    instances: list[InstanceOut]
    databases: list[DatabaseOut]


class SidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str | None
    has_credentials: bool


class SystemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    tags: list[str] = Field(validation_alias=AliasChoices("tag_list", "tags"))
    pool_id: int | None
    stage: str | None = None
    depends_on_ids: list[int]
    required_by_ids: list[int]
    instances: list[InstanceOut]


class DiscoveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instances_added: list[str]
    instances_updated: list[str]
    instances_missing: list[str]
    databases_added: list[str]
    databases_updated: list[str]
    databases_missing: list[str]
    warnings: list[str]


class ActivityLogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    level: str
    message: str
    # For the timeline: request_start, request_stop, status or op_started; the instance or
    # host the line is about; for status the status per instance label.
    event: str | None = None
    subject: str | None = None
    data: dict[str, str] | None = None

    @field_validator("data", mode="before")
    @classmethod
    def _parse_data(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    target_type: str
    target_label: str
    requested_by: str | None
    system_id: int | None
    instance_id: int | None
    host_id: int | None
    # The mass operation this activity belongs to.
    parent_id: int | None
    status: str
    timeout_seconds: int
    error: str | None
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ActivityDetail(ActivityOut):
    entries: list[ActivityLogEntryOut]
    # Children of a mass operation.
    children: list[ActivityOut]
    # Settings: of a mass operation (parallel, stop_on_error, targets) or of a custom
    # operation (custom: its definition, parameters: the values passed).
    options: dict | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _parse_options(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value


class ParameterDef(BaseModel):
    """A parameter of a custom operation; passed to the host agent as PARAM-<name>."""

    name: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=128)
    type: Literal["STRING", "INTEGER", "BOOLEAN"] = "STRING"
    required: bool = False
    default: str | None = Field(default=None, max_length=255)
    # Regular expression a string must match completely; empty: [A-Za-z0-9._-]*
    pattern: str | None = Field(default=None, max_length=255)
    help: str | None = None


class OperationOut(BaseModel):
    key: str
    name: str | None = None
    targets: list[str]
    role: str
    mass: bool
    custom: bool = False
    # Locks its target (custom operations can lock nothing, e.g. reading logs).
    locks: bool = True
    # False: only as a step of an operation template.
    standalone: bool = True
    parameters: list[ParameterDef] = []


class CustomOperationIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    # "Name:" of the configuration file in operations.d of the host agent.
    agent_operation: str = Field(min_length=1, max_length=128)
    target: Literal["INSTANCE", "SYSTEM", "HOST"]
    instance_types: list[str] = []
    ordering: Literal["parallel", "roles", "sequential"] = "parallel"
    role: Literal["viewer", "operator", "configurator", "admin"] = "configurator"
    mass: bool = True
    # Locks the instance, system or host like start and stop; off for read-only scripts.
    locks: bool = True
    # False: only as a step of an operation template, not in menus or the landscape.
    standalone: bool = True
    timeout_seconds: int = Field(default=600, ge=10, le=86400)
    parameters: list[ParameterDef] = Field(default=[], max_length=50)


class CustomOperationOut(CustomOperationIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    instance_types: list[str]
    parameters: list[ParameterDef]


class RunIn(BaseModel):
    # Values of the parameters by name, e.g. {"KRNLREL": "793", "ONLYPREPARE": true}.
    parameters: dict[str, str | int | bool] = {}


class MassOperationIn(BaseModel):
    operation: str
    target_type: Literal["SYSTEM", "INSTANCE", "HOST"]
    target_ids: list[int] = Field(min_length=1, max_length=500)
    parallel: int = Field(default=5, ge=1, le=20)
    stop_on_error: bool = False
    # For custom operations: parameter values by name.
    parameters: dict[str, str | int | bool] = {}


class SystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    instance_ids: list[int] = Field(min_length=1, max_length=200)
    pool_id: int | None = None


Stage = Literal["sandbox", "development", "quality", "preprod", "production"]


class SystemUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)
    # Left out: unchanged; null: no stage.
    stage: Stage | None = None


class InstanceIds(BaseModel):
    instance_ids: list[int] = Field(min_length=1, max_length=200)


class TagsIn(BaseModel):
    # E.g. ["dev", "sla=1"]; replaces all tags.
    tags: list[str] = Field(max_length=50)


class RefreshOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    system: SystemOut
    warnings: list[str]


class DependenciesIn(BaseModel):
    depends_on: list[int] = Field(max_length=100)


class PoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=1000)


class PoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    system_ids: list[int]


class PoolAssignment(BaseModel):
    pool_id: int | None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None
    role: str
    active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None


Role = Literal["viewer", "operator", "configurator", "admin"]


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    role: Role
    # Start password; the user must change it at the first sign-in.
    password: str = Field(min_length=1)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=1)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expires_at: datetime | None = None


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class NewTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Shown only once; only a hash is stored.
    token: str
    info: TokenOut


class TemplateStepIn(BaseModel):
    # Number of the step; predecessors refer to it. Default: its place in the list.
    position: int | None = Field(default=None, ge=1, le=999)
    # Key of a built-in or custom operation.
    operation: str
    target_type: Literal["INSTANCE", "SYSTEM", "HOST"]
    # Fixed targets; empty: the selection chosen when the template starts.
    targets: list[int] = Field(default=[], max_length=100)
    # Positions of the steps that must have finished first; empty: from the start.
    after: list[int] = Field(default=[], max_length=50)
    # Values of the custom operation's parameters.
    parameters: dict[str, str] = {}
    # Parameters asked for when the template starts (the value above as default).
    ask: list[str] = []
    on_error: Literal["stop", "continue", "stop_and_start"] = "stop"


class TemplateIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    role: Literal["viewer", "operator", "configurator", "admin"] = "operator"
    steps: list[TemplateStepIn] = Field(min_length=1, max_length=50)


class StepTargetOut(BaseModel):
    id: int
    # Name of the target; null if it no longer exists.
    label: str | None


class TemplateStepOut(TemplateStepIn):
    position: int
    # Name of the operation (custom) or its key (built-in); null if it no longer exists.
    name: str | None
    target_labels: list[StepTargetOut] = []


class TemplateOut(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    # Type of the selection ("$selection") the steps without fixed targets run on; null if
    # every step has fixed targets.
    selection: str | None
    role: str
    steps: list[TemplateStepOut]
    # False if a step uses an operation that no longer exists; the template is then not
    # offered for running.
    valid: bool


class TemplateRunIn(RunIn):
    # The selection; empty for a template with fixed targets only.
    target_ids: list[int] = Field(default=[], max_length=500)


class ScheduleIn(BaseModel):
    operation: str
    # "" and no targets for a template with fixed targets only.
    target_type: Literal["SYSTEM", "INSTANCE", "HOST", ""]
    target_ids: list[int] = Field(default=[], max_length=500)
    parameters: dict[str, str | int | bool] = {}
    recurrence: Literal["once", "daily", "interval"]
    # once: the moment (with time zone); daily: time_of_day local time and weekdays
    # (1 = Monday, e.g. "12345"); interval: every interval_minutes (at least 5).
    run_at: datetime | None = None
    time_of_day: str | None = None
    weekdays: str = "1234567"
    interval_minutes: int | None = None
    enabled: bool = True


class ScheduleOut(ScheduleIn):
    id: int
    created_by: str
    created_at: datetime
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_activity_id: int | None
    last_error: str | None


class BuildingBlocksOut(BaseModel):
    # Keys of the operations used most often in the last 90 days, by all users.
    top: list[str]
    # Keys the user marked as favorites.
    favorites: list[str]
    # Every operation a step may use, as in /api/landscape (also those only for templates).
    operations: list[dict] = []


class FavoritesIn(BaseModel):
    operations: list[str] = Field(default=[], max_length=100)


class AttentionRulesIn(BaseModel):
    # Rule -> settings; see attention.DEFAULT_RULES. Missing rules and settings: defaults.
    rules: dict[str, dict]


class AttentionExceptionsIn(BaseModel):
    disabled_rules: list[str] = Field(default=[], max_length=20)
    hidden_systems: list[int] = Field(default=[], max_length=1000)
    hidden_pools: list[int] = Field(default=[], max_length=1000)

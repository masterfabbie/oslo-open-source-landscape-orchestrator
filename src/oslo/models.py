"""Inventory: hosts, SIDs, instances, systems, pools and databases.

A *system* is a group of instances put together by the user, e.g. an ABAP system with its
HANA database. Its instances may belong to different SIDs. Discovery finds instances and
SIDs; it never creates systems.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    column_property,
    foreign,
    mapped_column,
    relationship,
)

from .roles import Role, instance_role, instance_type_key

# Stages of systems, in the order of the overview's columns.
STAGES = ("sandbox", "development", "quality", "preprod", "production")
STATUS_UNKNOWN = "UNKNOWN"


class Base(DeclarativeBase):
    pass


system_dependencies = Table(
    "system_dependencies",
    Base.metadata,
    Column("system_id", ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True),
    Column("depends_on_id", ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True),
)

# A system belongs to at most one pool, hence system_id alone is the key.
pool_systems = Table(
    "pool_systems",
    Base.metadata,
    Column("system_id", ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True),
    Column("pool_id", ForeignKey("pools.id", ondelete="CASCADE"), nullable=False, index=True),
)

activity_systems = Table(
    "activity_systems",
    Base.metadata,
    Column("activity_id", ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
    Column("system_id", ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True),
)

# Hosts an activity locks besides its own host_id, e.g. the hosts of an operation template.
activity_hosts = Table(
    "activity_hosts",
    Base.metadata,
    Column("activity_id", ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
    Column("host_id", ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True),
)


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    # Hostname or IP used to connect; ``name`` is what the landscape calls the host.
    address: Mapped[str] = mapped_column(String(255))
    hostagent_port: Mapped[int | None] = mapped_column(Integer)
    https: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    # Added to the default sapstartsrv ports (5NN13). Only needed for test setups where
    # several simulated hosts share one machine.
    sapcontrol_port_offset: Mapped[int] = mapped_column(Integer, default=0)

    username: Mapped[str | None] = mapped_column(String(255))
    password_encrypted: Mapped[str | None] = mapped_column(Text)

    os_name: Mapped[str | None] = mapped_column(String(255))
    os_version: Mapped[str | None] = mapped_column(String(255))
    cpu_count: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)

    reachable: Mapped[bool | None] = mapped_column(Boolean)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    instances: Mapped[list[Instance]] = relationship(
        back_populates="host",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Instance.number",
    )
    databases: Mapped[list[Database]] = relationship(
        back_populates="host",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Database.name",
    )
    agent_info: Mapped[HostAgentInfo | None] = relationship(
        back_populates="host", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin"
    )
    tags: Mapped[list[HostTag]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="HostTag.key",
    )

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password_encrypted)

    @property
    def tag_list(self) -> list[str]:
        return [tag.text for tag in self.tags]

    @property
    def hostagent_version(self) -> str | None:
        return self.agent_info.display if self.agent_info else None


class HostAgentInfo(Base):
    """Version of the host agent, read at each discovery.

    A separate table so that existing databases get it at startup without a migration.
    """

    __tablename__ = "host_agent_info"

    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True
    )
    release: Mapped[str] = mapped_column(String(16))
    patch: Mapped[str | None] = mapped_column(String(16))
    details: Mapped[str | None] = mapped_column(String(255))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    host: Mapped[Host] = relationship(back_populates="agent_info")

    @property
    def display(self) -> str:
        """E.g. "7.22 PL72"."""
        release = self.release
        if len(release) == 3 and release.isdigit():
            release = f"{release[0]}.{release[1:]}"
        return f"{release} PL{self.patch}" if self.patch else release


class Sid(Base):
    """An SAP system ID as reported by the host agent."""

    __tablename__ = "sids"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(8), unique=True)
    # Optional credentials of <sid>adm for the sapstartsrv of the instances of this SID.
    # Without them the credentials of the host are used.
    username: Mapped[str | None] = mapped_column(String(255))
    password_encrypted: Mapped[str | None] = mapped_column(Text)

    instances: Mapped[list[Instance]] = relationship(
        back_populates="sid", passive_deletes=True, order_by="Instance.number"
    )

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password_encrypted)


class System(Base):
    """A group of instances managed together, possibly of several SIDs."""

    __tablename__ = "systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Stage in the overview: sandbox, development, quality, preprod or production (STAGES).
    stage: Mapped[str | None] = mapped_column(String(16))

    instances: Mapped[list[Instance]] = relationship(
        back_populates="system", order_by="Instance.number"
    )
    # Other systems that must run for this one, e.g. a shared database system.
    depends_on: Mapped[list[System]] = relationship(
        secondary=system_dependencies,
        primaryjoin=lambda: System.id == system_dependencies.c.system_id,
        secondaryjoin=lambda: System.id == system_dependencies.c.depends_on_id,
        back_populates="required_by",
        order_by="System.name",
    )
    pool: Mapped[Pool | None] = relationship(
        secondary=pool_systems, back_populates="systems", uselist=False
    )
    tags: Mapped[list[SystemTag]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="SystemTag.key",
    )
    required_by: Mapped[list[System]] = relationship(
        secondary=system_dependencies,
        primaryjoin=lambda: System.id == system_dependencies.c.depends_on_id,
        secondaryjoin=lambda: System.id == system_dependencies.c.system_id,
        back_populates="depends_on",
        order_by="System.name",
    )

    @property
    def tag_list(self) -> list[str]:
        return [tag.text for tag in self.tags]

    @property
    def pool_id(self) -> int | None:
        return self.pool.id if self.pool else None

    @property
    def depends_on_ids(self) -> list[int]:
        return [system.id for system in self.depends_on]

    @property
    def required_by_ids(self) -> list[int]:
        return [system.id for system in self.required_by]


class _TagMixin:
    """A tag: a key with an optional value, e.g. "dev" or "sla=1". One value per key."""

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Empty for a tag without value.
    value: Mapped[str] = mapped_column(String(64), default="")

    @property
    def text(self) -> str:
        return f"{self.key}={self.value}" if self.value else self.key


class HostTag(_TagMixin, Base):
    __tablename__ = "host_tags"

    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True
    )


class SystemTag(_TagMixin, Base):
    __tablename__ = "system_tags"

    system_id: Mapped[int] = mapped_column(
        ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True
    )


class Pool(Base):
    """Systems that belong together, e.g. development, test and production of one product."""

    __tablename__ = "pools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    systems: Mapped[list[System]] = relationship(
        secondary=pool_systems, back_populates="pool", order_by="System.name"
    )

    @property
    def system_ids(self) -> list[int]:
        return [system.id for system in self.systems]


class Instance(Base):
    __tablename__ = "instances"
    __table_args__ = (UniqueConstraint("host_id", "sid_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    sid_id: Mapped[int] = mapped_column(ForeignKey("sids.id", ondelete="CASCADE"))
    # None while the instance is not assigned to a system.
    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="SET NULL"), index=True
    )
    number: Mapped[str] = mapped_column(String(2))
    # SAPLOCALHOST of the instance; may be a virtual hostname.
    hostname: Mapped[str] = mapped_column(String(255))
    sap_version_info: Mapped[str | None] = mapped_column(String(255))
    features: Mapped[str | None] = mapped_column(String(255))
    start_priority: Mapped[str | None] = mapped_column(String(16))
    last_status: Mapped[str] = mapped_column(String(16), default=STATUS_UNKNOWN)
    status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    host: Mapped[Host] = relationship(back_populates="instances")
    sid: Mapped[Sid] = relationship(back_populates="instances")
    system: Mapped[System | None] = relationship(back_populates="instances")

    @property
    def sid_name(self) -> str:
        return self.sid.name

    @property
    def label(self) -> str:
        """SID and instance number, e.g. DEV/00.

        If the same SID and number exist on several hosts, the instance hostname is added,
        e.g. DEV/00 (sapapp2).
        """
        label = f"{self.sid.name}/{self.number}"
        if (self.same_number_count or 0) > 1:
            label += f" ({self.hostname})"
        return label

    @property
    def role(self) -> Role:
        return instance_role(self.features)

    @property
    def is_agent(self) -> bool:
        return self.role is Role.AGENT

    @property
    def type_key(self) -> str | None:
        """Translation key of the instance type, e.g. "itype.abap"."""
        return instance_type_key(self.features)

    @property
    def priority(self) -> float:
        """Start priority as a number; unknown priorities start last."""
        try:
            return float(self.start_priority or "")
        except ValueError:
            return float("inf")


class Database(Base):
    __tablename__ = "databases"
    __table_args__ = (UniqueConstraint("host_id", "name", "type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32))
    instance_name: Mapped[str | None] = mapped_column(String(255))
    vendor: Mapped[str | None] = mapped_column(String(64))
    release: Mapped[str | None] = mapped_column(String(64))
    last_status: Mapped[str] = mapped_column(String(16), default=STATUS_UNKNOWN)
    status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    host: Mapped[Host] = relationship(back_populates="databases")


class Activity(Base):
    """One requested operation and its outcome. Kept as history when the target is deleted."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    target_type: Mapped[str] = mapped_column(String(16))
    target_label: Mapped[str] = mapped_column(String(255))
    system_id: Mapped[int | None] = mapped_column(
        ForeignKey("systems.id", ondelete="SET NULL"), index=True
    )
    instance_id: Mapped[int | None] = mapped_column(ForeignKey("instances.id", ondelete="SET NULL"))
    # Target of host operations, e.g. a discovery.
    host_id: Mapped[int | None] = mapped_column(ForeignKey("hosts.id", ondelete="SET NULL"))
    # The mass operation this activity belongs to.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), index=True
    )
    # Settings of a mass operation as JSON: operation, targets, parallel, stop_on_error.
    options: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # Username of whoever requested the activity.
    requested_by: Mapped[str | None] = mapped_column(String(64))
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # False for custom operations that lock nothing (e.g. reading logs): they run beside
    # other activities and do not keep others from starting.
    locks: Mapped[bool] = mapped_column(Boolean, default=True)

    # All systems the activity may touch; used to keep activities from overlapping.
    systems: Mapped[list[System]] = relationship(secondary=activity_systems)
    hosts: Mapped[list[Host]] = relationship(secondary=activity_hosts)
    children: Mapped[list[Activity]] = relationship(
        primaryjoin=lambda: Activity.id == foreign(Activity.parent_id),
        order_by="Activity.id",
        viewonly=True,
    )
    entries: Mapped[list[ActivityLogEntry]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityLogEntry.id",
    )


class ActivityLogEntry(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    level: Mapped[str] = mapped_column(String(8))
    message: Mapped[str] = mapped_column(Text)
    # Structured part for the timeline of the activity page (all optional): ``event`` is
    # request_start, request_stop, status or op_started; ``subject`` the instance (label)
    # or host the line is about; ``data`` JSON, for status the status per instance label.
    event: Mapped[str | None] = mapped_column(String(16))
    subject: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[str | None] = mapped_column(Text)

    activity: Mapped[Activity] = relationship(back_populates="entries")


# Number of instances with the same SID and instance number, on any host. A table alias is
# used because aliasing the mapped class here would configure the mappers too early.
_other_instance = Instance.__table__.alias("other_instance")
Instance.same_number_count = column_property(
    select(func.count(_other_instance.c.id))
    .where(
        _other_instance.c.sid_id == Instance.sid_id,
        _other_instance.c.number == Instance.number,
    )
    .correlate_except(_other_instance)
    .scalar_subquery(),
    # Keep the loaded value when the instance is updated; reloading it would need IO at
    # attribute access, which async sessions do not allow.
    expire_on_flush=False,
)


class User(Base):
    """A person who signs in. Roles: viewer < operator < configurator < admin."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Set for start passwords given by an admin; the user must choose a new one.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    # Increased to end all browser sessions, e.g. after a password or role change.
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ApiToken.id",
    )

    @property
    def label(self) -> str:
        return self.display_name or self.username


class ApiToken(Base):
    """Personal token for the REST API; only its SHA-256 hash is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # First characters of the token, to recognize it in lists.
    prefix: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="tokens")


class UserSetting(Base):
    """Per-user preferences, e.g. which landscape filters are shown."""

    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class PlatformSetting(Base):
    """Settings of the whole platform that admins change, e.g. the rules of the overview's
    "needs attention" list (key "attention.rules", JSON)."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class CustomOperation(Base):
    """An operation defined in the tool that runs a script configured in the host agent's
    operations.d, like a custom operation in LaMa's Automation Studio."""

    __tablename__ = "custom_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Used in URLs and the API, e.g. "copy_kernel".
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    # "Name:" in the configuration file in operations.d.
    agent_operation: Mapped[str] = mapped_column(String(128))
    # INSTANCE, SYSTEM (every matching instance of the system) or HOST.
    target: Mapped[str] = mapped_column(String(16))
    # Instance types it applies to (TYPE_VALUES of filters.py), comma separated; empty: all.
    instance_types: Mapped[str] = mapped_column(String(255), default="")
    # For SYSTEM: "parallel", "roles" (like a system start) or "sequential".
    ordering: Mapped[str] = mapped_column(String(16), default="parallel")
    role: Mapped[str] = mapped_column(String(16))
    mass: Mapped[bool] = mapped_column(Boolean, default=True)
    # Locks the instance, system or host like start and stop; off for read-only scripts.
    locks: Mapped[bool] = mapped_column(Boolean, default=True)
    # False: only as a step of an operation template, not in menus or the landscape.
    standalone: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    parameters: Mapped[list[CustomOperationParameter]] = relationship(
        back_populates="operation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CustomOperationParameter.position",
        lazy="selectin",
    )


class CustomOperationParameter(Base):
    """A parameter of a custom operation; passed to the host agent as PARAM-<name>."""

    __tablename__ = "custom_operation_parameters"
    __table_args__ = (UniqueConstraint("operation_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("custom_operations.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    # STRING, INTEGER or BOOLEAN.
    type: Mapped[str] = mapped_column(String(16))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    default: Mapped[str | None] = mapped_column(String(255))
    # Regular expression a string value must match completely; empty: the safe default.
    pattern: Mapped[str | None] = mapped_column(String(255))
    help: Mapped[str | None] = mapped_column(Text)

    operation: Mapped[CustomOperation] = relationship(back_populates="parameters")


class OperationTemplate(Base):
    """Steps of operations with their targets and values, run as a graph (steps after their
    predecessors, independent ones in parallel), like an operation template in LaMa (e.g.
    prepare kernel, stop, copy kernel, start)."""

    __tablename__ = "operation_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Shares the key space of custom operations, e.g. "kernel_update".
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    # Type of the "$selection" placeholder (INSTANCE, SYSTEM or HOST) the steps without
    # fixed targets run on, chosen when the template starts (a dialog template); "" if every
    # step has fixed targets (a template that runs as it is, e.g. scheduled).
    target: Mapped[str] = mapped_column(String(16))
    # Role needed to run the template; at least the highest role of its steps.
    role: Mapped[str] = mapped_column(String(16))
    # Unused since migration 0008: a selection of several targets is one run.
    mass: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list[TemplateStep]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TemplateStep.position",
        lazy="selectin",
    )


class TemplateStep(Base):
    __tablename__ = "template_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("operation_templates.id", ondelete="CASCADE"), index=True
    )
    # Number of the step within the template; predecessors refer to it.
    position: Mapped[int] = mapped_column(Integer)
    # Key of a built-in or custom operation of the catalog.
    operation: Mapped[str] = mapped_column(String(64))
    # INSTANCE, SYSTEM or HOST.
    target_type: Mapped[str] = mapped_column(String(16), default="")
    # Ids of fixed targets (JSON list); empty: the "$selection" of the run.
    targets: Mapped[str] = mapped_column(Text, default="[]")
    # Positions of the steps that must have finished first (JSON list); none: from the start.
    after: Mapped[str] = mapped_column(Text, default="[]")
    # Values of the parameters of a custom operation (name -> value, JSON).
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    # Names of parameters asked for when the template starts (JSON list), the template's
    # value as the default; the others are fixed.
    ask: Mapped[str] = mapped_column(Text, default="[]")
    # stop: start no further steps; continue: go on; stop_and_start: like stop, then start
    # the systems of the step again (steps on systems and instances).
    on_error: Mapped[str] = mapped_column(String(16), default="stop")

    template: Mapped[OperationTemplate] = relationship(back_populates="steps")


class Schedule(Base):
    """An operation (built-in, custom or template) planned for later, once or recurring."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(64))
    # "" for a template whose steps all have fixed targets.
    target_type: Mapped[str] = mapped_column(String(16))
    # Ids of the targets (JSON list); several run as one mass operation (a template: as its
    # selection).
    target_ids: Mapped[str] = mapped_column(Text)
    # Parameter values as in a run (JSON), for templates "<step>.<NAME>".
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    # once (run_at), daily (time_of_day on weekdays), interval (every interval_minutes).
    recurrence: Mapped[str] = mapped_column(String(16))
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_of_day: Mapped[str | None] = mapped_column(String(5))  # "22:00", local time
    weekdays: Mapped[str] = mapped_column(String(7), default="1234567")  # 1 = Monday
    interval_minutes: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The run happens with the rights of this user, checked again when it is due.
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_id: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)

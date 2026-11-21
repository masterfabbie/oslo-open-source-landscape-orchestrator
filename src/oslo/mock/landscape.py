"""In-memory model of a simulated SAP landscape.

Instances change state over time: a start request moves an instance to STARTING and,
after ``start_duration`` seconds, to RUNNING. State is resolved lazily from a timeline
of scheduled transitions, so no background tasks are needed and tests can use a fake clock.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

HOSTAGENT_PORT = 1128


class Status(Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"


STATUS_COLOR = {
    Status.STOPPED: "GRAY",
    Status.STARTING: "YELLOW",
    Status.RUNNING: "GREEN",
    Status.STOPPING: "YELLOW",
}
STATUS_TEXT = {
    Status.STOPPED: "Stopped",
    Status.STARTING: "Starting",
    Status.RUNNING: "Running",
    Status.STOPPING: "Stopping",
}


@dataclass(frozen=True)
class InstanceKind:
    features: str
    start_priority: str
    processes: tuple[tuple[str, str], ...]


# Start priorities follow the automatic calculation of sapstartsrv
# (HDB 0.3, ENQREP 0.5, (A)SCS 1, other 3).
INSTANCE_KINDS: dict[str, InstanceKind] = {
    "HDB": InstanceKind(
        "HDB|HDB_WORKER",
        "0.3",
        (
            ("hdbdaemon", "HDB Daemon"),
            ("hdbnameserver", "HDB Nameserver"),
            ("hdbindexserver", "HDB Indexserver"),
        ),
    ),
    "ERS": InstanceKind("ENQREP", "0.5", (("enq_replicator", "Enqueue Replicator"),)),
    "ASCS": InstanceKind(
        "MESSAGESERVER|ENQUE",
        "1",
        (("msg_server", "MessageServer"), ("enq_server", "Enqueue Server")),
    ),
    "SCS": InstanceKind(
        "MESSAGESERVER|ENQUE",
        "1",
        (("msg_server", "MessageServer"), ("enq_server", "Enqueue Server")),
    ),
    "ABAP": InstanceKind(
        "ABAP|GATEWAY|ICMAN|IGS",
        "3",
        (
            ("disp+work", "Dispatcher"),
            ("igswd_mt", "IGS Watchdog"),
            ("gwrd", "Gateway"),
            ("icman", "ICM"),
        ),
    ),
    "J2EE": InstanceKind(
        "J2EE|IGS", "3", (("jstart", "J2EE Server"), ("igswd_mt", "IGS Watchdog"))
    ),
    # Diagnostics agent of SAP Solution Manager. The feature SMDAGENT is confirmed by a real
    # system; its start priority and process names are assumptions.
    "SMDAGENT": InstanceKind("SMDAGENT", "3", (("jstart", "SMD Agent"),)),
}


@dataclass
class MockInstance:
    sid: str
    nr: int
    kind: str
    hostname: str
    # The instance's sapstartsrv is registered and running (it answers on its port).
    service_running: bool = True
    # Scheduled transitions, sorted by time. The first entry is the current state.
    _timeline: list[tuple[float, Status]] = field(default_factory=list, repr=False)
    _started_at: float | None = field(default=None, repr=False)

    @property
    def kind_info(self) -> InstanceKind:
        return INSTANCE_KINDS[self.kind]

    def status(self, now: float) -> Status:
        timeline = self._timeline
        while len(timeline) > 1 and timeline[1][0] <= now:
            timeline.pop(0)
            if timeline[0][1] is Status.STARTING:
                self._started_at = timeline[0][0]
        return timeline[0][1]

    def started_at(self, now: float) -> float | None:
        """Time the current run began, or None if the instance is stopped."""
        return None if self.status(now) is Status.STOPPED else self._started_at

    def schedule_start(self, now: float, duration: float, delay: float = 0.0) -> bool:
        """Schedule a start. Returns False if the instance is or will be running anyway."""
        self.status(now)
        last_time, last_status = self._timeline[-1]
        if last_status in (Status.STARTING, Status.RUNNING):
            return False
        begin = max(now + delay, last_time)
        self._timeline += [(begin, Status.STARTING), (begin + duration, Status.RUNNING)]
        self.status(now)
        return True

    def schedule_stop(self, now: float, duration: float, delay: float = 0.0) -> bool:
        """Schedule a stop. Returns False if the instance is or will be stopped anyway."""
        self.status(now)
        last_time, last_status = self._timeline[-1]
        if last_status in (Status.STOPPING, Status.STOPPED):
            return False
        begin = max(now + delay, last_time)
        self._timeline += [(begin, Status.STOPPING), (begin + duration, Status.STOPPED)]
        self.status(now)
        return True


@dataclass
class MockDatabase:
    name: str
    type: str
    # Instance number whose state the database follows; None means always running.
    instance_nr: int | None = None


@dataclass
class MockCustomOperation:
    """An operation configured in operations.d of the host agent.

    ``command`` lists the parameters in the order of the command line. As on a real host
    agent, parameters that are not passed are left out and the following ones move up.
    ``PARAM-SLEEP`` sets the duration in seconds (default 2), ``PARAM-RC`` the exit code.
    """

    name: str
    description: str
    command: tuple[str, ...]


@dataclass
class MockOperationRun:
    id: str
    host: str
    operation: MockCustomOperation
    arguments: list[str]
    started: float
    duration: float
    exit_code: int
    cancelled: bool = False


@dataclass
class MockHost:
    name: str
    bind: str = "127.0.0.1"
    port_offset: int = 0
    opsys: str = "Linux"
    instances: list[MockInstance] = field(default_factory=list)
    databases: list[MockDatabase] = field(default_factory=list)

    @property
    def hostagent_port(self) -> int:
        return HOSTAGENT_PORT + self.port_offset

    def sapcontrol_port(self, nr: int) -> int:
        return 50013 + 100 * nr + self.port_offset

    def instance(self, nr: int) -> MockInstance | None:
        return next((i for i in self.instances if i.nr == nr), None)


class MockLandscape:
    def __init__(
        self,
        hosts: list[MockHost],
        users: dict[str, str] | None = None,
        start_duration: float = 3.0,
        stop_duration: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        strict_sapstartsrv_auth: bool = False,
        custom_operations: list[MockCustomOperation] | None = None,
    ) -> None:
        self.hosts = hosts
        # Configured in operations.d of every host, like a shared configuration.
        self.custom_operations = {op.name: op for op in custom_operations or []}
        self.operation_runs: dict[str, MockOperationRun] = {}
        self.users = users or {}
        # True: administrative sapstartsrv calls are allowed only to <sid>adm, as on real
        # systems; other known users get "Permission denied".
        self.strict_sapstartsrv_auth = strict_sapstartsrv_auth
        self.start_duration = start_duration
        self.stop_duration = stop_duration
        self.clock = clock

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], clock: Callable[[], float] = time.monotonic
    ) -> MockLandscape:
        now = clock()
        hosts = []
        for host_data in data["hosts"]:
            host = MockHost(
                name=host_data["name"],
                bind=host_data.get("bind", "127.0.0.1"),
                port_offset=host_data.get("port_offset", 0),
                opsys=host_data.get("opsys", "Linux"),
            )
            for inst in host_data.get("instances", []):
                if inst["kind"] not in INSTANCE_KINDS:
                    raise ValueError(f"Unknown instance kind: {inst['kind']!r}")
                running = inst.get("running", False)
                host.instances.append(
                    MockInstance(
                        sid=inst["sid"],
                        nr=int(inst["nr"]),
                        kind=inst["kind"],
                        hostname=inst.get("hostname", host.name),
                        _timeline=[(now, Status.RUNNING if running else Status.STOPPED)],
                        _started_at=now if running else None,
                    )
                )
            for db in host_data.get("databases", []):
                host.databases.append(MockDatabase(db["name"], db["type"], db.get("instance_nr")))
            hosts.append(host)
        return cls(
            hosts,
            users=data.get("users"),
            start_duration=data.get("start_duration", 3.0),
            stop_duration=data.get("stop_duration", 2.0),
            clock=clock,
            strict_sapstartsrv_auth=data.get("strict_sapstartsrv_auth", False),
            custom_operations=[
                MockCustomOperation(
                    op["name"], op.get("description", op["name"]), tuple(op["command"])
                )
                for op in data.get("custom_operations", [])
            ],
        )

    def start_operation(
        self, host: MockHost, operation: MockCustomOperation, arguments: dict[str, str]
    ) -> MockOperationRun:
        values = [arguments[key] for key in operation.command if arguments.get(key, "") != ""]
        try:
            duration = float(arguments.get("PARAM-SLEEP", "2"))
        except ValueError:
            duration = 2.0
        try:
            exit_code = int(arguments.get("PARAM-RC", "0"))
        except ValueError:
            exit_code = 0
        run = MockOperationRun(
            id=f"MOCK{len(self.operation_runs) + 1:028d}",
            host=host.name,
            operation=operation,
            arguments=values,
            started=self.clock(),
            duration=duration,
            exit_code=exit_code,
        )
        self.operation_runs[run.id] = run
        return run

    def operation_finished(self, run: MockOperationRun) -> bool:
        return run.cancelled or self.clock() >= run.started + run.duration

    def host(self, name: str) -> MockHost:
        for host in self.hosts:
            if host.name == name:
                return host
        raise KeyError(name)

    def system_instances(self, sid: str) -> list[tuple[MockHost, MockInstance]]:
        return [(h, i) for h in self.hosts for i in h.instances if i.sid == sid]

    def start_instance(self, instance: MockInstance) -> bool:
        return instance.schedule_start(self.clock(), self.start_duration)

    def stop_instance(self, instance: MockInstance) -> bool:
        return instance.schedule_stop(self.clock(), self.stop_duration)

    def restart_instance(self, instance: MockInstance) -> None:
        now = self.clock()
        instance.schedule_stop(now, self.stop_duration)
        instance.schedule_start(now, self.start_duration)

    def start_system(self, sid: str, kinds: set[str] | None = None) -> None:
        """Start instances in ascending priority order, one priority level after another."""
        self._run_system(sid, kinds, start=True)

    def stop_system(self, sid: str, kinds: set[str] | None = None) -> None:
        """Stop instances in descending priority order."""
        self._run_system(sid, kinds, start=False)

    def _run_system(self, sid: str, kinds: set[str] | None, start: bool) -> None:
        now = self.clock()
        duration = self.start_duration if start else self.stop_duration
        levels: dict[float, list[MockInstance]] = {}
        for _, inst in self.system_instances(sid):
            if kinds is None or inst.kind in kinds:
                levels.setdefault(float(inst.kind_info.start_priority), []).append(inst)
        delay = 0.0
        for priority in sorted(levels, reverse=not start):
            scheduled = False
            for inst in levels[priority]:
                if start:
                    scheduled |= inst.schedule_start(now, duration, delay)
                else:
                    scheduled |= inst.schedule_stop(now, duration, delay)
            if scheduled:
                delay += duration

    def database_status(self, host: MockHost, db: MockDatabase) -> Status:
        if db.instance_nr is None:
            return Status.RUNNING
        instance = host.instance(db.instance_nr)
        return instance.status(self.clock()) if instance else Status.STOPPED


def default_landscape_config() -> dict[str, Any]:
    """Sample landscape: ABAP system DEV on sapapp1, HANA system HDV on sapdb1.

    As in real landscapes, the HANA database has its own SID; DEV uses it as database.
    The HANA instance reports its system database and one tenant, like a real
    multi-tenant system.
    """
    return {
        "start_duration": 3,
        "stop_duration": 2,
        "users": {"devadm": "mock", "sapadm": "mock"},
        # Echoes its arguments like a test script; see MockCustomOperation.
        "custom_operations": [
            {
                "name": "OSLO_TEST",
                "description": "Test operation",
                "command": [
                    "SAPSYSTEMNAME",
                    "SAPSYSTEM",
                    "SERVICE_SUBTYPE",
                    "PARAM-A",
                    "PARAM-SLEEP",
                    "PARAM-RC",
                ],
            }
        ],
        "hosts": [
            {
                "name": "sapapp1",
                "port_offset": 0,
                "instances": [
                    {"sid": "DEV", "nr": 1, "kind": "ASCS", "running": True},
                    {"sid": "DEV", "nr": 0, "kind": "ABAP", "running": True},
                ],
            },
            {
                "name": "sapdb1",
                "port_offset": 10000,
                "instances": [{"sid": "HDV", "nr": 2, "kind": "HDB", "running": True}],
                "databases": [
                    {"name": "SYSTEMDB@HDV", "type": "hdb", "instance_nr": 2},
                    {"name": "HDV@HDV", "type": "hdb", "instance_nr": 2},
                ],
            },
        ],
    }

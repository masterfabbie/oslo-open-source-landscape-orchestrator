"""Client for the SAPHostControl web service of the SAP Host Agent (one host)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from ..soapxml import SAPHOSTCONTROL_NS, items
from .base import SoapClient, SoapFaultError, SoapProtocolError, as_dict

HOSTAGENT_HTTP_PORT = 1128
HOSTAGENT_HTTPS_PORT = 1129


class InstanceStatus(Enum):
    INSTALLED = "S-INSTALLED"
    RUNNING = "S-RUNNING"
    STOPPED = "S-STOPPED"


class DatabaseStatus(Enum):
    UNKNOWN = "SAPHostControl-DB-UNKNOWN"
    STOPPED = "SAPHostControl-DB-STOPPED"
    STOPPING = "SAPHostControl-DB-STOPPING"
    RUNNING = "SAPHostControl-DB-RUNNING"
    STARTING = "SAPHostControl-DB-STARTING"
    WARNING = "SAPHostControl-DB-WARNING"
    INSERVICE = "SAPHostControl-DB-INSERVICE"
    ERROR = "SAPHostControl-DB-ERROR"


class InstanceOption(Enum):
    INSTANCE = "O-INSTANCE"
    SERVICE = "O-SERVICE"
    PREHOOK = "O-PREHOOK"
    POSTHOOK = "O-POSTHOOK"
    CLEANUP = "O-CLEANUP"
    FORCE = "O-FORCE"
    ERRORHOOK = "O-ERRORHOOK"
    SERVICEONLY = "O-SERVICEONLY"
    NOSYSTEMD = "O-NOSYSTEMD"


@dataclass(frozen=True)
class SapInstance:
    sid: str
    hostname: str
    system_number: str
    sap_version_info: str


@dataclass(frozen=True)
class DatabaseComponent:
    name: str
    description: str
    status: DatabaseStatus
    status_description: str
    properties: dict[str, str]


@dataclass(frozen=True)
class Database:
    status: DatabaseStatus
    properties: dict[str, str]
    components: list[DatabaseComponent]

    @property
    def name(self) -> str:
        return self.properties.get("Database/Name", "")

    @property
    def type(self) -> str:
        return self.properties.get("Database/Type", "")


@dataclass(frozen=True)
class DatabaseState:
    status: DatabaseStatus
    components: list[DatabaseComponent]


@dataclass(frozen=True)
class CimAttribute:
    type: str
    value: str


@dataclass(frozen=True)
class CimObject:
    properties: dict[str, CimAttribute]
    members: list[CimObject] = field(default_factory=list)

    @property
    def class_name(self) -> str:
        return self.value("CreationClassName")

    def value(self, name: str, default: str = "") -> str:
        attribute = self.properties.get(name)
        return attribute.value if attribute else default

    def find(self, class_name: str) -> list[CimObject]:
        """This object and all nested members of the given class."""
        found = [self] if self.class_name == class_name else []
        for member in self.members:
            found += member.find(class_name)
        return found


@dataclass(frozen=True)
class LogMessage:
    """One line of an operation: severity (Info, Warning, Error), source and text.

    Source is the description of the operation for lines of the script and
    "saphostcontrol" for lines of the host agent itself.
    """

    severity: str
    source: str
    text: str

    @property
    def display(self) -> str:
        if self.source == "saphostcontrol":
            return f"saphostcontrol: {self.text}"
        return self.text


LOG_PREFIX = "LogMsg/"


def log_messages(entries: list[tuple[str, str]]) -> list[LogMessage]:
    """Group the messages of an operation into lines.

    A real host agent returns each line of a script as four messages with the keys
    LogMsg/TimeStamp, LogMsg/Severity, LogMsg/Source and LogMsg/Text. A line starts at
    LogMsg/TimeStamp or when a key repeats. Other messages become a line of their own with
    the key as severity.
    """
    lines: list[LogMessage] = []
    current: dict[str, str] | None = None

    def close() -> None:
        if current is not None:
            lines.append(
                LogMessage(
                    current.get("Severity", "Info") or "Info",
                    current.get("Source", ""),
                    current.get("Text", ""),
                )
            )

    for key, value in entries:
        if not key.startswith(LOG_PREFIX):
            close()
            current = None
            lines.append(LogMessage(key or "Info", "", value))
            continue
        name = key[len(LOG_PREFIX) :]
        if current is None or name == "TimeStamp" or name in current:
            close()
            current = {}
        current[name] = value
    close()
    return lines


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    messages: dict[str, str]
    # All messages in order; keys may repeat, e.g. for log lines.
    entries: list[tuple[str, str]] = field(default_factory=list)

    @property
    def log(self) -> list[LogMessage]:
        """The messages grouped into lines (see :func:`log_messages`)."""
        return log_messages(self.entries)


# Fault codes of the host agent's OperationException, as seen on a real host agent.
FAULT_TIMEOUT = 255  # GetOperationResults: the operation is still running
FAULT_COMMAND_FAILED = 127  # the command ended with an exit code other than 0, or was cancelled
FAULT_UNKNOWN_OPERATION = -20  # "Operation ID not found"


class OperationFault(SoapFaultError):
    """A fault with the host agent's OperationException: fault code and messages."""

    def __init__(self, fault: SoapFaultError, code: int | None, result: OperationResult) -> None:
        super().__init__(fault.faultstring, fault.faultcode, fault.http_status, fault.detail)
        self.code = code
        self.result = result

    @classmethod
    def from_fault(cls, fault: SoapFaultError) -> OperationFault:
        detail = fault.detail
        try:
            code = int(detail.get("mFaultCode"))
        except (TypeError, ValueError):
            code = None
        result = _operation_result(
            {
                "mOperationID": detail.get("mOperationID"),
                "mOperationResults": detail.get("mResponseMessages"),
            }
        )
        return cls(fault, code, result)


@dataclass(frozen=True)
class HostAgentVersion:
    release: str
    patch: str
    # Version line of saphostexec, e.g. "722 (EXT), patch 1611, changelist ...".
    details: str

    @property
    def display(self) -> str:
        """E.g. "7.22 PL72", the way the host agent version is usually named."""
        release = self.release
        if len(release) == 3 and release.isdigit():
            release = f"{release[0]}.{release[1:]}"
        return f"{release} PL{self.patch}" if self.patch else release


_VERSION_FIELD = re.compile(r"(kernel release|patch number)\s{2,}(\S+)\s*$")
_SAPHOSTEXEC_LINE = re.compile(r"/saphostexec:\s*(.+?)\s*$")


def parse_version_info(result: OperationResult) -> HostAgentVersion | None:
    """Host agent version from the messages of the operation "versioninfo".

    Recognized are the lines "kernel release", "patch number" and the component line of
    saphostexec. Only the text of the messages is used, not their keys.
    """
    fields: dict[str, str] = {}
    details = ""
    for key, value in result.entries:
        for text in (value, f"{key}: {value}"):
            if match := _VERSION_FIELD.search(text):
                fields.setdefault(match.group(1), match.group(2))
            if not details and (match := _SAPHOSTEXEC_LINE.search(text)):
                details = match.group(1)
    if "kernel release" not in fields:
        return None
    return HostAgentVersion(fields["kernel release"], fields.get("patch number", ""), details)


def _property_dict(value: Any) -> dict[str, str]:
    return {item.get("mKey", ""): item.get("mValue", "") for item in map(as_dict, items(value))}


def _property_list(values: dict[str, str | None]) -> list[dict[str, str]]:
    return [{"mKey": key, "mValue": value} for key, value in values.items() if value is not None]


def _db_status(value: Any) -> DatabaseStatus:
    try:
        return DatabaseStatus(value)
    except ValueError as exc:
        raise SoapProtocolError(f"Unknown database status: {value!r}") from exc


def _components(value: Any) -> list[DatabaseComponent]:
    components = []
    for item in map(as_dict, items(value)):
        properties = _property_dict(item.get("mProperties"))
        components.append(
            DatabaseComponent(
                name=properties.get("Database/ComponentName", ""),
                description=properties.get("Database/ComponentDescription", ""),
                status=_db_status(item.get("mStatus")),
                status_description=properties.get("Database/ComponentStatusDescription", ""),
                properties=properties,
            )
        )
    return components


def _cim_object(value: Any) -> CimObject:
    data = as_dict(value)
    return CimObject(
        properties={
            item.get("mName", ""): CimAttribute(item.get("mType", ""), item.get("mValue", ""))
            for item in map(as_dict, items(data.get("mProperties")))
        },
        members=[_cim_object(member) for member in items(data.get("mMembers"))],
    )


def _operation_result(value: Any) -> OperationResult:
    data = as_dict(value)
    entries = [
        (item.get("mMessageKey", "") or "", item.get("mMessageValue", "") or "")
        for item in map(as_dict, items(data.get("mOperationResults")))
    ]
    return OperationResult(
        operation_id=data.get("mOperationID", "") or "",
        messages=dict(entries),
        entries=entries,
    )


class HostAgentClient(SoapClient):
    namespace = SAPHOSTCONTROL_NS
    path = "/SAPHostControl.cgi"

    def __init__(
        self,
        host: str,
        *,
        port: int | None = None,
        https: bool = False,
        auth: tuple[str, str] | None = None,
        verify: bool | str = True,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if port is None:
            port = HOSTAGENT_HTTPS_PORT if https else HOSTAGENT_HTTP_PORT
        scheme = "https" if https else "http"
        super().__init__(
            f"{scheme}://{host}:{port}",
            auth=auth,
            verify=verify,
            timeout=timeout,
            transport=transport,
        )
        self.host = host

    async def list_instances(
        self,
        status: InstanceStatus = InstanceStatus.INSTALLED,
        hostname: str | None = None,
    ) -> list[SapInstance]:
        """SAP instances on the host. ``hostname`` limits the list to one SAPLOCALHOST."""
        result = await self.call(
            "ListInstances",
            {"aSelector": {"aInstanceStatus": status.value, "aHostname": hostname}},
        )
        return [
            SapInstance(
                sid=item.get("mSid", ""),
                hostname=item.get("mHostname", ""),
                system_number=item.get("mSystemNumber", ""),
                sap_version_info=item.get("mSapVersionInfo", ""),
            )
            for item in map(as_dict, items(result.get("aInstances")))
        ]

    async def list_databases(self) -> list[Database]:
        result = await self.call("ListDatabases", {"aArguments": []})
        return [
            Database(
                status=_db_status(item.get("mStatus")),
                properties=_property_dict(item.get("mDatabase")),
                components=_components(item.get("mComponents")),
            )
            for item in map(as_dict, items(result.get("result")))
        ]

    async def get_database_status(
        self,
        name: str,
        type: str,
        *,
        instance_name: str | None = None,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> DatabaseState:
        """Overall status and components of one database.

        Database user and password are required for the types ``ada``, ``sap`` and ``db6``.
        """
        arguments = _property_list(
            {
                "Database/Name": name,
                "Database/Type": type,
                "Database/InstanceName": instance_name,
                "Database/Host": host,
                "Database/Username": username,
                "Database/Password": password,
            }
        )
        result = await self.call("GetDatabaseStatus", {"aArguments": arguments})
        return DatabaseState(
            status=_db_status(result.get("status")),
            components=_components(result.get("result")),
        )

    async def get_computer_system(self) -> CimObject:
        """Host information: computer system, operating system, file systems, processes."""
        result = await self.call("GetComputerSystem", {"aArguments": []})
        return _cim_object(result.get("result"))

    async def execute_operation(
        self, name: str, arguments: dict[str, str] | None = None, *, timeout: int = -1
    ) -> OperationResult:
        """Run a named operation, e.g. "versioninfo". ``timeout`` -1 waits until it is done.

        Confirmed with a real host agent for "versioninfo" and sapadm; the messages are its
        log lines.
        """
        result = await self.call(
            "ExecuteOperation",
            {
                "aOperation": name,
                "aArguments": _property_list(arguments or {}),
                "aOptions": {"mTimeout": timeout, "mOptions": [], "mSoftTimeout": 0},
            },
        )
        return _operation_result(result.get("result"))

    async def execute_async(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> OperationResult:
        """Start a named operation without waiting; the result carries the operation ID."""
        return await self.execute_operation(name, arguments, timeout=0)

    async def is_operation_finished(self, operation_id: str) -> bool:
        result = await self.call("IsOperationFinished", {"aOperationID": operation_id})
        return str(result.get("IsFinished", "")).lower() == "true"

    async def get_operation_results(
        self, operation_id: str, *, timeout: int = 0
    ) -> OperationResult:
        """Messages of an operation.

        A real host agent answers for an operation that is still running with the fault code
        255 ("Timeout occurred") and the messages so far, and for one that ended with an
        exit code other than 0 with fault code 127 and all messages. Both raise
        :class:`OperationFault` with the messages.
        """
        try:
            result = await self.call(
                "GetOperationResults",
                {
                    "aOperationID": operation_id,
                    "aOptions": {"mTimeout": timeout, "mOptions": [], "mSoftTimeout": 0},
                },
            )
        except SoapFaultError as exc:
            raise OperationFault.from_fault(exc) from exc
        return _operation_result(result.get("result"))

    async def cancel_operation(self, operation_id: str, *, hard: bool = True) -> OperationResult:
        """Cancel a running operation; O-HARD ends the process.

        A real host agent answered a successful cancel of a script with fault code 127 and
        the messages up to the cancel ("exit code = 15"). That is returned, not raised.
        """
        try:
            result = await self.call(
                "CancelOperation",
                {
                    "aOperationID": operation_id,
                    "aType": "O-HARD" if hard else "O-SOFT",
                    "aOptions": {"mTimeout": 0, "mOptions": [], "mSoftTimeout": 0},
                },
            )
        except SoapFaultError as exc:
            fault = OperationFault.from_fault(exc)
            if fault.code == FAULT_COMMAND_FAILED:
                return fault.result
            raise fault from exc
        return _operation_result(result.get("result"))

    async def get_version(self) -> HostAgentVersion | None:
        """Version of the host agent; None if the output is not recognized."""
        return parse_version_info(await self.execute_operation("versioninfo"))

    async def start_instance(
        self,
        sid: str,
        system_number: str | int,
        *,
        hostname: str | None = None,
        timeout: int = 0,
        options: Sequence[InstanceOption] = (InstanceOption.INSTANCE,),
    ) -> OperationResult:
        """Start an instance. ``timeout`` 0 is asynchronous, -1 waits until it is done.

        ``hostname`` is the SAPLOCALHOST of the instance as reported by ListInstances. It is
        required for instances with a virtual hostname; a real host agent answered "SAP
        Instance not found!" without it.
        """
        return await self._instance_operation(
            "StartInstance", sid, system_number, hostname, timeout, options
        )

    async def stop_instance(
        self,
        sid: str,
        system_number: str | int,
        *,
        hostname: str | None = None,
        timeout: int = 0,
        soft_timeout: int = 0,
        options: Sequence[InstanceOption] = (InstanceOption.INSTANCE,),
    ) -> OperationResult:
        """Stop an instance. ``timeout`` 0 is asynchronous, -1 waits until it is done.

        ``hostname``: see :meth:`start_instance`.
        """
        return await self._instance_operation(
            "StopInstance", sid, system_number, hostname, timeout, options, soft_timeout
        )

    async def register_instance_service(
        self, sid: str, system_number: str | int, *, hostname: str | None = None
    ) -> OperationResult:
        """Register the sapstartsrv of an instance (sapstartsrv -reg) and start it, and wait.

        A real host agent answered with the log lines of "sapstartsrv -reg" and
        "sapcontrol -function StartService" (checked with saphostctrl as root; whether
        sapadm may call it is an assumption)."""
        return await self._instance_operation(
            "RegisterInstanceService", sid, system_number, hostname, -1, ()
        )

    async def unregister_instance_service(
        self, sid: str, system_number: str | int, *, hostname: str | None = None
    ) -> OperationResult:
        """Stop the sapstartsrv of an instance (StopService) and unregister it
        (sapstartsrv -unreg), and wait. The instance's processes are not stopped."""
        return await self._instance_operation(
            "UnregisterInstanceService", sid, system_number, hostname, -1, ()
        )

    async def _instance_operation(
        self,
        method: str,
        sid: str,
        system_number: str | int,
        hostname: str | None,
        timeout: int,
        options: Sequence[InstanceOption],
        soft_timeout: int = 0,
    ) -> OperationResult:
        number = f"{int(system_number):02d}"
        result = await self.call(
            method,
            {
                "aInstance": {"mSid": sid, "mHostname": hostname, "mSystemNumber": number},
                "aOptions": {
                    "mTimeout": timeout,
                    "mOptions": [option.value for option in options],
                    "mSoftTimeout": soft_timeout,
                },
            },
        )
        return _operation_result(result.get("response"))

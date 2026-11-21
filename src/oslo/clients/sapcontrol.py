"""Client for the SAPControl web service of sapstartsrv (one SAP instance)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from ..soapxml import SAPCONTROL_NS, items
from .base import SoapClient, SoapProtocolError, as_dict, as_int


class StateColor(Enum):
    GRAY = "SAPControl-GRAY"
    GREEN = "SAPControl-GREEN"
    YELLOW = "SAPControl-YELLOW"
    RED = "SAPControl-RED"


class StartStopOption(Enum):
    ALL = "SAPControl-ALL-INSTANCES"
    SCS = "SAPControl-SCS-INSTANCES"
    DIALOG = "SAPControl-DIALOG-INSTANCES"
    ABAP = "SAPControl-ABAP-INSTANCES"
    J2EE = "SAPControl-J2EE-INSTANCES"
    PRIORITY_LEVEL = "SAPControl-PRIORITY-LEVEL"
    TREX = "SAPControl-TREX-INSTANCES"
    ENQREP = "SAPControl-ENQREP-INSTANCES"
    HDB = "SAPControl-HDB-INSTANCES"
    ALLNOHDB = "SAPControl-ALLNOHDB-INSTANCES"


@dataclass(frozen=True)
class OSProcess:
    name: str
    description: str
    dispstatus: StateColor
    textstatus: str
    starttime: str
    elapsedtime: str
    pid: int


@dataclass(frozen=True)
class SystemInstance:
    hostname: str
    instance_nr: int
    http_port: int
    https_port: int
    start_priority: str
    features: tuple[str, ...]
    dispstatus: StateColor


def _color(value: Any) -> StateColor:
    try:
        return StateColor(value)
    except ValueError as exc:
        raise SoapProtocolError(f"Unknown state color: {value!r}") from exc


def sapcontrol_port(instance_nr: int, https: bool = False) -> int:
    """Default port of sapstartsrv: 5<NR>13 for HTTP, 5<NR>14 for HTTPS."""
    if not 0 <= instance_nr <= 99:
        raise ValueError(f"Instance number out of range: {instance_nr}")
    return 50013 + 100 * instance_nr + (1 if https else 0)


class SapControlClient(SoapClient):
    namespace = SAPCONTROL_NS
    path = "/"

    def __init__(
        self,
        host: str,
        instance_nr: int,
        *,
        port: int | None = None,
        https: bool = False,
        auth: tuple[str, str] | None = None,
        verify: bool | str = True,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        port = port if port is not None else sapcontrol_port(instance_nr, https)
        scheme = "https" if https else "http"
        super().__init__(
            f"{scheme}://{host}:{port}",
            auth=auth,
            verify=verify,
            timeout=timeout,
            transport=transport,
        )
        self.host = host
        self.instance_nr = instance_nr

    async def get_process_list(self) -> list[OSProcess]:
        """Processes started by sapstartsrv according to the start profile."""
        result = await self.call("GetProcessList")
        return [
            OSProcess(
                name=item.get("name", ""),
                description=item.get("description", ""),
                dispstatus=_color(item.get("dispstatus")),
                textstatus=item.get("textstatus", ""),
                starttime=item.get("starttime", ""),
                elapsedtime=item.get("elapsedtime", ""),
                pid=as_int(item.get("pid"), "pid"),
            )
            for item in map(as_dict, items(result.get("process")))
        ]

    async def get_system_instance_list(self, timeout: int = 0) -> list[SystemInstance]:
        """All instances of the SAP system this instance belongs to."""
        result = await self.call("GetSystemInstanceList", {"timeout": timeout})
        return [
            SystemInstance(
                hostname=item.get("hostname", ""),
                instance_nr=as_int(item.get("instanceNr"), "instanceNr"),
                http_port=as_int(item.get("httpPort"), "httpPort"),
                https_port=as_int(item.get("httpsPort"), "httpsPort"),
                start_priority=item.get("startPriority", ""),
                features=tuple(f for f in item.get("features", "").split("|") if f),
                dispstatus=_color(item.get("dispstatus")),
            )
            for item in map(as_dict, items(result.get("instance")))
        ]

    async def start(self) -> None:
        """Trigger an instance start. Returns immediately; poll the process list for progress."""
        await self.call("Start")

    async def stop(self, softtimeout: int = 0) -> None:
        """Trigger an instance stop. Returns immediately."""
        await self.call("Stop", {"softtimeout": softtimeout})

    async def restart_instance(self, softtimeout: int = 0) -> None:
        """Trigger an instance restart. Returns immediately."""
        await self.call("RestartInstance", {"softtimeout": softtimeout})

    async def start_system(
        self,
        options: StartStopOption = StartStopOption.ALL,
        *,
        waittimeout: int = 300,
        prioritylevel: str | None = None,
    ) -> None:
        """Trigger the start of the whole system or parts of it. Returns immediately."""
        await self.call(
            "StartSystem",
            {
                "options": options.value,
                "prioritylevel": prioritylevel,
                "waittimeout": waittimeout,
            },
        )

    async def stop_system(
        self,
        options: StartStopOption = StartStopOption.ALL,
        *,
        softtimeout: int = 0,
        waittimeout: int = 300,
        prioritylevel: str | None = None,
    ) -> None:
        """Trigger the stop of the whole system or parts of it. Returns immediately."""
        await self.call(
            "StopSystem",
            {
                "options": options.value,
                "prioritylevel": prioritylevel,
                "softtimeout": softtimeout,
                "waittimeout": waittimeout,
            },
        )

    async def restart_system(
        self,
        options: StartStopOption = StartStopOption.ALL,
        *,
        softtimeout: int = 0,
        waittimeout: int = 300,
        prioritylevel: str | None = None,
    ) -> None:
        """Trigger a restart of the whole system or parts of it. Returns immediately."""
        await self.call(
            "RestartSystem",
            {
                "options": options.value,
                "prioritylevel": prioritylevel,
                "softtimeout": softtimeout,
                "waittimeout": waittimeout,
            },
        )

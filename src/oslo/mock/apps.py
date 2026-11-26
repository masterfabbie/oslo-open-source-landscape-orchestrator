"""ASGI apps simulating SAPHostControl (host agent) and SAPControl (sapstartsrv).

Element names and enum values follow the WSDLs of a host agent 7.22 and a sapstartsrv.
Contents the WSDLs leave open are modelled on sample output of ``saphostctrl`` (CIM classes of
GetComputerSystem, database components). Assumptions are marked in comments.
"""

from __future__ import annotations

import base64
import binascii
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, Response

from .landscape import (
    STATUS_COLOR,
    STATUS_TEXT,
    MockDatabase,
    MockHost,
    MockInstance,
    MockLandscape,
    Status,
)
from .soap import SoapFault, build_fault, build_response, items, parse_request

MAX_BODY_BYTES = 1_000_000
XML_CONTENT_TYPE = "text/xml; charset=utf-8"

Handler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class SoapService:
    prefix: str
    namespace: str
    handlers: dict[str, Handler]
    protected: frozenset[str]
    # Returns the users allowed to call protected methods; None allows every known user.
    # A callable, so tests can change the landscape after the app was built.
    administrators: Callable[[], frozenset[str] | None] = lambda: None


def _check_auth(request: Request, users: dict[str, str]) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        raise SoapFault("HTTP Error: 'Unauthorized'", "SOAP-ENV:Client", 401)
    try:
        user, _, password = base64.b64decode(encoded).decode("utf-8").partition(":")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise SoapFault("Invalid Credentials") from exc
    expected = users.get(user)
    if expected is None or not secrets.compare_digest(expected, password):
        raise SoapFault("Invalid Credentials")
    return user


def _soap_app(title: str, service: SoapService, users: dict[str, str]) -> FastAPI:
    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/{path:path}")
    async def call(request: Request) -> Response:
        try:
            body = await request.body()
            if len(body) > MAX_BODY_BYTES:
                raise SoapFault("Request too large", "SOAP-ENV:Client")
            method, params = parse_request(body)
            handler = service.handlers.get(method)
            if handler is None:
                raise SoapFault(f"Method '{method}' not implemented", "SOAP-ENV:Client")
            if method in service.protected:
                user = _check_auth(request, users)
                allowed = service.administrators()
                if allowed is not None and user not in allowed:
                    raise SoapFault("Permission denied")
            payload = handler(params)
        except SoapFault as fault:
            headers = {"WWW-Authenticate": 'Basic realm="gSOAP Web Service"'}
            return Response(
                build_fault(fault),
                status_code=fault.http_status,
                media_type=XML_CONTENT_TYPE,
                headers=headers if fault.http_status == 401 else None,
            )
        return Response(
            build_response(service.prefix, service.namespace, method, payload),
            media_type=XML_CONTENT_TYPE,
        )

    return app


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


# --- SAPControl (sapstartsrv of one instance) -------------------------------------------

SAPCONTROL_PROTECTED = frozenset(
    {"Start", "Stop", "RestartInstance", "StartSystem", "StopSystem", "RestartSystem"}
)

_ALL_KINDS = {"HDB", "ERS", "ASCS", "SCS", "ABAP", "J2EE"}
START_STOP_OPTIONS: dict[str, set[str] | None] = {
    "SAPControl-ALL-INSTANCES": None,
    "SAPControl-SCS-INSTANCES": {"ASCS", "SCS"},
    "SAPControl-DIALOG-INSTANCES": {"ABAP", "J2EE"},
    "SAPControl-ABAP-INSTANCES": {"ABAP"},
    "SAPControl-J2EE-INSTANCES": {"J2EE"},
    "SAPControl-TREX-INSTANCES": set(),
    "SAPControl-ENQREP-INSTANCES": {"ERS"},
    "SAPControl-HDB-INSTANCES": {"HDB"},
    "SAPControl-ALLNOHDB-INSTANCES": _ALL_KINDS - {"HDB"},
}


def create_sapcontrol_app(landscape: MockLandscape, host_name: str, nr: int) -> FastAPI:
    host = landscape.host(host_name)
    instance = host.instance(nr)
    if instance is None:
        raise KeyError(f"No instance {nr:02d} on host {host_name}")

    def get_process_list(_: dict[str, Any]) -> dict[str, Any]:
        if not instance.service_running:
            # In-process (MockLandscapeTransport) the connection is refused; the mock server
            # on real ports can only answer with a fault.
            raise SoapFault("sapstartsrv is not running")
        now = landscape.clock()
        status = instance.status(now)
        started_at = instance.started_at(now)
        starttime = elapsed = ""
        if started_at is not None:
            wall_start = time.localtime(time.time() - (now - started_at))
            starttime = time.strftime("%Y %m %d %H:%M:%S", wall_start)
            elapsed = _format_duration(now - started_at)
        return {
            "process": [
                {
                    "name": name,
                    "description": description,
                    "dispstatus": f"SAPControl-{STATUS_COLOR[status]}",
                    "textstatus": STATUS_TEXT[status],
                    "starttime": starttime,
                    "elapsedtime": elapsed,
                    "pid": -1 if status is Status.STOPPED else 1000 + nr * 100 + index,
                }
                for index, (name, description) in enumerate(instance.kind_info.processes)
            ]
        }

    def get_system_instance_list(_: dict[str, Any]) -> dict[str, Any]:
        now = landscape.clock()
        return {
            "instance": [
                {
                    "hostname": inst.hostname,
                    "instanceNr": inst.nr,
                    "httpPort": inst_host.sapcontrol_port(inst.nr),
                    "httpsPort": inst_host.sapcontrol_port(inst.nr) + 1,
                    "startPriority": inst.kind_info.start_priority,
                    "features": inst.kind_info.features,
                    "dispstatus": f"SAPControl-{STATUS_COLOR[inst.status(now)]}",
                }
                for inst_host, inst in landscape.system_instances(instance.sid)
            ]
        }

    def start(_: dict[str, Any]) -> dict[str, Any]:
        landscape.start_instance(instance)
        return {}

    def stop(_: dict[str, Any]) -> dict[str, Any]:
        landscape.stop_instance(instance)
        return {}

    def restart_instance(_: dict[str, Any]) -> dict[str, Any]:
        landscape.restart_instance(instance)
        return {}

    def _kinds(params: dict[str, Any]) -> set[str] | None:
        option = params.get("options") or "SAPControl-ALL-INSTANCES"
        if option not in START_STOP_OPTIONS:
            raise SoapFault(f"Option '{option}' is not supported by the mock")
        return START_STOP_OPTIONS[option]

    def start_system(params: dict[str, Any]) -> dict[str, Any]:
        landscape.start_system(instance.sid, _kinds(params))
        return {}

    def stop_system(params: dict[str, Any]) -> dict[str, Any]:
        landscape.stop_system(instance.sid, _kinds(params))
        return {}

    def restart_system(params: dict[str, Any]) -> dict[str, Any]:
        kinds = _kinds(params)
        landscape.stop_system(instance.sid, kinds)
        landscape.start_system(instance.sid, kinds)
        return {}

    service = SoapService(
        prefix="SAPControl",
        namespace="urn:SAPControl",
        handlers={
            "GetProcessList": get_process_list,
            "GetSystemInstanceList": get_system_instance_list,
            "Start": start,
            "Stop": stop,
            "RestartInstance": restart_instance,
            "StartSystem": start_system,
            "StopSystem": stop_system,
            "RestartSystem": restart_system,
        },
        protected=SAPCONTROL_PROTECTED,
        # Real systems allow administrative calls only to <sid>adm (unless configured
        # otherwise); the mock does so when the landscape asks for it.
        administrators=lambda: (
            frozenset({f"{instance.sid.lower()}adm"}) if landscape.strict_sapstartsrv_auth else None
        ),
    )
    title = f"Mock sapstartsrv {instance.sid}/{nr:02d} on {host_name}"
    return _soap_app(title, service, landscape.users)


# --- SAPHostControl (host agent) ----------------------------------------------------------

HOSTCONTROL_PROTECTED = frozenset(
    {
        "StartInstance",
        "StopInstance",
        "RegisterInstanceService",
        "UnregisterInstanceService",
        "ExecuteOperation",
        "IsOperationFinished",
        "GetOperationResults",
        "CancelOperation",
    }
)

# Output of the operation "versioninfo" of a real host agent 7.22, shortened. The real host
# agent returned these lines as log messages; the message key used per line is an assumption.
# Operations of the OSLO operations bundle the mock knows (only on hosts with a bundle).
BUNDLE_OPERATIONS = (
    "oslo_version",
    "oslo_update",
    "oslo_restart_service",
    "oslo_restart_service_force",
)

HOSTAGENT_VERSION_LINES = (
    "Retrieve version info: *************************** Component ********************",
    "Retrieve version info: /usr/sap/hostctrl/exe/saphostexec: 722 (EXT), patch 1611, "
    "changelist 2315890, linuxx86_64, opt (EXT) (Oct 13 2026, 09:26:37)",
    "Retrieve version info: --------------------",
    "Retrieve version info: SAPHOSTAGENT information",
    "Retrieve version info: --------------------",
    "Retrieve version info: kernel release                722",
    "Retrieve version info: kernel make variant           722_EXT_REL",
    "Retrieve version info: patch number                  72",
    "Retrieve version info: latest change number          2315890",
)

_DB_STATUS = {
    Status.RUNNING: "SAPHostControl-DB-RUNNING",
    Status.STOPPED: "SAPHostControl-DB-STOPPED",
    Status.STARTING: "SAPHostControl-DB-STARTING",
    Status.STOPPING: "SAPHostControl-DB-STOPPING",
}


def _properties(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"mKey": key, "mValue": value} for key, value in values.items()]


def _cim_attributes(*attributes: tuple[str, str, Any]) -> list[dict[str, Any]]:
    return [{"mName": name, "mType": type_, "mValue": value} for name, type_, value in attributes]


def create_hostagent_app(landscape: MockLandscape, host_name: str) -> FastAPI:
    host: MockHost = landscape.host(host_name)

    def list_instances(params: dict[str, Any]) -> dict[str, Any]:
        selector = params.get("aSelector")
        selector = selector if isinstance(selector, dict) else {}
        wanted = selector.get("aInstanceStatus") or "S-INSTALLED"
        if wanted not in ("S-INSTALLED", "S-RUNNING", "S-STOPPED"):
            raise SoapFault(f"Invalid instance status '{wanted}'", "SOAP-ENV:Client")
        hostname = selector.get("aHostname")
        now = landscape.clock()
        result = []
        for inst in host.instances:
            stopped = inst.status(now) is Status.STOPPED
            if wanted == "S-RUNNING" and stopped:
                continue
            if wanted == "S-STOPPED" and not stopped:
                continue
            if hostname and inst.hostname != hostname:
                continue
            result.append(
                {
                    "mSid": inst.sid,
                    "mHostname": inst.hostname,
                    "mSystemNumber": f"{inst.nr:02d}",
                    "mSapVersionInfo": "753, patch 1100, changelist 2200000",
                }
            )
        return {"aInstances": result}

    def _database_properties(db: MockDatabase) -> list[dict[str, Any]]:
        # Name, Type, InstanceName and Host are documented in the WSDL. Release is confirmed
        # against a real host agent; the key for the vendor is an assumption.
        values = {"Database/Name": db.name, "Database/Type": db.type}
        instance = host.instance(db.instance_nr) if db.instance_nr is not None else None
        if instance is not None:
            values["Database/InstanceName"] = f"{instance.kind}{instance.nr:02d}"
        values |= {
            "Database/Host": host.name,
            "Database/Vendor": db.type.upper(),
            "Database/Release": "2.00.000.00",
        }
        return _properties(values)

    def _components(db: MockDatabase) -> list[dict[str, Any]]:
        status = landscape.database_status(host, db)
        instance = host.instance(db.instance_nr) if db.instance_nr is not None else None
        processes = instance.kind_info.processes if instance else (("database", "Database"),)
        return [
            {
                "mProperties": _properties(
                    {
                        "Database/ComponentName": name,
                        "Database/ComponentDescription": description,
                        "Database/ComponentStatusDescription": STATUS_TEXT[status],
                    }
                ),
                "mStatus": _DB_STATUS[status],
            }
            for name, description in processes
        ]

    def list_databases(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "result": [
                {
                    "mStatus": _DB_STATUS[landscape.database_status(host, db)],
                    "mDatabase": _database_properties(db),
                    "mComponents": _components(db),
                }
                for db in host.databases
            ]
        }

    def get_database_status(params: dict[str, Any]) -> dict[str, Any]:
        arguments = {
            item.get("mKey"): item.get("mValue")
            for item in items(params.get("aArguments"))
            if isinstance(item, dict)
        }
        name = arguments.get("Database/Name")
        for db in host.databases:
            if db.name == name:
                return {
                    "result": _components(db),
                    "status": _DB_STATUS[landscape.database_status(host, db)],
                }
        raise SoapFault(f"Database '{name}' not found")

    def get_computer_system(_: dict[str, Any]) -> dict[str, Any]:
        # Classes, attribute names (including the spelling "IPAdresses") and types follow real
        # saphostctrl output. Nesting the other classes as members of the computer system is
        # an assumption; the WSDL only defines mProperties and mMembers.
        hostnames = sorted({host.name} | {inst.hostname for inst in host.instances})
        return {
            "result": {
                "mProperties": _cim_attributes(
                    ("CreationClassName", "String", "ITSAMComputerSystem"),
                    ("Name", "String", host.name),
                    ("Hostnames", "String[] sep=;", "".join(f"{name};" for name in hostnames)),
                    ("IPAdresses", "String[] sep=;", f"{host.bind};"),
                ),
                "mMembers": [
                    {
                        "mProperties": _cim_attributes(
                            ("CreationClassName", "String", "ITSAMOperatingSystem"),
                            ("Name", "String", host.opsys),
                            ("Version", "String", "6.4.0-mock"),
                            ("TotalVisibleMemorySize", "uint64", 16777216),
                            ("FreePhysicalMemory", "uint64", 8388608),
                            ("CPU Count", "uint16", 4),
                        )
                    },
                    {
                        "mProperties": _cim_attributes(
                            ("CreationClassName", "String", "ITSAMFileSystem"),
                            ("Name", "String", "/"),
                            ("FileSystemSize", "uint64", 102400),
                            ("AvailableSpace", "uint64", 51200),
                            ("FileSystemType", "String", "xfs"),
                            ("Remote", "boolean", "false"),
                        )
                    },
                ],
            }
        }

    def _find_instance(params: dict[str, Any]) -> MockInstance:
        # A real host agent identifies an instance by SID, number and SAPLOCALHOST. Without
        # mHostname it found instances running under the physical hostname, but answered
        # "SAP Instance not found!" for an instance with a virtual hostname.
        spec = params.get("aInstance")
        spec = spec if isinstance(spec, dict) else {}
        sid, number = spec.get("mSid"), spec.get("mSystemNumber")
        hostname = (spec.get("mHostname") or host.name).lower()
        for inst in host.instances:
            if (
                inst.sid == sid
                and f"{inst.nr:02d}" == str(number).zfill(2)
                and inst.hostname.lower() == hostname
            ):
                return inst
        raise SoapFault("SAP Instance not found!")

    def _operation_result(description: str) -> dict[str, Any]:
        return {
            "response": {
                "mOperationID": "",
                "mOperationResults": [{"mMessageKey": "description", "mMessageValue": description}],
            }
        }

    def _operation_fault(message: str, code: int, run=None, lines=None) -> SoapFault:
        return SoapFault(
            message,
            detail=(
                "urn:SAPHostControl",
                "OperationException",
                {
                    "mFaultCode": code,
                    "mMessage": message,
                    "mOperationID": run.id if run else None,
                    "mResponseMessages": lines or [],
                },
            ),
        )

    def _line(severity: str, source: str, text: str) -> list[dict[str, str]]:
        """One line as a real host agent returns it: four messages LogMsg/*."""
        return [
            {"mMessageKey": "LogMsg/TimeStamp", "mMessageValue": ""},
            {"mMessageKey": "LogMsg/Severity", "mMessageValue": severity},
            {"mMessageKey": "LogMsg/Source", "mMessageValue": source},
            {"mMessageKey": "LogMsg/Text", "mMessageValue": text},
        ]

    def _run_lines(run, final: bool) -> list[dict[str, str]]:
        """Messages of a run, as a real host agent returns them for a test script."""
        desc = run.operation.description
        if run.output is not None:
            lines = []
            for text in run.output:
                severity = "Error" if text.startswith("[ERROR]") else "Info"
                lines += _line(severity, desc, text)
            if run.exit_code:
                failed = f"{desc} hook failed (exit code = {run.exit_code})"
                lines += _line("Error", "saphostcontrol", failed)
            else:
                lines += _line("Info", "saphostcontrol", f"{desc} hook successfully executed")
            return lines
        lines = _line("Info", desc, f"count={len(run.arguments)}")
        for i, value in enumerate(run.arguments, start=1):
            lines += _line("Info", desc, f"arg{i}=[{value}]")
        lines += _line("Warning", desc, " test warning")
        if not final:
            lines += _line("Info", "saphostcontrol", f"Executing {desc} hook")
        elif run.cancelled or run.exit_code:
            code = 15 if run.cancelled else run.exit_code
            lines += _line("Error", desc, " test error")
            lines += _line("Error", "saphostcontrol", f"{desc} hook failed (exit code = {code})")
        else:
            lines += _line("Info", "saphostcontrol", f"{desc} hook successfully executed")
        return lines

    def _run(params: dict[str, Any]):
        run = landscape.operation_runs.get(params.get("aOperationID") or "")
        if run is None or run.host != host.name or run.delivered:
            raise _operation_fault("Operation ID not found", -20)
        return run

    def is_operation_finished(params: dict[str, Any]) -> dict[str, Any]:
        try:
            run = _run(params)
        except SoapFault as exc:
            raise _operation_fault("Failed to determine operation status", -20) from exc
        return {"IsFinished": landscape.operation_finished(run)}

    def get_operation_results(params: dict[str, Any]) -> dict[str, Any]:
        run = _run(params)
        run.results_requested = True
        if not landscape.operation_finished(run):
            raise _operation_fault("Timeout occurred", 255, run, _run_lines(run, final=False))
        if run.exit_code or run.cancelled:
            raise _operation_fault("Command execution failed.", 127, run, _run_lines(run, True))
        run.delivered = True  # forgotten afterwards, like on a real host
        return {"result": {"mOperationID": run.id, "mOperationResults": _run_lines(run, True)}}

    def cancel_operation(params: dict[str, Any]) -> dict[str, Any]:
        run = _run(params)
        if landscape.operation_finished(run):
            raise _operation_fault("Operation ID not found", -20)
        run.cancelled = True
        lines = _run_lines(run, final=True)
        del landscape.operation_runs[run.id]  # a real host agent forgets cancelled operations
        raise _operation_fault("Command execution failed.", 127, run, lines)

    def execute_operation(params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("aOperation")
        arguments = {
            item.get("mKey"): item.get("mValue") or ""
            for item in items(params.get("aArguments"))
            if isinstance(item, dict)
        }
        if name in BUNDLE_OPERATIONS:
            if host.bundle_version is None:
                raise SoapFault(f"Operation '{name}' not found")
            run = landscape.run_bundle_operation(host, name, arguments)
            return {"result": {"mOperationID": run.id, "mOperationResults": []}}
        custom = landscape.custom_operations.get(name or "")
        if custom is not None:
            run = landscape.start_operation(host, custom, arguments)
            return {"result": {"mOperationID": run.id, "mOperationResults": []}}
        if name != "versioninfo":
            raise SoapFault(f"Operation '{name}' not found")
        lines = ["saphostcontrol: Executing 'Retrieve version info'", *HOSTAGENT_VERSION_LINES]
        return {
            "result": {
                "mOperationID": "MOCKOPERATION",
                "mOperationResults": [
                    {"mMessageKey": "Info", "mMessageValue": line} for line in lines
                ],
            }
        }

    def start_instance(params: dict[str, Any]) -> dict[str, Any]:
        inst = _find_instance(params)
        landscape.start_instance(inst)
        return _operation_result(f"Start of instance {inst.sid}/{inst.nr:02d} triggered")

    def stop_instance(params: dict[str, Any]) -> dict[str, Any]:
        inst = _find_instance(params)
        landscape.stop_instance(inst)
        return _operation_result(f"Stop of instance {inst.sid}/{inst.nr:02d} triggered")

    def _service_result(commands: list[str]) -> dict[str, Any]:
        """Lines as a real host agent returned them for (Un)RegisterInstanceService."""
        lines: list[dict[str, str]] = []
        for command in commands:
            if command.startswith("sapstartsrv"):
                lines += _line("Info", "saphostcontrol", f"Executing '{command}'")
            lines += _line("Info", "saphostcontrol", "exitcode=0")
            lines += _line("Info", "saphostcontrol", f"'{command}' successfully executed")
        return {"response": {"mOperationID": "", "mOperationResults": lines}}

    def register_instance_service(params: dict[str, Any]) -> dict[str, Any]:
        inst = _find_instance(params)
        inst.service_running = True
        return _service_result(["sapstartsrv -reg", "sapcontrol -function StartService"])

    def unregister_instance_service(params: dict[str, Any]) -> dict[str, Any]:
        inst = _find_instance(params)
        inst.service_running = False
        return _service_result(["sapcontrol -function StopService", "sapstartsrv -unreg"])

    service = SoapService(
        prefix="SAPHostControl",
        namespace="urn:SAPHostControl",
        handlers={
            "ListInstances": list_instances,
            "ListDatabases": list_databases,
            "GetDatabaseStatus": get_database_status,
            "GetComputerSystem": get_computer_system,
            "StartInstance": start_instance,
            "StopInstance": stop_instance,
            "RegisterInstanceService": register_instance_service,
            "UnregisterInstanceService": unregister_instance_service,
            "ExecuteOperation": execute_operation,
            "IsOperationFinished": is_operation_finished,
            "GetOperationResults": get_operation_results,
            "CancelOperation": cancel_operation,
        },
        protected=HOSTCONTROL_PROTECTED,
    )
    return _soap_app(f"Mock SAP Host Agent on {host_name}", service, landscape.users)

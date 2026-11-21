"""Description of a custom operation and the context parameters passed to its script.

Kept free of the catalog and the runner, which both use it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Host, Instance, System
from .roles import Role as InstanceRole
from .roles import instance_type_key


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    type: str  # STRING, INTEGER, BOOLEAN
    required: bool
    default: str | None
    pattern: str | None
    help: str | None


@dataclass(frozen=True)
class CustomSpec:
    """Snapshot of a custom operation, also stored with each activity that runs it."""

    id: int
    name: str
    description: str | None
    agent_operation: str
    target: str  # INSTANCE, SYSTEM or HOST
    instance_types: tuple[str, ...]  # empty: all types
    ordering: str  # parallel, roles, sequential
    timeout_seconds: int
    parameters: tuple[ParameterSpec, ...]
    # Locks its target like start and stop; snapshots from before migration 0008 lack it.
    locks: bool = True

    def to_dict(self) -> dict:
        data = self.__dict__ | {"parameters": [p.__dict__ for p in self.parameters]}
        data["instance_types"] = list(self.instance_types)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> CustomSpec:
        return cls(
            **(
                data
                | {
                    "instance_types": tuple(data["instance_types"]),
                    "parameters": tuple(ParameterSpec(**p) for p in data["parameters"]),
                }
            )
        )


def spec_applies(spec: CustomSpec, instance: Instance, *, system: bool = False) -> bool:
    """Whether a custom operation applies to an instance.

    Without instance types it applies to every instance; run on a whole system it then
    leaves out diagnostics agents, like system operations do.
    """
    if not spec.instance_types:
        return not (system and instance.is_agent)
    key = instance_type_key(instance.features)
    return bool(key) and key.removeprefix("itype.") in spec.instance_types


def _technology(system: System | None) -> str:
    """ABAP or J2EE from the application servers of the system.

    Assumption: LaMa derives the part after the slash from the system's technology; the tool
    takes it from the features of the application servers in the same system.
    """
    features: set[str] = set()
    for instance in system.instances if system else []:
        if instance.role is InstanceRole.APPLICATION:
            features |= set((instance.features or "").split("|"))
    if "ABAP" in features and "J2EE" in features:
        return "Shared"
    if "J2EE" in features:
        return "J2EE"
    if "ABAP" in features:
        return "ABAP"
    return "None"


def service_subtype(instance: Instance, system: System | None) -> str:
    """SERVICE_SUBTYPE as LaMa names it, e.g. Instance_SCS/ABAP.

    Assumptions: the primary application server cannot be told apart and is reported as
    Instance_Application_Server; HANA instances as Instance_System_HDB; diagnostics agents as
    Instance_Diag_Agnt/SolMan.
    """
    names = set((instance.features or "").split("|"))
    if "SMDAGENT" in names:
        return "Instance_Diag_Agnt/SolMan"
    technology = _technology(system)
    if "HDB" in names:
        return f"Instance_System_HDB/{technology}"
    if "ENQREP" in names:
        return f"Instance_ERS/{technology}"
    if names & {"MESSAGESERVER", "ENQUE"}:
        return f"Instance_SCS/{technology}"
    if "ABAP" in names and "J2EE" in names:
        return "Instance_Application_Server/Shared"
    if "J2EE" in names:
        return "Instance_Application_Server/J2EE"
    if "ABAP" in names:
        return "Instance_Application_Server/ABAP"
    return "Instance_Application_Server/None"


def instance_arguments(instance: Instance, system: System | None) -> dict[str, str]:
    """Context parameters of an instance, named as in LaMa."""
    return {
        "SAPSYSTEMNAME": instance.sid.name,
        "SAPSYSTEM": instance.number,
        "SAPLOCALHOST": instance.hostname,
        "PHYSICAL_HOSTNAME": instance.host.name,
        "SERVICE_CLASS": "Instance",
        "SERVICE_SUBTYPE": service_subtype(instance, system),
    }


def host_arguments(host: Host) -> dict[str, str]:
    """Context parameters of a host, named as in LaMa."""
    arguments = {"PHYSICAL_HOSTNAME": host.name, "RealHostName": host.name}
    if host.os_name:
        arguments["OS_TYPE"] = host.os_name
    if host.os_version:
        arguments["OS_VERSION"] = host.os_version
    if host.cpu_count is not None:
        arguments["CPUS"] = str(host.cpu_count)
    if host.memory_kb is not None:
        arguments["MEMAV"] = str(host.memory_kb)
    return arguments

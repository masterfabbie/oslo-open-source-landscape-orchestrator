from __future__ import annotations

from oslo.roles import Role, instance_role


def test_roles_from_features():
    assert instance_role("HDB|HDB_WORKER") is Role.DATABASE
    assert instance_role("MESSAGESERVER|ENQUE") is Role.CENTRAL
    assert instance_role("ENQREP") is Role.CENTRAL
    assert instance_role("ABAP|GATEWAY|ICMAN|IGS") is Role.APPLICATION
    assert instance_role("J2EE|IGS") is Role.APPLICATION
    assert instance_role("SMDAGENT") is Role.AGENT
    # Unknown or missing features start last and stop first.
    assert instance_role(None) is Role.APPLICATION
    assert instance_role("SOMETHING") is Role.APPLICATION

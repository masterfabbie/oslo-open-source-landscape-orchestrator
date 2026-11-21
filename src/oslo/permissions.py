"""Which role a route needs. Shared by the REST API and the web interface.

Roles build on each other (viewer < operator < configurator < admin):

- viewer: read everything, refresh the status of a system, own account and preferences
- operator: also start, stop and restart instances and systems
- configurator: also change the configuration (hosts, discovery, systems, pools, tags,
  credentials)
- admin: also users and platform settings
"""

from __future__ import annotations

from .users import Role

# Operations of the catalog: the route needs at least an operator; the handler then checks
# the role the chosen operation requires (catalog.py).
OPERATION_ROUTES = frozenset(
    {
        "/instances/{instance_id}/{operation}",
        "/systems/{system_id}/{operation}",
        "/hosts/{host_id}/{operation}",
        "/mass-operations",
        "/instances/{instance_id}/operations/{key}",
        "/systems/{system_id}/operations/{key}",
        "/hosts/{host_id}/operations/{key}",
        "/run/{kind}/{target_id}/{key}",
        "/activities/{activity_id}/cancel",
        "/templates/{template_id}/run",
    }
)


def required_role(method: str, path: str) -> Role:
    """``path`` is the route template, e.g. "/systems/{system_id}/{operation}", without the
    "/api" prefix for API routes."""
    if path == "/templates/{template_id}/run":
        # Running a template needs its own role, checked by the handler.
        return Role.OPERATOR
    if path == "/attention-rules" and method not in ("GET", "HEAD"):
        return Role.ADMIN
    if path.startswith(
        ("/administration", "/users", "/custom-operations", "/templates", "/platform")
    ):
        return Role.ADMIN
    # Web area "Operations": custom operations and templates. "/operations" alone is the
    # catalog in the API (and a redirect on the web).
    if path.startswith("/operations/"):
        return Role.ADMIN
    if path.startswith(("/account", "/me")):
        return Role.VIEWER
    if path.startswith("/configuration"):
        return Role.CONFIGURATOR
    if path == "/run/{kind}/{target_id}/{key}":
        return Role.OPERATOR
    if method in ("GET", "HEAD"):
        return Role.VIEWER
    if path.startswith("/schedules"):
        # Planning needs at least an operator; the role of the operation is checked too.
        return Role.VIEWER if method in ("GET", "HEAD") else Role.OPERATOR
    if path.endswith("/refresh"):
        return Role.VIEWER
    if path in OPERATION_ROUTES:
        return Role.OPERATOR
    return Role.CONFIGURATOR

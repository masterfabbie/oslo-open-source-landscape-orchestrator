"""Run the mock landscape: one host agent endpoint per host, one sapstartsrv per instance."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import signal
from collections.abc import Iterator
from pathlib import Path

import uvicorn

from .apps import create_hostagent_app, create_sapcontrol_app
from .landscape import MockLandscape, default_landscape_config


class _Server(uvicorn.Server):
    """uvicorn server without its own signal handling.

    Several servers share one process here; ``serve`` installs one handler for all of them.
    """

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def build_servers(landscape: MockLandscape, log_level: str = "warning") -> list[uvicorn.Server]:
    servers = []
    for host in landscape.hosts:
        endpoints = [(host.hostagent_port, create_hostagent_app(landscape, host.name))]
        endpoints += [
            (host.sapcontrol_port(inst.nr), create_sapcontrol_app(landscape, host.name, inst.nr))
            for inst in host.instances
        ]
        for port, app in endpoints:
            config = uvicorn.Config(app, host=host.bind, port=port, log_level=log_level)
            servers.append(_Server(config))
    return servers


def describe(landscape: MockLandscape) -> str:
    lines = []
    for host in landscape.hosts:
        lines.append(f"{host.name}: host agent  http://{host.bind}:{host.hostagent_port}")
        for inst in host.instances:
            url = f"http://{host.bind}:{host.sapcontrol_port(inst.nr)}"
            lines.append(f"{host.name}: {inst.sid}/{inst.nr:02d} {inst.kind:<5} {url}")
    return "\n".join(lines)


async def serve(landscape: MockLandscape, log_level: str = "warning") -> None:
    servers = build_servers(landscape, log_level)

    def shutdown() -> None:
        for server in servers:
            server.should_exit = True

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # not available on Windows
            loop.add_signal_handler(signum, shutdown)
    await asyncio.gather(*(server.serve() for server in servers))


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated SAP Host Agent / sapstartsrv")
    parser.add_argument("--config", type=Path, help="JSON file describing the landscape")
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()

    config = json.loads(args.config.read_text()) if args.config else default_landscape_config()
    landscape = MockLandscape.from_dict(config)
    print(describe(landscape), flush=True)
    try:
        asyncio.run(serve(landscape, args.log_level))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

"""
Runtime functions for quick-start server operations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Union

from toonic.server.config import SourceConfig
from toonic.server.quick.builder import ConfigBuilder

logger = logging.getLogger("toonic.quick.runtime")


def watch(*sources: Union[str, SourceConfig, Dict]) -> ConfigBuilder:
    """Start building a monitoring config from one or more sources.

    Returns a ConfigBuilder for fluent chaining:
        srv = watch("./src/", "log:./app.log").goal("find bugs").build()
    """
    builder = ConfigBuilder()
    for src in sources:
        builder.add(src)
    return builder


async def monitor(
    *sources: Union[str, SourceConfig, Dict],
    goal: str = "analyze and monitor",
    interval: float = 30.0,
    model: str = "",
    web: bool = True,
    port: int = 8900,
    **kwargs,
) -> None:
    """One-liner: start monitoring sources immediately.

    Usage:
        await monitor("log:./app.log", goal="detect errors", interval=10)
        await monitor("./src/", "log:./app.log", "docker:*", goal="full-stack")
    """
    builder = watch(*sources).goal(goal).interval(interval).port(port)
    if model:
        builder.model(model)
    if not web:
        builder.no_web()
    server = builder.build()
    await serve(server, web=web, host=builder._host, port=port)


async def _serve_web(
    app,
    server,
    host: str,
    port: int,
) -> None:
    """Run server with Web UI enabled."""
    import uvicorn

    print(f"\n  Toonic Server")
    print(f"  Web UI:  http://{host}:{port}/")
    print(f"  Goal:    {server.config.goal}")
    print(f"  Sources: {len(server.config.sources)}")
    uvi_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uvi_server = uvicorn.Server(uvi_config)
    try:
        await uvi_server.serve()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await server.stop()


async def _serve_headless(server) -> None:
    """Run server in headless mode (no Web UI)."""
    print(f"  Toonic Server (headless)")
    print(f"  Goal:    {server.config.goal}")
    print(f"  Sources: {len(server.config.sources)}")
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        await server.stop()


async def serve(
    server,
    web: bool = True,
    host: str = "0.0.0.0",
    port: int = 8900,
) -> None:
    """Run a ToonicServer instance (blocking).

    Starts Web UI by default. Use web=False for headless mode.
    """
    await server.start()

    if web:
        try:
            from toonic.server.transport.rest_api import create_app
        except ImportError:
            logger.warning("FastAPI/uvicorn not installed — running headless")
            web = False

    if web:
        app = create_app(server)
        await _serve_web(app, server, host, port)
    else:
        await _serve_headless(server)


def run(
    *sources: Union[str, SourceConfig, Dict],
    goal: str = "analyze and monitor",
    **kwargs,
) -> None:
    """Synchronous entry point — calls asyncio.run(monitor(...)).

    Usage (in a script):
        from toonic.server.quick import run
        run("./src/", "log:./app.log", goal="find bugs")
    """
    asyncio.run(monitor(*sources, goal=goal, **kwargs))

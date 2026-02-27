"""
Toonic Autopilot — autonomous project development.

Usage:
    toonic init "REST API for task management" --name my-api
    toonic autopilot ./my-api --goal "build MVP"
"""

from toonic.autopilot.scaffold import ProjectScaffold
from toonic.autopilot.executor import ActionExecutor
from toonic.autopilot.loop import AutopilotLoop

__all__ = ["ProjectScaffold", "ActionExecutor", "AutopilotLoop"]

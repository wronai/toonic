"""
Backward compatibility — delegates to app.py.

All routes have been moved to transport/routes/ modules.
Import create_app from here or from app.py — both work.
"""

from toonic.server.transport.app import create_app, _load_template

__all__ = ["create_app", "_load_template"]

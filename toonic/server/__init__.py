"""
Toonic Server — bidirectional TOON streaming between data sources and LLMs.

Usage:
    python -m toonic.server            # start server
    python -m toonic.server --help     # show options

Quick-start:
    from toonic.server.quick import watch, monitor, run

    # Fluent builder
    srv = watch("./src/", "log:./app.log").goal("find bugs").build()

    # One-liner (async)
    await monitor("log:./app.log", goal="detect errors")

    # One-liner (sync)
    run("./src/", "log:./app.log", goal="find bugs")
"""

__all__ = ["ServerConfig", "ToonicServer", "watch", "monitor", "run"]

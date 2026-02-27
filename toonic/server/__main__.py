"""
Entry point: python -m toonic.server

Usage:
    python -m toonic.server --source file:./src/ --goal "analyze code"
    python -m toonic.server --config toonic-server.yaml
    python -m toonic.server --source file:./src/ --source log:./app.log --source rtsp://cam1
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import socket
import subprocess
import sys
from pathlib import Path


def check_port_occupied(host: str, port: int) -> bool:
    """Check if port is occupied."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def stop_process_using_port(host: str, port: int) -> bool:
    """Stop process using the specified port."""
    try:
        # Find process ID using the port
        result = subprocess.run(
            ["lsof", "-ti", f"{host}:{port}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split()
            for pid in pids:
                try:
                    subprocess.run(["kill", "-9", pid], timeout=5)
                    print(f"Stopped process {pid} using port {port}")
                except subprocess.TimeoutExpired:
                    print(f"Failed to stop process {pid}")
            return True
        else:
            print(f"No process found using port {port}")
            return False
    except subprocess.TimeoutExpired:
        print("Timeout while checking port usage")
        return False
    except FileNotFoundError:
        print("lsof command not available (not on Unix-like system)")
        return False
    except Exception as e:
        print(f"Error stopping process: {e}")
        return False


def ensure_port_available(host: str, port: int) -> None:
    """Ensure port is available, stop conflicting process if needed."""
    if check_port_occupied(host, port):
        print(f"Port {port} is occupied, attempting to stop conflicting process...")
        if stop_process_using_port(host, port):
            # Wait a moment for the process to fully stop
            import time
            time.sleep(1)
            if check_port_occupied(host, port):
                print(f"Warning: Port {port} still occupied after stopping process")
            else:
                print(f"Port {port} is now available")
        else:
            print(f"Could not stop process using port {port}")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="toonic-server",
        description="Toonic Server — bidirectional TOON streaming for LLM analysis",
    )
    parser.add_argument("--config", "-c", help="Config YAML file")
    parser.add_argument("--source", "-s", action="append", default=[],
                        help="Data source (file:path, log:path, rtsp://url)")
    parser.add_argument("--goal", "-g", default="analyze project structure and suggest improvements",
                        help="Analysis goal")
    parser.add_argument("--model", "-m", default="", help="LLM model override")
    parser.add_argument("--interval", "-i", type=float, default=30.0,
                        help="Analysis interval seconds (0=one-shot)")
    parser.add_argument("--when", "-w", default="",
                        help='Trigger condition in natural language, e.g. '
                             '"person detected for 1s, otherwise every 60s"')
    parser.add_argument("--triggers", "-t", default="",
                        help="YAML file with trigger rules")
    parser.add_argument("--host", default=None, help="Server host")
    parser.add_argument("--port", "-p", type=int, default=None, help="HTTP/WS port")
    parser.add_argument("--no-web", action="store_true", help="Disable web UI")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


# Protocols that have a matching watcher and work out of the box.
_SUPPORTED_PROTOCOLS = {
    # HttpWatcher (incl. WebSocket/gRPC probe via HTTP)
    "http", "https", "ws", "wss", "grpc",
    # StreamWatcher
    "rtsp", "rtsps", "rtmp",
    # DatabaseWatcher
    "postgresql", "postgres", "mysql", "redis", "mongodb",
}

# Protocols recognised but without a dedicated watcher yet.
_UNSUPPORTED_PROTOCOLS = {
    "ftp", "sftp", "ssh",
    "mqtt", "amqp", "kafka", "nats", "stomp",
    "ldap",
}


def parse_source_string(source_str: str):
    """Parse source string like 'file:./src/' or 'rtsp://cam1'.

    Supports 20 popular protocols (see _SUPPORTED_PROTOCOLS / _UNSUPPORTED_PROTOCOLS).
    Delegates category detection to toonic.server.quick.parse_source.
    """
    from toonic.server.config import SourceConfig
    from toonic.server.quick import parse_source as quick_parse_source

    # ── Protocol URLs: proto://... ──────────────────────────────
    if "://" in source_str and not source_str.startswith("file:"):
        proto = source_str.split("://", 1)[0].lower()

        if proto in _UNSUPPORTED_PROTOCOLS:
            supported = sorted(_SUPPORTED_PROTOCOLS)
            raise ValueError(
                f"Protocol '{proto}://' is not supported by any watcher yet.\n"
                f"Supported protocols: {', '.join(p + '://' for p in supported)}\n"
                f"Use a prefix instead (e.g. data:{source_str}) to treat it as raw data."
            )

        src = quick_parse_source(source_str)
        return SourceConfig(path_or_url=src.path_or_url, category=src.category, options=src.options)

    # ── Prefixed: log:path, docker:*, db:./app.db, etc. ─────────
    if ":" in source_str:
        prefix, _, path = source_str.partition(":")

        # Prefixes that watchers require as part of the source string.
        keep_prefixes = {
            "log", "logs",
            "dir", "directory",
            "docker", "container",
            "db", "sqlite", "postgres", "postgresql", "mysql", "redis", "mongodb", "mongo",
            "net", "ping", "dns",
            "proc", "pid", "port", "tcp", "service",
        }

        src = quick_parse_source(source_str)

        if prefix.lower() in keep_prefixes:
            normalized = source_str
        else:
            # For file-like prefixes normalize to raw path for FileWatcher.
            normalized = path

        return SourceConfig(path_or_url=normalized, category=src.category, options=src.options)

    # ── Plain path ──────────────────────────────────────────────
    return SourceConfig(path_or_url=source_str, category="code")


async def run_server(args):
    from toonic.server.config import ServerConfig, ModelConfig
    from toonic.server.main import ToonicServer
    from toonic.server.triggers.dsl import TriggerConfig, load_triggers

    # Build config
    if args.config and Path(args.config).exists():
        try:
            config = ServerConfig.from_yaml_file(args.config)
        except ImportError:
            config = ServerConfig.from_env()
    else:
        config = ServerConfig.from_env()

    if args.host is not None:
        config.host = args.host
    if args.port is not None:
        config.port = args.port
    config.goal = args.goal
    config.interval = args.interval
    config.log_level = args.log_level

    if args.model:
        for m in config.models.values():
            m.model = args.model

    # Parse sources
    for src_str in args.source:
        config.sources.append(parse_source_string(src_str))

    # Build trigger config
    trigger_config = None

    if args.triggers and Path(args.triggers).exists():
        # Load from YAML file
        yaml_str = Path(args.triggers).read_text()
        trigger_config = load_triggers(yaml_str)
        print(f"  Triggers: loaded {len(trigger_config.triggers)} rule(s) from {args.triggers}")

    elif args.when:
        # Generate from natural language via NLP2YAML
        from toonic.server.triggers.nlp2yaml import NLP2YAML
        nlp = NLP2YAML(model=args.model)
        # Detect source type from --source args
        source_hint = ""
        for src in args.source:
            if "rtsp://" in src or src.endswith((".mp4", ".avi")):
                source_hint = "video"
                break
            elif "log" in src.lower():
                source_hint = "logs"
                break
        print(f"  Generating triggers from: {args.when}")
        trigger_config = await nlp.generate(args.when, source=source_hint, goal=args.goal)
        from toonic.server.triggers.dsl import dump_triggers
        yaml_out = dump_triggers(trigger_config)
        print(f"  Generated YAML:\n{yaml_out}")
        # Save to CWD so user can inspect/edit
        triggers_path = Path("triggers.yaml")
        triggers_path.write_text(yaml_out)
        print(f"  Saved to: {triggers_path.resolve()}")

    # Create server
    server = ToonicServer(config, trigger_config=trigger_config)

    if args.no_web:
        # Run server without web UI
        await server.start()
        print(f"Toonic Server running (no-web mode)")
        print(f"  Goal: {config.goal}")
        print(f"  Sources: {len(config.sources)}")
        print(f"  Interval: {config.interval}s")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await server.stop()
    else:
        # Run with FastAPI web UI
        try:
            from toonic.server.transport.rest_api import create_app
            import uvicorn
        except ImportError:
            print("ERROR: pip install fastapi uvicorn")
            print("  Or run with --no-web flag")
            sys.exit(1)

        # Ensure port is available before starting web UI
        ensure_port_available(config.host, config.port)

        app = create_app(server)

        # Start server in background
        await server.start()

        print(f"\n  Toonic Server")
        print(f"  ─────────────────────────────────")
        print(f"  Web UI:   http://{config.host}:{config.port}/")
        print(f"  API:      http://{config.host}:{config.port}/api/status")
        print(f"  WS:       ws://{config.host}:{config.port}/ws")
        print(f"  Goal:     {config.goal}")
        print(f"  Sources:  {len(config.sources)}")
        print(f"  Interval: {config.interval}s")
        print(f"  Model:    {args.model or 'default'}")
        print(f"  Data:     {server.data_dir.resolve()}/")
        print(f"  History:  {server.data_dir.resolve()}/history.db")
        print(f"  Logs:     {server.data_dir.resolve()}/events.jsonl")
        if trigger_config:
            print(f"  Triggers: {len(trigger_config.triggers)} rule(s)")
        print()

        uvi_config = uvicorn.Config(
            app, host=config.host, port=config.port,
            log_level=config.log_level.lower(),
        )
        uvi_server = uvicorn.Server(uvi_config)

        try:
            await uvi_server.serve()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await server.stop()


def main():
    args = parse_args()
    import os
    data_dir = Path(os.environ.get("TOONIC_DATA_DIR", "./toonic_data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    log_file = data_dir / "server.log"
    # Console + file logging
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(str(log_file), encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    try:
        asyncio.run(run_server(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

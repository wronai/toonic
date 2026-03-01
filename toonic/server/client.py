"""
Toonic CLI Shell Client — interactive shell for Toonic Server.

Usage:
    python -m toonic.server.client                        # connect to localhost:8900
    python -m toonic.server.client --url http://host:8900 # custom URL
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from typing import Optional, Callable, Dict, List

import datetime

try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# Fallback: use urllib for basic HTTP
import urllib.request
import urllib.error


class ToonicClient:
    """REST + WebSocket client for Toonic Server."""

    def __init__(self, base_url: str = "http://localhost:8900"):
        self.base_url = base_url.rstrip("/")
        self.ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

    def get_status(self) -> dict:
        return self._get("/api/status")

    def get_actions(self, limit: int = 10) -> list:
        return self._get(f"/api/actions?limit={limit}")

    def get_formats(self) -> dict:
        return self._get("/api/formats")

    def analyze(self, goal: str = "", model: str = "") -> dict:
        return self._post("/api/analyze", {"goal": goal, "model": model})

    def add_source(self, path_or_url: str, category: str = "code") -> dict:
        return self._post("/api/sources", {"path_or_url": path_or_url, "category": category})

    def convert(self, path: str, fmt: str = "toon") -> dict:
        return self._post("/api/convert", {"path": path, "format": fmt})

    def get_history(self, limit: int = 20, **filters) -> list:
        params = "&".join(f"{k}={v}" for k, v in filters.items() if v)
        qs = f"?limit={limit}" + (f"&{params}" if params else "")
        return self._get(f"/api/history{qs}")

    def get_history_stats(self) -> dict:
        return self._get("/api/history/stats")

    def nlp_query(self, question: str) -> dict:
        return self._post("/api/query", {"question": question})

    def sql_query(self, sql: str) -> dict:
        return self._post("/api/sql", {"sql": sql})

    def _get(self, path: str) -> dict:
        url = self.base_url + path
        if HAS_HTTPX:
            import httpx
            r = httpx.get(url, timeout=30)
            return r.json()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _post(self, path: str, data: dict) -> dict:
        url = self.base_url + path
        if HAS_HTTPX:
            import httpx
            r = httpx.post(url, json=data, timeout=60)
            return r.json()
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())


# ══════════════════════════════════════════════════════════════
# Shell Command Handlers
# ══════════════════════════════════════════════════════════════

SHELL_COMMANDS = {
    "help": "Show this help",
    "status": "Show server status",
    "actions [N]": "Show recent LLM actions",
    "formats": "List supported formats",
    "analyze [goal]": "Trigger analysis with optional goal",
    "add <path> [category]": "Add data source",
    "convert <path> [format]": "Convert file to TOON/YAML/JSON",
    "model <name>": "Override model for next analyze",
    "history [N]": "Show last N conversation exchanges",
    "history-stats": "Show conversation history statistics",
    "query <question>": "NLP query on conversation history",
    "sql <SELECT ...>": "Raw SQL query on history database",
    "quit": "Exit shell",
}


def _print_help() -> None:
    """Print shell help text."""
    print("\nCommands:")
    for cmd, desc in SHELL_COMMANDS.items():
        print(f"  {cmd:30s} {desc}")
    print()


def _print_status(client: ToonicClient) -> None:
    """Print server status."""
    data = client.get_status()
    print(f"\n  Running:  {data.get('running')}")
    print(f"  Uptime:   {data.get('uptime_s', 0)}s")
    print(f"  Goal:     {data.get('goal', '')}")
    print(f"  Sources:  {json.dumps(data.get('sources', {}), indent=2)}")
    print(f"  Chunks:   {data.get('total_chunks', 0)}")
    print(f"  Actions:  {data.get('total_actions', 0)}")
    acc = data.get("accumulator", {})
    print(f"  Tokens:   {acc.get('total_tokens', 0)} / {acc.get('max_tokens', 0)}")
    router = data.get("router", {})
    print(f"  LLM:      {router.get('total_requests', 0)} requests, {router.get('total_tokens', 0)} tokens")
    print()


def _print_actions(client: ToonicClient, parts: List[str]) -> None:
    """Print recent LLM actions."""
    limit = int(parts[1]) if len(parts) > 1 else 10
    actions = client.get_actions(limit)
    if not actions:
        print("  No actions yet")
    for a in actions:
        print(f"\n  [{a.get('action_type', '?')}] {a.get('model_used', '')} ({a.get('duration_s', 0):.1f}s)")
        content = a.get("content", "")
        print(f"  {content[:300]}")
    print()


def _print_formats(client: ToonicClient) -> None:
    """Print supported formats."""
    data = client.get_formats()
    for cat, exts in data.get("categories", {}).items():
        print(f"  {cat:15s} {', '.join(exts)}")
    print(f"\n  Total handlers: {data.get('total_handlers', 0)}")


def _cmd_analyze(client: ToonicClient, parts: List[str], current_model: str) -> None:
    """Execute analyze command."""
    goal = " ".join(parts[1:]) if len(parts) > 1 else ""
    print(f"  Analyzing... (model: {current_model or 'default'})")
    data = client.analyze(goal=goal, model=current_model)
    print(f"\n  [{data.get('action_type', '?')}] confidence={data.get('confidence', 0):.1%}")
    print(f"  Model: {data.get('model_used', '')}")
    content = data.get("content", "")
    for line in content.split("\n"):
        print(f"  {line}")
    print()


def _cmd_add(client: ToonicClient, parts: List[str]) -> bool:
    """Execute add source command. Returns True if executed."""
    if len(parts) < 2:
        print("  Usage: add <path> [category]")
        return False
    path = parts[1]
    cat = parts[2] if len(parts) > 2 else "code"
    data = client.add_source(path, cat)
    print(f"  Added: {data.get('source_id', '')} ({data.get('status', '')})")
    return True


def _cmd_convert(client: ToonicClient, parts: List[str]) -> bool:
    """Execute convert command. Returns True if executed."""
    if len(parts) < 2:
        print("  Usage: convert <path> [toon|yaml|json]")
        return False
    path = parts[1]
    fmt = parts[2] if len(parts) > 2 else "toon"
    data = client.convert(path, fmt)
    if "error" in data:
        print(f"  Error: {data['error']}")
    else:
        print(f"\n  Format: {data.get('format')} | Tokens: ~{data.get('tokens', 0)}\n")
        print(data.get("spec", ""))
        print()
    return True


def _cmd_model(parts: List[str], current_model: str) -> str:
    """Execute model command. Returns updated model name."""
    if len(parts) > 1:
        new_model = parts[1]
        print(f"  Model set to: {new_model}")
        return new_model
    else:
        print(f"  Current model: {current_model or 'default'}")
        return current_model


def _print_history(client: ToonicClient, parts: List[str]) -> None:
    """Print conversation history."""
    limit = int(parts[1]) if len(parts) > 1 else 10
    records = client.get_history(limit=limit)
    if not records:
        print("  No history yet")
    for r in records:
        ts = datetime.datetime.fromtimestamp(r.get("timestamp", 0)).strftime("%H:%M:%S")
        print(f"  [{ts}] {r.get('model', '?'):40s} [{r.get('action_type', '?')}] "
              f"conf={r.get('confidence', 0):.0%} {r.get('duration_s', 0):.1f}s")
        content = r.get("content", "")[:150]
        if content:
            print(f"         {content}")
    print()


def _print_history_stats(client: ToonicClient) -> None:
    """Print history statistics."""
    data = client.get_history_stats()
    print(f"\n  Enabled:    {data.get('enabled', False)}")
    print(f"  Exchanges:  {data.get('total_exchanges', 0)}")
    print(f"  Tokens:     {data.get('total_tokens', 0)}")
    print(f"  Avg time:   {data.get('avg_duration_s', 0)}s")
    print(f"  Session:    {data.get('session_id', '')}")
    by_cat = data.get("by_category", {})
    if by_cat:
        print(f"  Categories: {json.dumps(by_cat)}")
    by_model = data.get("by_model", {})
    if by_model:
        print(f"  Models:     {json.dumps(by_model)}")
    print()


def _cmd_query(client: ToonicClient, parts: List[str]) -> bool:
    """Execute NLP query command. Returns True if executed."""
    question = " ".join(parts[1:]) if len(parts) > 1 else ""
    if not question:
        print("  Usage: query <natural language question>")
        return False
    print(f"  Querying: {question}")
    data = client.nlp_query(question)
    if "error" in data:
        print(f"  Error: {data['error']}")
    else:
        print(f"  SQL: {data.get('sql', '')}")
        print(f"  Results: {data.get('count', 0)} rows ({data.get('duration_s', 0)}s)")
        for row in data.get("results", [])[:20]:
            print(f"    {json.dumps(row, default=str)[:200]}")
    print()
    return True


def _cmd_sql(client: ToonicClient, line: str) -> bool:
    """Execute SQL query command. Returns True if executed."""
    sql_str = line[4:].strip() if len(line) > 4 else ""
    if not sql_str:
        print("  Usage: sql SELECT * FROM exchanges LIMIT 10")
        return False
    data = client.sql_query(sql_str)
    if "error" in data:
        print(f"  Error: {data['error']}")
    else:
        print(f"  Results: {data.get('count', 0)} rows")
        for row in data.get("results", [])[:20]:
            print(f"    {json.dumps(row, default=str)[:200]}")
    print()
    return True


# ══════════════════════════════════════════════════════════════
# Shell Command Router
# ══════════════════════════════════════════════════════════════

CommandHandler = Callable[..., bool | None]


def _get_command_handler(cmd: str) -> Optional[CommandHandler]:
    """Get handler function for a command. Returns None for unknown commands."""
    handlers: Dict[str, CommandHandler] = {
        "help": _print_help,
        "status": _print_status,
        "actions": _print_actions,
        "formats": _print_formats,
        "analyze": _cmd_analyze,
        "add": _cmd_add,
        "convert": _cmd_convert,
        "model": _cmd_model,
        "history": _print_history,
        "history-stats": _print_history_stats,
        "query": _cmd_query,
        "sql": _cmd_sql,
    }
    return handlers.get(cmd)


def _should_exit(cmd: str) -> bool:
    """Check if command should exit the shell."""
    return cmd in ("quit", "exit", "q")


def _execute_command(
    cmd: str,
    parts: List[str],
    line: str,
    client: ToonicClient,
    current_model: str,
) -> tuple[bool, str]:
    """Execute a shell command. Returns (should_continue, new_model)."""
    if _should_exit(cmd):
        return False, current_model

    if cmd == "model":
        new_model = _cmd_model(parts, current_model)
        return True, new_model

    handler = _get_command_handler(cmd)
    if handler is None:
        print(f"  Unknown command: {cmd}. Type 'help' for commands.")
        return True, current_model

    # Handle commands with different signatures
    if cmd in ("help", "formats"):
        handler(client)
    elif cmd == "status":
        handler(client)
    elif cmd in ("actions", "history"):
        handler(client, parts)
    elif cmd == "analyze":
        handler(client, parts, current_model)
    elif cmd in ("add", "convert", "query"):
        handler(client, parts)
    elif cmd == "history-stats":
        handler(client)
    elif cmd == "sql":
        handler(client, line)

    return True, current_model


def run_shell(base_url: str = "http://localhost:8900"):
    """Interactive shell for Toonic Server."""
    client = ToonicClient(base_url)

    print(f"\n  Toonic Shell — connected to {base_url}")
    print(f"  Type 'help' for commands, 'quit' to exit\n")

    current_model = ""

    while True:
        try:
            line = input("toonic> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split(maxsplit=2)
        cmd = parts[0].lower()

        try:
            should_continue, current_model = _execute_command(
                cmd, parts, line, client, current_model
            )
            if not should_continue:
                break
        except urllib.error.URLError as e:
            print(f"  Connection error: {e}")
        except Exception as e:
            print(f"  Error: {e}")


def main():
    parser = argparse.ArgumentParser(prog="toonic-client", description="Toonic CLI Shell")
    parser.add_argument("--url", default="http://localhost:8900", help="Server URL")
    parser.add_argument("--status", action="store_true", help="Show status and exit")
    parser.add_argument("--analyze", nargs="?", const="", help="Trigger analysis and exit")
    parser.add_argument("--convert", help="Convert file and exit")
    parser.add_argument("--format", default="toon", help="Output format for --convert")
    args = parser.parse_args()

    client = ToonicClient(args.url)

    if args.status:
        data = client.get_status()
        print(json.dumps(data, indent=2))
        return

    if args.analyze is not None:
        data = client.analyze(goal=args.analyze)
        print(json.dumps(data, indent=2))
        return

    if args.convert:
        data = client.convert(args.convert, args.format)
        if "spec" in data:
            print(data["spec"])
        else:
            print(json.dumps(data, indent=2))
        return

    run_shell(args.url)


if __name__ == "__main__":
    main()

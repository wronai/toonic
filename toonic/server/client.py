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
from typing import Optional

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


def run_shell(base_url: str = "http://localhost:8900"):
    """Interactive shell for Toonic Server."""
    client = ToonicClient(base_url)

    print(f"\n  Toonic Shell — connected to {base_url}")
    print(f"  Type 'help' for commands, 'quit' to exit\n")

    commands = {
        "help": "Show this help",
        "status": "Show server status",
        "actions": "Show recent LLM actions",
        "formats": "List supported formats",
        "analyze [goal]": "Trigger analysis with optional goal",
        "add <path> [category]": "Add data source",
        "convert <path> [format]": "Convert file to TOON/YAML/JSON",
        "model <name>": "Override model for next analyze",
        "quit": "Exit shell",
    }

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
            if cmd in ("quit", "exit", "q"):
                break

            elif cmd == "help":
                print("\nCommands:")
                for c, desc in commands.items():
                    print(f"  {c:30s} {desc}")
                print()

            elif cmd == "status":
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

            elif cmd == "actions":
                limit = int(parts[1]) if len(parts) > 1 else 10
                actions = client.get_actions(limit)
                if not actions:
                    print("  No actions yet")
                for a in actions:
                    print(f"\n  [{a.get('action_type', '?')}] {a.get('model_used', '')} ({a.get('duration_s', 0):.1f}s)")
                    content = a.get("content", "")
                    print(f"  {content[:300]}")
                print()

            elif cmd == "formats":
                data = client.get_formats()
                for cat, exts in data.get("categories", {}).items():
                    print(f"  {cat:15s} {', '.join(exts)}")
                print(f"\n  Total handlers: {data.get('total_handlers', 0)}")

            elif cmd == "analyze":
                goal = " ".join(parts[1:]) if len(parts) > 1 else ""
                print(f"  Analyzing... (model: {current_model or 'default'})")
                data = client.analyze(goal=goal, model=current_model)
                print(f"\n  [{data.get('action_type', '?')}] confidence={data.get('confidence', 0):.1%}")
                print(f"  Model: {data.get('model_used', '')}")
                content = data.get("content", "")
                # Print content with wrapping
                for line in content.split("\n"):
                    print(f"  {line}")
                print()

            elif cmd == "add":
                if len(parts) < 2:
                    print("  Usage: add <path> [category]")
                    continue
                path = parts[1]
                cat = parts[2] if len(parts) > 2 else "code"
                data = client.add_source(path, cat)
                print(f"  Added: {data.get('source_id', '')} ({data.get('status', '')})")

            elif cmd == "convert":
                if len(parts) < 2:
                    print("  Usage: convert <path> [toon|yaml|json]")
                    continue
                path = parts[1]
                fmt = parts[2] if len(parts) > 2 else "toon"
                data = client.convert(path, fmt)
                if "error" in data:
                    print(f"  Error: {data['error']}")
                else:
                    print(f"\n  Format: {data.get('format')} | Tokens: ~{data.get('tokens', 0)}\n")
                    print(data.get("spec", ""))
                    print()

            elif cmd == "model":
                if len(parts) > 1:
                    current_model = parts[1]
                    print(f"  Model set to: {current_model}")
                else:
                    print(f"  Current model: {current_model or 'default'}")

            else:
                print(f"  Unknown command: {cmd}. Type 'help' for commands.")

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

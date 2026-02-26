"""
REST API + WebSocket transport — FastAPI-based server with web UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("toonic.transport.rest")

# HTML template for web UI
WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Toonic Server</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e0e0e0; }
  .header { background: #1a1d27; padding: 16px 24px; border-bottom: 1px solid #2a2d3a; display: flex; align-items: center; gap: 16px; }
  .header h1 { font-size: 20px; color: #60a5fa; }
  .header .status { font-size: 13px; color: #6b7280; }
  .header .status.ok { color: #34d399; }
  .container { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; height: calc(100vh - 60px); }
  .panel { background: #1a1d27; border: 1px solid #2a2d3a; border-radius: 8px; display: flex; flex-direction: column; overflow: hidden; }
  .panel-title { padding: 10px 16px; font-size: 13px; font-weight: 600; color: #9ca3af; border-bottom: 1px solid #2a2d3a; text-transform: uppercase; letter-spacing: 0.5px; }
  .panel-body { flex: 1; overflow-y: auto; padding: 12px; font-size: 13px; font-family: 'JetBrains Mono', 'Fira Code', monospace; }
  .event { padding: 6px 8px; margin: 2px 0; border-radius: 4px; border-left: 3px solid #374151; }
  .event.context { border-left-color: #3b82f6; }
  .event.action { border-left-color: #10b981; background: #0d2818; }
  .event.error { border-left-color: #ef4444; background: #2d1010; }
  .event.status { border-left-color: #8b5cf6; }
  .event .ts { color: #6b7280; font-size: 11px; }
  .event .type { color: #60a5fa; font-weight: 600; }
  .controls { padding: 12px; border-top: 1px solid #2a2d3a; display: flex; gap: 8px; flex-wrap: wrap; }
  input, select, button { font-size: 13px; padding: 6px 12px; border-radius: 6px; border: 1px solid #374151; background: #111827; color: #e0e0e0; }
  input { flex: 1; min-width: 150px; }
  button { background: #2563eb; border-color: #2563eb; cursor: pointer; font-weight: 500; }
  button:hover { background: #1d4ed8; }
  button.danger { background: #dc2626; border-color: #dc2626; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px; padding: 12px; }
  .stat { background: #111827; padding: 10px; border-radius: 6px; text-align: center; }
  .stat .val { font-size: 22px; font-weight: 700; color: #60a5fa; }
  .stat .lbl { font-size: 11px; color: #6b7280; margin-top: 2px; }
  pre { white-space: pre-wrap; word-break: break-all; }
  .full-width { grid-column: 1 / -1; }
  @media (max-width: 768px) { .container { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="header">
  <h1>&#x1f680; Toonic Server</h1>
  <span class="status" id="ws-status">Connecting...</span>
</div>
<div class="container">
  <div class="panel">
    <div class="panel-title">Live Events</div>
    <div class="panel-body" id="events"></div>
  </div>
  <div class="panel">
    <div class="panel-title">LLM Actions</div>
    <div class="panel-body" id="actions"></div>
    <div class="controls">
      <input id="goal-input" placeholder="Goal: analyze, fix bugs, optimize..." value="">
      <select id="model-select">
        <option value="">Default model</option>
        <option value="google/gemini-2.5-flash-preview:thinking">Gemini Flash</option>
        <option value="anthropic/claude-sonnet-4">Claude Sonnet</option>
        <option value="openai/gpt-4o">GPT-4o</option>
      </select>
      <button onclick="analyzeNow()">Analyze Now</button>
    </div>
  </div>
  <div class="panel">
    <div class="panel-title">Sources</div>
    <div class="panel-body" id="sources"></div>
    <div class="controls">
      <input id="source-path" placeholder="/path/to/source or rtsp://...">
      <select id="source-cat">
        <option value="code">code</option>
        <option value="config">config</option>
        <option value="logs">logs</option>
        <option value="data">data</option>
        <option value="video">video</option>
        <option value="audio">audio</option>
      </select>
      <button onclick="addSource()">Add Source</button>
    </div>
  </div>
  <div class="panel">
    <div class="panel-title">Server Stats</div>
    <div class="stats" id="stats"></div>
  </div>
</div>
<script>
let ws;
const eventsDiv = document.getElementById('events');
const actionsDiv = document.getElementById('actions');
const sourcesDiv = document.getElementById('sources');
const statsDiv = document.getElementById('stats');
const statusEl = document.getElementById('ws-status');

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onopen = () => { statusEl.textContent = 'Connected'; statusEl.className = 'status ok'; };
  ws.onclose = () => { statusEl.textContent = 'Disconnected'; statusEl.className = 'status'; setTimeout(connect, 2000); };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleEvent(msg);
  };
}

function handleEvent(msg) {
  const ts = new Date(msg.timestamp * 1000).toLocaleTimeString();
  if (msg.event === 'context') {
    addEvent(eventsDiv, 'context', ts, `[${msg.data.category}] ${msg.data.source_id}`, msg.data.toon_spec?.substring(0, 200) || '');
  } else if (msg.event === 'action') {
    addEvent(actionsDiv, 'action', ts, `[${msg.data.action_type}] ${msg.data.model_used}`, msg.data.content?.substring(0, 500) || '');
  } else if (msg.event === 'error') {
    addEvent(eventsDiv, 'error', ts, 'ERROR', JSON.stringify(msg.data));
  } else if (msg.event === 'source_added') {
    addEvent(sourcesDiv, 'status', ts, msg.data.source_id, msg.data.type);
  } else {
    addEvent(eventsDiv, 'status', ts, msg.event, JSON.stringify(msg.data).substring(0, 200));
  }
}

function addEvent(container, cls, ts, title, body) {
  const div = document.createElement('div');
  div.className = `event ${cls}`;
  div.innerHTML = `<span class="ts">${ts}</span> <span class="type">${title}</span><pre>${body}</pre>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  if (container.children.length > 200) container.removeChild(container.firstChild);
}

async function analyzeNow() {
  const goal = document.getElementById('goal-input').value;
  const model = document.getElementById('model-select').value;
  const resp = await fetch('/api/analyze', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({goal, model})
  });
  const data = await resp.json();
  addEvent(actionsDiv, 'action', new Date().toLocaleTimeString(), `[${data.action_type}]`, data.content?.substring(0, 500) || JSON.stringify(data));
}

async function addSource() {
  const path = document.getElementById('source-path').value;
  const cat = document.getElementById('source-cat').value;
  if (!path) return;
  await fetch('/api/sources', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path_or_url: path, category: cat})
  });
  document.getElementById('source-path').value = '';
}

async function refreshStats() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    statsDiv.innerHTML = `
      <div class="stat"><div class="val">${data.total_chunks || 0}</div><div class="lbl">Chunks</div></div>
      <div class="stat"><div class="val">${data.total_actions || 0}</div><div class="lbl">Actions</div></div>
      <div class="stat"><div class="val">${Object.keys(data.sources || {}).length}</div><div class="lbl">Sources</div></div>
      <div class="stat"><div class="val">${data.accumulator?.total_tokens || 0}</div><div class="lbl">Tokens</div></div>
      <div class="stat"><div class="val">${data.router?.total_requests || 0}</div><div class="lbl">LLM Calls</div></div>
      <div class="stat"><div class="val">${data.uptime_s || 0}s</div><div class="lbl">Uptime</div></div>
    `;
  } catch(e) {}
}

connect();
setInterval(refreshStats, 3000);
refreshStats();
</script>
</body>
</html>"""


def create_app(server) -> Any:
    """Create FastAPI app with REST API + WebSocket + Web UI."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError:
        raise ImportError("pip install fastapi uvicorn")

    app = FastAPI(title="Toonic Server", version="1.0.0")
    ws_clients: set = set()

    # ── Event broadcaster ────────────────────────────────────

    async def broadcast_event(event):
        """Broadcast server events to all WebSocket clients."""
        data = json.dumps(event.to_dict())
        disconnected = set()
        for client in ws_clients:
            try:
                await client.send_text(data)
            except Exception:
                disconnected.add(client)
        ws_clients -= disconnected

    server.on_event(broadcast_event)

    # ── Web UI ───────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def web_ui():
        return WEB_UI_HTML

    # ── WebSocket ────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        ws_clients.add(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                # Handle client commands via WebSocket
                if msg.get("command") == "analyze":
                    action = await server.analyze_now(
                        goal=msg.get("goal", ""),
                        model=msg.get("model", ""),
                    )
                    await websocket.send_text(json.dumps({
                        "event": "action", "data": action.to_dict(), "timestamp": time.time()
                    }))
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            ws_clients.discard(websocket)

    # ── REST API ─────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        return server.get_status()

    @app.get("/api/actions")
    async def get_actions(limit: int = 20):
        return server.get_actions(limit)

    @app.post("/api/analyze")
    async def analyze_now(body: dict = {}):
        action = await server.analyze_now(
            goal=body.get("goal", ""),
            model=body.get("model", ""),
        )
        return action.to_dict()

    @app.post("/api/sources")
    async def add_source(body: dict = {}):
        from toonic.server.config import SourceConfig
        src = SourceConfig(
            path_or_url=body.get("path_or_url", ""),
            category=body.get("category", "code"),
        )
        sid = await server.add_source(src)
        return {"source_id": sid, "status": "added"}

    @app.delete("/api/sources/{source_id}")
    async def remove_source(source_id: str):
        await server.remove_source(source_id)
        return {"source_id": source_id, "status": "removed"}

    @app.post("/api/convert")
    async def convert_file(body: dict = {}):
        """Convert a file to TOON/YAML/JSON spec."""
        from toonic.pipeline import Pipeline
        path = body.get("path", "")
        fmt = body.get("format", "toon")
        try:
            spec = Pipeline.to_spec(path, fmt=fmt)
            tokens = len(spec.split()) * 4 // 3
            return {"spec": spec, "tokens": tokens, "format": fmt}
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    @app.get("/api/formats")
    async def list_formats():
        from toonic.pipeline import Pipeline
        return Pipeline.formats()

    import time  # needed for websocket event timestamp
    return app

"""
REST API + WebSocket transport — FastAPI-based server with web UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
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
  .header { background: #1a1d27; padding: 12px 24px; border-bottom: 1px solid #2a2d3a; display: flex; align-items: center; gap: 16px; }
  .header h1 { font-size: 18px; color: #60a5fa; }
  .header .status { font-size: 12px; padding: 3px 10px; border-radius: 12px; background: #1f2937; }
  .header .status.ok { color: #34d399; background: #0d2818; }
  .header .goal { font-size: 12px; color: #6b7280; margin-left: auto; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tabs { display: flex; background: #1a1d27; border-bottom: 1px solid #2a2d3a; padding: 0 16px; }
  .tab { padding: 10px 18px; font-size: 13px; cursor: pointer; color: #6b7280; border-bottom: 2px solid transparent; transition: all 0.2s; }
  .tab:hover { color: #e0e0e0; }
  .tab.active { color: #60a5fa; border-bottom-color: #60a5fa; }
  .tab .badge { background: #374151; color: #9ca3af; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px; }
  .tab.active .badge { background: #1e3a5f; color: #60a5fa; }
  .main { height: calc(100vh - 90px); overflow: hidden; }
  .tab-content { display: none; height: 100%; }
  .tab-content.active { display: flex; flex-direction: column; }
  .split { display: grid; grid-template-columns: 1fr 1fr; gap: 0; height: 100%; }
  .split-v { display: grid; grid-template-rows: auto 1fr; height: 100%; }
  .panel { display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid #2a2d3a; }
  .panel:last-child { border-right: none; }
  .panel-hdr { padding: 8px 14px; font-size: 12px; font-weight: 600; color: #9ca3af; background: #141720; border-bottom: 1px solid #2a2d3a; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center; gap: 8px; }
  .panel-hdr .cnt { font-size: 10px; color: #60a5fa; background: #1e3a5f; padding: 1px 6px; border-radius: 8px; }
  .panel-body { flex: 1; overflow-y: auto; padding: 8px; font-size: 12px; font-family: 'JetBrains Mono', 'Fira Code', monospace; }
  .ev { padding: 5px 8px; margin: 1px 0; border-radius: 4px; border-left: 3px solid #374151; background: #111827; }
  .ev:hover { background: #1a1f2e; }
  .ev.ctx { border-left-color: #3b82f6; }
  .ev.act { border-left-color: #10b981; background: #0a1f15; }
  .ev.trg { border-left-color: #f59e0b; background: #1a1505; }
  .ev.err { border-left-color: #ef4444; background: #1f0a0a; }
  .ev.sts { border-left-color: #8b5cf6; }
  .ev .ts { color: #4b5563; font-size: 10px; }
  .ev .tp { font-weight: 600; margin: 0 4px; }
  .ev .tp.ctx { color: #3b82f6; }
  .ev .tp.act { color: #10b981; }
  .ev .tp.trg { color: #f59e0b; }
  .ev .tp.err { color: #ef4444; }
  .ev .tp.sts { color: #8b5cf6; }
  .ev pre { white-space: pre-wrap; word-break: break-all; color: #9ca3af; margin-top: 2px; font-size: 11px; max-height: 120px; overflow: hidden; }
  .ev.expanded pre { max-height: none; }
  .controls { padding: 8px 12px; border-top: 1px solid #2a2d3a; display: flex; gap: 6px; flex-wrap: wrap; background: #141720; }
  input, select, button { font-size: 12px; padding: 5px 10px; border-radius: 6px; border: 1px solid #374151; background: #111827; color: #e0e0e0; }
  input { flex: 1; min-width: 120px; }
  button { background: #2563eb; border-color: #2563eb; cursor: pointer; font-weight: 500; }
  button:hover { background: #1d4ed8; }
  button.sm { padding: 3px 8px; font-size: 11px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px; padding: 10px; }
  .stat { background: #111827; padding: 8px; border-radius: 6px; text-align: center; }
  .stat .v { font-size: 20px; font-weight: 700; color: #60a5fa; }
  .stat .l { font-size: 10px; color: #6b7280; margin-top: 2px; }
  .exchange { padding: 8px 12px; margin: 4px 0; background: #111827; border-radius: 6px; border: 1px solid #1f2937; cursor: pointer; }
  .exchange:hover { border-color: #374151; }
  .exchange .meta { font-size: 11px; color: #6b7280; display: flex; gap: 12px; }
  .exchange .meta span { display: flex; align-items: center; gap: 4px; }
  .exchange .content { margin-top: 6px; font-size: 12px; color: #d1d5db; max-height: 80px; overflow: hidden; }
  .exchange.expanded .content { max-height: none; }
  .tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 4px; }
  .tag.cat { background: #1e3a5f; color: #60a5fa; }
  .tag.model { background: #1a2e1a; color: #34d399; }
  .tag.type { background: #2d1f3d; color: #a78bfa; }
  .trigger-rule { padding: 8px 12px; margin: 4px 0; background: #111827; border-radius: 6px; border: 1px solid #1f2937; }
  .trigger-rule .name { font-weight: 600; color: #f59e0b; }
  .trigger-rule .detail { font-size: 11px; color: #6b7280; margin-top: 4px; }
  .empty { color: #4b5563; text-align: center; padding: 40px; font-size: 13px; }
  @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="header">
  <h1>&#x1f680; Toonic Server</h1>
  <span class="status" id="ws-status">Connecting...</span>
  <span class="goal" id="goal-display"></span>
</div>
<div class="tabs">
  <div class="tab active" data-tab="events">Events <span class="badge" id="ev-cnt">0</span></div>
  <div class="tab" data-tab="actions">LLM Actions <span class="badge" id="act-cnt">0</span></div>
  <div class="tab" data-tab="history">History</div>
  <div class="tab" data-tab="triggers">Triggers</div>
  <div class="tab" data-tab="sources">Sources</div>
  <div class="tab" data-tab="overview">Overview</div>
</div>
<div class="main">
  <!-- Events tab -->
  <div class="tab-content active" id="tc-events">
    <div class="panel-hdr">Live Event Stream <span class="cnt" id="ev-total">0</span>
      <button class="sm" onclick="clearEvents()" style="margin-left:auto">Clear</button>
      <select id="ev-filter" onchange="filterEvents()" style="font-size:11px;padding:2px 6px">
        <option value="">All</option><option value="context">Context</option><option value="trigger">Triggers</option>
        <option value="action">Actions</option><option value="status">Status</option><option value="error">Errors</option>
      </select>
    </div>
    <div class="panel-body" id="events-list"></div>
  </div>
  <!-- Actions tab -->
  <div class="tab-content" id="tc-actions">
    <div class="panel-hdr">LLM Exchanges <span class="cnt" id="act-total">0</span></div>
    <div class="panel-body" id="actions-list"></div>
    <div class="controls">
      <input id="goal-input" placeholder="Goal: describe, find bugs, optimize...">
      <select id="model-select">
        <option value="">Default</option>
        <option value="google/gemini-2.5-flash-preview:thinking">Gemini Flash</option>
        <option value="anthropic/claude-sonnet-4">Claude Sonnet</option>
        <option value="openai/gpt-4o">GPT-4o</option>
      </select>
      <button onclick="analyzeNow()">&#x25B6; Analyze Now</button>
    </div>
  </div>
  <!-- History tab -->
  <div class="tab-content" id="tc-history">
    <div class="panel-hdr">Conversation History (SQLite)
      <button class="sm" onclick="loadHistory()" style="margin-left:auto">Refresh</button>
    </div>
    <div class="panel-body" id="history-list"><div class="empty">Click Refresh to load</div></div>
    <div class="controls">
      <input id="query-input" placeholder="NLP query: errors from last hour, show code analyses...">
      <button onclick="nlpQuery()">Query</button>
    </div>
  </div>
  <!-- Triggers tab -->
  <div class="tab-content" id="tc-triggers">
    <div class="panel-hdr">Trigger Rules &amp; Stats</div>
    <div class="panel-body" id="triggers-list"><div class="empty">Loading...</div></div>
  </div>
  <!-- Sources tab -->
  <div class="tab-content" id="tc-sources">
    <div class="panel-hdr">Data Sources</div>
    <div class="panel-body" id="sources-list"></div>
    <div class="controls">
      <input id="source-path" placeholder="/path or rtsp://...">
      <select id="source-cat"><option>code</option><option>config</option><option>logs</option><option>data</option><option>video</option><option>audio</option></select>
      <button onclick="addSource()">Add Source</button>
    </div>
  </div>
  <!-- Overview tab -->
  <div class="tab-content" id="tc-overview">
    <div class="panel-hdr">Server Overview</div>
    <div class="panel-body">
      <div class="stats" id="stats"></div>
      <div id="data-dir" style="padding:10px;font-size:12px;color:#6b7280"></div>
    </div>
  </div>
</div>
<script>
let ws, evCount=0, actCount=0, allEvents=[], currentFilter='';
const $=id=>document.getElementById(id);

// Tabs
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  $('tc-'+t.dataset.tab).classList.add('active');
  if(t.dataset.tab==='triggers') loadTriggers();
  if(t.dataset.tab==='overview') refreshStats();
});

function connect() {
  const proto = location.protocol==='https:'?'wss:':'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onopen=()=>{$('ws-status').textContent='Connected';$('ws-status').className='status ok';};
  ws.onerror=()=>{$('ws-status').textContent='WS Error';$('ws-status').className='status';};
  $('ws-status').textContent='Connecting...';
  ws.onclose=()=>{$('ws-status').textContent='Disconnected';$('ws-status').className='status';setTimeout(connect,2000);};
  ws.onmessage=(e)=>handleEvent(JSON.parse(e.data));
}

function handleEvent(msg) {
  allEvents.push(msg);
  if(allEvents.length>1000) allEvents=allEvents.slice(-500);
  evCount++;
  $('ev-cnt').textContent=evCount;
  $('ev-total').textContent=evCount;
  const evType = msg.event||'unknown';
  const cls = {context:'ctx',action:'act',trigger:'trg',error:'err',analysis_start:'sts',status:'sts',source_added:'sts'}[evType]||'sts';
  if(currentFilter && evType!==currentFilter) return;
  const ts = new Date((msg.timestamp||Date.now()/1000)*1000).toLocaleTimeString();
  let title='', body='';
  const d = msg.data||{};
  if(evType==='context'){
    title=`[${d.category||'?'}] ${(d.source_id||'').substring(0,50)}`;
    body=(d.toon_spec||'').substring(0,200);
  } else if(evType==='action'){
    actCount++; $('act-cnt').textContent=actCount;
    title=`[${d.action_type||'?'}] ${d.model_used||''}`;
    body=(d.content||'').substring(0,600);
    addAction(msg);
  } else if(evType==='trigger'){
    title=`[${d.rule||'?'}] ${d.reason||''}`;
    const dets=(d.detections||[]).map(x=>`${x.event_type}:${(x.score||0).toFixed(2)}`).join(', ');
    body=dets||d.goal||'';
  } else if(evType==='error'){
    title='ERROR'; body=JSON.stringify(d);
  } else {
    title=evType; body=JSON.stringify(d).substring(0,300);
  }
  addEv($('events-list'), cls, ts, title, body);
}

function addEv(el, cls, ts, title, body) {
  const div=document.createElement('div'); div.className='ev '+cls;
  div.innerHTML=`<span class="ts">${ts}</span><span class="tp ${cls}">${title}</span>`+(body?`<pre>${esc(body)}</pre>`:'');
  div.onclick=()=>div.classList.toggle('expanded');
  el.appendChild(div); el.scrollTop=el.scrollHeight;
  if(el.children.length>500) el.removeChild(el.firstChild);
}

function addAction(msg) {
  const d=msg.data||{}, el=$('actions-list');
  const div=document.createElement('div'); div.className='exchange';
  div.innerHTML=`<div class="meta">
    <span class="tag type">${d.action_type||'?'}</span>
    <span class="tag model">${d.model_used||''}</span>
    <span>${(d.duration_s||0).toFixed(1)}s</span>
    <span>${new Date((msg.timestamp||Date.now()/1000)*1000).toLocaleTimeString()}</span>
  </div><div class="content">${esc(d.content||'')}</div>`;
  div.onclick=()=>div.classList.toggle('expanded');
  el.appendChild(div); el.scrollTop=el.scrollHeight;
  $('act-total').textContent=actCount;
}

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function clearEvents(){$('events-list').innerHTML='';}
function filterEvents(){
  currentFilter=$('ev-filter').value;
  $('events-list').innerHTML='';
  allEvents.forEach(m=>{
    if(!currentFilter||m.event===currentFilter) handleEventReplay(m);
  });
}
function handleEventReplay(msg){
  const evType=msg.event||'unknown';
  const cls={context:'ctx',action:'act',trigger:'trg',error:'err'}[evType]||'sts';
  const ts=new Date((msg.timestamp||Date.now()/1000)*1000).toLocaleTimeString();
  const d=msg.data||{};
  let title='',body='';
  if(evType==='context'){title=`[${d.category}] ${(d.source_id||'').substring(0,50)}`;body=(d.toon_spec||'').substring(0,200);}
  else if(evType==='action'){title=`[${d.action_type}] ${d.model_used||''}`;body=(d.content||'').substring(0,400);}
  else if(evType==='trigger'){title=`[${d.rule}] ${d.reason}`;body=d.goal||'';}
  else{title=evType;body=JSON.stringify(d).substring(0,200);}
  addEv($('events-list'),cls,ts,title,body);
}

async function analyzeNow(){
  const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({goal:$('goal-input').value,model:$('model-select').value})});
  const d=await r.json();
  addEv($('events-list'),'act',new Date().toLocaleTimeString(),`[${d.action_type}]`,(d.content||'').substring(0,400));
}
async function addSource(){
  const p=$('source-path').value,c=$('source-cat').value; if(!p) return;
  await fetch('/api/sources',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path_or_url:p,category:c})});
  $('source-path').value=''; refreshSources();
}
async function loadHistory(){
  const el=$('history-list'); el.innerHTML='<div class="empty">Loading...</div>';
  const r=await fetch('/api/history?limit=50'); const data=await r.json();
  el.innerHTML='';
  if(!data.length){el.innerHTML='<div class="empty">No history yet</div>';return;}
  data.reverse().forEach(h=>{
    const div=document.createElement('div');div.className='exchange';
    div.innerHTML=`<div class="meta">
      <span class="tag cat">${h.category||'?'}</span>
      <span class="tag type">${h.action_type||'?'}</span>
      <span class="tag model">${h.model||''}</span>
      <span>${(h.duration_s||0).toFixed(1)}s</span>
      <span>${h.confidence?(h.confidence*100).toFixed(0)+'%':''}</span>
      <span>${new Date((h.timestamp||0)*1000).toLocaleString()}</span>
    </div>
    <div class="content"><strong>Goal:</strong> ${esc(h.goal||'')}<br><strong>Response:</strong> ${esc((h.response||'').substring(0,500))}</div>`;
    div.onclick=()=>div.classList.toggle('expanded');
    el.appendChild(div);
  });
}
async function nlpQuery(){
  const q=$('query-input').value; if(!q) return;
  const el=$('history-list'); el.innerHTML='<div class="empty">Querying...</div>';
  const r=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
  const data=await r.json();
  el.innerHTML=`<div class="ev sts" style="margin:8px"><pre>SQL: ${esc(data.sql||'')}</pre></div>`;
  (data.results||[]).forEach(row=>{
    const div=document.createElement('div');div.className='exchange';div.innerHTML=`<pre>${esc(JSON.stringify(row,null,2))}</pre>`;
    el.appendChild(div);
  });
  if(!data.results?.length) el.innerHTML+='<div class="empty">No results</div>';
}
async function loadTriggers(){
  const el=$('triggers-list'); el.innerHTML='<div class="empty">Loading...</div>';
  const r=await fetch('/api/triggers'); const data=await r.json();
  el.innerHTML='';
  if(data.config) {
    (data.config.triggers||[]).forEach(t=>{
      const div=document.createElement('div');div.className='trigger-rule';
      const events=(t.events||[]).map(e=>`<span class="tag cat">${e.type}${e.label?':'+e.label:''} thr=${e.threshold}</span>`).join(' ');
      div.innerHTML=`<div class="name">${t.name}</div><div class="detail">
        Mode: <strong>${t.mode}</strong> | Interval: ${t.interval_s||'-'}s | Cooldown: ${t.cooldown_s||'-'}s<br>
        Events: ${events||'none'}<br>
        ${t.fallback?.periodic_s?'Fallback: every '+t.fallback.periodic_s+'s':''}
        ${t.goal?'<br>Goal: <em>'+esc(t.goal)+'</em>':''}
      </div>`;
      el.appendChild(div);
    });
  }
  if(data.stats){
    const s=data.stats;
    el.innerHTML+=`<div class="ev sts" style="margin:8px"><pre>Rules: ${s.total_rules}\n${(s.rules||[]).map(r=>r.rule+': events='+r.event_count+' periodic='+r.periodic_count).join('\n')}</pre></div>`;
  }
}
async function refreshSources(){
  try{
    const r=await fetch('/api/status');const d=await r.json();
    const el=$('sources-list');el.innerHTML='';
    Object.entries(d.sources||{}).forEach(([sid,typ])=>{
      el.innerHTML+=`<div class="ev sts"><span class="tp sts">${sid}</span> <span class="tag model">${typ}</span></div>`;
    });
    if(!Object.keys(d.sources||{}).length) el.innerHTML='<div class="empty">No sources</div>';
  }catch(e){}
}
async function refreshStats(){
  try{
    const r=await fetch('/api/status');const d=await r.json();
    $('goal-display').textContent=d.goal||'';
    $('stats').innerHTML=`
      <div class="stat"><div class="v">${d.total_chunks||0}</div><div class="l">Chunks</div></div>
      <div class="stat"><div class="v">${d.total_actions||0}</div><div class="l">Actions</div></div>
      <div class="stat"><div class="v">${d.total_events||0}</div><div class="l">Events</div></div>
      <div class="stat"><div class="v">${Object.keys(d.sources||{}).length}</div><div class="l">Sources</div></div>
      <div class="stat"><div class="v">${d.accumulator?.total_tokens||0}</div><div class="l">Tokens</div></div>
      <div class="stat"><div class="v">${d.router?.total_requests||0}</div><div class="l">LLM Calls</div></div>
      <div class="stat"><div class="v">${d.trigger_stats?.total_rules||0}</div><div class="l">Trigger Rules</div></div>
      <div class="stat"><div class="v">${d.uptime_s||0}s</div><div class="l">Uptime</div></div>
    `;
    $('data-dir').innerHTML=`Data directory: <code>${d.data_dir||'?'}</code>`;
    refreshSources();
  }catch(e){}
}

connect();
setInterval(refreshStats,5000);
refreshStats();
// Load initial events from server
fetch('/api/events?limit=100').then(r=>r.json()).then(evts=>(evts||[]).forEach(handleEvent)).catch(()=>{});
</script>
</body>
</html>"""


def create_app(server) -> Any:
    """Create FastAPI app with REST API + WebSocket + Web UI."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse, JSONResponse
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError("pip install fastapi uvicorn")

    app = FastAPI(title="Toonic Server", version="1.0.0")
    
    # Add CORS middleware for WebSocket support
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
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
        logger.info("WebSocket connect: /ws")
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
            logger.info("WebSocket disconnect: /ws")
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

    # ── Events + Triggers ───────────────────────────────────

    @app.get("/api/events")
    async def get_events(limit: int = 100, event_type: str = ""):
        """Get recent event log entries."""
        return server.get_event_log(limit=limit, event_type=event_type)

    @app.get("/api/triggers")
    async def get_triggers():
        """Get trigger configuration and stats."""
        from toonic.server.triggers.dsl import TriggerConfig
        cfg = server.trigger_config
        return {
            "config": cfg.to_dict() if cfg else None,
            "stats": server.trigger_scheduler.get_stats(),
        }

    @app.get("/api/data-dir")
    async def get_data_dir():
        """List files in the data directory."""
        data_dir = server.data_dir
        files = []
        for f in sorted(data_dir.rglob("*")):
            if f.is_file():
                files.append({
                    "path": str(f.relative_to(data_dir)),
                    "size_bytes": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                })
        return {
            "data_dir": str(data_dir.resolve()),
            "files": files,
        }

    # ── History + Query ──────────────────────────────────────

    @app.get("/api/history")
    async def get_history(limit: int = 20, category: str = "",
                          model: str = "", action_type: str = ""):
        return server.get_history(limit=limit, category=category,
                                  model=model, action_type=action_type)

    @app.get("/api/history/stats")
    async def get_history_stats():
        return server.get_history_stats()

    @app.post("/api/query")
    async def nlp_query(body: dict = {}):
        """NLP query on conversation history."""
        question = body.get("question", body.get("query", ""))
        if not question:
            return JSONResponse(status_code=400, content={"error": "question required"})
        return await server.nlp_query(question)

    @app.post("/api/sql")
    async def sql_query(body: dict = {}):
        """Raw SQL query on conversation history."""
        sql = body.get("sql", "")
        if not sql:
            return JSONResponse(status_code=400, content={"error": "sql required"})
        return server.sql_query(sql)

    return app

# Example: Programmatic Python API

Use Toonic from Python — from one-liner quick-start to low-level component access.

## Quick Module (recommended)

The `toonic.server.quick` module provides the simplest API:

```python
from toonic.server.quick import watch, run, parse_source

# One-liner: start monitoring (blocking, with Web UI)
run("./src/", "log:./app.log", goal="find bugs")

# Fluent builder: full control
server = (
    watch("./src/")
    .logs("./app.log")
    .docker("*")
    .database("db:./app.db")
    .network("8.8.8.8,1.1.1.1")
    .goal("full-stack monitoring")
    .triggers("./triggers.yaml")
    .interval(30)
    .tokens(100_000, {"code": 0.3, "logs": 0.3, "system": 0.4})
    .build()
)

# Auto-detect source type from string
src = parse_source("log:./app.log")     # → SourceConfig(category="logs")
src = parse_source("./data.csv")         # → SourceConfig(category="data")
src = parse_source("rtsp://cam:554/s")   # → SourceConfig(category="video")
src = parse_source("docker:*")           # → SourceConfig(category="container")
```

### ConfigBuilder typed methods

| Method | Category | Example |
|--------|----------|--------|
| `.add(str)` | auto-detect | `.add("log:./app.log")` |
| `.code(path)` | code | `.code("./src/")` |
| `.logs(path)` | logs | `.logs("./app.log")` |
| `.video(url)` | video | `.video("rtsp://cam:554/s")` |
| `.docker(filter)` | container | `.docker("*")` |
| `.database(dsn)` | database | `.database("db:./app.db")` |
| `.network(hosts)` | network | `.network("8.8.8.8,1.1.1.1")` |
| `.process(target)` | process | `.process("proc:nginx")` |
| `.http(url)` | api | `.http("https://api.example.com")` |
| `.directory(path)` | infra | `.directory("./data/")` |

---

## Low-Level Components

For advanced use, access individual components directly:

| Component | Module | What it does |
|-----------|--------|-------------|
| `ConfigBuilder` | `toonic.server.quick` | Fluent server config builder |
| `parse_source` | `toonic.server.quick` | Universal source string parser |
| `ContextAccumulator` | `toonic.server.core.accumulator` | Priority-based token budget management |
| `LLMPipeline` | `toonic.server.llm.pipeline` | Orchestrates prompt → model → call → parse |
| `LLMCaller` | `toonic.server.llm.caller` | LLM API calls with retry and mock fallback |
| `ResponseParser` | `toonic.server.llm.parser` | Parse raw LLM output into `ActionResponse` |
| `PromptBuilder` | `toonic.server.llm.prompts` | Build prompts for different use-cases |
| `TriggerConfig` | `toonic.server.triggers.dsl` | Parse/create YAML trigger rules |
| `ContextChunk` | `toonic.server.models` | Data model for context chunks |
| `ToonicServer` | `toonic.server.main` | Full server (if you need everything) |

---

## Low-Level Examples

### 1. Accumulator with Priority

```python
from toonic.server.core.accumulator import ContextAccumulator, BudgetConfig
from toonic.server.models import ContextChunk, SourceCategory, ContentType

# Custom budget: 50k tokens, heavy on logs
acc = ContextAccumulator(config=BudgetConfig(
    total_tokens=50_000,
    allocations={"code": 0.30, "logs": 0.40, "video": 0.10, "system": 0.20},
))

# Add high-priority error log
acc.update(ContextChunk(
    source_id="app-log",
    category=SourceCategory.LOGS,
    toon_spec="2025-01-15 ERROR [db] Connection pool exhausted",
    content_type=ContentType.LOG_ENTRIES,
    priority=0.8,
))

# Add low-priority info log
acc.update(ContextChunk(
    source_id="app-log-info",
    category=SourceCategory.LOGS,
    toon_spec="2025-01-15 INFO [api] Request completed in 45ms",
    content_type=ContentType.LOG_ENTRIES,
    priority=0.3,
))

# Add code chunk
acc.update(ContextChunk(
    source_id="main.py",
    category=SourceCategory.CODE,
    toon_spec="M main.py | f process_request(req) | f handle_error(e)",
    content_type=ContentType.TOON_SPEC,
    priority=0.5,
))

# Get priority-sorted chunks within budget
chunks, images = acc.get_chunks(categories=["logs", "code"])
for c in chunks:
    print(f"  [{c.category.value}] pri={c.priority:.1f} {c.toon_spec[:60]}")

# Or get legacy string context
context = acc.get_context(goal="find the root cause of connection pool exhaustion")
print(context[:500])
```

### 2. LLM Pipeline (mock mode — no API key needed)

```python
import asyncio
from toonic.server.llm.pipeline import LLMPipeline
from toonic.server.llm.caller import LLMCaller
from toonic.server.llm.parser import ResponseParser
from toonic.server.llm.prompts import CodeAnalysisPrompt
from toonic.server.models import ContextChunk, SourceCategory, ContentType

async def main():
    # Empty api_key forces mock mode (no real API calls)
    pipeline = LLMPipeline(
        caller=LLMCaller(api_key="", model_map={}),
        parser=ResponseParser(),
        prompt_builder=CodeAnalysisPrompt(),
    )

    chunks = [
        ContextChunk(
            source_id="app.py",
            category=SourceCategory.CODE,
            toon_spec="M app.py | c UserService | m get_user(id) | m delete_user(id)",
            content_type=ContentType.TOON_SPEC,
            priority=0.5,
        ),
    ]

    result = await pipeline.execute(
        goal="find bugs in user management code",
        category="code",
        chunks=chunks,
    )

    print(f"Action: {result.action_type}")
    print(f"Content: {result.content[:200]}")
    print(f"Confidence: {result.confidence}")

asyncio.run(main())
```

### 3. Prompt Builder Selection

```python
from toonic.server.llm.prompts import (
    select_prompt_builder,
    GenericPrompt,
    CodeAnalysisPrompt,
    CCTVEventPrompt,
)
from toonic.server.models import SourceCategory

# Auto-selects CodeAnalysisPrompt
builder = select_prompt_builder(
    goal="find bugs in the code",
    categories={SourceCategory.CODE},
)
print(type(builder).__name__)  # CodeAnalysisPrompt

# Auto-selects CCTVEventPrompt
builder = select_prompt_builder(
    goal="CCTV security: detect intrusions",
    categories={SourceCategory.VIDEO},
)
print(type(builder).__name__)  # CCTVEventPrompt

# Falls back to GenericPrompt
builder = select_prompt_builder(
    goal="summarize the data",
    categories={SourceCategory.DATA},
)
print(type(builder).__name__)  # GenericPrompt
```

### 4. Response Parser

```python
from toonic.server.llm.parser import ResponseParser

parser = ResponseParser()

# parse() expects a dict (as returned by LLMCaller)
# Parse JSON response (with or without markdown fences)
raw = {
    "content": '```json\n{"action": "alert", "content": "Hardcoded API key in config.py:15", "confidence": 0.95, "affected_files": ["config.py"]}\n```',
    "model": "google/gemini-2.5-flash-preview:thinking",
}
result = parser.parse(raw, category="code")
print(f"Action: {result.action_type}")       # "alert"
print(f"Content: {result.content}")           # "Hardcoded API key..."
print(f"Confidence: {result.confidence}")     # 0.95
print(f"Files: {result.affected_files}")      # ["config.py"]

# Plain text fallback
result = parser.parse({"content": "No issues found."}, category="code")
print(f"Action: {result.action_type}")  # "report"

# Direct string → dict parsing (for custom use)
d = parser.parse_raw_to_dict('{"action": "alert", "severity": "high"}')
print(d)  # {"action": "alert", "severity": "high"}
```

### 5. Trigger DSL

```python
from toonic.server.triggers.dsl import (
    TriggerConfig, TriggerRule, EventCondition, FallbackConfig,
    load_triggers, dump_triggers,
)

# Create trigger config programmatically
config = TriggerConfig(triggers=[
    TriggerRule(
        name="error-alert",
        source="logs",
        mode="on_event",
        events=[
            EventCondition(type="pattern", regex="ERROR|CRITICAL", count_threshold=5, window_s=60),
        ],
        fallback=FallbackConfig(periodic_s=300),
        cooldown_s=30,
        goal="analyze error spike",
        priority=9,
    ),
    TriggerRule(
        name="periodic-review",
        source="code",
        mode="periodic",
        interval_s=300,
        goal="review recent changes",
        priority=5,
    ),
])

# Serialize to YAML
yaml_str = dump_triggers(config)
print(yaml_str)

# Parse from YAML
parsed = load_triggers(yaml_str)
for rule in parsed.triggers:
    print(f"  {rule.name}: mode={rule.mode}, priority={rule.priority}")

# Filter rules for a source
log_rules = config.get_rules_for_source("logs")
print(f"Rules for logs: {[r.name for r in log_rules]}")
```

### 6. Full Server (programmatic startup)

```python
import asyncio
from toonic.server.config import ServerConfig, SourceConfig
from toonic.server.main import ToonicServer

async def main():
    config = ServerConfig(
        goal="monitor application health",
        interval=30.0,
        sources=[
            SourceConfig(path_or_url="./src/", category="code"),
            SourceConfig(path_or_url="./logs/app.log", category="logs"),
        ],
    )

    server = ToonicServer(config)
    await server.start()

    # Add sources dynamically
    await server.add_source(SourceConfig(
        path_or_url="db:./app.db",
        category="database",
    ))

    # Check accumulator stats
    stats = server.accumulator.get_stats()
    print(f"Sources: {stats['total_sources']}, Tokens: {stats['total_tokens']}")

    # Let it run for a while...
    await asyncio.sleep(60)
    await server.stop()

asyncio.run(main())
```

---

## Running the Demos

```bash
# Install toonic with server extras
pip install -e ".[server,llm]"

# Quick module demo (recommended — start here)
python examples/programmatic-api/demo_quick.py

# Low-level component demos
python examples/programmatic-api/demo_accumulator.py
python examples/programmatic-api/demo_pipeline.py
```

## Files in This Example

- **`README.md`** — this file
- **`demo_quick.py`** — ConfigBuilder, parse_source, watch() demos (start here)
- **`demo_accumulator.py`** — priority-based eviction demo
- **`demo_pipeline.py`** — prompt builders, response parser, LLM pipeline demo

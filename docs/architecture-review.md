# Toonic Architecture Review — SOLID, CQRS, Event Sourcing

## Current State Assessment

### SOLID Principles

| Principle | Status | Notes |
|-----------|--------|-------|
| **S** — Single Responsibility | ✅ Good | Each watcher handles one source type. LLMPipeline delegates to Caller/Parser/PromptBuilder. Router is thin adapter. |
| **O** — Open/Closed | ✅ Good | `WatcherRegistry` + `BaseWatcher` ABC — add watchers without modifying server. `PromptBuilder` protocol — add prompt strategies without touching pipeline. |
| **L** — Liskov Substitution | ✅ Good | All 9 watchers are interchangeable via `BaseWatcher`. All prompt builders via `PromptBuilder` protocol. |
| **I** — Interface Segregation | ⚠️ Minor | `ToonicServer` has both lifecycle (start/stop) and query (analyze_now/nlp_query/sql_query) concerns. Could split into `ServerLifecycle` + `QueryService`. Low priority — class is 384 lines. |
| **D** — Dependency Inversion | ✅ Good | `LLMRouter` depends on `LLMPipeline` (abstraction), not concrete caller. `TriggerScheduler` depends on `TriggerConfig` (data), not specific detector implementations. |

**Violation found in examples (fixed):**
- `security-audit/continuous_monitoring.py` (524L) violated SRP — combined monitoring, alerting, email, webhook, reporting in one class. **Fixed**: replaced with `quick_audit.py` using Toonic's built-in watchers (130L).
- `security-audit/enterprise_features.py` (718L) — custom ML anomaly detection duplicating Toonic's detector system. **Recommendation**: remove or mark as "advanced/standalone".

### CQRS (Command Query Responsibility Segregation)

| Aspect | Status | Implementation |
|--------|--------|---------------|
| **Commands** (writes) | ✅ Separated | `ToonicServer.add_source()`, `accumulator.update()`, `history.record()` — all write operations |
| **Queries** (reads) | ✅ Separated | `QueryAdapter.nlp_query()`, `QueryAdapter.sql_query()`, `history.recent()` — read-only |
| **Event emission** | ✅ Good | `_emit_event()` writes to `events.jsonl` (append-only log) |
| **Model separation** | ⚠️ Partial | `ContextChunk` is used for both write (accumulator) and read (get_chunks). Could have separate `ChunkWrite` / `ChunkView` models, but current approach is pragmatic for the codebase size. |

**The architecture naturally follows CQRS:**
- Write path: Watcher → Accumulator → TriggerScheduler → LLMRouter → History
- Read path: QueryAdapter → History DB (SQLite) → formatted results
- These paths are independent — writes don't block reads.

### Event Sourcing

| Aspect | Status | Implementation |
|--------|--------|---------------|
| **Event log** | ✅ Implemented | `events.jsonl` — append-only log of all server events |
| **Exchange log** | ✅ Implemented | `exchanges.jsonl` — append-only log of LLM interactions |
| **History DB** | ✅ Implemented | `history.db` (SQLite) — queryable exchange store |
| **Event replay** | ⚠️ Not implemented | Events are logged but cannot be replayed to reconstruct state. Would need a `replay()` method on ToonicServer. |
| **Event types** | ✅ Well-defined | `ServerEvent` dataclass with typed `event_type` field |
| **Immutability** | ✅ Good | `ContextChunk` and `ActionResponse` are dataclasses (effectively immutable after creation) |

**The server already uses event sourcing patterns:**
- All state changes emit `ServerEvent` objects
- Events persisted to `events.jsonl` (append-only = event store)
- `TriggerScheduler` reacts to events (event-driven)
- History DB is a read-model (materialized view of exchanges)

## Architecture Diagram

```
                         ┌─────────────────────────────────────┐
                         │         Presets (quick.py)           │
                         │  security_audit | code_review | ...  │
                         └──────────────┬──────────────────────┘
                                        │ ConfigBuilder
                                        ▼
┌────────────┐    ┌──────────────────────────────────────────────────┐
│  CLI/API   │───▶│              ToonicServer (main.py)              │
└────────────┘    │  Lifecycle: start() → add_source() → stop()      │
                  │  Query:     analyze_now() → nlp_query()          │
                  └──┬─────────┬──────────┬──────────┬───────────────┘
                     │         │          │          │
        ┌────────────┘    ┌────┘     ┌────┘     ┌────┘
        ▼                 ▼          ▼          ▼
   ┌─────────┐    ┌────────────┐ ┌────────┐ ┌──────────────┐
   │ Watchers │    │Accumulator │ │ Router │ │TriggerSchedul│
   │ (9 types)│    │ (priority) │ │  (LLM) │ │ (events/cron)│
   └────┬─────┘    └─────┬──────┘ └───┬────┘ └──────┬───────┘
        │ chunks         │ context    │ action      │ trigger
        ▼                ▼            ▼             ▼
   ┌──────────────────────────────────────────────────────────┐
   │              Event Bus (_emit_event)                      │
   │  → events.jsonl  → exchanges.jsonl  → WebSocket clients  │
   └──────────────────────────────────────────────────────────┘
```

## Recommendations

### Low Priority (current architecture is sound)
1. **Event replay**: Add `ToonicServer.replay(events_file)` for debugging/testing
2. **Interface segregation**: Split `ToonicServer` into `ServerLifecycle` + `AnalysisService` + `QueryService`
3. **CQRS read models**: Separate `ChunkView` from `ContextChunk` for query results

### Done
- ✅ Presets reduce user code from 20+ lines to 1-2 lines
- ✅ `run_all.py` verifies all examples without starting servers
- ✅ `quick_audit.py` replaces 1200+ lines of custom security code
- ✅ `project.toon` regenerated with 97 files
- ✅ CLI `examples` command for discovery and verification

#!/bin/bash
# Toonic Autopilot Demo — runs 3 example projects
set -e

echo "=============================================="
echo "  Toonic Autopilot Demo"
echo "=============================================="
echo ""

# ── Example 1: REST API ──────────────────────────────────────────
echo "╔══════════════════════════════════════════╗"
echo "║  Example 1: REST API for task management ║"
echo "╚══════════════════════════════════════════╝"
echo ""

mkdir -p /tmp/demos
cd /tmp/demos

echo ">>> toonic init 'REST API for task management with CRUD operations' --name task-api"
python -m toonic init "REST API for task management with CRUD operations" --name task-api -o /tmp/demos/task-api

echo ""
echo "--- Generated files ---"
find /tmp/demos/task-api -type f | sort
echo ""
echo "--- project.toon ---"
cat /tmp/demos/task-api/project.toon
echo ""
echo "--- ROADMAP.md ---"
cat /tmp/demos/task-api/ROADMAP.md

# Run tests on scaffold
echo ""
echo ">>> Running initial tests..."
cd /tmp/demos/task-api
pip install -e . 2>/dev/null || true
python -m pytest tests/ -v --tb=short 2>&1 || echo "(some tests may fail — that's expected before autopilot)"

echo ""
echo ""

# ── Example 2: CLI Tool ─────────────────────────────────────────
echo "╔══════════════════════════════════════════╗"
echo "║  Example 2: CLI word counter tool        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

cd /tmp/demos
echo ">>> toonic init 'CLI tool for counting words and lines in files' --name wordcount"
python -m toonic init "CLI tool for counting words and lines in files" --name wordcount -o /tmp/demos/wordcount

echo ""
echo "--- Generated files ---"
find /tmp/demos/wordcount -type f | sort
echo ""

cd /tmp/demos/wordcount
pip install -e . 2>/dev/null || true
python -m pytest tests/ -v --tb=short 2>&1 || echo "(scaffold tests)"

echo ""
echo ""

# ── Example 3: Data Pipeline ────────────────────────────────────
echo "╔══════════════════════════════════════════╗"
echo "║  Example 3: CSV data pipeline            ║"
echo "╚══════════════════════════════════════════╝"
echo ""

cd /tmp/demos
echo ">>> toonic init 'Data pipeline for transforming CSV files with filtering and aggregation' --name csv-pipeline"
python -m toonic init "Data pipeline for transforming CSV files with filtering and aggregation" --name csv-pipeline -o /tmp/demos/csv-pipeline

echo ""
echo "--- Generated files ---"
find /tmp/demos/csv-pipeline -type f | sort
echo ""

cd /tmp/demos/csv-pipeline
pip install -e . 2>/dev/null || true
python -m pytest tests/ -v --tb=short 2>&1 || echo "(scaffold tests)"

echo ""
echo ""

# ── Autopilot dry-run ───────────────────────────────────────────
echo "╔══════════════════════════════════════════╗"
echo "║  Autopilot dry-run (no LLM key needed)   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

cd /tmp/demos/task-api
echo ">>> toonic autopilot . --goal 'build MVP' --max-iter 2 --dry-run --no-test"
python -m toonic autopilot . --goal "build MVP with CRUD endpoints for tasks" --max-iter 2 --dry-run --no-test 2>&1 || true

echo ""
echo ""

# ── Summary ─────────────────────────────────────────────────────
echo "=============================================="
echo "  Demo Complete — Summary"
echo "=============================================="
echo ""
echo "✓ Example 1: task-api      (REST API, Python/FastAPI)"
echo "✓ Example 2: wordcount     (CLI tool, Python)"  
echo "✓ Example 3: csv-pipeline  (Data pipeline, Python)"
echo ""
echo "What works:"
echo "  ✓ toonic init — scaffolds project from description"
echo "  ✓ project.toon — TOON spec generated"
echo "  ✓ ROADMAP.md — development roadmap generated"
echo "  ✓ Skeleton code + tests + config"
echo "  ✓ toonic autopilot --dry-run — loop runs (mock LLM)"
echo ""
echo "What's needed for FULL autonomous development:"
echo "  ✗ OPENROUTER_API_KEY — set env var for real LLM calls"
echo "  ✗ Then: toonic autopilot ./task-api --goal 'build MVP'"
echo "  ✗ LLM generates concrete code → executor writes files"
echo "  ✗ Tests run automatically → fix loop if failures"
echo "  ✗ ROADMAP tasks get checked off automatically"
echo ""
echo "Try with real LLM:"
echo "  export OPENROUTER_API_KEY=sk-or-..."
echo "  toonic init 'REST API for bookstore' --name bookstore"
echo "  toonic autopilot ./bookstore --goal 'build MVP' --max-iter 10"
echo ""

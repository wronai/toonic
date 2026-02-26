"""
Shared fixtures for toonic tests
"""

import pytest
import tempfile
import os
from pathlib import Path

from toonic.core.registry import FormatRegistry
from toonic.formats import initialize_all_handlers


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset FormatRegistry before each test."""
    FormatRegistry.reset()
    initialize_all_handlers()
    yield
    FormatRegistry.reset()


@pytest.fixture
def tmp_md(tmp_path):
    """Create a temp Markdown file."""
    p = tmp_path / "test.md"
    p.write_text("""---
title: Test Document
lang: pl
---

# Introduction

This is the intro section with some content about the project.

## Installation

Install via pip: `pip install toonic`.

## Usage

Run the command and see results.
""")
    return p


@pytest.fixture
def tmp_csv(tmp_path):
    """Create a temp CSV file."""
    p = tmp_path / "data.csv"
    p.write_text("id,name,email,age\n1,Alice,alice@ex.com,30\n2,Bob,bob@ex.com,25\n3,Carol,carol@ex.com,35\n")
    return p


@pytest.fixture
def tmp_env(tmp_path):
    """Create a temp .env file."""
    p = tmp_path / "config.env"
    p.write_text("DB_HOST=localhost\nDB_PORT=5432\nAPI_SECRET_KEY=mysecret123\nDEBUG=true\n")
    return p


@pytest.fixture
def tmp_sql(tmp_path):
    """Create a temp SQL file."""
    p = tmp_path / "schema.sql"
    p.write_text("""
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE posts (
    id BIGSERIAL PRIMARY KEY,
    author_id BIGINT NOT NULL REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    body TEXT
);

CREATE VIEW active_users AS SELECT * FROM users WHERE created_at > NOW() - INTERVAL '30 days';
""")
    return p


@pytest.fixture
def tmp_json(tmp_path):
    """Create a temp JSON data file."""
    import json
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"users": [{"id": 1, "name": "Alice"}], "total": 100}))
    return p


@pytest.fixture
def tmp_txt(tmp_path):
    """Create a temp text file."""
    p = tmp_path / "notes.txt"
    p.write_text("First paragraph about toonic.\n\nSecond paragraph about formats.")
    return p

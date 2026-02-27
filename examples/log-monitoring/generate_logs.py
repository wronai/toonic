#!/usr/bin/env python3
"""
Log generator — simulates realistic application logs for testing Toonic log monitoring.

Usage:
    python examples/log-monitoring/generate_logs.py [--output ./test.log] [--mode normal|error-spike|mixed]

Modes:
    normal      — mostly INFO/DEBUG with occasional WARNING
    error-spike — burst of ERROR/CRITICAL within 60s (triggers error-spike rule)
    mixed       — realistic mix: steady INFO, periodic WARNING, rare ERROR bursts
"""

import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

COMPONENTS = ["api", "db", "auth", "cache", "worker", "scheduler", "gateway", "metrics"]

MESSAGES = {
    "DEBUG": [
        "Cache hit for key user:{uid}",
        "DB query took {ms}ms: SELECT * FROM users WHERE id={uid}",
        "Request headers: Content-Type=application/json, Accept=*/*",
        "Worker pool: {n}/8 threads active",
        "Heartbeat check OK — uptime {h}h",
    ],
    "INFO": [
        "Request POST /api/v2/users completed in {ms}ms — 200 OK",
        "User {uid} logged in from {ip}",
        "Scheduled job 'cleanup' started",
        "DB connection pool: {n}/100 active connections",
        "Processed {n} events in batch",
        "Cache eviction: {n} entries removed, {pct}% hit rate",
        "Health check passed — all services healthy",
        "Deployment v2.{v} rolling out to production",
    ],
    "WARNING": [
        "Slow query ({ms}ms): SELECT * FROM orders WHERE status='pending'",
        "Cache miss rate {pct}% exceeds threshold 20%",
        "Connection pool {pct}% utilized ({n}/100)",
        "Rate limit approaching for client {ip}: {n}/1000 requests",
        "Retry attempt {n}/3 for external API call",
        "Memory usage at {pct}% — threshold is 85%",
        "Certificate expires in {n} days for api.example.com",
    ],
    "ERROR": [
        "NullPointerException in UserController.getProfile() at line {n}",
        "Connection refused: postgresql://db-primary:5432 — retrying in {n}s",
        "HTTP 503 from payment-service: Service Unavailable",
        "Authentication failed for user {uid}: invalid token",
        "Timeout after {ms}ms waiting for redis://cache:6379",
        "Failed to serialize response: unexpected bytes at position {n}",
        "Disk usage critical: /data at {pct}% — threshold 90%",
    ],
    "CRITICAL": [
        "Connection pool exhausted — 0/{n} available, all requests queued",
        "Out of memory: cannot allocate {n}MB — heap dump written",
        "Database replication lag: {n}s (threshold: 5s)",
        "SSL certificate EXPIRED for api.example.com",
        "Unrecoverable error in worker thread: segmentation fault",
        "Data corruption detected in table 'transactions' — row {n}",
    ],
}


def _fill(template: str) -> str:
    """Fill template placeholders with random values."""
    return (
        template
        .replace("{uid}", str(random.randint(1000, 9999)))
        .replace("{ms}", str(random.randint(5, 5000)))
        .replace("{ip}", f"{random.randint(10,200)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}")
        .replace("{n}", str(random.randint(1, 200)))
        .replace("{h}", str(random.randint(1, 720)))
        .replace("{pct}", str(random.randint(10, 99)))
        .replace("{v}", str(random.randint(100, 999)))
    )


def generate_line(level: str) -> str:
    """Generate a single log line."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    comp = random.choice(COMPONENTS)
    msg = _fill(random.choice(MESSAGES[level]))
    return f"{ts} {level:8s} [{comp}] {msg}"


def run_normal(out, count: int = 50, delay: float = 0.2):
    """Normal mode: mostly INFO."""
    weights = {"DEBUG": 0.15, "INFO": 0.60, "WARNING": 0.20, "ERROR": 0.04, "CRITICAL": 0.01}
    levels = list(weights.keys())
    probs = list(weights.values())
    for _ in range(count):
        level = random.choices(levels, probs)[0]
        line = generate_line(level)
        out.write(line + "\n")
        out.flush()
        time.sleep(delay)


def run_error_spike(out, count: int = 30, delay: float = 0.1):
    """Error spike: burst of errors to trigger error-spike rule."""
    # Warm-up: 10 normal lines
    for _ in range(10):
        out.write(generate_line("INFO") + "\n")
        out.flush()
        time.sleep(delay)

    print(">>> ERROR SPIKE starting (10 errors in ~5s) <<<", file=sys.stderr)

    # Spike: 10 errors in quick succession
    for _ in range(10):
        level = random.choice(["ERROR", "ERROR", "ERROR", "CRITICAL"])
        out.write(generate_line(level) + "\n")
        out.flush()
        time.sleep(delay * 0.5)

    # Cooldown: 10 normal lines
    for _ in range(10):
        out.write(generate_line(random.choice(["INFO", "WARNING"])) + "\n")
        out.flush()
        time.sleep(delay)


def run_mixed(out, duration: float = 120.0, delay: float = 0.3):
    """Mixed mode: realistic traffic with periodic error bursts."""
    end_time = time.time() + duration
    error_burst_at = time.time() + random.uniform(20, 40)
    burst_count = 0

    while time.time() < end_time:
        if time.time() >= error_burst_at and burst_count < 8:
            level = random.choice(["ERROR", "CRITICAL"])
            burst_count += 1
            if burst_count >= 8:
                error_burst_at = time.time() + random.uniform(30, 60)
                burst_count = 0
        else:
            level = random.choices(
                ["DEBUG", "INFO", "WARNING", "ERROR"],
                [0.10, 0.65, 0.20, 0.05],
            )[0]

        out.write(generate_line(level) + "\n")
        out.flush()
        time.sleep(delay + random.uniform(-0.1, 0.2))


def main():
    parser = argparse.ArgumentParser(description="Generate test log data for Toonic")
    parser.add_argument("--output", "-o", default="", help="Output file (default: stdout)")
    parser.add_argument("--mode", "-m", default="mixed", choices=["normal", "error-spike", "mixed"])
    parser.add_argument("--duration", "-d", type=float, default=120.0, help="Duration in seconds (mixed mode)")
    args = parser.parse_args()

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        out = open(args.output, "a")
    else:
        out = sys.stdout

    try:
        print(f"Generating {args.mode} logs...", file=sys.stderr)
        if args.mode == "normal":
            run_normal(out)
        elif args.mode == "error-spike":
            run_error_spike(out)
        elif args.mode == "mixed":
            run_mixed(out, duration=args.duration)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
    finally:
        if args.output:
            out.close()


if __name__ == "__main__":
    main()

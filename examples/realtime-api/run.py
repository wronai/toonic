#!/usr/bin/env python3
"""
Realtime API recipes — run with: python examples/realtime-api/run.py
"""
from toonic.server.quick import watch
from examples._helpers import print_config_summary


SCENARIOS = {
    "ws_wss_grpc": [
        "ws://localhost:8080/stream",
        "wss://api.example.com/realtime",
        "grpc://localhost:50051",
    ],
    "hybrid_api": [
        "https://httpbin.org/get",
        "ws://localhost:8080/stream",
        "grpc://localhost:50051",
    ],
}


if __name__ == "__main__":
    for name, sources in SCENARIOS.items():
        cfg = (
            watch(*sources)
            .goal(f"realtime api health: {name}")
            .interval(30)
            .build_config()
        )
        print(f"\n=== {name} ===")
        print_config_summary(cfg)

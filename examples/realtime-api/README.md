# Example: Realtime API (WS/WSS + gRPC + HTTP)

This example shows protocol recipes for realtime/API endpoints using supported URL schemes.

## Python Quick API

```python
from toonic.server.quick import watch

server = (
    watch(
        "ws://localhost:8080/stream",
        "wss://api.example.com/realtime",
        "grpc://localhost:50051",
        "https://httpbin.org/get",
    )
    .goal("monitor realtime api endpoints and connectivity drift")
    .interval(30)
    .build()
)
```

## CLI

```bash
python -m toonic.server \
  --source "ws://localhost:8080/stream" \
  --source "grpc://localhost:50051" \
  --source "https://httpbin.org/get" \
  --goal "realtime api endpoint health" \
  --interval 30
```

## Notes

- `ws://` and `wss://` are accepted by source parser and mapped to `api` category.
- `grpc://` is mapped to `api` category.
- `http(s)://` is mapped to `web` category.

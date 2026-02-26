FROM python:3.12-slim

WORKDIR /app

# System deps for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml VERSION README.md ./
COPY toonic/ toonic/

RUN pip install --no-cache-dir -e ".[all]" && \
    pip install --no-cache-dir fastapi uvicorn litellm websockets httpx pyyaml

COPY toonic-server.yaml ./
COPY examples/ examples/

EXPOSE 8900

ENTRYPOINT ["python", "-m", "toonic.server"]
CMD ["--port", "8900"]

"""Configuration for sample project."""

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
PORT = int(os.environ.get("PORT", "8080"))
MAX_CONNECTIONS = 100
CACHE_TTL = 300

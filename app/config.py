from __future__ import annotations

import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:////tmp/cyber-shell-backend.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    API_KEY = os.getenv("API_KEY", "replace-me")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", "v1")

    HTTP_TOOL_ALLOWED_HOSTS = [
        item.strip()
        for item in os.getenv("HTTP_TOOL_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
        if item.strip()
    ]
    HTTP_TOOL_ALLOWED_METHODS = [
        item.strip().upper()
        for item in os.getenv("HTTP_TOOL_ALLOWED_METHODS", "GET,HEAD").split(",")
        if item.strip()
    ]
    HTTP_TOOL_TIMEOUT_SECONDS = int(os.getenv("HTTP_TOOL_TIMEOUT_SECONDS", "5"))
    MAX_TOOL_ROWS = int(os.getenv("MAX_TOOL_ROWS", "20"))
    MAX_OUTPUT_PREVIEW_CHARS = int(os.getenv("MAX_OUTPUT_PREVIEW_CHARS", "1200"))

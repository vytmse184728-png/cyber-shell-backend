from __future__ import annotations

import os


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:////tmp/cyber-shell-backend.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    API_KEY = os.getenv("API_KEY", "replace-me")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", "v1beta")
    APP_PORT = int(os.getenv("APP_PORT", "60081"))

    # Single fixed base URL used by the HTTP tool. The model cannot override this.
    HTTP_TOOL_TARGET_URL = os.getenv(
        "HTTP_TOOL_TARGET_URL",
        "http://127.0.0.1",
    ).strip()

    # Host header values the model may choose from.
    HTTP_TOOL_ALLOWED_HOSTS = [
        item.lower()
        for item in _split_csv(
            os.getenv(
                "HTTP_TOOL_ALLOWED_HOSTS",
                "cmd.lab.local,sql.lab.local,idor.lab.local",
            )
        )
    ]

    # Keep this configurable. The defaults allow the common verbs used during verification.
    HTTP_TOOL_ALLOWED_METHODS = [
        item.strip().upper()
        for item in _split_csv(
            os.getenv(
                "HTTP_TOOL_ALLOWED_METHODS",
                "GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS",
            )
        )
    ]

    HTTP_TOOL_TIMEOUT_SECONDS = int(os.getenv("HTTP_TOOL_TIMEOUT_SECONDS", "5"))
    MAX_TOOL_ROWS = int(os.getenv("MAX_TOOL_ROWS", "20"))
    MAX_OUTPUT_PREVIEW_CHARS = int(os.getenv("MAX_OUTPUT_PREVIEW_CHARS", "1200"))

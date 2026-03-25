from __future__ import annotations

from urllib.parse import urlparse

import requests
from flask import current_app


SAFE_HEADER_ALLOWLIST = {"accept", "content-type", "user-agent"}



def send_http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
) -> dict:
    method = (method or "GET").upper().strip()
    allowed_methods = set(current_app.config["HTTP_TOOL_ALLOWED_METHODS"])
    if method not in allowed_methods:
        return {
            "error": f"method '{method}' is not allowed",
            "allowed_methods": sorted(allowed_methods),
        }

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"error": "only http and https are allowed"}

    allowed_hosts = set(current_app.config["HTTP_TOOL_ALLOWED_HOSTS"])
    if parsed.hostname not in allowed_hosts:
        return {
            "error": f"host '{parsed.hostname}' is not allowlisted",
            "allowed_hosts": sorted(allowed_hosts),
        }

    filtered_headers = {}
    for key, value in (headers or {}).items():
        if key.lower() in SAFE_HEADER_ALLOWLIST:
            filtered_headers[key] = value

    response = requests.request(
        method=method,
        url=url,
        headers=filtered_headers,
        timeout=current_app.config["HTTP_TOOL_TIMEOUT_SECONDS"],
        allow_redirects=False,
    )

    body_preview = response.text[:2000]
    safe_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "content-length", "server", "location"}
    }
    return {
        "url": url,
        "final_url": response.url,
        "status_code": response.status_code,
        "headers": safe_headers,
        "body_preview": body_preview,
    }

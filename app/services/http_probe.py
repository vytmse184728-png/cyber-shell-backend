from __future__ import annotations

import json
import posixpath
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from flask import current_app


BLOCKED_HEADER_NAMES = {"host", "content-length", "transfer-encoding", "connection"}
RESPONSE_HEADER_ALLOWLIST = {"content-type", "content-length", "server", "location"}


def _normalize_host_header(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip().lower()
    return value or None


def _allowed_host_headers() -> set[str]:
    values = current_app.config.get("HTTP_TOOL_ALLOWED_HOSTS", []) or []
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _stringify_scalar(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _normalize_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be an object")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in headers.items():
        key = str(raw_key).strip()
        if not key:
            continue
        if key.lower() in BLOCKED_HEADER_NAMES:
            continue
        normalized[key] = _stringify_scalar(raw_value)
    return normalized


def _extend_query_pairs(pairs: list[tuple[str, str]], query_params: dict[str, Any] | None) -> None:
    if query_params is None:
        return
    if not isinstance(query_params, dict):
        raise ValueError("query_params must be an object")

    for raw_key, raw_value in query_params.items():
        key = str(raw_key)
        if raw_value is None:
            continue
        if isinstance(raw_value, list):
            for item in raw_value:
                pairs.append((key, _stringify_scalar(item)))
        else:
            pairs.append((key, _stringify_scalar(raw_value)))


def _build_request_url(target_url: str, path: str | None, query_params: dict[str, Any] | None) -> str:
    parsed_target = urlsplit(target_url)
    if parsed_target.scheme not in {"http", "https"} or not parsed_target.netloc:
        raise ValueError("HTTP_TOOL_TARGET_URL must be a valid absolute http/https URL")

    final_path = parsed_target.path or "/"
    query_pairs: list[tuple[str, str]] = list(parse_qsl(parsed_target.query, keep_blank_values=True))

    if path is not None and str(path).strip():
        raw_path = str(path).strip()
        parsed_path = urlsplit(raw_path)
        if parsed_path.scheme or parsed_path.netloc or raw_path.startswith("//"):
            raise ValueError("path must not include scheme or host")
        if parsed_path.fragment:
            raise ValueError("path must not include a fragment")

        final_path = parsed_path.path or "/"
        if not final_path.startswith("/"):
            final_path = "/" + final_path
        normalized_path = posixpath.normpath(final_path)
        if normalized_path in {".", ""}:
            normalized_path = "/"
        if raw_path.endswith("/") and not normalized_path.endswith("/"):
            normalized_path += "/"
        final_path = normalized_path
        query_pairs.extend(parse_qsl(parsed_path.query, keep_blank_values=True))

    _extend_query_pairs(query_pairs, query_params)
    final_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parsed_target.scheme, parsed_target.netloc, final_path, final_query, ""))


def _prepare_body(headers: dict[str, str], body: Any) -> tuple[dict[str, Any], str]:
    if body is None or body == "":
        return {}, "none"

    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = value.lower()
            break

    if isinstance(body, (dict, list)):
        if "application/x-www-form-urlencoded" in content_type and isinstance(body, dict):
            payload = {
                str(key): _stringify_scalar(value) if not isinstance(value, list) else [_stringify_scalar(item) for item in value]
                for key, value in body.items()
                if value is not None
            }
            return {"data": payload}, "form"

        headers.setdefault("Content-Type", "application/json")
        return {"data": json.dumps(body, ensure_ascii=False)}, "json"

    return {"data": _stringify_scalar(body)}, "text"


def send_http_request(
    host_header: str | None = None,
    method: str = "GET",
    path: str | None = None,
    query_params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    body: Any = None,
) -> dict:
    method = (method or "GET").upper().strip()
    allowed_methods = {
        str(item).strip().upper()
        for item in (current_app.config.get("HTTP_TOOL_ALLOWED_METHODS", []) or [])
        if str(item).strip()
    }
    if method not in allowed_methods:
        return {
            "error": f"method '{method}' is not allowed",
            "allowed_methods": sorted(allowed_methods),
        }

    allowed_host_headers = _allowed_host_headers()
    normalized_host_header = _normalize_host_header(host_header)
    if not normalized_host_header:
        if len(allowed_host_headers) == 1:
            normalized_host_header = next(iter(allowed_host_headers))
        else:
            return {
                "error": "host_header is required because multiple allowed Host headers are configured",
                "allowed_host_headers": sorted(allowed_host_headers),
            }

    if normalized_host_header not in allowed_host_headers:
        return {
            "error": f"host header '{host_header}' is not allowed",
            "allowed_host_headers": sorted(allowed_host_headers),
        }

    target_url = str(current_app.config["HTTP_TOOL_TARGET_URL"]).strip()

    try:
        request_url = _build_request_url(target_url, path, query_params)
        request_headers = _normalize_headers(headers)
        request_headers["Host"] = normalized_host_header
        body_kwargs, body_kind = _prepare_body(request_headers, body)
    except ValueError as exc:
        return {
            "error": str(exc),
            "fixed_base_url": target_url,
            "host_header_used": normalized_host_header,
        }

    try:
        response = requests.request(
            method=method,
            url=request_url,
            headers=request_headers,
            timeout=current_app.config["HTTP_TOOL_TIMEOUT_SECONDS"],
            allow_redirects=False,
            **body_kwargs,
        )
    except requests.RequestException as exc:
        return {
            "error": "request_failed",
            "method_used": method,
            "host_header_used": normalized_host_header,
            "fixed_base_url": target_url,
            "url_used": request_url,
            "custom_header_names": sorted(key for key in request_headers.keys() if key.lower() != "host"),
            "body_kind": body_kind,
            "details": str(exc),
        }

    safe_headers = {
        key: value
        for key, value in response.headers.items()
        if key.lower() in RESPONSE_HEADER_ALLOWLIST
    }

    return {
        "method_used": method,
        "host_header_used": normalized_host_header,
        "fixed_base_url": target_url,
        "url_used": request_url,
        "custom_header_names": sorted(key for key in request_headers.keys() if key.lower() != "host"),
        "body_kind": body_kind,
        "status_code": response.status_code,
        "headers": safe_headers,
        "body_preview": response.text[:2000],
    }

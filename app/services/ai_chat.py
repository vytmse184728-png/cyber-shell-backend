from __future__ import annotations

from typing import Any

from flask import current_app
from google import genai
from google.genai import types

from .db_tools import get_recent_events, get_session_overview, search_events
from .http_probe import send_http_request


def _http_allowed_host_headers() -> list[str]:
    values = current_app.config.get("HTTP_TOOL_ALLOWED_HOSTS", []) or []
    return [str(item).strip() for item in values if str(item).strip()]


def _http_allowed_methods() -> list[str]:
    values = current_app.config.get("HTTP_TOOL_ALLOWED_METHODS", []) or []
    return [str(item).strip().upper() for item in values if str(item).strip()]


def _infer_site_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for host in _http_allowed_host_headers():
        lowered = host.lower()
        if "cmd" in lowered and "cmd" not in aliases:
            aliases["cmd"] = host
        if "sql" in lowered and "sql" not in aliases:
            aliases["sql"] = host
        if "idor" in lowered and "idor" not in aliases:
            aliases["idor"] = host
    return aliases


def build_system_prompt() -> str:
    target_url = str(current_app.config.get("HTTP_TOOL_TARGET_URL", "")).strip()
    host_headers = _http_allowed_host_headers()
    allowed_methods = _http_allowed_methods()
    aliases = _infer_site_aliases()

    host_headers_text = ", ".join(host_headers) if host_headers else "(none configured)"
    methods_text = ", ".join(allowed_methods) if allowed_methods else "(none configured)"

    alias_lines = []
    for alias in ("cmd", "sql", "idor"):
        if alias in aliases:
            alias_lines.append(
                f"- If the user mentions the {alias} site, prefer Host header '{aliases[alias]}'."
            )
    alias_text = "\n".join(alias_lines) if alias_lines else "- No site aliases were inferred."

    return f"""
You are Cyber Shell's testing support assistant for red-team lab workflows.

PRIMARY ROLE:
- Help the user analyze terminal telemetry, Burp-side evidence, and constrained HTTP verification results.
- Give grounded assessments, next steps, and concise operator guidance.
- Prefer accuracy over confidence. If evidence is incomplete, say so plainly.

EVIDENCE STANDARD:
- Never claim you performed a pentest, ran a shell command, created a Burp tab, sent a Burp request, or confirmed an exploit unless the relevant tool output explicitly proves it.
- Distinguish clearly between:
  - evidence of a request or attempt
  - evidence of a successful action
  - a hypothesis or likely vulnerability
  - missing or inconclusive evidence
- If the user asks whether something succeeded, answer from tool output only. Do not infer success from intent.

TOOL USAGE POLICY:
- Start conservatively. Use database/log tools before drawing conclusions.
- If you need to verify an HTTP service, only use `send_http_request` within the allowed limits.
- Never pass session_id, hostname, or keyword to `send_http_request`.
- The HTTP tool does not accept a URL from the model.
- The backend always uses this fixed base URL: {target_url}
- Allowed Host header values: {host_headers_text}
- Allowed HTTP methods: {methods_text}
- The HTTP tool may customize method, path, query_params, headers, and body.
- The Host header must come from the allowlist.
- Never invent or override the fixed base URL.
{alias_text}

LOCAL BURP MCP BRIDGE RULES:
- `query_local_mcp` is a client-side relay tool, not direct unrestricted control of Burp.
- Treat `query_local_mcp` as a constrained local evidence-query interface. It may return Burp proxy history, scanner issues, websocket history, or a list of available MCP tools.
- Do not assume `query_local_mcp` can execute arbitrary side-effecting Burp actions.
- Never claim that `create_repeater_tab`, `send_http1_request`, or any other MCP function was executed unless the returned local tool result explicitly confirms that exact action and its outcome.
- If the user requests a Burp-side action that is not explicitly confirmed by the local tool result, explain that the current relay may not support that action reliably and ask the user to verify manually or request an implemented alternative.

RESPONSE STYLE:
- Reply in English.
- Be concise, practical, and easy to scan.
- Prefer short sections and bullet points when helpful.
- Only ask a brief follow-up if a required tool input is genuinely ambiguous.
- If there is not enough data, state which additional logs, Burp evidence, or HTTP checks are needed.
""".strip()


def _tool_declarations() -> list[types.Tool]:
    host_headers = _http_allowed_host_headers()
    allowed_methods = _http_allowed_methods()

    host_header_schema: dict[str, Any] = {"type": "string"}
    if host_headers:
        host_header_schema["enum"] = host_headers
    if len(host_headers) == 1:
        host_header_schema["default"] = host_headers[0]

    method_schema: dict[str, Any] = {"type": "string", "default": allowed_methods[0] if allowed_methods else "GET"}
    if allowed_methods:
        method_schema["enum"] = allowed_methods

    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="query_local_mcp",
                    description="Query the user's local Burp Suite MCP bridge for proxy history, websocket history, scanner issues, or tool inventory. This tool runs locally on the client and is primarily for evidence retrieval, not guaranteed side-effecting actions.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural-language request for Burp evidence, such as 'show full proxy history', 'search proxy history for login', 'list available Burp MCP tools', or 'show scanner issues'.",
                            }
                        },
                        "required": ["query"],
                    },
                ),
                types.FunctionDeclaration(
                    name="get_session_overview",
                    description="Get a high-level summary of the current shell session to determine which lab the user is touching, recent commands, and likely blockers.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "hostname": {"type": "string"},
                            "since_minutes": {"type": "integer", "default": 180},
                        },
                    },
                ),
                types.FunctionDeclaration(
                    name="get_recent_events",
                    description="Get recent command events, optionally filtered to failures only, to inspect the latest evidence in the current session.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "hostname": {"type": "string"},
                            "failures_only": {"type": "boolean", "default": False},
                            "since_minutes": {"type": "integer", "default": 180},
                            "limit": {"type": "integer", "default": 10},
                        },
                    },
                ),
                types.FunctionDeclaration(
                    name="search_events",
                    description="Search logs by keyword in commands or output, for example ping.php, idor_profile.php, SQL App, uid=, or SQL ERROR.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string"},
                            "session_id": {"type": "string"},
                            "hostname": {"type": "string"},
                            "limit": {"type": "integer", "default": 10},
                        },
                        "required": ["keyword"],
                    },
                ),
                types.FunctionDeclaration(
                    name="send_http_request",
                    description=(
                        "Send a flexible HTTP request to the single fixed backend-configured base URL. "
                        "The model may customize method, path, query_params, headers, and body, "
                        "but it may not provide or override the base URL. "
                        "The Host header must be allowlisted."
                    ),
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "host_header": host_header_schema,
                            "method": method_schema,
                            "path": {
                                "type": "string",
                                "description": "Optional path relative to the fixed base URL, for example /login or /api/products.",
                            },
                            "query_params": {
                                "type": "object",
                                "description": "Optional query parameters to append to the fixed base URL.",
                            },
                            "headers": {
                                "type": "object",
                                "description": "Optional extra headers. Host is controlled separately and cannot be overridden here.",
                            },
                            "body": {
                                "type": "string",
                                "description": "Optional raw request body. For JSON bodies, send a serialized JSON string and set Content-Type accordingly.",
                            },
                        },
                    },
                ),
            ]
        )
    ]


def _history_to_contents(history: list[dict[str, Any]] | None) -> list[types.Content]:
    contents: list[types.Content] = []
    for item in (history or [])[-16:]:
        role = str(item.get("role") or "user")
        if role == "tool":
            tool_name = str(item.get("tool_name") or "").strip()
            if not tool_name:
                continue
            part_kwargs = {
                "name": tool_name,
                "response": {"result": item.get("tool_result")},
            }
            tool_call_id = item.get("tool_call_id")
            if tool_call_id:
                part_kwargs["id"] = tool_call_id
            contents.append(
                types.Content(
                    role="tool",
                    parts=[types.Part.from_function_response(**part_kwargs)],
                )
            )
            continue

        text = (item.get("text") or "").strip()
        if not text:
            continue
        model_role = "model" if role in {"assistant", "model"} else "user"
        contents.append(types.Content(role=model_role, parts=[types.Part.from_text(text=text)]))
    return contents


def _dispatch_tool(name: str, args: dict[str, Any], default_session_id: str | None) -> dict:
    args = dict(args or {})

    if name == "get_session_overview":
        if default_session_id and not args.get("session_id"):
            args["session_id"] = default_session_id
        allowed = {"session_id", "hostname", "since_minutes"}
        return get_session_overview(**{k: v for k, v in args.items() if k in allowed})

    if name == "get_recent_events":
        if default_session_id and not args.get("session_id"):
            args["session_id"] = default_session_id
        allowed = {"session_id", "hostname", "failures_only", "since_minutes", "limit"}
        return get_recent_events(**{k: v for k, v in args.items() if k in allowed})

    if name == "search_events":
        if default_session_id and not args.get("session_id"):
            args["session_id"] = default_session_id
        allowed = {"keyword", "session_id", "hostname", "limit"}
        return search_events(**{k: v for k, v in args.items() if k in allowed})

    if name == "send_http_request":
        allowed = {"host_header", "method", "path", "query_params", "headers", "body"}
        http_args = {k: v for k, v in args.items() if k in allowed}

        host_headers = _http_allowed_host_headers()
        if not http_args.get("host_header") and len(host_headers) == 1:
            http_args["host_header"] = host_headers[0]

        return send_http_request(**http_args)

    return {"error": f"unknown tool: {name}"}


def run_chat(
    *,
    message: str | None = None,
    session_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
    tool_name: str | None = None,
    tool_result: Any | None = None,
    tool_call_id: str | None = None,
    tool_args: dict[str, Any] | None = None,
) -> dict:
    gemini_api_key = current_app.config.get("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    contents = _history_to_contents(history)
    if session_id:
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=f"Preferred session context: {session_id}. Use this session_id for log-reading tools unless the user asks otherwise."
                    )
                ],
            )
        )
    if tool_name:
        contents.append(
            types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name=tool_name,
                            args=tool_args or {},
                            **({"id": tool_call_id} if tool_call_id else {}),
                        )
                    )
                ],
            )
        )
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": tool_result},
                        **({"id": tool_call_id} if tool_call_id else {}),
                    )
                ],
            )
        )
    if message:
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=_tool_declarations(),
        temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    tool_trace: list[dict[str, Any]] = []
    with genai.Client(
        api_key=gemini_api_key,
        http_options={"api_version": current_app.config["GEMINI_API_VERSION"]},
    ) as client:
        response = None
        for _ in range(4):
            response = client.models.generate_content(
                model=current_app.config["GEMINI_MODEL"],
                contents=contents,
                config=config,
            )
            function_calls = list(response.function_calls or [])
            if not function_calls:
                return {
                    "answer": (response.text or "I do not have enough data to conclude yet.").strip(),
                    "tool_trace": tool_trace,
                }

            if response.candidates and response.candidates[0].content:
                contents.append(response.candidates[0].content)

            function_response_parts = []
            for function_call in function_calls:
                if function_call.name == "query_local_mcp":
                    relay_args = dict(getattr(function_call, "args", {}) or {})
                    return {
                        "status": "requires_local_action",
                        "action": {
                            "tool": "query_local_mcp",
                            "args": {
                                "query": str(relay_args.get("query") or "").strip(),
                            },
                        },
                        "tool_trace": tool_trace
                        + [
                            {
                                "tool": function_call.name,
                                "args": relay_args,
                                "relay_required": True,
                                "tool_call_id": getattr(function_call, "id", None),
                            }
                        ],
                    }

                result = _dispatch_tool(
                    function_call.name,
                    getattr(function_call, "args", {}) or {},
                    session_id,
                )
                tool_trace.append(
                    {
                        "tool": function_call.name,
                        "args": getattr(function_call, "args", {}) or {},
                        "result": result,
                    }
                )
                part_kwargs = {
                    "name": function_call.name,
                    "response": {"result": result},
                }
                function_call_id = getattr(function_call, "id", None)
                if function_call_id:
                    part_kwargs["id"] = function_call_id
                function_response_parts.append(types.Part.from_function_response(**part_kwargs))

            contents.append(types.Content(role="tool", parts=function_response_parts))

    return {
        "status": "completed",
        "answer": (response.text or "I do not have enough data to conclude yet.").strip()
        if response is not None
        else "I do not have enough data to conclude yet.",
        "tool_trace": tool_trace,
    }

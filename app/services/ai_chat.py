from __future__ import annotations

from typing import Any

from flask import current_app
from google import genai
from google.genai import types

from .db_tools import get_recent_events, get_session_overview, search_events
from .http_probe import send_http_request

SYSTEM_PROMPT = """
You are a testing support assistant for Cyber Shell.
MISSION:
- Only provide guidance, explanations, concise assessments, and next steps.
- Never claim you performed a pentest, ran a command, or confirmed an exploit without direct evidence in the logs or tool output.
- Start conservatively. Use the database tools before drawing conclusions.
- Distinguish between evidence of an attempt, evidence of successful execution, and inconclusive results.
- If you need to verify an HTTP service, only use the send_http_request tool within the allowed limits.
- If there is not enough data, clearly say which additional logs or commands are needed.
- Reply in English, concise, practical, and easy to scan.
""".strip()



def _tool_declarations() -> list[types.Tool]:
    return [
        types.Tool(
            function_declarations=[
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
                    description="Send a safely restricted HTTP request to verify whether an endpoint responds. Use only when log evidence is insufficient and a simple check is needed.",
                    parameters_json_schema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "method": {"type": "string", "default": "GET"},
                            "headers": {"type": "object"},
                        },
                        "required": ["url"],
                    },
                ),
            ]
        )
    ]



def _history_to_contents(history: list[dict[str, str]] | None) -> list[types.Content]:
    contents: list[types.Content] = []
    for item in (history or [])[-16:]:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        role = "model" if item.get("role") in {"assistant", "model"} else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    return contents



def _dispatch_tool(name: str, args: dict[str, Any], default_session_id: str | None) -> dict:
    args = dict(args or {})
    if default_session_id and not args.get("session_id"):
        args["session_id"] = default_session_id

    if name == "get_session_overview":
        return get_session_overview(**args)
    if name == "get_recent_events":
        return get_recent_events(**args)
    if name == "search_events":
        return search_events(**args)
    if name == "send_http_request":
        return send_http_request(**args)
    return {"error": f"unknown tool: {name}"}



def run_chat(
    *,
    message: str,
    session_id: str | None = None,
    history: list[dict[str, str]] | None = None,
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
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
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
        "answer": (response.text or "I do not have enough data to conclude yet.").strip()
        if response is not None
        else "I do not have enough data to conclude yet.",
        "tool_trace": tool_trace,
    }

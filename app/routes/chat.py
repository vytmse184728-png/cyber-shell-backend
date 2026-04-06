from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from ..extensions import db
from ..models import ChatConversation, ChatMessage
from ..services.ai_chat import run_chat

bp = Blueprint("chat", __name__)



def _conversation_title_from_text(text: str) -> str:
    title = " ".join((text or "").strip().split())
    return (title[:77] + "...") if len(title) > 80 else (title or "New chat")



def _message_history(conversation: ChatConversation) -> list[dict[str, object]]:
    history: list[dict[str, object]] = []
    for msg in conversation.messages:
        if msg.role == "tool":
            tool_meta = next(
                (
                    trace
                    for trace in (msg.tool_trace_json or [])
                    if trace.get("tool")
                ),
                {},
            )
            history.append(
                {
                    "role": "tool",
                    "tool_name": tool_meta.get("tool"),
                    "tool_result": msg.body,
                    "tool_call_id": tool_meta.get("tool_call_id"),
                }
            )
            continue

        if msg.body:
            history.append({"role": msg.role, "text": msg.body})
    return history


def _sse_event(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _answer_chunks(answer: str, chunk_size: int = 48):
    text = answer or ""
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]


@bp.get("/api/sessions/<session_id>/conversations")
def list_conversations(session_id: str):
    rows = (
        db.session.query(ChatConversation)
        .filter(ChatConversation.session_id == session_id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        .all()
    )
    return jsonify([row.to_dict() for row in rows])


@bp.post("/api/sessions/<session_id>/conversations")
def create_conversation(session_id: str):
    payload = request.get_json(silent=True) or {}
    title = _conversation_title_from_text(str(payload.get("title") or "New chat"))
    conversation = ChatConversation(session_id=session_id, title=title)
    db.session.add(conversation)
    db.session.commit()
    return jsonify(conversation.to_dict()), 201


@bp.get("/api/conversations/<int:conversation_id>/messages")
def get_conversation_messages(conversation_id: int):
    conversation = db.session.get(ChatConversation, conversation_id)
    if conversation is None:
        return jsonify({"error": "conversation not found"}), 404
    return jsonify({
        "conversation": conversation.to_dict(),
        "messages": [message.to_dict() for message in conversation.messages],
    })


@bp.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid json"}), 400

    message = (payload.get("message") or "").strip()
    tool_name = (payload.get("tool_name") or "").strip()
    tool_result = payload.get("tool_result")
    has_tool_callback = bool(tool_name) and tool_result is not None
    stream = bool(payload.get("stream"))

    if not message and not has_tool_callback:
        return jsonify({"error": "message is required"}), 400

    session_id = (payload.get("session_id") or "").strip() or None
    conversation_id = payload.get("conversation_id")
    history = payload.get("history") if isinstance(payload.get("history"), list) else []

    conversation = None
    if conversation_id is not None:
        conversation = db.session.get(ChatConversation, int(conversation_id))
        if conversation is None:
            return jsonify({"error": "conversation not found"}), 404
        session_id = conversation.session_id
        history = _message_history(conversation)
    elif session_id and message:
        conversation = ChatConversation(session_id=session_id, title=_conversation_title_from_text(message))
        db.session.add(conversation)
        db.session.flush()
    elif has_tool_callback:
        return jsonify({"error": "conversation_id is required for tool callbacks"}), 400

    if conversation is not None and message:
        conversation.updated_at = datetime.now(timezone.utc)
        db.session.add(ChatMessage(conversation_id=conversation.id, role="user", body=message))
        db.session.commit()
        history = _message_history(conversation)

    tool_call_id = None
    tool_args = None
    if conversation is not None and has_tool_callback:
        last_relay = next(
            (
                trace
                for stored_message in reversed(conversation.messages)
                for trace in (stored_message.tool_trace_json or [])
                if trace.get("relay_required") and trace.get("tool") == tool_name
            ),
            {},
        )
        tool_call_id = last_relay.get("tool_call_id")
        tool_args = last_relay.get("args") if isinstance(last_relay.get("args"), dict) else None

    try:
        result = run_chat(
            message=message or None,
            session_id=session_id,
            history=history,
            tool_name=tool_name or None,
            tool_result=tool_result,
            tool_call_id=tool_call_id,
            tool_args=tool_args,
        )
    except Exception as exc:
        current_app.logger.exception("chat request failed")
        error_payload = {
            "error": str(exc) or "chat request failed",
            "type": exc.__class__.__name__,
        }
        if current_app.debug:
            error_payload["traceback"] = traceback.format_exc()
        if stream:
            @stream_with_context
            def generate_error():
                yield _sse_event("error", error_payload)

            return Response(
                generate_error(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
                status=500,
            )
        return jsonify(error_payload), 500

    if conversation is not None:
        if conversation.title == "New chat" and message:
            conversation.title = _conversation_title_from_text(message)
        conversation.updated_at = datetime.now(timezone.utc)
        if has_tool_callback:
            db.session.add(
                ChatMessage(
                    conversation_id=conversation.id,
                    role="tool",
                    body=str(tool_result),
                    tool_trace_json=[
                        {
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                        }
                    ],
                )
            )
        if result.get("status") == "requires_local_action":
            db.session.add(
                ChatMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    body="",
                    tool_trace_json=result.get("tool_trace") or [],
                )
            )
        else:
            db.session.add(
                ChatMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    body=result["answer"],
                    tool_trace_json=result.get("tool_trace") or [],
                )
            )
        db.session.commit()
        result["conversation_id"] = conversation.id

    if stream:
        @stream_with_context
        def generate():
            yield _sse_event(
                "meta",
                {
                    "conversation_id": result.get("conversation_id"),
                    "status": result.get("status"),
                },
            )
            if result.get("status") == "requires_local_action":
                yield _sse_event(
                    "requires_local_action",
                    {
                        "conversation_id": result.get("conversation_id"),
                        "action": result.get("action") or {},
                    },
                )
                return

            answer = str(result.get("answer") or "")
            for chunk in _answer_chunks(answer):
                yield _sse_event("delta", {"text": chunk})
            yield _sse_event(
                "completed",
                {
                    "conversation_id": result.get("conversation_id"),
                    "status": result.get("status", "completed"),
                    "answer": answer,
                    "tool_trace": result.get("tool_trace") or [],
                },
            )

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return jsonify(result)

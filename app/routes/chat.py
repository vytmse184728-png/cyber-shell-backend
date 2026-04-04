from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import ChatConversation, ChatMessage
from ..services.ai_chat import run_chat

bp = Blueprint("chat", __name__)



def _conversation_title_from_text(text: str) -> str:
    title = " ".join((text or "").strip().split())
    return (title[:77] + "...") if len(title) > 80 else (title or "New chat")



def _message_history(conversation: ChatConversation) -> list[dict[str, str]]:
    return [{"role": msg.role, "text": msg.body} for msg in conversation.messages]


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
    if not message:
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
    elif session_id:
        conversation = ChatConversation(session_id=session_id, title=_conversation_title_from_text(message))
        db.session.add(conversation)
        db.session.flush()

    if conversation is not None:
        conversation.updated_at = datetime.now(timezone.utc)
        db.session.add(ChatMessage(conversation_id=conversation.id, role="user", body=message))
        db.session.commit()
        history = _message_history(conversation)

    try:
        result = run_chat(message=message, session_id=session_id, history=history)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    if conversation is not None:
        if conversation.title == "New chat":
            conversation.title = _conversation_title_from_text(message)
        conversation.updated_at = datetime.now(timezone.utc)
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

    return jsonify(result)

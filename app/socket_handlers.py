from __future__ import annotations

from flask import request
from flask_socketio import emit, join_room, leave_room

from .extensions import socketio


@socketio.on("connect")
def handle_connect(auth=None):
    join_room("sessions")
    emit("connected", {"ok": True, "sid": request.sid})


@socketio.on("disconnect")
def handle_disconnect():
    return None


@socketio.on("subscribe_session")
def handle_subscribe_session(data=None):
    session_id = str((data or {}).get("session_id") or "").strip()
    if not session_id:
        return
    join_room(f"session:{session_id}")
    emit("subscribed", {"session_id": session_id})


@socketio.on("unsubscribe_session")
def handle_unsubscribe_session(data=None):
    session_id = str((data or {}).get("session_id") or "").strip()
    if not session_id:
        return
    leave_room(f"session:{session_id}")
    emit("unsubscribed", {"session_id": session_id})

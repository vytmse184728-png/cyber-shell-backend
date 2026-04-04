from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError

from ..auth import is_valid_bearer_header
from ..extensions import db, socketio
from ..models import TerminalEvent

bp = Blueprint("ingest", __name__)

REQUIRED_FIELDS = {
    "session_id",
    "hostname",
    "shell",
    "seq",
    "cwd",
    "cmd",
    "exit_code",
    "output",
    "output_truncated",
    "started_at",
    "finished_at",
    "is_interactive",
}



def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))



def _session_summary(session_id: str) -> dict | None:
    row = (
        db.session.query(
            TerminalEvent.session_id,
            func.max(TerminalEvent.hostname).label("hostname"),
            func.max(TerminalEvent.finished_at).label("last_seen_at"),
            func.count(TerminalEvent.id).label("event_count"),
            func.sum(case((TerminalEvent.exit_code != 0, 1), else_=0)).label("failed_count"),
        )
        .filter(TerminalEvent.session_id == session_id)
        .group_by(TerminalEvent.session_id)
        .first()
    )
    if row is None:
        return None
    return {
        "session_id": row.session_id,
        "hostname": row.hostname,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "event_count": int(row.event_count or 0),
        "failed_count": int(row.failed_count or 0),
    }


@bp.post("/api/terminal-events")
def ingest_terminal_event():
    if not is_valid_bearer_header(request.headers.get("Authorization")):
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid json"}), 400

    missing = sorted(REQUIRED_FIELDS - set(payload.keys()))
    if missing:
        return jsonify({"error": "missing fields", "missing": missing}), 400

    event = TerminalEvent(
        session_id=str(payload["session_id"]),
        hostname=str(payload["hostname"]),
        shell=str(payload["shell"]),
        seq=int(payload["seq"]),
        cwd=str(payload["cwd"]),
        cmd=str(payload["cmd"]),
        exit_code=int(payload["exit_code"]),
        output=str(payload["output"]),
        output_truncated=bool(payload["output_truncated"]),
        started_at=_parse_datetime(str(payload["started_at"])),
        finished_at=_parse_datetime(str(payload["finished_at"])),
        is_interactive=bool(payload["is_interactive"]),
        metadata_json=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )

    db.session.add(event)
    created = True
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        created = False
        current_app.logger.info(
            "duplicate terminal event ignored: session_id=%s seq=%s",
            event.session_id,
            event.seq,
        )

    if created:
        socketio.emit(
            "terminal_event",
            {
                "session_id": event.session_id,
                "event": event.to_timeline_dict(),
            },
            to=f"session:{event.session_id}",
        )

        summary = _session_summary(event.session_id)
        if summary:
            socketio.emit("session_updated", summary, to="sessions")

    return jsonify({"status": "accepted"}), 202

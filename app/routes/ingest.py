from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from ..auth import is_valid_bearer_header
from ..extensions import db
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
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.info(
            "duplicate terminal event ignored: session_id=%s seq=%s",
            event.session_id,
            event.seq,
        )

    return jsonify({"status": "accepted"}), 202

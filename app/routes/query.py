from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, case, desc, func, or_

from ..extensions import db
from ..models import TerminalEvent

bp = Blueprint("query", __name__)



def _session_card(row) -> dict:
    return {
        "session_id": row.session_id,
        "hostname": row.hostname,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "event_count": int(row.event_count or 0),
        "failed_count": int(row.failed_count or 0),
    }


@bp.get("/api/sessions")
def list_sessions():
    limit = max(1, min(int(request.args.get("limit", 50)), 200))
    failed_case = case((TerminalEvent.exit_code != 0, 1), else_=0)
    rows = (
        db.session.query(
            TerminalEvent.session_id,
            func.max(TerminalEvent.hostname).label("hostname"),
            func.max(TerminalEvent.finished_at).label("last_seen_at"),
            func.count(TerminalEvent.id).label("event_count"),
            func.sum(failed_case).label("failed_count"),
        )
        .group_by(TerminalEvent.session_id)
        .order_by(desc("last_seen_at"))
        .limit(limit)
        .all()
    )
    return jsonify([_session_card(row) for row in rows])


@bp.get("/api/sessions/<session_id>/overview")
def get_session_overview(session_id: str):
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
        return jsonify({"error": "session not found"}), 404
    return jsonify(_session_card(row))


@bp.get("/api/sessions/<session_id>/events")
def get_session_events(session_id: str):
    limit = max(1, min(int(request.args.get("limit", 20)), 50))
    before_finished_at = (request.args.get("before_finished_at") or "").strip()
    before_id = request.args.get("before_id", type=int)

    query = db.session.query(TerminalEvent).filter(TerminalEvent.session_id == session_id)

    if before_finished_at and before_id:
        cursor_dt = datetime.fromisoformat(before_finished_at.replace("Z", "+00:00"))
        query = query.filter(
            or_(
                TerminalEvent.finished_at < cursor_dt,
                and_(
                    TerminalEvent.finished_at == cursor_dt,
                    TerminalEvent.id < before_id,
                ),
            )
        )

    rows = (
        query.order_by(TerminalEvent.finished_at.desc(), TerminalEvent.id.desc())
        .limit(limit)
        .all()
    )

    ordered_for_ui = list(reversed(rows))
    items = [row.to_timeline_dict() for row in ordered_for_ui]

    next_cursor = None
    if len(rows) == limit:
        oldest_row = rows[-1]
        next_cursor = {
            "before_finished_at": oldest_row.finished_at.isoformat(),
            "before_id": oldest_row.id,
        }

    return jsonify(
        {
            "session_id": session_id,
            "items": items,
            "next_cursor": next_cursor,
            "has_more": len(rows) == limit,
        }
    )

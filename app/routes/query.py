from __future__ import annotations

from collections import Counter
from math import ceil

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import case, desc, func, or_

from ..extensions import db
from ..models import ChatConversation, TerminalEvent
from ..session_utils import infer_findings, infer_lab, lab_label, session_labs, summarize_output

bp = Blueprint("query", __name__)


def _session_card(row) -> dict:
    recent_events = (
        db.session.query(TerminalEvent)
        .filter(TerminalEvent.session_id == row.session_id)
        .order_by(desc(TerminalEvent.finished_at))
        .limit(40)
        .all()
    )
    labs = session_labs(recent_events)
    findings: Counter[str] = Counter()
    for event in recent_events:
        findings.update(infer_findings(event.cmd, event.output))
    last_output = summarize_output(recent_events[0].output, 180) if recent_events else ""
    return {
        "session_id": row.session_id,
        "hostname": row.hostname,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "event_count": int(row.event_count or 0),
        "failed_count": int(row.failed_count or 0),
        "labs": labs,
        "lab_labels": [lab_label(item) for item in labs],
        "dominant_lab": labs[0],
        "conversation_count": db.session.query(ChatConversation.id)
        .filter(ChatConversation.session_id == row.session_id)
        .count(),
        "last_output_summary": last_output,
        "top_findings": [item for item, _count in findings.most_common(3)],
    }


@bp.get("/api/sessions")
def list_sessions():
    limit = max(1, min(int(request.args.get("limit", 50)), 200))
    lab_filter = (request.args.get("lab") or "").strip().lower()
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
    items = [_session_card(row) for row in rows]
    if lab_filter:
        items = [item for item in items if lab_filter in item["labs"]]
    return jsonify(items)


@bp.get("/api/sessions/<session_id>/overview")
def get_session_overview(session_id: str):
    rows = (
        db.session.query(TerminalEvent)
        .filter(TerminalEvent.session_id == session_id)
        .order_by(desc(TerminalEvent.finished_at))
        .limit(100)
        .all()
    )
    if not rows:
        return jsonify({"error": "session not found"}), 404

    lab_counter: Counter[str] = Counter()
    finding_counter: Counter[str] = Counter()
    failure_count = 0
    for row in rows:
        lab_counter[infer_lab(row.cmd, row.output, row.metadata_json)] += 1
        finding_counter.update(infer_findings(row.cmd, row.output))
        if row.exit_code != 0:
            failure_count += 1

    return jsonify(
        {
            "session_id": session_id,
            "hostname": rows[0].hostname,
            "event_count": len(rows),
            "failed_count": failure_count,
            "labs": [
                {"lab": lab, "label": lab_label(lab), "count": count}
                for lab, count in lab_counter.most_common()
            ],
            "findings": [
                {"key": finding, "count": count}
                for finding, count in finding_counter.most_common()
            ],
            "latest_command": rows[0].cmd,
            "latest_output_summary": summarize_output(rows[0].output, 220),
        }
    )


@bp.get("/api/sessions/<session_id>/events")
def get_session_events(session_id: str):
    page = max(1, int(request.args.get("page", 1)))
    page_size = max(5, min(int(request.args.get("page_size", 12)), 50))
    search = (request.args.get("search") or "").strip().lower()
    lab = (request.args.get("lab") or "all").strip().lower()

    query = db.session.query(TerminalEvent).filter(TerminalEvent.session_id == session_id)
    if search:
        like_value = f"%{search}%"
        query = query.filter(
            or_(
                TerminalEvent.cmd.ilike(like_value),
                TerminalEvent.output.ilike(like_value),
                TerminalEvent.cwd.ilike(like_value),
            )
        )

    rows = query.order_by(desc(TerminalEvent.finished_at)).limit(500).all()
    filtered = []
    for row in rows:
        inferred = infer_lab(row.cmd, row.output, row.metadata_json)
        if lab != "all" and inferred != lab:
            continue
        filtered.append(row)

    total = len(filtered)
    page_count = max(1, ceil(total / page_size)) if total else 1
    page = min(page, page_count)
    start = (page - 1) * page_size
    end = start + page_size
    items = [
        row.to_dict(output_preview_chars=current_app.config["MAX_OUTPUT_PREVIEW_CHARS"])
        for row in filtered[start:end]
    ]

    return jsonify(
        {
            "session_id": session_id,
            "page": page,
            "page_size": page_size,
            "page_count": page_count,
            "total": total,
            "items": items,
        }
    )


@bp.get("/api/events/<int:event_id>")
def get_event_detail(event_id: int):
    row = db.session.get(TerminalEvent, event_id)
    if row is None:
        return jsonify({"error": "event not found"}), 404

    payload = row.to_dict(output_preview_chars=max(current_app.config["MAX_OUTPUT_PREVIEW_CHARS"], len(row.output)))
    payload["output_full"] = row.output
    return jsonify(payload)

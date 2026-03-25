from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, or_

from ..extensions import db
from ..models import TerminalEvent

ISSUE_PATTERNS = {
    "missing_command": ["command not found"],
    "permission_denied": ["permission denied"],
    "missing_file": ["no such file or directory"],
    "connection_refused": ["connection refused"],
    "timeout": ["timed out", "timeout"],
    "dns_error": ["temporary failure in name resolution", "name or service not known"],
    "auth_error": ["unauthorized", "forbidden", "authentication failed"],
}


def _base_query(
    *,
    session_id: str | None = None,
    hostname: str | None = None,
    since_minutes: int | None = None,
):
    query = db.session.query(TerminalEvent)
    if session_id:
        query = query.filter(TerminalEvent.session_id == session_id)
    if hostname:
        query = query.filter(TerminalEvent.hostname == hostname)
    if since_minutes is not None:
        threshold = datetime.now(timezone.utc) - timedelta(minutes=max(since_minutes, 1))
        query = query.filter(TerminalEvent.finished_at >= threshold)
    return query



def _event_preview(event: TerminalEvent, limit: int = 400) -> dict:
    return {
        "seq": event.seq,
        "cmd": event.cmd,
        "cwd": event.cwd,
        "exit_code": event.exit_code,
        "finished_at": event.finished_at.astimezone(timezone.utc).isoformat(),
        "output_preview": event.output[:limit],
    }



def _detect_issues(events: list[TerminalEvent]) -> list[dict]:
    counter: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}

    for event in events:
        haystack = f"{event.cmd}\n{event.output}".lower()
        for label, patterns in ISSUE_PATTERNS.items():
            if any(pattern in haystack for pattern in patterns):
                counter[label] += 1
                examples.setdefault(label, []).append(event.output[:240])

    result = []
    for label, count in counter.most_common(5):
        result.append(
            {
                "issue": label,
                "count": count,
                "examples": examples.get(label, [])[:2],
            }
        )
    return result



def get_recent_events(
    session_id: str | None = None,
    hostname: str | None = None,
    failures_only: bool = False,
    since_minutes: int | None = 180,
    limit: int = 10,
) -> dict:
    query = _base_query(
        session_id=session_id,
        hostname=hostname,
        since_minutes=since_minutes,
    ).order_by(desc(TerminalEvent.finished_at))
    if failures_only:
        query = query.filter(TerminalEvent.exit_code != 0)

    rows = query.limit(max(1, min(limit, 50))).all()
    return {
        "session_id": session_id,
        "hostname": hostname,
        "count": len(rows),
        "events": [_event_preview(row) for row in rows],
    }



def search_events(
    keyword: str,
    session_id: str | None = None,
    hostname: str | None = None,
    limit: int = 10,
) -> dict:
    needle = (keyword or "").strip()
    if not needle:
        return {"error": "keyword is required"}

    like_value = f"%{needle}%"
    query = _base_query(session_id=session_id, hostname=hostname).filter(
        or_(TerminalEvent.cmd.ilike(like_value), TerminalEvent.output.ilike(like_value))
    )
    rows = query.order_by(desc(TerminalEvent.finished_at)).limit(max(1, min(limit, 50))).all()
    return {
        "keyword": needle,
        "count": len(rows),
        "events": [_event_preview(row) for row in rows],
    }



def get_session_overview(
    session_id: str | None = None,
    hostname: str | None = None,
    since_minutes: int = 180,
) -> dict:
    rows = _base_query(
        session_id=session_id,
        hostname=hostname,
        since_minutes=since_minutes,
    ).order_by(desc(TerminalEvent.finished_at)).limit(200).all()

    total = len(rows)
    failed = [row for row in rows if row.exit_code != 0]
    success = total - len(failed)

    return {
        "session_id": session_id,
        "hostname": hostname,
        "since_minutes": since_minutes,
        "total_events": total,
        "successful_events": success,
        "failed_events": len(failed),
        "last_commands": [_event_preview(row) for row in rows[:8]],
        "likely_blockers": _detect_issues(failed or rows),
    }

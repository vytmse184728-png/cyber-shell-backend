from __future__ import annotations

from collections import Counter
from datetime import timezone
from typing import Iterable

LAB_KEYS = ("cmd-web", "sql-web", "idor-web", "other")
LAB_LABELS = {
    "cmd-web": "CMD",
    "sql-web": "SQL",
    "idor-web": "IDOR",
    "other": "Other",
}


def infer_lab(cmd: str = "", output: str = "", metadata: dict | None = None) -> str:
    meta = metadata or {}
    metadata_lab = str(meta.get("lab") or meta.get("app") or "").strip().lower()
    if metadata_lab in {"cmd-web", "cmd"}:
        return "cmd-web"
    if metadata_lab in {"sql-web", "sql"}:
        return "sql-web"
    if metadata_lab in {"idor-web", "idor"}:
        return "idor-web"

    haystack = "\n".join([cmd or "", output or "", metadata_lab]).lower()
    if any(token in haystack for token in ["idor_profile.php", "idor_login.php", "idor_logs.php", "idor web", ":8082", "ownership_mismatch"]):
        return "idor-web"
    if any(token in haystack for token in ["ping.php", "dns.php", "ping tool", "network app", ":8081", ";id", ";uname"]):
        return "cmd-web"
    if any(token in haystack for token in ["sql app", "product catalog", "api/products.php", "/?q=", ":8080", "union select", "or 1=1", "and 1=2"]):
        return "sql-web"
    return "other"



def lab_label(lab: str | None) -> str:
    return LAB_LABELS.get(lab or "other", "Other")



def format_dt(value) -> str | None:
    if value is None:
        return None
    try:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(value)



def summarize_output(text: str | None, limit: int = 360) -> str:
    text = (text or "").replace("\r", "").strip()
    if not text:
        return "No output captured."
    compact = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        compact.append(line)
        if len(compact) >= 5:
            break
    preview = "\n".join(compact) if compact else text
    return preview[: limit - 1] + "…" if len(preview) > limit else preview



def infer_findings(cmd: str = "", output: str = "") -> list[str]:
    haystack = f"{cmd}\n{output}".lower()
    findings: list[str] = []
    if "uid=" in haystack or "linux " in haystack and (";id" in haystack or ";uname" in haystack):
        findings.append("command-execution")
    if "ownership_mismatch" in haystack:
        findings.append("ownership-mismatch")
    if "sql error" in haystack:
        findings.append("sql-error")
    if "or 1=1" in haystack or "and 1=2" in haystack or "union select" in haystack:
        findings.append("sqli-payload")
    if "permission denied" in haystack:
        findings.append("permission-denied")
    if "connection refused" in haystack:
        findings.append("connection-refused")
    return findings



def session_labs(events: Iterable) -> list[str]:
    counter: Counter[str] = Counter()
    for event in events:
        counter[infer_lab(getattr(event, "cmd", ""), getattr(event, "output", ""), getattr(event, "metadata_json", {}) or {})] += 1
    ranked = [lab for lab, count in counter.most_common() if count > 0]
    return ranked or ["other"]

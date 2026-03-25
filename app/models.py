from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db
from .session_utils import infer_findings, infer_lab, lab_label, summarize_output


class TerminalEvent(db.Model):
    __tablename__ = "terminal_events"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_session_seq"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(db.String(128), index=True, nullable=False)
    hostname: Mapped[str] = mapped_column(db.String(255), index=True, nullable=False)
    shell: Mapped[str] = mapped_column(db.String(64), nullable=False)
    seq: Mapped[int] = mapped_column(db.Integer, nullable=False)
    cwd: Mapped[str] = mapped_column(db.Text, nullable=False)
    cmd: Mapped[str] = mapped_column(db.Text, nullable=False)
    exit_code: Mapped[int] = mapped_column(db.Integer, index=True, nullable=False)
    output: Mapped[str] = mapped_column(db.Text, nullable=False)
    output_truncated: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), index=True, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), index=True, nullable=False)
    is_interactive: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(db.JSON, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def inferred_lab(self) -> str:
        return infer_lab(self.cmd, self.output, self.metadata_json)

    def to_dict(self, output_preview_chars: int = 1200) -> dict:
        preview = self.output[:output_preview_chars]
        return {
            "id": self.id,
            "session_id": self.session_id,
            "hostname": self.hostname,
            "shell": self.shell,
            "seq": self.seq,
            "cwd": self.cwd,
            "cmd": self.cmd,
            "exit_code": self.exit_code,
            "output_preview": preview,
            "output_summary": summarize_output(preview, limit=min(output_preview_chars, 360)),
            "output_truncated": self.output_truncated,
            "started_at": self.started_at.astimezone(timezone.utc).isoformat(),
            "finished_at": self.finished_at.astimezone(timezone.utc).isoformat(),
            "is_interactive": self.is_interactive,
            "metadata": self.metadata_json,
            "received_at": self.received_at.astimezone(timezone.utc).isoformat()
            if self.received_at
            else None,
            "lab": self.inferred_lab(),
            "lab_label": lab_label(self.inferred_lab()),
            "findings": infer_findings(self.cmd, self.output),
        }


class ChatConversation(db.Model):
    __tablename__ = "chat_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(db.String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(db.String(255), nullable=False, default="New chat")
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat()
            if self.created_at
            else None,
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat()
            if self.updated_at
            else None,
            "message_count": len(self.messages),
            "preview": self.messages[-1].body[:120] if self.messages else "",
        }


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(db.String(32), nullable=False)
    body: Mapped[str] = mapped_column(db.Text, nullable=False)
    tool_trace_json: Mapped[list] = mapped_column(db.JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[ChatConversation] = relationship(back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "body": self.body,
            "tool_trace": self.tool_trace_json,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat()
            if self.created_at
            else None,
        }

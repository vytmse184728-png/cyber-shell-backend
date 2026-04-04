from __future__ import annotations

from flask import Flask, jsonify, render_template
from sqlalchemy import text

from .config import Config
from .extensions import db, socketio
from .routes.chat import bp as chat_bp
from .routes.ingest import bp as ingest_bp
from .routes.query import bp as query_bp


def _ensure_runtime_indexes() -> None:
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_terminal_events_session_finished_id "
            "ON terminal_events (session_id, finished_at DESC, id DESC)"
        )
    )
    db.session.commit()



def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    socketio.init_app(app)

    app.register_blueprint(ingest_bp)
    app.register_blueprint(query_bp)
    app.register_blueprint(chat_bp)

    from . import socket_handlers  # noqa: F401

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    with app.app_context():
        db.create_all()
        _ensure_runtime_indexes()

    return app

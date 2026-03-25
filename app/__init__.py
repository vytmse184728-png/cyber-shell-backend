from __future__ import annotations

from flask import Flask, jsonify, render_template

from .config import Config
from .extensions import db
from .routes.chat import bp as chat_bp
from .routes.ingest import bp as ingest_bp
from .routes.query import bp as query_bp



def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(ingest_bp)
    app.register_blueprint(query_bp)
    app.register_blueprint(chat_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    return app

import os

from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", "60081"))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)

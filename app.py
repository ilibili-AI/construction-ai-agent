import os
from datetime import datetime, timezone
from flask import Flask, jsonify
from config import FLASK_SECRET_KEY, APP_ENV
from services.database import init_db

def create_app():
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY

    init_db()

    from routes.chat_routes import chat_bp
    from routes.dashboard_routes import dashboard_bp
    from routes.vapi_routes import vapi_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(vapi_bp)

    @app.context_processor
    def template_helpers():
        from routes.dashboard_routes import (
            quality_class, urgency_class,
            display_quality, display_priority,
        )
        return {
            "quality_class": quality_class,
            "urgency_class": urgency_class,
            "display_quality": display_quality,
            "display_priority": display_priority,
        }

    @app.route("/health")
    def health_check():
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }), 200

    return app


app = create_app()

if __name__ == "__main__":
    flask_env = os.environ.get("FLASK_ENV", APP_ENV)
    debug = flask_env not in ("production", "prod")
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
    )
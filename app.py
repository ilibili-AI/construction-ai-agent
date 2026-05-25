import os
from flask import Flask
from config import FLASK_SECRET_KEY, APP_ENV
from services.database import init_db

def create_app():
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY

    init_db()

    from routes.chat_routes import chat_bp
    from routes.dashboard_routes import dashboard_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(dashboard_bp)

    @app.context_processor
    def template_helpers():
        from routes.dashboard_routes import (
            quality_class, urgency_class, display_quality, display_priority
        )
        return {
            "quality_class": quality_class,
            "urgency_class": urgency_class,
            "display_quality": display_quality,
            "display_priority": display_priority,
        }

    return app

app = create_app()

if __name__ == "__main__":
    debug = APP_ENV != "production"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=debug)
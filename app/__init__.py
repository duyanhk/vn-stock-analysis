from flask import Flask
import os

from config import DevelopmentConfig, ProductionConfig

# Prevent vnai from calling sys.exit() on API rate limit so our wait-and-retry can run
from .patch_vnai_rate_limit import apply_vnai_rate_limit_patch
apply_vnai_rate_limit_patch()


def create_app() -> Flask:
    """
    Application factory for the financial scraping UI.
    """
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load config: ProductionConfig when FLASK_ENV=production, else DevelopmentConfig
    if os.getenv("FLASK_ENV") == "production":
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    # Ensure output directory exists
    os.makedirs(app.config["OUTPUT_DIR"], exist_ok=True)

    # Register routes
    from .routes import bp as main_bp

    app.register_blueprint(main_bp)

    # Ensure 500 errors return JSON (not HTML) so the frontend can parse them
    @app.errorhandler(500)
    def handle_500(err):
        from flask import jsonify
        import traceback
        print("500 error:", err)
        print(traceback.format_exc())
        return jsonify({"records": [], "error": "Server error. Check Render logs for details."}), 500

    return app



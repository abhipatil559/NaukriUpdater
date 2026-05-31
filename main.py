# ----------------------------------------------------------------------------------
# main.py — Naukri Profile Refresh Agent (Flask Web Service)
#
# Endpoints:
#   GET  /                  → Health check
#   POST /api/auth/register → Register
#   POST /api/auth/login    → Login
#   GET  /api/profile       → Get user's Naukri settings (JWT)
#   PUT  /api/profile       → Update user's Naukri settings (JWT)
#   GET  /api/refresh       → Cron: refresh all active users
# ----------------------------------------------------------------------------------

from flask import Flask, jsonify
from flask_cors import CORS
from src.models.database import db
from src.routes.auth import auth_bp
from src.routes.profile import profile_bp
from src.routes.cron import cron_bp
from dotenv import load_dotenv
import logging
import os
import sys

load_dotenv(override=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("naukri-agent")

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

# CORS — allow requests from any frontend origin (Vercel or localhost)
CORS(app, resources={r"/*": {"origins": "*"}})

# Database config
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///noperi.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Fix Render's postgres:// → postgresql://
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace(
        "postgres://", "postgresql://", 1
    )

# Init database
db.init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(cron_bp)

# Create tables on startup
with app.app_context():
    db.create_all()
    logger.info("Database tables created/verified")


# ── Health Check ──────────────────────────────────────────────────────────────

@app.route("/")
def health():
    return jsonify({
        "status": "running",
        "service": "Naukri Profile Refresh Agent",
        "version": "2.0.0",
    })


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    logger.info("Starting server on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=True)
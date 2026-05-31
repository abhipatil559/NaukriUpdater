"""
Profile routes — CRUD for Naukri automation settings.
JWT-protected: user can only view/edit their own profile.
"""

from flask import Blueprint, request, jsonify, g
from src.models.database import db, Profile
from src.utils.encryption import encrypt, decrypt
from functools import wraps
import jwt
import os

profile_bp = Blueprint("profile", __name__, url_prefix="/api")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")


def jwt_required(f):
    """Decorator to require a valid JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            g.user_id = payload["user_id"]
            g.email = payload["email"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated


@profile_bp.route("/profile", methods=["GET"])
@jwt_required
def get_profile():
    profile = Profile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({"profile": None})
    return jsonify({"profile": profile.to_dict()})


@profile_bp.route("/profile", methods=["PUT"])
@jwt_required
def update_profile():
    data = request.get_json() or {}

    profile = Profile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        profile = Profile(user_id=g.user_id)
        db.session.add(profile)

    # Update fields if provided
    if "naukri_username" in data:
        profile.naukri_username = data["naukri_username"]

    if "naukri_password" in data and data["naukri_password"]:
        profile.naukri_password = encrypt(data["naukri_password"])

    if "resume_drive_link" in data:
        profile.resume_drive_link = data["resume_drive_link"]

    if "headline_1" in data:
        profile.headline_1 = data["headline_1"]

    if "headline_2" in data:
        profile.headline_2 = data["headline_2"]

    if "summary_1" in data:
        profile.summary_1 = data["summary_1"]

    if "summary_2" in data:
        profile.summary_2 = data["summary_2"]

    if "refresh_interval" in data:
        profile.refresh_interval = int(data["refresh_interval"])

    if "is_active" in data:
        profile.is_active = bool(data["is_active"])

    db.session.commit()
    return jsonify({"profile": profile.to_dict()})

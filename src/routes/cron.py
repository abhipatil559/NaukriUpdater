"""
Cron route — called by cron-job.org to refresh all active users' Naukri profiles.
Protected by CRON_SECRET query parameter.
"""

from flask import Blueprint, request, jsonify
from src.models.database import db, Profile
from src.utils.encryption import decrypt
from src.client.naukri_client import NaukriLoginClient
from src.client.profile_extractor import extract_profile
from datetime import datetime
import logging
import requests
import tempfile
import os
import re

cron_bp = Blueprint("cron", __name__, url_prefix="/api")
logger = logging.getLogger("naukri-agent")

CRON_SECRET = os.getenv("CRON_SECRET", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def _download_resume_from_drive(drive_link: str) -> str:
    """Download a resume PDF from Google Drive link and return the temp file path."""
    # Extract file ID from various Google Drive URL formats
    match = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]+)", drive_link)
    if not match:
        raise ValueError(f"Could not extract file ID from: {drive_link}")

    file_id = match.group(1)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    res = requests.get(download_url, timeout=30)
    res.raise_for_status()

    if res.content[:4] != b"%PDF":
        raise ValueError("Downloaded file is not a valid PDF")

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(res.content)
    tmp.close()
    return tmp.name


def _refresh_user(profile: Profile, cycle: int) -> dict:
    """Run one profile refresh cycle for a single user. Returns result dict."""
    result = {"user_id": profile.user_id, "naukri_user": profile.naukri_username, "actions": []}

    # Decrypt Naukri password
    naukri_password = decrypt(profile.naukri_password)

    # Download resume
    resume_path = None
    if profile.resume_drive_link:
        try:
            resume_path = _download_resume_from_drive(profile.resume_drive_link)
            result["actions"].append({"action": "download_resume", "status": "success"})
        except Exception as e:
            result["actions"].append({"action": "download_resume", "status": "failed", "error": str(e)})
            logger.error("Resume download failed for user %s: %s", profile.naukri_username, e)

    # Login to Naukri
    try:
        client = NaukriLoginClient(profile.naukri_username, naukri_password)
        client.login()
        result["actions"].append({"action": "login", "status": "success"})
    except Exception as e:
        error_msg = str(e)
        logger.error("Naukri login failed for %s: %s", profile.naukri_username, error_msg)
        result["actions"].append({"action": "login", "status": "failed", "error": error_msg})
        result["overall"] = "failed"
        profile.last_status = "failed"
        profile.last_error = error_msg
        profile.last_refreshed = datetime.utcnow()
        db.session.commit()
        return result

    # Upload resume
    if resume_path:
        try:
            client.update_resume(resume_path)
            result["actions"].append({"action": "resume_upload", "status": "success"})
        except Exception as e:
            result["actions"].append({"action": "resume_upload", "status": "failed", "error": str(e)})
            logger.error("Resume upload failed for user %s: %s", profile.naukri_username, e)
        finally:
            # Clean up temp file
            try:
                os.unlink(resume_path)
            except OSError:
                pass

    # Update headline
    try:
        h1 = profile.headline_1 or ""
        h2 = profile.headline_2 or ""
        if h1 and h2:
            headline = h1 if cycle % 2 == 1 else h2
            client.update_profile(headline=headline)
            which = "A" if cycle % 2 == 1 else "B"
            result["actions"].append({"action": f"headline_{which}", "status": "success"})
    except Exception as e:
        result["actions"].append({"action": "headline", "status": "failed", "error": str(e)})

    # Update summary
    try:
        s1 = profile.summary_1 or ""
        s2 = profile.summary_2 or ""
        if s1 and s2:
            summary = s1 if cycle % 2 == 1 else s2
            client.update_profile(summary=summary)
            which = "A" if cycle % 2 == 1 else "B"
            result["actions"].append({"action": f"summary_{which}", "status": "success"})
    except Exception as e:
        result["actions"].append({"action": "summary", "status": "failed", "error": str(e)})

    # Update profile status in DB
    profile.last_refreshed = datetime.utcnow()
    profile.last_status = "success"
    profile.last_error = None
    profile.total_refreshes = (profile.total_refreshes or 0) + 1
    db.session.commit()

    result["overall"] = "success"
    return result


@cron_bp.route("/refresh", methods=["GET"])
def refresh_all():
    """Refresh all active users' Naukri profiles. Called by cron-job.org."""
    # Allow secret via query param OR Authorization header (Bearer token)
    secret = request.args.get("secret", "")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        secret = auth_header.split(" ", 1)[1]

    if CRON_SECRET and secret != CRON_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    active_profiles = Profile.query.filter_by(is_active=True).filter(
        Profile.naukri_username.isnot(None),
        Profile.naukri_password.isnot(None),
    ).all()

    if not active_profiles:
        return jsonify({"message": "No active profiles to refresh", "refreshed": 0})

    results = []
    # Use total_refreshes as cycle counter per user for A/B alternation
    for profile in active_profiles:
        # Check if it's time to refresh this profile
        if profile.last_refreshed:
            elapsed = (datetime.utcnow() - profile.last_refreshed).total_seconds()
            if elapsed < (profile.refresh_interval or 3600):
                continue

        cycle = (profile.total_refreshes or 0) + 1
        try:
            logger.info("Refreshing user: %s (cycle %d)", profile.naukri_username, cycle)
            result = _refresh_user(profile, cycle)
            results.append(result)
        except Exception as e:
            logger.error("Failed to refresh user %s: %s", profile.naukri_username, e)
            profile.last_status = "failed"
            profile.last_error = str(e)
            profile.last_refreshed = datetime.utcnow()
            db.session.commit()
            results.append({"user_id": profile.user_id, "overall": "failed", "error": str(e)})

    success_count = sum(1 for r in results if r.get("overall") == "success")
    failed_count = len(results) - success_count

    return jsonify({
        "refreshed": success_count,
        "failed": failed_count,
        "total_users": len(active_profiles),
        "results": results,
    })

#!/usr/bin/env python3
"""
local_cron.py — Local Naukri Profile Refresh Worker

Runs on your home machine (residential IP) to avoid Naukri's reCAPTCHA
blocking on datacenter IPs. Fetches active user profiles from the Render
backend, logs into Naukri for each user, uploads their resume, and
rotates headlines/summaries.

Usage:
    python local_cron.py              # run once
    python local_cron.py --dry-run    # fetch profiles but don't touch Naukri

Crontab (runs at 9 AM, 2 PM, 8 PM daily):
    0 9,14,20 * * * cd /path/to/NopeRi && python3 local_cron.py >> cron.log 2>&1

Required .env variables:
    RENDER_API_URL=https://your-app.onrender.com
    CRON_SECRET=your-cron-secret
    FERNET_KEY=your-fernet-key
"""

import os
import re
import sys
import time
import tempfile
import argparse
import requests as http_requests
from datetime import datetime
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Import the Naukri client from the project
from src.client.naukri_client import NaukriLoginClient

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

RENDER_API_URL = os.getenv("RENDER_API_URL", "").rstrip("/")
CRON_SECRET = os.getenv("CRON_SECRET", "")
FERNET_KEY = os.getenv("FERNET_KEY", "")

DELAY_BETWEEN_USERS = 30  # seconds between users to avoid rate-limiting


# ── Helpers ───────────────────────────────────────────────────────────────────

def decrypt_password(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted password."""
    if not FERNET_KEY:
        raise RuntimeError("FERNET_KEY not set in .env")
    f = Fernet(FERNET_KEY.encode())
    return f.decrypt(encrypted.encode()).decode()


def download_resume(drive_link: str) -> str | None:
    """Download a resume PDF from Google Drive. Returns temp file path or None."""
    match = re.search(r"(?:/d/|id=)([a-zA-Z0-9_-]+)", drive_link)
    if not match:
        print(f"    ⚠ Could not extract file ID from: {drive_link}")
        return None

    file_id = match.group(1)
    url = f"https://drive.google.com/uc?export=download&id={file_id}"

    try:
        res = http_requests.get(url, timeout=30)
        res.raise_for_status()

        if res.content[:4] != b"%PDF":
            print("    ⚠ Downloaded file is not a valid PDF")
            return None

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(res.content)
        tmp.close()
        return tmp.name

    except Exception as e:
        print(f"    ⚠ Resume download failed: {e}")
        return None


def fetch_profiles() -> list:
    """Fetch active profiles from the Render backend."""
    url = f"{RENDER_API_URL}/api/cron/profiles?secret={CRON_SECRET}"
    try:
        res = http_requests.get(url, timeout=30)
        res.raise_for_status()
        data = res.json()
        return data.get("profiles", [])
    except Exception as e:
        print(f"❌ Failed to fetch profiles from backend: {e}")
        sys.exit(1)


def report_results(results: list):
    """Send refresh results back to the Render backend."""
    url = f"{RENDER_API_URL}/api/cron/results?secret={CRON_SECRET}"
    try:
        res = http_requests.post(url, json={"results": results}, timeout=30)
        res.raise_for_status()
        data = res.json()
        print(f"\n📡 Results reported to backend: {data.get('updated', 0)} users updated")
    except Exception as e:
        print(f"\n⚠ Failed to report results to backend: {e}")


# ── Main refresh logic ────────────────────────────────────────────────────────

def refresh_user(profile: dict) -> dict:
    """Refresh a single user's Naukri profile. Returns result dict."""
    user_id = profile["user_id"]
    username = profile["naukri_username"]
    cycle = (profile.get("total_refreshes", 0) or 0) + 1

    result = {
        "user_id": user_id,
        "naukri_user": username,
        "status": "success",
        "error": None,
        "actions": [],
    }

    # Decrypt password
    try:
        password = decrypt_password(profile["naukri_password_encrypted"])
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"Decryption failed: {e}"
        result["actions"].append({"action": "decrypt", "status": "failed", "error": str(e)})
        return result

    # Download resume
    resume_path = None
    if profile.get("resume_drive_link"):
        resume_path = download_resume(profile["resume_drive_link"])
        status = "success" if resume_path else "failed"
        result["actions"].append({"action": "download_resume", "status": status})

    # Login to Naukri
    try:
        print(f"    🔐 Logging in to Naukri...")
        client = NaukriLoginClient(username, password)
        client.login()
        result["actions"].append({"action": "login", "status": "success"})
        print(f"    ✅ Login successful")
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        result["actions"].append({"action": "login", "status": "failed", "error": str(e)})
        print(f"    ❌ Login failed: {e}")
        return result

    # Upload resume
    if resume_path:
        try:
            print(f"    📄 Uploading resume...")
            client.update_resume(resume_path)
            result["actions"].append({"action": "resume_upload", "status": "success"})
            print(f"    ✅ Resume uploaded")
        except Exception as e:
            result["actions"].append({"action": "resume_upload", "status": "failed", "error": str(e)})
            print(f"    ⚠ Resume upload failed: {e}")
        finally:
            try:
                os.unlink(resume_path)
            except OSError:
                pass

    # Update headline (A/B rotation)
    h1 = profile.get("headline_1") or ""
    h2 = profile.get("headline_2") or ""
    if h1 and h2:
        try:
            headline = h1 if cycle % 2 == 1 else h2
            which = "A" if cycle % 2 == 1 else "B"
            print(f"    📝 Updating headline ({which})...")
            client.update_profile(headline=headline)
            result["actions"].append({"action": f"headline_{which}", "status": "success"})
            print(f"    ✅ Headline updated")
        except Exception as e:
            result["actions"].append({"action": "headline", "status": "failed", "error": str(e)})
            print(f"    ⚠ Headline update failed: {e}")

    # Update summary (A/B rotation)
    s1 = profile.get("summary_1") or ""
    s2 = profile.get("summary_2") or ""
    if s1 and s2:
        try:
            summary = s1 if cycle % 2 == 1 else s2
            which = "A" if cycle % 2 == 1 else "B"
            print(f"    📝 Updating summary ({which})...")
            client.update_profile(summary=summary)
            result["actions"].append({"action": f"summary_{which}", "status": "success"})
            print(f"    ✅ Summary updated")
        except Exception as e:
            result["actions"].append({"action": "summary", "status": "failed", "error": str(e)})
            print(f"    ⚠ Summary update failed: {e}")

    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Local Naukri Profile Refresh Worker")
    parser.add_argument("--dry-run", action="store_true", help="Fetch profiles but don't touch Naukri")
    args = parser.parse_args()

    # Validate config
    if not RENDER_API_URL:
        print("❌ RENDER_API_URL not set in .env")
        sys.exit(1)
    if not CRON_SECRET:
        print("❌ CRON_SECRET not set in .env")
        sys.exit(1)
    if not FERNET_KEY:
        print("❌ FERNET_KEY not set in .env")
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'─' * 60}")
    print(f"  🔄 Naukri Local Cron — {now}")
    print(f"{'─' * 60}")

    # Fetch profiles
    print(f"\n📡 Fetching profiles from {RENDER_API_URL}...")
    profiles = fetch_profiles()
    print(f"   Found {len(profiles)} active profile(s)\n")

    if not profiles:
        print("Nothing to do. Exiting.")
        return

    if args.dry_run:
        print("🏁 Dry run — skipping Naukri operations")
        for p in profiles:
            print(f"  • {p['naukri_username']} (refreshes: {p.get('total_refreshes', 0)})")
        return

    # Process each user
    results = []
    for i, profile in enumerate(profiles, 1):
        print(f"{'─' * 60}")
        print(f"  👤 [{i}/{len(profiles)}] {profile['naukri_username']}")
        print(f"{'─' * 60}")

        result = refresh_user(profile)
        results.append(result)

        # Delay between users to avoid Naukri rate-limiting
        if i < len(profiles):
            print(f"\n  ⏳ Waiting {DELAY_BETWEEN_USERS}s before next user...")
            time.sleep(DELAY_BETWEEN_USERS)

    # Report results to backend
    report_results(results)

    # Print summary
    success = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - success

    print(f"\n{'─' * 60}")
    print(f"  📊 Summary")
    print(f"{'─' * 60}")
    print(f"  Total users:  {len(results)}")
    print(f"  ✅ Success:    {success}")
    print(f"  ❌ Failed:     {failed}")

    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        actions_str = ", ".join(
            f"{a['action']}={'✓' if a['status'] == 'success' else '✗'}"
            for a in r.get("actions", [])
        )
        error_str = f" — {r['error']}" if r.get("error") else ""
        print(f"  {icon} {r['naukri_user']}: {actions_str}{error_str}")

    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()

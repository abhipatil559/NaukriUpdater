"""
profile_extractor.py

Sends resume text to Groq and extracts a structured candidate profile.
The profile is cached to disk as JSON and only re-extracted when the
resume file changes (detected via SHA-256 checksum).
"""

import json
import os
import re
import logging
import requests
from colorama import Fore, Style

from src.utils.resume_parser import extract_text, file_checksum

logger = logging.getLogger(__name__)

CACHE_FILE = "resume_profile.json"

EXTRACTION_PROMPT = """\
You are a resume analysis engine. Extract a structured candidate profile from the resume text below.

Return ONLY valid JSON with exactly these keys (no markdown, no explanation):

{{
  "name": "Full Name",
  "experience_years": 2.3,
  "role_focus": "backend",
  "core_stack": ["node.js", "python", "mongodb", "rest api", "aws"],
  "secondary_stack": ["docker", "selenium", "langchain", "fastapi"],
  "target_roles": ["backend developer", "fullstack developer", "SDE1"],
  "target_role_keywords": ["Node.js developer", "Python developer", "backend developer"],
  "preferred_work_style": ["startups", "product companies", "remote", "hybrid"],
  "will_not_do": ["pure frontend", "mobile", "ML research", "data science"],
  "veto_keywords_title": ["android developer", "ios developer", "flutter developer", "data scientist", "ml engineer", "intern", "internship"],
  "software_keywords_title": ["software", "developer", "engineer", "backend", "fullstack", "python", "node"],
  "frontend_veto_keywords": ["angular", "vue", "flutter", "android", "ios", "mobile", "kotlin", "swift"]
}}

RULES:
- "role_focus": one of "backend", "frontend", "fullstack", "devops", "data", "mobile", "other"
- "core_stack": the 5-8 technologies the candidate is strongest at (mentioned most / highlighted)
- "secondary_stack": everything else they know, including tools, libraries, platforms
- "target_roles": job titles they'd be a good fit for based on their experience
- "target_role_keywords": search keywords to find matching jobs (use natural job title formats like "Node.js developer", not just "node")
- "will_not_do": roles or domains they clearly don't match (infer from what's missing)
- "veto_keywords_title": if these appear in a job title, skip the job entirely (roles way outside their profile)
- "software_keywords_title": if at least one of these appears in a job title, it's likely relevant
- "frontend_veto_keywords": technologies/roles that signal a pure frontend/mobile job (to deprioritize)
- All stack/skill entries should be lowercase
- Be precise — don't invent skills not evident in the resume

RESUME TEXT:
{resume_text}
"""


def extract_profile(resume_path: str, groq_api_key: str, force: bool = False) -> dict:
    """
    Extract a structured candidate profile from a resume PDF.

    Checks a local cache first. If the resume hasn't changed (same SHA-256),
    returns the cached profile without calling the LLM.

    Args:
        resume_path:   Path to the resume PDF file.
        groq_api_key:  Groq API key for the extraction LLM call.
        force:         If True, skip cache and always re-extract.

    Returns:
        A dict containing the structured candidate profile.

    Raises:
        FileNotFoundError: If the resume PDF doesn't exist.
        RuntimeError:      If the LLM call or JSON parsing fails.
    """
    if not os.path.exists(resume_path):
        raise FileNotFoundError(f"Resume not found: {resume_path}")

    checksum = file_checksum(resume_path)

    # ── check cache ──────────────────────────────────────────────────────
    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cached = json.load(f)
            if cached.get("_checksum") == checksum:
                logger.info("Resume unchanged — using cached profile")
                return cached
        except (json.JSONDecodeError, KeyError):
            pass  # cache corrupt, re-extract

    # ── extract text ─────────────────────────────────────────────────────
    logger.info("Parsing resume PDF: %s", resume_path)
    resume_text = extract_text(resume_path)

    if not resume_text.strip():
        raise RuntimeError("Resume PDF produced no text — is it a scanned image?")

    # ── call Groq ────────────────────────────────────────────────────────
    logger.info("Extracting profile via Groq LLM...")
    prompt = EXTRACTION_PROMPT.format(resume_text=resume_text)

    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
            timeout=60,
        )

        if res.status_code != 200:
            raise RuntimeError(f"Groq API error {res.status_code}: {res.text[:300]}")

        content = res.json()["choices"][0]["message"]["content"]
        content = re.sub(r"```json|```", "", content).strip()
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise RuntimeError(f"Could not parse JSON from LLM response: {content[:300]}")

        profile = json.loads(match.group(0))

    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned invalid JSON: {e}")

    # ── validate required keys ───────────────────────────────────────────
    required_keys = [
        "core_stack", "secondary_stack", "role_focus",
        "veto_keywords_title", "software_keywords_title",
    ]
    missing = [k for k in required_keys if k not in profile]
    if missing:
        raise RuntimeError(f"Profile missing required keys: {missing}")

    # ── cache to disk ────────────────────────────────────────────────────
    profile["_checksum"] = checksum
    profile["_resume_path"] = resume_path

    with open(CACHE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    logger.info("Profile extracted and cached to %s", CACHE_FILE)
    return profile


def print_profile_summary(profile: dict) -> None:
    """
    Print a rich, colorful console summary of the extracted candidate profile.
    """
    LINE  = f"{Fore.WHITE}{'─' * 60}{Style.RESET_ALL}"
    THIN  = f"{Fore.WHITE}{'·' * 60}{Style.RESET_ALL}"

    print(f"\n{LINE}")
    print(f"  {Fore.CYAN}{Style.BRIGHT}📄  RESUME PROFILE SUMMARY{Style.RESET_ALL}")
    print(LINE)

    # ── identity ────────────────────────────────────────────────
    name = profile.get("name", "Unknown")
    exp  = profile.get("experience_years", "?")
    focus = profile.get("role_focus", "?")
    print(f"  {Fore.WHITE}Name       :{Style.RESET_ALL}  {Style.BRIGHT}{name}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Experience :{Style.RESET_ALL}  {Fore.YELLOW}{exp} years{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Focus      :{Style.RESET_ALL}  {Fore.GREEN}{focus}{Style.RESET_ALL}")

    print(THIN)

    # ── core stack ──────────────────────────────────────────────
    core = profile.get("core_stack", [])
    if core:
        tags = "  ".join(f"{Fore.GREEN}[{s}]{Style.RESET_ALL}" for s in core)
        print(f"  {Fore.WHITE}Core Stack :{Style.RESET_ALL}  {tags}")

    # ── secondary stack ─────────────────────────────────────────
    secondary = profile.get("secondary_stack", [])
    if secondary:
        tags = "  ".join(f"{Fore.CYAN}[{s}]{Style.RESET_ALL}" for s in secondary)
        print(f"  {Fore.WHITE}Also Knows :{Style.RESET_ALL}  {tags}")

    print(THIN)

    # ── target roles ────────────────────────────────────────────
    roles = profile.get("target_roles", [])
    if roles:
        roles_str = ", ".join(f"{Fore.YELLOW}{r}{Style.RESET_ALL}" for r in roles)
        print(f"  {Fore.WHITE}Target Roles    :{Style.RESET_ALL}  {roles_str}")

    # ── search keywords ─────────────────────────────────────────
    keywords = profile.get("target_role_keywords", [])
    if keywords:
        kw_str = ", ".join(f"{Fore.YELLOW}{k}{Style.RESET_ALL}" for k in keywords)
        print(f"  {Fore.WHITE}Search Keywords :{Style.RESET_ALL}  {kw_str}")

    # ── preferred locations ─────────────────────────────────────
    locations = profile.get("preferred_locations", [])
    if locations:
        loc_str = ", ".join(f"{Fore.BLUE}{l}{Style.RESET_ALL}" for l in locations)
        print(f"  {Fore.WHITE}Locations       :{Style.RESET_ALL}  {loc_str}")

    # ── work style ──────────────────────────────────────────────
    prefs = profile.get("preferred_work_style", [])
    if prefs:
        pref_str = ", ".join(f"{Fore.MAGENTA}{p}{Style.RESET_ALL}" for p in prefs)
        print(f"  {Fore.WHITE}Prefers         :{Style.RESET_ALL}  {pref_str}")

    print(THIN)

    # ── will not do ─────────────────────────────────────────────
    wont = profile.get("will_not_do", [])
    if wont:
        wont_str = ", ".join(f"{Fore.RED}{w}{Style.RESET_ALL}" for w in wont)
        print(f"  {Fore.WHITE}Will NOT Do :{Style.RESET_ALL}  {wont_str}")

    # ── veto title keywords ─────────────────────────────────────
    veto = profile.get("veto_keywords_title", [])
    if veto:
        veto_str = "  ".join(f"{Fore.RED}[✗ {v}]{Style.RESET_ALL}" for v in veto[:10])
        extra = f"  {Fore.WHITE}+{len(veto) - 10} more{Style.RESET_ALL}" if len(veto) > 10 else ""
        print(f"  {Fore.WHITE}Veto Titles :{Style.RESET_ALL}  {veto_str}{extra}")

    print(LINE)
    print()

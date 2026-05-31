"""
jop_classifier.py

AI-powered job filtering pipeline. All candidate-specific data (stack,
veto keywords, scoring prompts) is driven by a structured profile dict
extracted from the user's resume — nothing is hardcoded.
"""

import json
import os
import re
import requests


class JobFilterPipeline2:

    # ── hard veto companies — not profile-specific ──────────────────────────
    VETO_COMPANIES = {
        "accenture", "wipro", "infosys", "tcs", "cognizant",
        "capgemini", "hcl", "tech mahindra", "mphasis", "hexaware",
        "ltimindtree", "persistent", "birlasoft",
    }

    # ── red flag sniff on description (cheap, pre-ai) ───────────────────────
    DESC_RED_FLAGS = {
        "walk-in":      r"walk.?in|walkin",
        "venue listed": r"venue\s*:|interview venue|bring your resume|carry your resume",
    }

    def __init__(
        self,
        groq_api_key,
        profile: dict,
        cache_file="score_cache.json",
        daily_apply_limit=50,
        min_apply_score=50,
        ai_score_limit=300,
        batch_size=50,
    ):
        self.api_key           = groq_api_key
        self.url               = "https://api.groq.com/openai/v1/chat/completions"
        self.cache_file        = cache_file
        self.daily_apply_limit = daily_apply_limit
        self.min_apply_score   = min_apply_score
        self.ai_score_limit    = ai_score_limit
        self.batch_size        = batch_size
        self.cache             = self._load_cache()

        # ── profile-driven filters ──────────────────────────────────────
        self.profile            = profile
        self.my_stack           = set(
            profile.get("core_stack", []) + profile.get("secondary_stack", [])
        )
        self.veto_titles        = [v.lower() for v in profile.get("veto_keywords_title", [])]
        self.software_keywords  = set(
            k.lower() for k in profile.get("software_keywords_title", [])
        )
        self.frontend_veto_keywords = set(
            k.lower() for k in profile.get("frontend_veto_keywords", [])
        )
        self.experience_years   = profile.get("experience_years", 2)
        self.max_exp_filter     = int(self.experience_years) + 2  # e.g. 2.3 → 4

    # =========================================================
    # MAIN
    # =========================================================
    def run(self, jobs):
        print("\nRAW JOBS:", len(jobs))

        jobs = self.normalize_jobs(jobs)
        print("AFTER NORMALIZE:", len(jobs))

        jobs = self.dedup(jobs)
        print("AFTER DEDUP:", len(jobs))

        jobs = self.hard_veto(jobs)
        print("AFTER HARD VETO:", len(jobs))

        jobs = self.experience_filter(jobs)
        print("AFTER EXP FILTER:", len(jobs))

        jobs = self.desc_red_flag_check(jobs)
        print("AFTER RED FLAG CHECK:", len(jobs))

        jobs = self.title_filter(jobs)
        print("AFTER TITLE FILTER:", len(jobs))

        jobs = self.company_veto(jobs)
        print("AFTER COMPANY VETO:", len(jobs))

        jobs = self.tag_presort(jobs)

        jobs = jobs[:self.ai_score_limit]
        print("AFTER LIMIT:", len(jobs))

        jobs = self.ai_score_batch(jobs)

        jobs = self.rank(jobs)
        print("AFTER RANK:", len(jobs))

        jobs = self.select(jobs)
        print("FINAL SELECTED:", len(jobs))

        for j in jobs:
            print(f"  {j.get('ai_score'):>3}  {j.get('title')} @ {j.get('company')}"
                  f"  |  {j.get('ai_reason', '')}")

        return jobs

    # =========================================================
    # NORMALIZE  — tags are the star, keep them clean
    # =========================================================
    def normalize_jobs(self, jobs):
        normalized = []

        for j in jobs:
            job = j if isinstance(j, dict) else j.__dict__

            # days old
            posted   = (job.get("posted_date") or "").lower()
            days_old = 7
            if "today" in posted or "hour" in posted or "just now" in posted:
                days_old = 0
            elif "yesterday" in posted:
                days_old = 1
            else:
                m = re.search(r"(\d+)\s*day", posted)
                if m:
                    days_old = int(m.group(1))
                else:
                    m = re.search(r"(\d+)\s*week", posted)
                    if m:
                        days_old = int(m.group(1)) * 7

            # experience range
            exp = job.get("experience") or ""
            exp_min, exp_max = 0, 10
            nums = re.findall(r"\d+", exp)
            if len(nums) >= 2:
                exp_min, exp_max = int(nums[0]), int(nums[1])
            elif len(nums) == 1:
                exp_min = exp_max = int(nums[0])

            # tags — normalize once, use everywhere
            raw_tags = job.get("tags") or job.get("skills") or []
            if isinstance(raw_tags, str):
                raw_tags = re.split(r"[,;|]", raw_tags)
            tags = [t.strip().lower() for t in raw_tags if t.strip()]

            normalized.append({
                "job_id":         job.get("job_id"),
                "title":          (job.get("title")       or "").strip(),
                "company":        (job.get("company")     or "").strip(),
                "location":       (job.get("location")    or "").strip(),
                "description":    (job.get("description") or "").strip(),
                "tags":           tags,
                "mandatory_tags": tags[:2],   # site signals these as primary
                "optional_tags":  tags[2:],
                "days_old":       days_old,
                "experience_min": exp_min,
                "experience_max": exp_max,
            })

        return normalized

    # =========================================================
    # DEDUP
    # =========================================================
    def dedup(self, jobs):
        seen, result = set(), []
        for j in jobs:
            job_id = j.get("job_id")
            if job_id is None:
                result.append(j)  # can't dedup without an id, just keep it
                continue
            if job_id in seen:
                continue
            seen.add(job_id)
            result.append(j)
        return result

    # =========================================================
    # HARD VETO  — title only, no ambiguity allowed
    # =========================================================
    def hard_veto(self, jobs):
        clean = []
        for j in jobs:
            title = (j.get("title") or "").lower()
            if any(kw in title for kw in self.veto_titles):
                print(f"  [VETO] {j.get('title')}")
                continue
            clean.append(j)
        return clean

    # =========================================================
    # EXPERIENCE FILTER  — derived from resume
    # =========================================================
    def experience_filter(self, jobs):
        return [
            j for j in jobs
            if j.get("experience_min", 0) <= self.max_exp_filter
            and j.get("experience_max", 10) > 0
        ]

    # =========================================================
    # DESC RED FLAG CHECK  — one cheap regex pass, nothing more
    # =========================================================
    def desc_red_flag_check(self, jobs):
        clean = []
        for j in jobs:
            desc = (j.get("description") or "").lower()
            flagged = [
                label for label, pat in self.DESC_RED_FLAGS.items()
                if re.search(pat, desc)
            ]
            if flagged:
                print(f"  [RED FLAG {flagged}] {j.get('title')}")
                continue
            clean.append(j)
        return clean

    # =========================================================
    # TITLE FILTER  — profile-driven keyword matching
    # =========================================================
    def title_filter(self, jobs):
        result = []
        for j in jobs:
            title = (j.get("title") or "").lower()

            # must have at least one software keyword
            if not any(kw in title for kw in self.software_keywords):
                print(f"  [TITLE FILTER - not software] {j.get('title')}")
                continue

            # must NOT be frontend/mobile/ml
            if any(kw in title for kw in self.frontend_veto_keywords):
                print(f"  [TITLE FILTER - frontend/mobile] {j.get('title')}")
                continue

            result.append(j)
        return result

    # =========================================================
    # COMPANY VETO
    # =========================================================
    def company_veto(self, jobs):
        clean = []
        for j in jobs:
            company = (j.get("company") or "").lower()
            if any(vc in company for vc in self.VETO_COMPANIES):
                print(f"  [COMPANY VETO] {j.get('title')} @ {j.get('company')}")
                continue
            clean.append(j)
        return clean

    # =========================================================
    # TAG PRESORT  — rough stack overlap count, no AI cost
    # =========================================================
    def tag_presort(self, jobs):
        my_stack = self.my_stack

        def overlap(j):
            tags          = set(j.get("tags", []))
            mandatory_hit = sum(1 for t in j.get("mandatory_tags", []) if t in my_stack)
            total_hit     = len(tags & my_stack)
            recency_bonus = max(0, 7 - j.get("days_old", 7))
            # mandatory tags weighted 3x — they represent the job's core ask
            return mandatory_hit * 3 + total_hit + recency_bonus

        return sorted(jobs, key=overlap, reverse=True)

    # =========================================================
    # AI SCORING  — tags go in, score + reason come out
    # =========================================================
    def ai_score_batch(self, jobs):
        result = []
        for i in range(0, len(jobs), self.batch_size):
            batch  = jobs[i:i + self.batch_size]
            scores = self._call_ai(batch)
            for idx, job in enumerate(batch):
                jid  = str(job.get("job_id") or "")
                data = self.cache.get(jid) if jid else None

                if not data:
                    data = scores.get(str(idx), {"score": 0, "reason": "no response"})
                    if not isinstance(data.get("score"), int):
                        data = {"score": 0, "reason": "parse error"}
                    if jid:
                        self.cache[jid] = data

                job["ai_score"]  = data.get("score", 0)
                job["ai_reason"] = data.get("reason", "")
                result.append(job)

        self._save_cache()
        return result

    # =========================================================
    # _build_ai_prompt  — dynamically generated from profile
    # =========================================================
    def _build_ai_prompt(self, job_block: str) -> str:
        p = self.profile
        exp       = p.get("experience_years", 2)
        focus     = p.get("role_focus", "backend")
        core      = ", ".join(p.get("core_stack", []))
        secondary = ", ".join(p.get("secondary_stack", []))
        targets   = ", ".join(p.get("target_roles", []))
        prefs     = ", ".join(p.get("preferred_work_style", []))
        wont_do   = ", ".join(p.get("will_not_do", []))

        # dynamic experience thresholds for the scoring rubric
        exp_int     = int(exp)
        exp_sweet   = f"0-{exp_int}"
        exp_ok      = f"0-{exp_int + 1}"
        exp_stretch = f"{exp_int + 1}-{exp_int + 2}"
        exp_far     = f"{exp_int + 2}-{exp_int + 3}"

        return f"""
You are a strict job filter for a {focus} developer. Score each job 0-100.
Be precise — avoid clustering scores at 85 or 60. Use the full range.

CANDIDATE:
- {exp} years experience, {focus}-focused
- Core stack: {core}
- Also knows: {secondary}
- Looking for: {targets}
- Prefers: {prefs}
- Will NOT do: {wont_do}

SCORING RUBRIC — use the full range, not just 85/60:

90-100 — perfect fit, apply immediately
  Core stack tech is a mandatory tag + {focus} role
  + exp {exp_sweet} yrs + familiar supporting stack. Startup or product company.

75-89 — strong fit, apply
  Core stack tech present (mandatory or optional) + {focus} lean
  + exp {exp_ok} yrs. Maybe one unfamiliar tag but overall good match.

55-74 — decent fit, apply with lower priority
  Some stack overlap, role is fullstack but not {focus}-heavy,
  or exp is {exp_stretch} yrs, or company type unclear.

30-54 — weak, skip unless nothing better
  Familiar tech present but role is vague, not {focus}-leaning,
  or exp mismatch {exp_far} yrs.

10-29 — poor match
  Very little stack overlap, or role is clearly not {focus}.

0-9 — do not apply
  Zero stack overlap with candidate's core stack.
  OR walk-in / venue / intern role.

RULES:
- Core stack tech in mandatory tags + exp {exp_sweet}yr {focus} → 90+, no exceptions
- Tangential tech alongside core stack is fine — judge the full picture
- Fullstack with {focus} lean → 65-80 depending on tag quality
- "Software Engineer" with core stack tags → treat as {focus}, score 70-85
- Roles entirely outside candidate's stack → 0-15
- DevOps/infra-only with no app dev → 20-40
- Intern roles → 0
- Missing stack items is normal, don't over-penalise
- Recency: 0-1 days old → mentally add 5 points

Return ONLY valid JSON, no explanation outside it:
{{
  "0": {{"score": 92, "reason": "Core stack match, junior {focus}, startup"}},
  "1": {{"score": 0,  "reason": "Zero stack overlap"}}
}}

Jobs:
{job_block}
"""

    def _call_ai(self, jobs):
        job_block = ""
        for i, j in enumerate(jobs):
            mandatory = ", ".join(j.get("mandatory_tags", [])) or "none"
            optional  = ", ".join(j.get("optional_tags",  [])) or "none"
            exp       = f"{j.get('experience_min', 0)}-{j.get('experience_max', 10)} yrs"

            job_block += (
                f"Job {i}:\n"
                f"  Title:     {j.get('title')}\n"
                f"  Company:   {j.get('company')}\n"
                f"  Mandatory: {mandatory}\n"
                f"  Optional:  {optional}\n"
                f"  Exp:       {exp}\n"
                f"  Days old:  {j.get('days_old', 7)}\n"
                f"---\n"
            )

        prompt = self._build_ai_prompt(job_block)

        try:
            res = requests.post(
                self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       "llama-3.3-70b-versatile",
                    "messages":    [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                timeout=90,
            )

            if res.status_code != 200:
                print("AI HTTP ERROR:", res.status_code, res.text[:200])
                return {}

            content = res.json()["choices"][0]["message"]["content"]
            content = re.sub(r"```json|```", "", content).strip()
            match   = re.search(r"\{.*\}", content, re.S)
            if not match:
                print("AI PARSE ERROR — raw:", content[:300])
                return {}

            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}

        except Exception as e:
            print("AI call error:", e)
            return {}

    # =========================================================
    # RANK  — ai score + small recency bump
    # =========================================================
    def rank(self, jobs):
        return sorted(
            jobs,
            key=lambda j: j.get("ai_score", 0) + max(0, 3 - j.get("days_old", 7)),
            reverse=True,
        )

    # =========================================================
    # SELECT
    # =========================================================
    def select(self, jobs):
        apply_list  = [j for j in jobs if j.get("ai_score", 0) >= self.min_apply_score]
        review_list = [j for j in jobs if 10 <= j.get("ai_score", 0) < self.min_apply_score]

        if review_list:
            print(f"\n── REVIEW MANUALLY ({len(review_list)}) ──")
            for j in review_list:
                print(f"  score={j.get('ai_score')}  {j.get('title')} @ {j.get('company')}"
                      f"  |  {j.get('ai_reason', '')}")

        return apply_list[:self.daily_apply_limit]

    # =========================================================
    # CACHE
    # =========================================================
    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f, indent=2)
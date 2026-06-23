"""
scheduler.py  --  Batch production scheduler for Stickman Studio
=================================================================
Reads daily_plan.json and runs the full pipeline for each video
idea sequentially, with configurable delays between runs.

Usage:
    from scheduler import start_batch_production, run_autonomous_cycle
    start_batch_production(delay_seconds=30)
    run_autonomous_cycle()  # full automatic: plan → produce → upload
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from orchestrator import run_pipeline

log = logging.getLogger("stickman_studio.scheduler")

_PLAN_PATH = Path("daily_plan.json")
_READY_DIR = Path("ready_to_upload")
_PROJECTS_DIR = Path("projects")
_STATE_FILE = Path("scheduler_state.json")

DAILY_LIMIT = 5
"""Maximum number of videos to produce per autonomous cycle."""

_HOURS_MIN = 5
_HOURS_MAX = 7
"""Randomised interval range (hours) between autonomous cycles."""

_MONTHLY_STATE_FILE = Path("system_state.json")
"""Persistent state for the 30-day monthly scheduler."""

_DAYS_IN_MONTH = 30
"""Number of days in a monthly plan."""

_VIDEOS_PER_DAY_MIN = 1
_VIDEOS_PER_DAY_MAX = 3
"""Videos to produce each day."""

_BLOCK_SIZE = 5
"""Days per time-block for publishing-window rotation."""

_PUBLISH_WINDOWS = ["08:00", "10:00", "14:00", "16:00", "20:00"]
"""Available publishing windows. One is picked randomly per 5-day block."""


def _slugify(text: str) -> str:
    import re
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "untitled"


def _delay_for_complexity(score: int, base_delay: float = 15.0) -> float:
    """Scale delay by complexity (1 → ~15s, 5 → ~45s)."""
    return base_delay * (0.5 + score * 0.5)


# ---------------------------------------------------------------------------
# Persistence for autonomous schedule state
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    """Load scheduler state from ``_STATE_FILE``."""
    if _STATE_FILE.is_file():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to load scheduler state: %s", exc)
    return {}


def _save_state(state: dict) -> None:
    """Persist scheduler state to ``_STATE_FILE``."""
    _STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _calculate_next_run(from_time: datetime | None = None) -> datetime:
    """Return a datetime randomly 5-7 hours after *from_time* (default: now)."""
    if from_time is None:
        from_time = datetime.now(timezone.utc)
    offset_hours = random.uniform(_HOURS_MIN, _HOURS_MAX)
    return from_time + __import__("datetime").timedelta(hours=offset_hours)


def get_next_run_info() -> dict:
    """Return UI-friendly info about the next scheduled autonomous run.

    Returns:
        A dict with keys:
            - last_publish_time (str | None): ISO-8601 or ``"Never"``.
            - next_run_time (str | None): ISO-8601 or ``"Not scheduled"``.
            - hours_until_next (float | None): Hours remaining, or 0 if due.
            - is_due (bool): ``True`` if ``next_run_time`` is in the past.
    """
    state = _load_state()
    last_str = state.get("last_publish_time")
    next_str = state.get("next_run_time")

    now = datetime.now(timezone.utc)

    last_display = last_str
    if not last_str:
        last_display = "Never"

    next_dt = None
    if next_str:
        try:
            next_dt = datetime.fromisoformat(next_str)
        except (ValueError, TypeError):
            pass

    if next_dt is None:
        return {
            "last_publish_time": last_display,
            "next_run_time": "Not scheduled",
            "hours_until_next": None,
            "is_due": False,
        }

    seconds = (next_dt - now).total_seconds()
    is_due = seconds <= 0
    hours = max(0.0, seconds / 3600.0)

    return {
        "last_publish_time": last_display,
        "next_run_time": next_dt.isoformat(),
        "hours_until_next": round(hours, 1),
        "is_due": is_due,
    }


def _save_ready(result: dict, idea: dict) -> Path | None:
    """Copy final.mp4 into ready_to_upload/<slug>/ and save metadata."""
    video = result.get("final_video")
    if not video or not Path(video).is_file():
        return None

    slug = _slugify(idea["title"])
    dest_dir = _READY_DIR / slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / "final.mp4"
    shutil.copy2(video, str(dest))

    meta = {
        "title": idea["title"],
        "hook": idea["hook"],
        "category": idea.get("category", ""),
        "video_mode": idea.get("video_mode", "animation"),
        "complexity_score": idea.get("complexity_score", 1),
        "elapsed_seconds": result.get("elapsed_seconds", 0),
        "source_project": str(Path(video).parent.parent.name),
    }
    (dest_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    log.info("Ready for upload: %s", dest)
    return dest


def start_batch_production(
    scenes: int = 3,
    video_mode: str | None = None,
    delay_seconds: float = 15.0,
    max_ideas: int | None = None,
) -> list[dict]:
    """Run the pipeline for every idea in daily_plan.json.

    Args:
        scenes: Number of scenes per video (passed to pipeline).
        video_mode: Override mode for all ideas (uses idea's own if None).
        delay_seconds: Base delay between pipeline runs (scaled by complexity).
        max_ideas: Limit how many ideas to process (None = all).

    Returns:
        List of result dicts, one per successfully processed idea.
    """
    if not _PLAN_PATH.is_file():
        log.error("No daily_plan.json found. Run content_planner first.")
        return []

    plan = json.loads(_PLAN_PATH.read_text(encoding="utf-8"))
    ideas = plan.get("ideas", [])
    if max_ideas:
        ideas = ideas[:max_ideas]

    log.info("=" * 60)
    log.info("Batch production: %d ideas from '%s'",
             len(ideas), plan.get("category", "?"))
    log.info("=" * 60)

    results: list[dict] = []
    ready_count = 0

    for i, idea in enumerate(ideas):
        title = idea["title"]
        mode = video_mode or idea.get("video_mode", "animation")
        complexity = idea.get("complexity_score", 3)

        log.info("")
        log.info("[%d/%d] %s", i + 1, len(ideas), title)
        log.info("       mode=%s  complexity=%d", mode, complexity)

        try:
            summary = run_pipeline(
                topic=title,
                scenes=scenes,
                video_mode=mode,
            )
            result = _save_ready(summary, idea)
            if result:
                ready_count += 1
            results.append(summary)
        except Exception as exc:
            log.error("[%d/%d] FAILED: %s", i + 1, len(ideas), exc)
            results.append({"error": str(exc), "_idea": title})
            continue

        if i < len(ideas) - 1:
            pause = _delay_for_complexity(complexity, delay_seconds)
            log.info("Buffer pause: %.0fs before next idea...", pause)
            time.sleep(pause)

    log.info("")
    log.info("=" * 60)
    log.info("Batch complete: %d/%d succeeded, %d ready to upload",
             ready_count, len(ideas), ready_count)
    log.info("Ready folder: %s", _READY_DIR.resolve())
    log.info("=" * 60)

    return results


def run_autonomous_cycle(
    category: str = "Science",
    scenes: int = 3,
    upload_results: bool = True,
    max_ideas: int = DAILY_LIMIT,
    force: bool = False,
) -> list[dict]:
    """Full autonomous workflow: plan → produce → upload → schedule next.

    Steps:
        1. Check scheduler state — skip if ``next_run_time`` is in the
           future (unless ``force=True``).
        2. Generate a content plan for *category*.
        3. Run the pipeline for each idea (up to ``max_ideas``, default
           ``DAILY_LIMIT`` = 5).
        4. Upload every successfully produced video to YouTube (public).
        5. Continue to the next idea if any single step fails.
        6. Persist ``last_publish_time`` and calculate the next randomised
           run time (5-7 hours from now).

    Args:
        force: Ignore the scheduled time and run immediately.

    Returns:
        List of result dicts, one per processed idea.
    """
    from content_planner import plan_content

    now = datetime.now(timezone.utc)

    # --- Gate: check schedule unless forced ---
    if not force:
        info = get_next_run_info()
        if not info["is_due"] and info["next_run_time"] != "Not scheduled":
            log.info(
                "Skipping — next run in %.1f hours (at %s)",
                info["hours_until_next"], info["next_run_time"],
            )
            return []
    else:
        log.info("Force flag set — running now regardless of schedule.")

    log.info("=" * 60)
    log.info("AUTONOMOUS CYCLE — category=%s  limit=%d", category, max_ideas)
    log.info("=" * 60)

    # Step 1 — generate plan
    log.info("-- Step 1: Content Plan --")
    try:
        plan = plan_content(category=category, count=max_ideas, output=_PLAN_PATH)
    except Exception as exc:
        log.error("Content planning failed: %s", exc)
        return []

    ideas = plan.get("ideas", [])[:max_ideas]
    if not ideas:
        log.warning("No ideas returned; aborting autonomous cycle.")
        return []

    log.info("Got %d ideas for '%s'", len(ideas), category)

    results: list[dict] = []
    ready_count = 0
    upload_count = 0

    for i, idea in enumerate(ideas):
        title = idea["title"]
        log.info("")
        log.info("[%d/%d] %s", i + 1, len(ideas), title)

        # Step 2 — produce video (slideshow mode for cost efficiency)
        log.info("-- Step 2: Production --")
        try:
            summary = run_pipeline(
                topic=title,
                scenes=scenes,
                video_mode="slideshow",
            )
        except Exception as exc:
            log.error("[%d/%d] PRODUCTION FAILED: %s", i + 1, len(ideas), exc)
            results.append({"error": str(exc), "_idea": title})
            continue

        # Copy to ready_to_upload
        result = _save_ready(summary, idea)
        if result:
            ready_count += 1
        results.append(summary)

        # Step 3 — upload to YouTube (auto‑publish — becomes public)
        if upload_results:
            log.info("-- Step 3: YouTube Upload (auto‑publish) --")
            final_video = summary.get("final_video")
            if final_video and Path(final_video).is_file():
                from uploader import YouTubeUploader

                try:
                    uploader = YouTubeUploader()
                    url = uploader.authenticate_and_upload(
                        video_path=final_video,
                        title=title,
                        description=(
                            f"{title}\n\n"
                            f"Generated by Stickman Studio\n\n"
                            f"Hook: {idea.get('hook', '')}"
                        ),
                        tags=["stickman", "education", category.lower(), title.lower()],
                        auto_publish=True,
                    )
                    summary["youtube_url"] = url
                    upload_count += 1
                    log.info("Published: %s", url)
                except Exception as exc:
                    log.error("YouTube publish failed for '%s': %s", title, exc)
            else:
                log.warning("No final video to upload for '%s'", title)

        # Pause before next idea (even on failure, to avoid rate limits)
        if i < len(ideas) - 1:
            delay = _delay_for_complexity(idea.get("complexity_score", 3), 15.0)
            log.info("Buffer pause: %.0fs before next idea...", delay)
            time.sleep(delay)

    # Step 4 — persist schedule for next cycle
    next_run = _calculate_next_run()
    state = {
        "last_publish_time": now.isoformat(),
        "next_run_time": next_run.isoformat(),
    }
    _save_state(state)

    log.info("")
    log.info("=" * 60)
    log.info("AUTONOMOUS CYCLE COMPLETE")
    log.info("  Produced:  %d/%d", ready_count, len(ideas))
    log.info("  Uploaded:  %d", upload_count)
    log.info("  Next run:  %s (in ~%.1f hours)",
             next_run.strftime("%H:%M UTC"), (next_run - now).total_seconds() / 3600)
    log.info("  Ready dir: %s", _READY_DIR.resolve())
    log.info("=" * 60)

    return results


# ======================================================================
# Monthly Scheduler  —  30-day autonomous production lifecycle
# ======================================================================

class MonthlyScheduler:
    """Manages a 30-day autonomous production plan with time variation.

    - Divides 30 days into 5-day blocks, each with a randomised
      publishing window (08:00, 10:00, 14:00, 16:00, or 20:00).
    - Produces 1-3 videos per day (random within range).
    - Persists progress to ``system_state.json`` so reboots are safe.
    """

    def __init__(self) -> None:
        self._state_path = _MONTHLY_STATE_FILE

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if self._state_path.is_file():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except Exception as exc:
                log.warning("Failed to load monthly state: %s", exc)
        return {"active": False}

    def _save(self, state: dict) -> None:
        self._state_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    def generate_plan(self, category: str = "Science") -> dict:
        """Create a 30-day plan and persist it."""
        state = self._load()
        now = datetime.now(timezone.utc)

        daily_entries: list[dict] = []
        block_count = (_DAYS_IN_MONTH + _BLOCK_SIZE - 1) // _BLOCK_SIZE

        for block_idx in range(block_count):
            window = random.choice(_PUBLISH_WINDOWS)
            day_start = block_idx * _BLOCK_SIZE + 1
            day_end = min(day_start + _BLOCK_SIZE - 1, _DAYS_IN_MONTH)

            for day in range(day_start, day_end + 1):
                video_count = random.randint(_VIDEOS_PER_DAY_MIN, _VIDEOS_PER_DAY_MAX)
                daily_entries.append({
                    "day": day,
                    "date": (now + timedelta(days=day - 1)).date().isoformat(),
                    "videos": video_count,
                    "window": window,
                    "status": "pending",
                    "completed": 0,
                    "published": 0,
                })

        state.update({
            "type": "monthly",
            "category": category,
            "active": True,
            "start_date": now.isoformat(),
            "daily_plan": daily_entries,
            "current_day": 0,
            "total_produced": 0,
            "total_published": 0,
            "health": "green",
            "last_error": None,
            "current_task": "Idle",
            "current_progress": 0.0,
        })
        self._save(state)
        log.info("Monthly plan generated: %d days, %s", _DAYS_IN_MONTH, category)
        return state

    # ------------------------------------------------------------------
    # Status / health
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return a snapshot for the dashboard UI."""
        state = self._load()
        now = datetime.now(timezone.utc)

        if not state.get("active", False):
            return {
                "active": False,
                "health": state.get("health", "green"),
                "days_remaining": _DAYS_IN_MONTH,
                "total_produced": state.get("total_produced", 0),
                "total_published": state.get("total_published", 0),
                "current_task": state.get("current_task", "Idle"),
                "current_progress": 0.0,
                "current_day": state.get("current_day", 0),
                "daily_plan": state.get("daily_plan", []),
                "last_error": state.get("last_error"),
                "start_date": state.get("start_date"),
            }

        total_planned = sum(d["videos"] for d in state.get("daily_plan", []))
        days_remaining = _DAYS_IN_MONTH - state.get("current_day", 0)

        health = state.get("health", "green")
        if state.get("last_error"):
            health = "red"
        elif days_remaining <= 5:
            health = "yellow"

        return {
            "active": state.get("active", False),
            "health": health,
            "days_remaining": max(0, days_remaining),
            "total_planned": total_planned,
            "total_produced": state.get("total_produced", 0),
            "total_published": state.get("total_published", 0),
            "current_task": state.get("current_task", "Idle"),
            "current_progress": state.get("current_progress", 0.0),
            "current_day": state.get("current_day", 0),
            "daily_plan": state.get("daily_plan", []),
            "last_error": state.get("last_error"),
            "start_date": state.get("start_date"),
        }

    def estimated_api_usage(self) -> dict:
        """Rough estimate of remaining API calls."""
        state = self._load()
        remaining_videos = sum(
            d["videos"] for d in state.get("daily_plan", [])
            if d["status"] != "completed"
        )
        return {
            "gemini_calls": remaining_videos,
            "imagen_calls": remaining_videos * 3,
            "edge_tts_calls": remaining_videos * 3,
            "youtube_uploads": remaining_videos,
            "total_videos_remaining": remaining_videos,
        }

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_daily_cycle(self, category: str = "Science") -> dict:
        """Execute today's videos in the monthly plan.

        Returns a result dict with produced/published counts.
        """
        state = self._load()
        if not state.get("active", False):
            return {"error": "Monthly mode is not active."}

        now = datetime.now(timezone.utc)
        daily_plan = state.get("daily_plan", [])
        current_day = state.get("current_day", 0)

        if current_day >= len(daily_plan):
            state["active"] = False
            state["current_task"] = "Complete"
            state["health"] = "green"
            self._save(state)
            return {"error": "Monthly plan already completed."}

        entry = daily_plan[current_day]
        target = entry["videos"]
        produced = 0
        published = 0

        log.info("=" * 60)
        log.info("MONTHLY DAY %d/%d — %d video(s) at %s",
                 entry["day"], _DAYS_IN_MONTH, target, entry["window"])
        log.info("=" * 60)

        from content_planner import plan_content as _plan

        for v in range(target):
            state["current_task"] = f"Video {v + 1}/{target} — planning"
            state["current_progress"] = (v / target) * 0.2
            self._save(state)

            try:
                plan = _plan(category=category, count=1, output=_PLAN_PATH)
            except Exception as exc:
                log.error("Plan step failed: %s", exc)
                state["last_error"] = str(exc)
                state["health"] = "yellow"
                self._save(state)
                continue

            ideas = plan.get("ideas", [])
            if not ideas:
                log.warning("No ideas — skipping video %d", v + 1)
                continue

            idea = ideas[0]
            title = idea["title"]

            state["current_task"] = f"Video {v + 1}/{target} — producing"
            state["current_progress"] = 0.3
            self._save(state)

            try:
                summary = run_pipeline(
                    topic=title, scenes=3, video_mode="slideshow",
                )
            except Exception as exc:
                log.error("Production failed for '%s': %s", title, exc)
                state["last_error"] = str(exc)
                state["health"] = "yellow"
                self._save(state)
                continue

            try:
                _save_ready(summary, idea)
            except Exception as exc:
                log.warning("Save-ready failed: %s", exc)

            produced += 1

            state["current_task"] = f"Video {v + 1}/{target} — publishing"
            state["current_progress"] = 0.7
            self._save(state)

            final_video = summary.get("final_video")
            if final_video and Path(final_video).is_file():
                from uploader import YouTubeUploader as _YT
                try:
                    uploader = _YT()
                    url = uploader.authenticate_and_upload(
                        video_path=final_video,
                        title=title,
                        description=(
                            f"{title}\n\n"
                            f"Generated by Stickman Studio\n\n"
                            f"Hook: {idea.get('hook', '')}"
                        ),
                        tags=["stickman", "education", category.lower(), title.lower()],
                        auto_publish=True,
                    )
                    published += 1
                    log.info("Published: %s", url)
                except Exception as exc:
                    log.error("Publish failed for '%s': %s", title, exc)
                    state["last_error"] = str(exc)

            if v < target - 1:
                time.sleep(30)

        entry["status"] = "completed"
        entry["completed"] = produced
        entry["published"] = published

        state["current_day"] = current_day + 1
        state["total_produced"] = state.get("total_produced", 0) + produced
        state["total_published"] = state.get("total_published", 0) + published
        state["current_task"] = f"Day {entry['day']} done"
        state["current_progress"] = 1.0
        state["last_error"] = None
        state["health"] = "green"
        self._save(state)

        log.info("Day %d complete: %d/%d produced, %d published",
                 entry["day"], produced, target, published)

        return {"day": entry["day"], "target": target,
                "produced": produced, "published": published}

    def kill(self) -> None:
        """Immediately pause all autonomous processes."""
        state = self._load()
        state["active"] = False
        state["health"] = "red"
        state["current_task"] = "KILLED by user"
        self._save(state)
        log.warning("Monthly scheduler KILLED by user.")

    def is_due(self) -> bool:
        """Check if the current day's window has arrived."""
        state = self._load()
        if not state.get("active", False):
            return False
        daily_plan = state.get("daily_plan", [])
        current_day = state.get("current_day", 0)
        if current_day >= len(daily_plan):
            return False
        entry = daily_plan[current_day]
        if entry["status"] == "completed":
            return False
        now = datetime.now(timezone.utc)
        try:
            hour, minute = map(int, entry["window"].split(":"))
            window_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return now >= window_dt
        except (ValueError, TypeError):
            return True

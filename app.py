from __future__ import annotations

import json
import logging
import queue
import sys
import threading
from pathlib import Path

import streamlit as st
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from orchestrator import run_pipeline
from content_planner import plan_content
from uploader import YouTubeUploader, upload_video, make_public
from scheduler import (
    start_batch_production, run_autonomous_cycle,
    DAILY_LIMIT, _READY_DIR, get_next_run_info,
    MonthlyScheduler, _DAYS_IN_MONTH,
)

_READY_DIR_PATH: Path = _READY_DIR

st.set_page_config(layout="wide", page_title="Stickman Studio Dashboard")

# ---------------------------------------------------------------------------
# Live-log plumbing
# ---------------------------------------------------------------------------
_log_queue: queue.Queue = queue.Queue()

# Shared state for the monthly scheduler thread (avoids st.session_state
# access from background threads, which can lose ScriptRunContext).
_monthly_status_dict: dict = {"task": "Idle", "progress": 0.0}
_monthly_stop_event = threading.Event()
"""Set this event to signal the monthly thread to stop immediately."""


class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self._q = q
        self.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s",
            datefmt="%H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put(self.format(record))
        except Exception:
            self.handleError(record)


_DONE_SENTINEL = object()
_PLAN_PATH = Path("daily_plan.json")
_PROJECTS_DIR = Path("projects")


def _load_plan() -> list[dict]:
    if _PLAN_PATH.is_file():
        try:
            data = json.loads(_PLAN_PATH.read_text(encoding="utf-8"))
            return data.get("ideas", [])
        except Exception:
            return []
    return []


def _find_projects() -> list[dict]:
    entries = []
    if not _PROJECTS_DIR.is_dir():
        return entries
    for d in sorted(_PROJECTS_DIR.iterdir()):
        if d.is_dir():
            meta = d / "manifest.json"
            final = d / "final.mp4"
            if final.is_file():
                info = {"dir": d.name, "path": str(final)}
                if meta.is_file():
                    try:
                        m = json.loads(meta.read_text(encoding="utf-8"))
                        info["topic"] = m.get("topic", d.name)
                    except Exception:
                        info["topic"] = d.name
                else:
                    info["topic"] = d.name
                entries.append(info)
    return list(reversed(entries))


def _upload_thread(
    file_path: str, title: str, description: str,
    key: str = "upload_result",
) -> None:
    """Run a YouTube upload with auto‑publish in a background thread."""
    logging.getLogger().addHandler(_QueueHandler(_log_queue))
    logging.getLogger().setLevel(logging.INFO)
    try:
        url = upload_video(
            file_path=file_path,
            title=title,
            description=description,
            tags=["stickman", "education", "stickman studio", title.lower()],
            auto_publish=True,
        )
        st.session_state[key] = ("success", url)
        logging.getLogger("stickman_studio.app").info(
            "Public link: %s", url
        )
    except Exception as exc:
        st.session_state[key] = ("error", str(exc))


def _autonomous_thread(category: str = "Science") -> None:
    """Run autonomous cycles in a loop with randomised 5-7h intervals."""
    import time as _time
    from datetime import datetime, timezone

    logging.getLogger().addHandler(_QueueHandler(_log_queue))
    logging.getLogger().setLevel(logging.INFO)
    log = logging.getLogger("stickman_studio.app")
    try:
        while st.session_state.get("autonomous_enabled", False):
            log.info("Autonomous cycle starting...")
            st.session_state.autonomous_status = "Running..."
            try:
                results = run_autonomous_cycle(
                    category=category,
                    scenes=3,
                    upload_results=True,
                    max_ideas=DAILY_LIMIT,
                    force=True,
                )
                produced = sum(1 for r in results if "error" not in r)
                st.session_state.daily_count = produced
            except Exception as cycle_err:
                log.error("Autonomous cycle failed: %s", cycle_err)
                st.session_state.autonomous_status = f"Cycle error: {cycle_err}"

            # Read the next scheduled run from persisted state
            from scheduler import get_next_run_info
            info = get_next_run_info()
            if info["hours_until_next"] is not None:
                h = info["hours_until_next"]
                st.session_state.autonomous_status = (
                    f"Idle — next run in ~{h:.1f}h"
                )
                log.info("Next cycle in ~%.1f hours (at %s)",
                         h, info["next_run_time"])
                # Sleep in short increments so we can detect disable
                slept = 0.0
                interval = 30.0  # check every 30s
                while slept < h * 3600:
                    if not st.session_state.get("autonomous_enabled", False):
                        log.info("Autonomous mode disabled during sleep.")
                        break
                    _time.sleep(interval)
                    slept += interval
            else:
                st.session_state.autonomous_status = "Idle — no schedule"
                _time.sleep(30)
    except Exception as exc:
        st.session_state.autonomous_status = f"Fatal: {exc}"
    finally:
        _log_queue.put(("__META__", _DONE_SENTINEL, {"batch": True}))


def _monthly_thread(category: str = "Science") -> None:
    """Background loop: check schedule, run daily cycle, wait for next window."""
    import time as _time

    logging.getLogger().addHandler(_QueueHandler(_log_queue))
    logging.getLogger().setLevel(logging.INFO)
    log = logging.getLogger("stickman_studio.app")

    _monthly_stop_event.clear()
    scheduler = MonthlyScheduler()

    # Generate plan on first run
    state = scheduler._load()
    if not state.get("daily_plan"):
        log.info("Generating 30-day plan for '%s'...", category)
        scheduler.generate_plan(category=category)

    try:
        while not _monthly_stop_event.is_set():
            if scheduler.is_due():
                log.info("Monthly window arrived — running daily cycle...")
                _monthly_status_dict["task"] = "Running daily cycle..."
                result = scheduler.run_daily_cycle(category=category)
                if "error" in result:
                    if "completed" in result["error"]:
                        _monthly_status_dict["task"] = "All days complete!"
                        break
                    log.warning("Cycle result: %s", result["error"])
                else:
                    _monthly_status_dict["task"] = (
                        f"Day {result['day']}: {result['produced']}/{result['target']} videos"
                    )
            else:
                info = scheduler.get_status()
                if info["days_remaining"] <= 0:
                    _monthly_status_dict["task"] = "Plan complete!"
                    break
                _monthly_status_dict["task"] = (
                    f"Awaiting window — day {info['current_day'] + 1}/{_DAYS_IN_MONTH}"
                )

            # Update progress from scheduler state
            _monthly_status_dict["progress"] = scheduler.get_status().get("current_progress", 0.0)

            # Sleep 60s between checks (check stop event every second)
            for _ in range(60):
                if _monthly_stop_event.is_set():
                    break
                _time.sleep(1)

    except Exception as exc:
        log.error("Monthly thread error: %s", exc)
        _monthly_status_dict["task"] = f"Error: {exc}"
        scheduler.kill()
    finally:
        _log_queue.put(("__META__", _DONE_SENTINEL, {"batch": True}))


def _publish_thread(video_url: str, key_suffix: str = "gallery") -> None:
    """Make a YouTube video public in a background thread."""
    logging.getLogger().addHandler(_QueueHandler(_log_queue))
    logging.getLogger().setLevel(logging.INFO)
    try:
        result = make_public(video_url)
        st.session_state[f"publish_result_{key_suffix}"] = ("success", result)
    except Exception as exc:
        st.session_state[f"publish_result_{key_suffix}"] = ("error", str(exc))


def _batch_thread() -> None:
    logging.getLogger().addHandler(_QueueHandler(_log_queue))
    logging.getLogger().setLevel(logging.INFO)
    try:
        results = start_batch_production(
            scenes=3,
            delay_seconds=15.0,
        )
        st.session_state.gallery = _find_projects()
        success = sum(1 for r in results if "error" not in r)
        st.session_state.batch_progress = (
            f"Batch done: {success}/{len(results)} succeeded"
        )
    except Exception as exc:
        st.session_state.batch_progress = f"Batch failed: {exc}"
    _log_queue.put(("__META__", _DONE_SENTINEL, {"batch": True}))


def _pipeline_thread(
    topic: str, scenes: int, video_mode: str,
    upload_to_yt: bool = False,
) -> None:
    logging.getLogger().addHandler(_QueueHandler(_log_queue))
    logging.getLogger().setLevel(logging.INFO)
    try:
        summary = run_pipeline(
            topic=topic,
            scenes=scenes,
            video_mode=video_mode,
            upload=False,
        )
        if upload_to_yt:
            final = summary.get("final_video")
            if final and Path(final).is_file():
                try:
                    uploader = YouTubeUploader()
                    url = uploader.authenticate_and_upload(
                        video_path=final,
                        title=topic,
                        description=f"Generated by Stickman Studio — {topic}",
                        auto_publish=True,
                    )
                    summary["youtube_url"] = url
                    log.info("Public link: %s", url)
                except Exception as yt_err:
                    log.error("YouTube publish failed: %s", yt_err)
        _log_queue.put(("__META__", _DONE_SENTINEL, summary))
    except Exception as exc:
        _log_queue.put(("__META__", exc, None))


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
for key in ("thread", "done", "result", "error", "logs", "plan_ideas", "gallery",
            "batch_thread", "batch_progress", "upload_result", "upload_result_gallery",
            "upload_result_ready", "autonomous_enabled", "schedule_time",
            "autonomous_status", "daily_count", "publish_result",
            "monthly_thread", "monthly_status", "monthly_active"):
    if key not in st.session_state:
        st.session_state[key] = {
            "thread": None, "done": False, "result": None,
            "error": None, "logs": [], "plan_ideas": _load_plan(),
            "gallery": _find_projects(),
            "batch_thread": None, "batch_progress": "",
            "upload_result": None, "upload_result_gallery": None,
            "upload_result_ready": None,
            "autonomous_enabled": False,
            "schedule_time": "08:00",
            "autonomous_status": "Idle",
            "daily_count": 0,
            "publish_result": None,
            "monthly_thread": None,
            "monthly_status": "Idle",
            "monthly_active": False,
        }[key]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Stickman Studio")
    st.divider()

    st.subheader("Content Planner")
    category = st.text_input("Category", placeholder="e.g., Space, Physics")
    if st.button("Generate Plan", use_container_width=True, disabled=not category):
        with st.spinner("Generating ideas..."):
            try:
                result = plan_content(category=category, count=10, output=_PLAN_PATH)
                st.session_state.plan_ideas = result.get("ideas", [])
                st.success(f"{len(st.session_state.plan_ideas)} ideas generated")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.plan_ideas:
        st.divider()
        df = pd.DataFrame(st.session_state.plan_ideas)
        display = df[["title", "category", "video_mode", "complexity_score"]].copy()
        display.columns = ["Title", "Format", "Mode", "Complexity"]
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Settings")
    video_mode = st.selectbox("Video Mode", ["animation", "slideshow"],
                              help="Animation = Veo AI (premium), Slideshow = Ken Burns (fast)")
    upload_to_yt = st.checkbox("Publish to YouTube", value=False,
                               help="Auto‑publishes as public after generation. OAuth browser tab opens on first use.")

    st.divider()
    st.subheader("Batch Production")
    batch_idle = (st.session_state.batch_thread is None
                  and st.session_state.thread is None)
    if st.button("Start Batch", use_container_width=True, type="primary",
                 disabled=not st.session_state.plan_ideas or not batch_idle):
        st.session_state.batch_thread = threading.Thread(
            target=_batch_thread, daemon=True
        )
        st.session_state.batch_thread.start()
        st.rerun()
    if st.session_state.batch_progress:
        st.caption(st.session_state.batch_progress)

    if _READY_DIR.is_dir():
        ready_count = len(list(_READY_DIR.iterdir()))
        if ready_count:
            st.caption(f"Ready to upload: {ready_count} video(s)")

    with st.expander("Help"):
        st.markdown(
            "1. Enter a **Category** and click *Generate Plan* to get viral ideas.\n"
            "2. Select an idea from the dropdown in the **Studio** tab.\n"
            "3. Click *Generate Video* to run the 4-phase pipeline.\n"
            "4. View finished videos in the **Gallery** tab.\n"
            "5. Use **Batch Production** to process all ideas automatically.\n"
            "6. Videos are **auto‑published** as public on YouTube when upload is enabled."
        )

# ---------------------------------------------------------------------------
# Trigger pipeline
# ---------------------------------------------------------------------------
idle = st.session_state.thread is None and st.session_state.batch_thread is None

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_gen, tab_gallery, tab_ready, tab_schedule, tab_monthly = st.tabs(
    ["Studio", "Gallery", "Ready to Upload", "Schedule", "Monthly"]
)

# ======================== GENERATION TAB ==============================
with tab_gen:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Select Idea")
        ideas = st.session_state.plan_ideas
        idea_titles = [i["title"] for i in ideas] if ideas else ["(no ideas — generate a plan first)"]

        selected_title = st.selectbox("Video Idea", idea_titles, disabled=not ideas)

        selected_idea = None
        if ideas and selected_title:
            for idea in ideas:
                if idea["title"] == selected_title:
                    selected_idea = idea
                    break

        if selected_idea:
            st.markdown(f"**Hook:** {selected_idea['hook']}")
            st.markdown(f"**Category:** {selected_idea['category']}  |  "
                        f"**Complexity:** {'⭐' * int(selected_idea.get('complexity_score', 1))}")
            st.markdown(f"**Mode:** {selected_idea.get('video_mode', video_mode)}")

        scenes = st.slider("Scene Count", 3, 10, 3)

        topic_for_gen = selected_title if selected_title and "(no ideas" not in selected_title else ""
        mode_for_gen = selected_idea.get("video_mode", video_mode) if selected_idea else video_mode

        gen_disabled = not topic_for_gen or not idle
        if st.button("Generate Video", type="primary", use_container_width=True,
                     disabled=gen_disabled):
            st.session_state.logs.clear()
            st.session_state.result = None
            st.session_state.error = None
            st.session_state.done = False
            st.session_state.thread = threading.Thread(
                target=_pipeline_thread,
                args=(topic_for_gen, scenes, mode_for_gen, upload_to_yt),
                daemon=True,
            )
            st.session_state.thread.start()
            st.rerun()

    # ------------------------------------------------------------------
    # Live output (right column or full width)
    # ------------------------------------------------------------------
    alive = (st.session_state.thread is not None
             and st.session_state.thread.is_alive())

    # Poll queue while thread is alive
    if alive:
        for _ in range(200):
            try:
                msg = _log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(msg, tuple) and msg[0] == "__META__":
                _, payload, result = msg
                if payload is _DONE_SENTINEL:
                    st.session_state.result = result
                    st.session_state.done = True
                    st.session_state.gallery = _find_projects()
                else:
                    st.session_state.error = str(payload)
                    st.session_state.done = True
            else:
                st.session_state.logs.append(msg)

    with col2:
        if alive or st.session_state.done:
            phase = "Starting..."
            for line in reversed(st.session_state.logs):
                for kw, label in [
                    ("phase 1", "Phase 1: Script (Gemini)"),
                    ("phase 2", "Phase 2: Images (Imagen)"),
                    ("phase 3s", "Phase 3S: Slideshow Clips"),
                    ("phase 3.5", "Phase 3.5: Narration (TTS)"),
                    ("phase 3", "Phase 3: Video"),
                    ("phase 4", "Phase 4: Assembly"),
                    ("upload", "Uploading to GCS"),
                    ("done in", "Complete!"),
                ]:
                    if kw in line.lower():
                        phase = label
                        break

            state = ("running" if not st.session_state.done
                     else "error" if st.session_state.error
                     else "complete")

            with st.status(phase, state=state, expanded=True):
                st.code("\n".join(st.session_state.logs[-80:]), language="")

                if st.session_state.done:
                    if st.session_state.error:
                        st.error(st.session_state.error)
                    elif st.session_state.result:
                        r = st.session_state.result
                        st.success(f"Done in {r.get('elapsed_seconds', 0):.1f}s")
                        final = r.get("final_video")
                        if final and Path(final).is_file():
                            st.video(str(final))
                            col_a, col_b = st.columns(2)
                            with col_a:
                                with open(final, "rb") as fh:
                                    st.download_button(
                                        "Download Video",
                                        fh,
                                        file_name=Path(final).name,
                                        mime="video/mp4",
                                    )
                            with col_b:
                                yt_result = st.session_state.upload_result
                                if yt_result and yt_result[0] == "success":
                                    st.success("Published!")
                                    st.markdown(f"[Public Link]({yt_result[1]})")
                                elif yt_result and yt_result[0] == "error":
                                    st.error(f"Publish failed: {yt_result[1]}")
                                elif st.button("Upload to YouTube",
                                               key="yt_upload_btn"):
                                    st.session_state.upload_result = None
                                    t = threading.Thread(
                                        target=_upload_thread,
                                        args=(final, r.get("topic", "Stickman Studio"),
                                              f"Generated by Stickman Studio — {r.get('topic', '')}",
                                              "upload_result"),
                                        daemon=True,
                                    )
                                    t.start()
                                    st.info("Publishing — "
                                            "check the console for OAuth flow.")
        else:
            st.info("Select an idea and click **Generate Video**.")

# ======================== GALLERY TAB ================================
with tab_gallery:
    gallery = st.session_state.gallery

    if not gallery:
        st.info("No completed projects found. Generate a video first!")
    else:
        st.subheader("Previously Generated Videos")
        labels = [f"{g['topic']}  ({g['dir']})" for g in gallery]
        selected_g = st.selectbox("Select a project", labels, key="gallery_select")

        if selected_g:
            idx = labels.index(selected_g)
            entry = gallery[idx]
            video_path = entry["path"]
            if Path(video_path).is_file():
                st.video(str(video_path))

                col_a, col_b, col_c = st.columns([1, 2, 2])
                with col_a:
                    with open(video_path, "rb") as fh:
                        st.download_button(
                            "Download",
                            fh,
                            file_name=Path(video_path).name,
                            mime="video/mp4",
                        )
                with col_b:
                    yt_res_g = st.session_state.upload_result_gallery
                    if yt_res_g and yt_res_g[0] == "success":
                        yt_url = yt_res_g[1]
                        st.success("Published!")
                        st.markdown(f"[Public Link]({yt_url})")
                    elif yt_res_g and yt_res_g[0] == "error":
                        st.error(f"Publish failed: {yt_res_g[1]}")
                    elif st.button("Publish to YouTube", key=f"yt_gallery_{entry['dir']}",
                                   type="primary"):
                        st.session_state.upload_result_gallery = None
                        t = threading.Thread(
                            target=_upload_thread,
                            args=(video_path, entry.get("topic", "Stickman Studio"),
                                  f"Generated by Stickman Studio — {entry.get('topic', '')}",
                                  "upload_result_gallery"),
                            daemon=True,
                        )
                        t.start()
                        st.info("Publishing — check the console for OAuth flow.")
            else:
                st.warning("Video file not found.")

# ======================== READY TO UPLOAD TAB ===========================
with tab_ready:
    if not _READY_DIR_PATH.is_dir():
        st.info("No videos ready for upload. Run batch production first.")
    else:
        entries = sorted(_READY_DIR_PATH.iterdir())
        ready_items = []
        for d in entries:
            if d.is_dir():
                meta_file = d / "metadata.json"
                video_file = d / "final.mp4"
                if video_file.is_file() and meta_file.is_file():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        meta = {"title": d.name}
                    ready_items.append((d.name, meta, video_file))

        if not ready_items:
            st.info("No videos ready for upload.")
        else:
            for name, meta, vp in ready_items:
                with st.container(border=True):
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.video(str(vp))
                    with c2:
                        st.subheader(meta.get("title", name))
                        st.markdown(f"**Hook:** {meta.get('hook', '')}")
                        st.markdown(
                            f"**Complexity:** {'⭐' * int(meta.get('complexity_score', 1))}  |  "
                            f"**Mode:** {meta.get('video_mode', 'animation')}"
                        )
                        yt_res_r = st.session_state.upload_result_ready
                        if yt_res_r and yt_res_r[0] == "success":
                            st.success("Published!")
                            st.markdown(f"[Public Link]({yt_res_r[1]})")
                        elif yt_res_r and yt_res_r[0] == "error":
                            st.error(f"Publish failed: {yt_res_r[1]}")
                        elif st.button("Publish to YouTube", key=f"yt_ready_{name}"):
                            st.session_state.upload_result_ready = None
                            desc = (
                                f"{meta.get('title', name)}\n\n"
                                f"Generated by Stickman Studio\n\n"
                                f"Hook: {meta.get('hook', '')}"
                            )
                            t = threading.Thread(
                                target=_upload_thread,
                                args=(str(vp), meta.get("title", name), desc,
                                      "upload_result_ready"),
                                daemon=True,
                            )
                            t.start()
                            st.info("Publishing — check the console for OAuth flow.")

# ======================== SCHEDULE TAB ==================================
with tab_schedule:
    st.subheader("Autonomous Production Scheduler")
    st.caption(
        "Cycles run on a randomised **5–7 hour** interval. Each cycle "
        "generates a content plan, produces up to **5 videos** (slideshow "
        "mode), **auto‑publishes** them as public on YouTube, then "
        "persists the next run time — so a server reboot won't reset it."
    )

    # Read next-run info from persisted state
    try:
        _next_info = get_next_run_info()
    except Exception:
        _next_info = {
            "last_publish_time": "Never",
            "next_run_time": "Not scheduled",
            "hours_until_next": None,
            "is_due": False,
        }

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        auto_enabled = st.toggle(
            "Autonomous Mode",
            value=st.session_state.autonomous_enabled,
            help="Enable autonomous cycles with randomised 5–7h intervals.",
        )
        st.session_state.autonomous_enabled = auto_enabled

        if auto_enabled:
            category_auto = st.text_input(
                "Category",
                value="Science",
                placeholder="e.g., Science, Physics",
                help="Topic category for content planning.",
            )

            if st.button("Start Cycle Now", type="primary", disabled=not idle):
                st.session_state.autonomous_status = "Starting..."
                t = threading.Thread(
                    target=_autonomous_thread,
                    args=(category_auto,),
                    daemon=True,
                )
                t.start()
                st.rerun()
        else:
            st.info("Toggle **Autonomous Mode** on to start scheduling.")

    with col_s2:
        # Next-run countdown
        _next_h = _next_info.get("hours_until_next")
        _next_time = _next_info.get("next_run_time", "Not scheduled")
        if _next_h is not None and _next_h > 0:
            st.metric("Next Run In", f"~{_next_h:.1f}h",
                      help=f"Scheduled at {_next_time}")
        elif _next_info.get("is_due"):
            st.metric("Next Run In", "Due now",
                      help="The scheduled time has passed — start a cycle.")
        else:
            st.metric("Next Run In", "Not scheduled",
                      help="Run a cycle to establish the schedule.")

        st.metric("Daily Limit", DAILY_LIMIT)
        st.metric("Status", st.session_state.autonomous_status)

        remaining = max(0, DAILY_LIMIT - st.session_state.daily_count)
        if st.session_state.daily_count > 0:
            st.progress(
                st.session_state.daily_count / DAILY_LIMIT,
                text=f"{remaining} slot(s) remaining today",
            )

        # Last published timestamp
        _last = _next_info.get("last_publish_time", "Never")
        st.caption(f"Last published: {_last}")

        if st.session_state.autonomous_status and "Idle" in st.session_state.autonomous_status:
            st.caption(f"Next update: {_next_info.get('next_run_time', 'N/A')}")

    st.divider()
    st.subheader("How It Works")
    st.markdown(
        "1. **Toggle On** Autonomous Mode.\n"
        "2. Set a **Category** and click **Start Cycle Now**.\n"
        "3. The system runs one full cycle (plan → produce → upload) "
        "and then schedules the **next** cycle **5–7 hours later**.\n"
        "4. The schedule is saved to ``scheduler_state.json`` — it "
        "survives server restarts.\n"
        "5. The countdown updates in real time under **Next Run In**.\n"
        f"6. Max **{DAILY_LIMIT} videos/cycle** to protect API credits."
    )

# ======================== MONTHLY TAB ==================================
_monthly_sched = MonthlyScheduler()
_monthly_info = _monthly_sched.get_status()

with tab_monthly:
    st.subheader("30-Day Autonomous Production")
    st.caption(
        "Produces 1-3 videos daily with randomised publishing windows "
        "(5-day blocks). Persists progress across restarts. "
        "Runs fully autonomously once started."
    )

    # Determine if the monthly thread is alive
    _monthly_thread_alive = (st.session_state.monthly_thread is not None
                             and st.session_state.monthly_thread.is_alive())

    # System Health
    health = _monthly_info.get("health", "green")
    health_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    cols_health = st.columns([1, 3, 2])
    with cols_health[0]:
        st.metric("System Health",
                  f"{health_emoji.get(health, '⚪')} {health.upper()}")
    with cols_health[1]:
        status_text = _monthly_status_dict.get("task",
                        st.session_state.monthly_status)
        st.metric("Status", status_text)
    with cols_health[2]:
        if st.button("KILL SWITCH", type="primary", use_container_width=True,
                     disabled=not _monthly_thread_alive):
            _monthly_sched.kill()
            _monthly_stop_event.set()
            st.session_state.monthly_status = "KILLED"
            _monthly_status_dict["task"] = "KILLED"
            st.rerun()

    # Monthly Overview
    st.subheader("Monthly Overview")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Days Remaining",
                  _monthly_info.get("days_remaining", _DAYS_IN_MONTH))
    with c2:
        st.metric("Videos Produced",
                  _monthly_info.get("total_produced", 0))
    with c3:
        st.metric("Videos Published",
                  _monthly_info.get("total_published", 0))
    with c4:
        st.metric("Planned Total",
                  _monthly_info.get("total_planned", 0))

    # Estimated API Usage
    api_est = _monthly_sched.estimated_api_usage()
    st.subheader("Estimated API Usage (Remaining)")
    c_api1, c_api2, c_api3, c_api4 = st.columns(4)
    with c_api1:
        st.metric("Gemini Calls", api_est.get("gemini_calls", 0))
    with c_api2:
        st.metric("Imagen Calls", api_est.get("imagen_calls", 0))
    with c_api3:
        st.metric("TTS Calls (local)", api_est.get("edge_tts_calls", 0))
    with c_api4:
        st.metric("YouTube Uploads", api_est.get("youtube_uploads", 0))

    # Progress bar for current task
    prog = _monthly_status_dict.get("progress",
             _monthly_info.get("current_progress", 0.0))
    task = _monthly_status_dict.get("task",
             _monthly_info.get("current_task", "Idle"))
    st.progress(prog, text=task)

    # Start / controls
    col_start, col_dummy = st.columns([1, 3])
    with col_start:
        if st.button("Start Monthly Plan", type="primary",
                     disabled=_monthly_thread_alive, use_container_width=True):
            _monthly_stop_event.clear()
            _monthly_status_dict["task"] = "Starting..."
            _monthly_status_dict["progress"] = 0.0
            st.session_state.monthly_status = "Starting..."
            st.session_state.monthly_thread = threading.Thread(
                target=_monthly_thread,
                args=("Science",),
                daemon=True,
            )
            st.session_state.monthly_thread.start()
            st.rerun()

    if _monthly_thread_alive:
        st.info("Monthly plan is running in the background.")

    # Daily plan table
    st.subheader("Daily Plan")
    plan_entries = _monthly_info.get("daily_plan", [])
    if plan_entries:
        df_plan = [
            {
                "Day": e["day"],
                "Date": e["date"],
                "Videos": e["videos"],
                "Window": e["window"],
                "Status": e["status"],
                "Completed": e["completed"],
                "Published": e["published"],
            }
            for e in plan_entries
        ]
        st.dataframe(df_plan, use_container_width=True, hide_index=True)
    else:
        st.info("No plan generated yet. Click **Start Monthly Plan**.")

    # System Logs
    with st.expander("System Logs", expanded=False):
        st.caption("Latest backend output from the current session.")
        log_text = "\n".join(st.session_state.logs[-100:]) if st.session_state.logs else "No logs yet."
        st.code(log_text, language="", line_numbers=True)

# ---------------------------------------------------------------------------
# Cleanup + polling
# ---------------------------------------------------------------------------
if st.session_state.done and st.session_state.thread is not None:
    st.session_state.thread = None

if alive and not st.session_state.done:
    st.rerun()

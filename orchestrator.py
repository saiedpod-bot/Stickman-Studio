"""
orchestrator.py  --  Main entry point
======================================
Reads .env configuration, delegates to storage.py for GCS operations,
ai_engine.py for Vertex AI model calls, and tts_engine.py for narration.

Pipeline: Gemini script -> Imagen images -> [Veo videos] -> TTS audio -> assembly

Usage:
    python orchestrator.py "How gravity works" --scenes 5 --upload

Programmatic usage:
    from orchestrator import run_pipeline
    summary = run_pipeline("How gravity works", scenes=3, video_mode="slideshow")
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import click

from stickman_studio.config import settings, init_vertex
from stickman_studio.logging_setup import configure_logging
from stickman_studio.models import slugify, StoryBoard

import ai_engine
from storage import StorageManager
from tts_engine import TTSEngine
from uploader import YouTubeUploader

log = logging.getLogger("stickman_studio.orchestrator")


def run_pipeline(
    topic: str,
    scenes: Optional[int] = None,
    video_mode: str = "slideshow",
    no_video: bool = False,
    no_audio: bool = False,
    upload: bool = False,
    bucket: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Execute the full pipeline and return a summary dict.

    Local caching: if an output file already exists on disk the
    corresponding API call is skipped.  This makes re-runs on the same
    project directory nearly free.

    Caller is responsible for logging configuration and Vertex AI init.
    This function does **not** call ``sys.exit`` on failure; it raises.
    """
    import json as _json

    root = Path(project_dir) if project_dir else Path.cwd() / "projects"
    slug = slugify(topic)
    out = root / slug
    out.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("Stickman Studio - %s", topic)
    log.info("Output: %s", out.resolve())
    log.info("Scenes: %s | Video: %s | Audio: %s | Mode: %s",
             scenes or settings.scene_count, not no_video, not no_audio, video_mode)
    log.info("=" * 60)

    start = time.time()

    # ------------------------------------------------------------------ #
    # Phase 1 — Script (Gemini) — cached via storyboard.json
    # ------------------------------------------------------------------ #
    sb_path = out / "storyboard.json"
    if sb_path.is_file():
        log.info("-- Phase 1: Script (cached — loading %s) --", sb_path.name)
        board = StoryBoard.load(sb_path)
        log.info("  Loaded %d scenes from cache", len(board.scenes))
    else:
        init_vertex()
        log.info("-- Phase 1: Script (Gemini) --")
        board = ai_engine.generate_script(topic, out, scenes)

    # ------------------------------------------------------------------ #
    # Phase 2 — Images (Imagen) — cached per-scene
    # ------------------------------------------------------------------ #
    all_images_cached = all(
        s.image_path and Path(s.image_path).is_file()
        for s in board.scenes
    )
    if all_images_cached:
        log.info("-- Phase 2: Images (all %d cached) --", len(board.scenes))
    else:
        init_vertex()
        log.info("-- Phase 2: Images (Imagen) --")
        board = ai_engine.generate_images(board, out)

    # ------------------------------------------------------------------ #
    # Phase 3 — Audio (TTS) — cached per-scene
    # ------------------------------------------------------------------ #
    audio_paths: list[Path] | None = None
    audio_dir = out / "audio"

    if not no_audio:
        cached_audio_paths: list[Path] = []
        all_audio_cached = True
        for i, scene in enumerate(board.scenes):
            p = audio_dir / f"scene_{i:02d}.mp3"
            if p.is_file():
                cached_audio_paths.append(p)
            else:
                all_audio_cached = False
                break

        if all_audio_cached and cached_audio_paths:
            log.info("-- Phase 3.5: Narration Audio (all %d cached) --",
                     len(cached_audio_paths))
            audio_paths = cached_audio_paths
        else:
            log.info("-- Phase 3.5: Narration Audio (TTS) --")
            tts = TTSEngine()
            audio_paths = tts.generate_per_scene_audio(board.scenes, audio_dir)
    else:
        log.info("-- Phase 3.5: Narration Audio (skipped) --")

    # ------------------------------------------------------------------ #
    # Phase 3b — Slideshow clips (Ken Burns) — cached per-scene
    # ------------------------------------------------------------------ #
    if video_mode == "slideshow" and audio_paths:
        all_slides_cached = all(
            s.video_path and Path(s.video_path).is_file()
            for s in board.scenes
        )
        if all_slides_cached:
            log.info("-- Phase 3S: Slideshow Clips (all %d cached) --",
                     len(board.scenes))
        else:
            log.info("-- Phase 3S: Slideshow Clips (Ken Burns) --")
            board = ai_engine.generate_slideshow(board, out, audio_paths)
    elif video_mode == "slideshow" and not audio_paths:
        log.info("-- Phase 3S: Slideshow Clips (skipped — no audio) --")

    # ------------------------------------------------------------------ #
    # Phase 3a — Veo video (only when mode == "animation")
    # ------------------------------------------------------------------ #
    if not no_video and video_mode == "animation":
        all_video_cached = all(
            s.video_path and Path(s.video_path).is_file()
            for s in board.scenes
        )
        if all_video_cached:
            log.info("-- Phase 3: Videos (all %d cached) --", len(board.scenes))
        else:
            init_vertex()
            log.info("-- Phase 3: Videos (Veo) --")
            board = ai_engine.generate_videos(board, out)
    elif video_mode == "slideshow":
        log.info("-- Phase 3: Videos (Veo skipped — slideshow mode) --")
    else:
        log.info("-- Phase 3: Videos (skipped --no-video) --")

    # ------------------------------------------------------------------ #
    # Phase 4 — Assembly — cached via final.mp4 + manifest
    # ------------------------------------------------------------------ #
    final_path = out / "final.mp4"
    manifest_path = out / "manifest.json"
    if final_path.is_file() and manifest_path.is_file():
        log.info("-- Phase 4: Assembly (cached — final.mp4 exists) --")
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            summary = {
                "project_dir": str(out),
                "manifest": str(manifest_path),
                "final_video": str(final_path),
                "scene_count": len(board.scenes),
                "images": sum(1 for s in board.scenes if s.image_path),
                "videos": sum(1 for s in board.scenes if s.video_path),
                "audio_tracks": len(audio_paths) if audio_paths else 0,
                "_cached": True,
            }
        except Exception:
            log.info("  Cache invalid — re-assembling...")
            summary = ai_engine.assemble_project(board, out, audio_paths)
    else:
        log.info("-- Phase 4: Assembly --")
        summary = ai_engine.assemble_project(board, out, audio_paths)

    elapsed = time.time() - start
    log.info("-" * 60)
    log.info("Done in %.1f seconds%s", elapsed,
             " (fully cached)" if summary.get("_cached") else "")
    for k, v in summary.items():
        if k == "_cached":
            continue
        log.info("  %s: %s", k, v)
    summary["elapsed_seconds"] = elapsed

    if upload:
        _upload_to_gcs(out, bucket)

    return summary


@click.command(context_settings={"max_content_width": 100})
@click.argument("topic", required=True)
@click.option("--scenes", "-s", default=None, type=int,
              help="Number of scenes (default: .env SCENE_COUNT)")
@click.option("--video-mode", "-vm", default="slideshow",
              type=click.Choice(["animation", "slideshow"], case_sensitive=False),
              help="'slideshow' (default, Ken Burns zoom) or 'animation' (Veo AI video)")
@click.option("--no-video", is_flag=True, default=False,
              help="Skip Veo video generation (images only)")
@click.option("--no-audio", is_flag=True, default=False,
              help="Skip TTS narration audio")
@click.option("--upload", "-u", is_flag=True, default=False,
              help="Upload artifacts to GCS after completion")
@click.option("--bucket", "-b", default=None,
              help="GCS bucket (default: GCS_STAGING_BUCKET from .env)")
@click.option("--project-dir", "-d", default=None,
              help="Output directory (default: projects/<slug>)")
@click.option("--youtube", "-yt", is_flag=True, default=False,
              help="Upload final video to YouTube after generation")
@click.option("--privacy", default="private",
              type=click.Choice(["private", "unlisted", "public"], case_sensitive=False),
              help="YouTube privacy status (default: private)")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Enable DEBUG logging")
def main(
    topic: str,
    scenes: Optional[int],
    video_mode: str,
    no_video: bool,
    no_audio: bool,
    upload: bool,
    bucket: Optional[str],
    project_dir: Optional[str],
    youtube: bool,
    privacy: str,
    verbose: bool,
) -> None:
    """CLI entry point — thin wrapper over ``run_pipeline``."""
    level = "DEBUG" if verbose else settings.log_level
    configure_logging(level)
    try:
        summary = run_pipeline(
            topic=topic,
            scenes=scenes,
            video_mode=video_mode,
            no_video=no_video,
            no_audio=no_audio,
            upload=upload,
            bucket=bucket,
            project_dir=project_dir,
        )

        if youtube:
            _upload_to_youtube(summary, privacy)

    except Exception as exc:
        log.exception("Pipeline failed: %s", exc)
        sys.exit(1)


def _upload_to_youtube(summary: dict, privacy: str = "private") -> None:
    """Upload final_video to YouTube using OAuth 2.0."""
    video = summary.get("final_video")
    if not video or not Path(video).is_file():
        log.warning("No final video found; skipping YouTube upload.")
        return

    project_dir = Path(summary.get("project_dir", ""))
    manifest_path = project_dir / "manifest.json"
    title = summary.get("topic", "Stickman Studio Video")
    description = f"Generated by Stickman Studio — {title}"

    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            script = manifest.get("script", "")
            description = (
                f"{title}\n\n"
                f"Generated by Stickman Studio\n\n"
                f"{script[:2000]}"
            )
        except Exception:
            pass

    log.info("-- Uploading to YouTube --")
    try:
        uploader = YouTubeUploader()
        url = uploader.authenticate_and_upload(
            video_path=video,
            title=title,
            description=description,
            tags=["stickman", "education", "animation", title.lower()],
            privacy_status=privacy,
        )
        log.info("YouTube upload complete: %s", url)
    except Exception as exc:
        log.error("YouTube upload failed: %s", exc)


def _upload_to_gcs(project_dir: Path, bucket: Optional[str] = None) -> None:
    """Upload the entire project folder to GCS."""
    log.info("-- Uploading to GCS --")
    try:
        gcs = StorageManager(bucket)
        count = gcs.upload_directory(project_dir, prefix=project_dir.name)
        log.info("Upload complete: %d files", count)
    except Exception as exc:
        log.error("Upload failed: %s", exc)


if __name__ == "__main__":
    main()

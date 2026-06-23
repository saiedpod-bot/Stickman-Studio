"""
phase3_video.py  —  VEO
=======================
Animates each generated scene image into a short (4-5s) clip using Veo
image-to-video. Veo runs as a long-running operation, so we submit the
job, then poll until completion with backoff.

Uses the unified google-genai SDK pointed at the Vertex AI backend.

Output: MP4 files in projects/<slug>/videos/, recorded on each Scene.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ..config import settings, init_vertex
from ..models import StoryBoard
from ..retry import with_retry

log = logging.getLogger("stickman_studio.phase3")


def _client():
    """google-genai client bound to Vertex AI."""
    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )


@with_retry
def _submit(client, image_path: Path, motion_prompt: str):
    """Submit an image->video Veo job; returns a long-running operation."""
    from google.genai import types

    image = types.Image.from_file(location=str(image_path))

    config = types.GenerateVideosConfig(
        aspect_ratio="16:9",
        number_of_videos=1,
        duration_seconds=max(4, min(settings.video_seconds, 8)),
        person_generation="allow_adult",
        enhance_prompt=True,
    )
    # Stage outputs to GCS when a bucket is configured (recommended for Veo).
    if settings.gcs_staging_bucket:
        config.output_gcs_uri = f"gs://{settings.gcs_staging_bucket}/veo_out/"

    return client.models.generate_videos(
        model=settings.veo_model,
        prompt=motion_prompt,
        image=image,
        config=config,
    )


def _poll(client, operation, poll_seconds: int = 15, max_minutes: int = 10):
    """Poll a Veo long-running operation until it finishes."""
    deadline = time.time() + max_minutes * 60
    while not operation.done:
        if time.time() > deadline:
            raise TimeoutError("Veo operation timed out.")
        log.info("  Veo rendering... (polling in %ss)", poll_seconds)
        time.sleep(poll_seconds)
        operation = client.operations.get(operation)
    if getattr(operation, "error", None):
        raise RuntimeError(f"Veo operation failed: {operation.error}")
    return operation


def _save_result(operation, dest: Path, client) -> Path:
    """Persist the generated video bytes to dest (handles GCS or inline bytes)."""
    result = operation.result
    videos = getattr(result, "generated_videos", None) or []
    if not videos:
        raise RuntimeError("Veo returned no videos.")

    video = videos[0].video
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Inline bytes path
    if getattr(video, "video_bytes", None):
        dest.write_bytes(video.video_bytes)
        return dest

    # GCS URI path — download via the SDK file helper.
    uri = getattr(video, "uri", None)
    if uri:
        try:
            client.files.download(file=video)
            if getattr(video, "video_bytes", None):
                dest.write_bytes(video.video_bytes)
                return dest
        except Exception:
            pass
        # Last resort: pull straight from GCS.
        _download_gcs(uri, dest)
        return dest

    raise RuntimeError("Veo result contained neither bytes nor a URI.")


def _download_gcs(gcs_uri: str, dest: Path) -> None:
    from google.cloud import storage

    assert gcs_uri.startswith("gs://"), gcs_uri
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_path = rest.partition("/")
    client = storage.Client(project=settings.gcp_project_id)
    blob = client.bucket(bucket_name).blob(blob_path)
    blob.download_to_filename(str(dest))


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    init_vertex()
    client = _client()
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    for scene in board.scenes:
        if not scene.image_path or not Path(scene.image_path).is_file():
            log.warning("Scene %d has no image; skipping video.", scene.index)
            continue

        log.info("Phase 3 (Veo): animating scene %d/%d — %s",
                 scene.index + 1, len(board.scenes), scene.title)

        motion_prompt = (
            f"Animate this minimalist stickman scene with subtle, smooth motion. "
            f"{scene.scene_prompt}. Keep the clean black-line-on-white style; "
            f"gentle camera, simple character movement."
        )

        operation = _submit(client, Path(scene.image_path), motion_prompt)
        operation = _poll(client, operation)
        out_path = videos_dir / f"scene_{scene.index:02d}.mp4"
        _save_result(operation, out_path, client)
        scene.video_path = str(out_path)
        log.info("  saved -> %s", out_path)

    board.save(project_dir / "storyboard.json")
    log.info("Phase 3 complete: %d clips generated", len(board.scenes))
    return board

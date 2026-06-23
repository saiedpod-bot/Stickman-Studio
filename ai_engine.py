"""
ai_engine.py  --  Vertex AI model interactions
================================================
Class AIEngine provides direct access to Gemini, Imagen 3.0, and Veo 2.0.

Callers that need the full pipeline (script -> images -> video -> assembly)
should use the module-level convenience functions at the bottom of this file,
which delegate internally to AIEngine.

Usage:
    from ai_engine import AIEngine

    ai = AIEngine()
    img = ai.generate_scene_image("a stickman waving")
    img.save("scene.png")

    mp4_bytes = ai.generate_video_clip("scene.png", "waving slowly")
    Path("clip.mp4").write_bytes(mp4_bytes)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from stickman_studio.config import settings, init_vertex

log = logging.getLogger("stickman_studio.ai_engine")


# --------------------------------------------------------------------------- #
# AIEngine class
# --------------------------------------------------------------------------- #

class AIEngine:
    """Holds initialised clients for Gemini, Imagen, and Veo.

    All three clients are created lazily on first access using the model
    names and credentials from .env.
    """

    def __init__(self) -> None:
        init_vertex()
        self._gemini: Optional["GenerativeModel"] = None
        self._imagen: Optional["ImageGenerationModel"] = None
        self._veo_client: Optional["genai.Client"] = None

    # ------------------------------------------------------------------ #
    # Lazy clients
    # ------------------------------------------------------------------ #

    @property
    def gemini(self):
        if self._gemini is None:
            from vertexai.generative_models import GenerativeModel
            self._gemini = GenerativeModel(settings.gemini_model)
            log.debug("Gemini client created: %s", settings.gemini_model)
        return self._gemini

    @property
    def imagen(self):
        if self._imagen is None:
            from vertexai.preview.vision_models import ImageGenerationModel
            self._imagen = ImageGenerationModel.from_pretrained(
                settings.imagen_generate_model
            )
            log.debug("Imagen client created: %s", settings.imagen_generate_model)
        return self._imagen

    @property
    def veo_client(self):
        if self._veo_client is None:
            from google import genai
            self._veo_client = genai.Client(
                vertexai=True,
                project=settings.gcp_project_id,
                location=settings.gcp_location,
            )
            log.debug("Veo (google-genai) client created")
        return self._veo_client

    # ------------------------------------------------------------------ #
    # Image generation  (Imagen 3.0)
    # ------------------------------------------------------------------ #

    def generate_scene_image(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
    ):
        """Generate a single scene image with Imagen 3.0.

        Args:
            prompt: Text description of the desired image.
            aspect_ratio: Image aspect ratio (e.g. "16:9", "9:16", "1:1").
            negative_prompt: Things to avoid in the generated image.

        Returns:
            A ``vertexai.preview.vision_models.Image`` object.
            Call ``.save(path)`` to persist it.

        Raises:
            RuntimeError: If Imagen returns no images or the call fails.
        """
        log.info("Imagen: generating image for prompt (first 80 chars): %s...",
                 prompt[:80])

        images = self.imagen.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt or (
                "color, photorealistic, 3d render, shadows, "
                "gradients, text, watermark, clutter"
            ),
            add_watermark=False,
            safety_filter_level="block_some",
            person_generation="allow_adult",
        )

        if not images or not images[0]:
            raise RuntimeError("Imagen returned no images for the given prompt.")

        log.info("Imagen: image generated successfully")
        return images[0]

    # ------------------------------------------------------------------ #
    # Video generation  (Veo 2.0, image-as-starting-frame)
    # ------------------------------------------------------------------ #

    def generate_video_clip(
        self,
        image_uri: str | Path,
        prompt: str,
        duration_seconds: int = 5,
        aspect_ratio: str = "16:9",
        poll_interval: int = 15,
        max_wait_minutes: int = 10,
    ) -> bytes:
        """Generate a short video clip using Veo 2.0 image-to-video.

        The input image is used as the **starting frame** of the generated
        clip. The prompt describes the motion/animation that should follow.

        Args:
            image_uri: Path to the input image (local file or gs:// URI).
            prompt: Natural-language description of the desired motion.
            duration_seconds: Target clip length (4-8 seconds).
            aspect_ratio: Output video aspect ratio.
            poll_interval: Seconds between Veo status polls.
            max_wait_minutes: Maximum time to wait for Veo completion.

        Returns:
            Raw MP4 bytes of the generated video clip.

        Raises:
            FileNotFoundError: If ``image_uri`` is a local path that does
                               not exist.
            TimeoutError: If Veo does not finish within *max_wait_minutes*.
            RuntimeError: If the Veo job fails or returns no videos.
        """
        from google.genai import types

        # Resolve the input image  ---------------------------------------
        image_path = Path(image_uri)
        if image_path.is_file():
            image = types.Image.from_file(location=str(image_path))
            log.info("Veo: using local image %s", image_path.name)
        else:
            # Assume a gs:// URI or remote reference
            image = types.Image(uri=str(image_uri))
            log.info("Veo: using remote image %s", str(image_uri)[:80])

        # Build the generation config  -----------------------------------
        config = types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            number_of_videos=1,
            duration_seconds=max(4, min(duration_seconds, 8)),
            person_generation="allow_adult",
            enhance_prompt=True,
        )

        if settings.gcs_staging_bucket:
            config.output_gcs_uri = (
                f"gs://{settings.gcs_staging_bucket}/veo_out/"
            )

        # Submit the image-to-video job  ---------------------------------
        log.info("Veo: submitting video generation (prompt: %s...)", prompt[:60])
        operation = self.veo_client.models.generate_videos(
            model=settings.veo_model,
            prompt=prompt,
            image=image,          # <-- starting frame (frames mode)
            config=config,
        )

        # Poll until done ------------------------------------------------
        deadline = time.time() + max_wait_minutes * 60
        while not operation.done:
            if time.time() > deadline:
                raise TimeoutError(
                    f"Veo operation did not complete within {max_wait_minutes} minutes."
                )
            log.info("  Veo rendering... (polling in %ss)", poll_interval)
            time.sleep(poll_interval)
            operation = self.veo_client.operations.get(operation)

        if getattr(operation, "error", None):
            raise RuntimeError(f"Veo operation failed: {operation.error}")

        # Extract result bytes -------------------------------------------
        result = operation.result
        videos = getattr(result, "generated_videos", None) or []
        if not videos:
            raise RuntimeError("Veo returned no videos.")

        video = videos[0].video

        if getattr(video, "video_bytes", None):
            log.info("Veo: clip generated (inline, %d bytes)", len(video.video_bytes))
            return video.video_bytes

        # GCS path -- download through the SDK file helper
        uri = getattr(video, "uri", None)
        if uri:
            log.info("Veo: clip at %s, downloading...", uri)
            try:
                self.veo_client.files.download(file=video)
                if getattr(video, "video_bytes", None):
                    return video.video_bytes
            except Exception:
                pass
            # Fallback: direct GCS download
            return _download_gcs_bytes(uri)

        raise RuntimeError("Veo result had neither inline bytes nor a URI.")


# --------------------------------------------------------------------------- #
# Module-level convenience: raw download helper
# --------------------------------------------------------------------------- #

def _download_gcs_bytes(gcs_uri: str) -> bytes:
    """Download a GCS object and return its raw bytes."""
    from google.cloud import storage

    assert gcs_uri.startswith("gs://"), gcs_uri
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_path = rest.partition("/")
    client = storage.Client(project=settings.gcp_project_id)
    blob = client.bucket(bucket_name).blob(blob_path)
    return blob.download_as_bytes()


# --------------------------------------------------------------------------- #
# Module-level convenience: full pipeline (keeps orchestrator compatible)
# --------------------------------------------------------------------------- #

from stickman_studio.models import StoryBoard

# Re-export so ``from ai_engine import generate_script`` still works.
# These are thin wrappers over the dedicated ``stickman_studio.phases.*``
# modules; they do *not* use AIEngine internally (the phases do their own
# initialisation for now).

def generate_script(
    topic: str,
    project_dir: str | Path,
    scene_count: Optional[int] = None,
) -> StoryBoard:
    from stickman_studio.phases.phase1_script import run as _phase1
    init_vertex()
    return _phase1(topic, Path(project_dir), scene_count)


def generate_images(
    board: StoryBoard,
    project_dir: str | Path,
    use_reference: bool = True,
) -> StoryBoard:
    import os as _os
    from stickman_studio.phases.phase2_images import run as _phase2
    _os.environ["IMAGEN_USE_REFERENCE"] = "1" if use_reference else "0"
    init_vertex()
    return _phase2(board, Path(project_dir))


def generate_videos(
    board: StoryBoard,
    project_dir: str | Path,
) -> StoryBoard:
    from stickman_studio.phases.phase3_video import run as _phase3
    init_vertex()
    return _phase3(board, Path(project_dir))


def generate_slideshow(
    board: StoryBoard,
    project_dir: str | Path,
    audio_paths: list[Path],
) -> StoryBoard:
    from stickman_studio.phases.phase3_slideshow import run as _slideshow
    return _slideshow(board, Path(project_dir), audio_paths)


def add_subtitles(
    project_dir: str | Path,
) -> Path | None:
    from stickman_studio.phases.phase4_subtitles import run as _subtitles
    return _subtitles(Path(project_dir))


def assemble_project(
    board: StoryBoard,
    project_dir: str | Path,
    audio_paths: Optional[list[Path]] = None,
) -> dict:
    from stickman_studio.phases.phase4_assembly import run as _phase4
    return _phase4(board, Path(project_dir), audio_paths)


def run_pipeline(
    topic: str,
    project_dir: str | Path,
    scene_count: Optional[int] = None,
    generate_video: bool = True,
) -> dict:
    """Run the full pipeline: script -> images -> [videos] -> assembly."""
    board = generate_script(topic, project_dir, scene_count)
    board = generate_images(board, project_dir)
    if generate_video:
        board = generate_videos(board, project_dir)
    return assemble_project(board, project_dir)

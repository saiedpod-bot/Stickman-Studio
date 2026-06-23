"""
phase2_images.py  —  IMAGEN 3
=============================
Step A: generate the CHARACTER REFERENCE image from the canonical
        character prompt (imagen-3.0-generate-*) and save it locally.
Step B: for each scene, generate a scene image that is CONDITIONED on the
        character reference (imagen-3.0-capability-* subject customization)
        so the same stickman appears consistently across scenes.

If the capability model / subject-reference feature is unavailable in your
project, set IMAGEN_USE_REFERENCE=0 and it falls back to prompt-only
generation that re-states the character description in every scene.

Output: PNG files in projects/<slug>/images/, with paths recorded on
        each Scene in the StoryBoard.
"""

from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path

from ..config import settings, init_vertex
from ..models import StoryBoard
from ..retry import with_retry

log = logging.getLogger("stickman_studio.phase2")

_NEGATIVE = "color, photorealistic, 3d render, shadows, gradients, text, watermark, clutter, realistic human, detailed illustration, astronaut, robot, animal, clothing, shading"


# --------------------------------------------------------------------------- #
# Step A — character reference
# --------------------------------------------------------------------------- #
@with_retry
def _generate_reference(prompt: str):
    from vertexai.preview.vision_models import ImageGenerationModel

    model = ImageGenerationModel.from_pretrained(settings.imagen_generate_model)
    return model.generate_images(
        prompt=prompt,
        number_of_images=1,
        aspect_ratio="16:9",
        negative_prompt=_NEGATIVE,
        add_watermark=False,
        safety_filter_level="block_some",
        person_generation="allow_adult",
    )


def _make_reference(board: StoryBoard, images_dir: Path) -> Path:
    log.info("Phase 2A (Imagen 3): generating character reference image")
    prompt = (
        f"{board.character_reference_prompt}. "
        "Full body, centered, T-pose-like neutral stance, "
        "minimalist stickman, clean black line art on plain white background, "
        "simple, no color, vector style, lots of negative space."
    )
    images = _generate_reference(prompt)
    ref_path = images_dir / "character_reference.png"
    images[0].save(location=str(ref_path), include_generation_parameters=False)
    log.info("Character reference saved -> %s", ref_path)
    return ref_path


# --------------------------------------------------------------------------- #
# Step B — scene images conditioned on the reference
# --------------------------------------------------------------------------- #
@with_retry
def _generate_scene_with_reference(scene_prompt: str, ref_path: Path):
    """Use Imagen 3 subject customization with the character reference."""
    from vertexai.preview.vision_models import (
        ImageGenerationModel,
        Image,
        SubjectReferenceImage,
    )

    model = ImageGenerationModel.from_pretrained(settings.imagen_capability_model)
    ref = SubjectReferenceImage(
        reference_id=1,
        image=Image.load_from_file(str(ref_path)),
        subject_description=(
            "a minimalist black line art stickman figure with a simple round head, "
            "thin stick body and limbs, no color, no shading, no clothing, no details"
        ),
        subject_type="SUBJECT_TYPE_PERSON",
    )
    full_prompt = (
        f"ACTION: The stickman figure {scene_prompt}."
        f" CONSTRAINTS: clean black line art, simple, no color, plain white background, "
        f"vector style, lots of negative space, no shading, no gradients."
    )
    return model.edit_image(
        prompt=full_prompt,
        number_of_images=1,
        reference_images=[ref],
        negative_prompt=_NEGATIVE,
    )


@with_retry
def _generate_scene_prompt_only(ref_prompt: str, scene_prompt: str):
    """Fallback: no reference image, restate character each time."""
    from vertexai.preview.vision_models import ImageGenerationModel

    model = ImageGenerationModel.from_pretrained(settings.imagen_generate_model)
    full_prompt = (
        f"{ref_prompt}. {scene_prompt}. "
        "Minimalist stickman, clean black line art on plain white background, "
        "simple, no color, vector style, lots of negative space."
    )
    return model.generate_images(
        prompt=full_prompt,
        number_of_images=1,
        aspect_ratio="16:9",
        negative_prompt=_NEGATIVE,
        add_watermark=False,
    )


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    init_vertex()
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    ref_path = _make_reference(board, images_dir)
    use_reference = os.getenv("IMAGEN_USE_REFERENCE", "1").strip() != "0"

    for scene in board.scenes:
        log.info("Phase 2B: scene %d/%d — %s",
                 scene.index + 1, len(board.scenes), scene.title)
        try:
            if use_reference:
                images = _generate_scene_with_reference(scene.scene_prompt, ref_path)
            else:
                images = _generate_scene_prompt_only(
                    board.character_reference_prompt, scene.scene_prompt
                )
        except Exception:
            log.warning("Reference-based generation failed for scene %d. "
                        "Falling back to prompt-only.\n%s",
                        scene.index, traceback.format_exc())
            images = _generate_scene_prompt_only(
                board.character_reference_prompt, scene.scene_prompt
            )

        img_path = images_dir / f"scene_{scene.index:02d}.png"
        images[0].save(location=str(img_path), include_generation_parameters=False)
        scene.image_path = str(img_path)
        log.info("  saved -> %s", img_path)

    board.save(project_dir / "storyboard.json")
    log.info("Phase 2 complete: %d scene images generated", len(board.scenes))
    return board

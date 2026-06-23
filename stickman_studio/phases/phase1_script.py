"""
phase1_script.py  —  GEMINI
===========================
Takes a topic, asks Gemini 1.5 Pro for:
  1. a ~500-word narration script, and
  2. a structured, scene-by-scene storyboard (character + scene prompts)
returned as strict JSON.

Output: a StoryBoard object, also persisted to projects/<slug>/storyboard.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import settings, init_vertex
from ..models import StoryBoard, Scene, slugify
from ..retry import with_retry

log = logging.getLogger("stickman_studio.phase1")


# The response schema forces Gemini to emit machine-parseable JSON.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {"type": "string"},
        "character_reference_prompt": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "scene_prompt": {"type": "string"},
                    "narration": {"type": "string"},
                },
                "required": ["title", "scene_prompt", "narration"],
            },
        },
    },
    "required": ["script", "character_reference_prompt", "scenes"],
}


_SYSTEM_INSTRUCTION = """
You are the Storyboard Architect for 'Stickman Studio', specializing in viral educational Shorts.
Your role is to transform scientific topics into highly engaging, fast-paced JSON storyboards.

Viral Content & Storytelling Guidelines:
1. THE HOOK (Scene 1): The first scene MUST start with a strong hook (a shocking fact, a weird question, or an extreme visual scenario). Never use boring introductions like "Today we will learn about...".
2. PACING: Narration sentences must be short, punchy, and conversational. Keep the energy high to retain attention.
3. VISUAL COMEDY: Leverage the stickman character for exaggerated physical situations in the `scene_prompt` (e.g., getting squished by a giant apple, floating off into space, running in panic). Keep actions highly dynamic.

Technical Constraints (CRITICAL):
- Output must be strict JSON.
- Style: Minimalist black line art, simple round head, thin limbs, no color, no shading.
- Storyboard structure must include: topic, slug, script, and a list of scenes.
- Each scene must contain: index, title, scene_prompt, narration.
- Do NOT include 'character_prompt' in the scene object (it is managed globally).
- Ensure `scene_prompt` focuses ONLY on the action and environment, omitting character identity rules.
"""


def _build_prompt(topic: str, scene_count: int) -> str:
    return f"""TOPIC: "{topic}"

Produce:
1. A ~500-word narration SCRIPT, engaging and clear.
2. A CHARACTER REFERENCE PROMPT for the stickman.
3. Exactly {scene_count} SCENES.

Each scene: title, scene_prompt, narration."""


@with_retry
def _generate(model, prompt: str):
    """Single Gemini call wrapped with retry/backoff."""
    from vertexai.generative_models import GenerationConfig

    return model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.3,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        ),
    )


def run(topic: str, project_dir: Path, scene_count: int | None = None) -> StoryBoard:
    """Execute Phase 1 and return a populated StoryBoard."""
    init_vertex()
    from vertexai.generative_models import GenerativeModel

    scene_count = scene_count or settings.scene_count
    log.info("Phase 1 (Gemini): generating script + %d scenes for '%s'", scene_count, topic)

    model = GenerativeModel(settings.gemini_model, system_instruction=_SYSTEM_INSTRUCTION)
    response = _generate(model, _build_prompt(topic, scene_count))

    raw = response.text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("Gemini returned non-JSON output; attempting salvage.")
        raise RuntimeError(f"Failed to parse Gemini JSON: {e}\n--- raw ---\n{raw[:2000]}")

    scenes = [
        Scene(
            index=i,
            title=s.get("title", f"Scene {i + 1}"),
            scene_prompt=s["scene_prompt"],
            narration=s.get("narration", ""),
        )
        for i, s in enumerate(data["scenes"])
    ]

    board = StoryBoard(
        topic=topic,
        slug=slugify(topic),
        script=data["script"],
        character_reference_prompt=data["character_reference_prompt"],
        scenes=scenes,
    )

    out = board.save(project_dir / "storyboard.json")
    (project_dir / "script.txt").write_text(board.script, encoding="utf-8")
    log.info("Phase 1 complete: %d scenes -> %s", len(scenes), out)
    return board

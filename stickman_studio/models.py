"""
models.py
=========
Typed data structures shared across phases plus (de)serialization
helpers for the scene JSON contract produced in Phase 1.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path


def slugify(text: str) -> str:
    """Filesystem-safe slug used for project folder names."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "untitled"


@dataclass
class Scene:
    index: int
    title: str
    scene_prompt: str       # describes the action/background for this scene
    narration: str = ""     # the script line(s) spoken over this scene

    # Populated as the pipeline progresses
    image_path: str | None = None
    video_path: str | None = None


@dataclass
class StoryBoard:
    topic: str
    slug: str
    script: str                      # full ~500-word script
    character_reference_prompt: str  # canonical character description
    scenes: list[Scene] = field(default_factory=list)

    # ---- serialization -------------------------------------------------
    def to_json(self) -> str:
        payload = {
            "topic": self.topic,
            "slug": self.slug,
            "script": self.script,
            "character_reference_prompt": self.character_reference_prompt,
            "scenes": [asdict(s) for s in self.scenes],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "StoryBoard":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        scenes = [Scene(**s) for s in data.get("scenes", [])]
        return cls(
            topic=data["topic"],
            slug=data["slug"],
            script=data.get("script", ""),
            character_reference_prompt=data["character_reference_prompt"],
            scenes=scenes,
        )

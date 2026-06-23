"""
tts_engine.py  --  Edge-TTS narration (free, local, no cloud cost)
==================================================================
Generates MP3 narration audio from scene text using the ``edge-tts``
library (Microsoft Edge TTS engine — runs fully locally).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("stickman_studio.tts")

_DEFAULT_VOICE = "en-US-JennyNeural"


class TTSEngine:
    """Generates narration audio using Edge-TTS (local, free).

    Uses Microsoft Edge's neural TTS voices. No cloud API calls needed.
    """

    def __init__(
        self,
        voice: str = _DEFAULT_VOICE,
    ) -> None:
        self._voice = voice

    def synthesize_speech(self, text: str, output_path: str | Path) -> Path:
        """Synthesise text into an MP3 file via edge-tts.

        Args:
            text: The text to speak.
            output_path: Where to write the MP3 file.

        Returns:
            The output Path.
        """
        import edge_tts

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        async def _do() -> None:
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(str(output))

        asyncio.run(_do())

        size = output.stat().st_size
        log.info("TTS: %d bytes -> %s  (voice=%s)", size, output, self._voice)
        return output

    def generate_per_scene_audio(
        self,
        scenes: list,
        output_dir: str | Path,
    ) -> list[Path]:
        """Generate one MP3 per scene from its narration text.

        Args:
            scenes: Iterable of objects with a ``narration`` attribute.
            output_dir: Directory to write MP3 files into.

        Returns:
            List of Paths to the generated audio files, one per scene.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for i, scene in enumerate(scenes):
            text = (scene.narration or "").strip()
            if not text:
                log.warning("Scene %d has no narration; skipping audio.", i)
                continue
            path = out_dir / f"scene_{i:02d}.mp3"
            self.synthesize_speech(text, path)
            paths.append(path)

        log.info("TTS: generated %d audio file(s)", len(paths))
        return paths

    def generate_script_audio(
        self,
        script_text: str,
        output_path: str | Path,
    ) -> Path:
        """Generate a single audio file from the full script text."""
        return self.synthesize_speech(script_text, output_path)

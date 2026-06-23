"""
phase4_subtitles.py  --  SUBTITLES
====================================
Reads storyboard.json scene metadata, uses moviepy to burn
lower-thirds subtitles onto final.mp4, and writes
final_with_subtitles.mp4.

Requirements:
  - moviepy >= 2.0 (PIL-based TextClip, no ImageMagick needed)
  - Arial font at C:\Windows\Fonts\arial.ttf
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from moviepy import VideoFileClip, TextClip, CompositeVideoClip

log = logging.getLogger("stickman_studio.subtitles")

_FONT = "C:\\Windows\\Fonts\\arial.ttf"
_FONT_SIZE = 28
_STROKE_WIDTH = 2
_SHADOW_OFFSET = 2
_MARGIN_BOTTOM = 30
_MAX_CHARS_PER_LINE = 40


def _wrap_text(text: str) -> str:
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > _MAX_CHARS_PER_LINE and current:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += len(word) + 1
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _make_subtitle_clip(
    text: str,
    video_w: int,
    video_h: int,
    start: float,
    duration: float,
) -> list[TextClip]:
    wrapped = _wrap_text(text[0].upper() + text[1:] if text else "")

    main = TextClip(
        text=wrapped,
        font=_FONT,
        font_size=_FONT_SIZE,
        color="white",
        stroke_color="black",
        stroke_width=_STROKE_WIDTH,
        method="label",
    )
    tw, th = main.size
    cx = (video_w - tw) // 2
    cy = video_h - th - _MARGIN_BOTTOM

    shadow = TextClip(
        text=wrapped,
        font=_FONT,
        font_size=_FONT_SIZE,
        color="black",
        stroke_color="black",
        stroke_width=_STROKE_WIDTH,
        method="label",
    )
    shadow = (
        shadow
        .with_position((cx + _SHADOW_OFFSET, cy + _SHADOW_OFFSET))
        .with_start(start)
        .with_duration(duration)
        .with_opacity(0.5)
    )

    main = (
        main
        .with_position((cx, cy))
        .with_start(start)
        .with_duration(duration)
    )
    return [shadow, main]


def run(project_dir: Path) -> Path | None:
    """Add lower-thirds subtitles to final.mp4.

    Args:
        project_dir: Output directory containing ``storyboard.json``
                     and ``final.mp4``.

    Returns:
        Path to ``final_with_subtitles.mp4``, or ``None`` on failure.
    """
    sb_path = project_dir / "storyboard.json"
    video_path = project_dir / "final.mp4"

    if not sb_path.is_file():
        log.error("storyboard.json not found at %s", sb_path)
        return None
    if not video_path.is_file():
        log.error("final.mp4 not found at %s", video_path)
        return None

    board = json.loads(sb_path.read_text(encoding="utf-8"))
    scenes = board.get("scenes", [])
    if not scenes:
        log.warning("No scenes found in storyboard; skipping subtitles.")
        return None

    video = VideoFileClip(str(video_path))
    log.info("Loaded video: %.1fs, %dx%d", video.duration, *video.size)
    video_w, video_h = video.size
    n = len(scenes)
    scene_duration = video.duration / n

    all_clips: list = [video]
    for i, scene in enumerate(scenes):
        title = scene.get("title", f"Scene {i + 1}")
        all_clips.extend(
            _make_subtitle_clip(
                title, video_w, video_h,
                start=i * scene_duration,
                duration=scene_duration,
            )
        )

    log.info("Compositing %d subtitle clip(s) over video", len(all_clips) - 1)
    final = CompositeVideoClip(all_clips)

    output_path = project_dir / "final_with_subtitles.mp4"
    log.info("Writing %s ...", output_path)
    final.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(project_dir / "_sub_temp.m4a"),
        remove_temp=True,
        logger=None,
    )

    video.close()
    final.close()

    log.info("Subtitles added -> %s", output_path)
    return output_path

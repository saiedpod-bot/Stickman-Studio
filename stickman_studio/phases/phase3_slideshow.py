from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from ..models import StoryBoard

log = logging.getLogger("stickman_studio.phase3_slideshow")

_FFMPEG: str | None = None


def _ffmpeg() -> str:
    global _FFMPEG
    if _FFMPEG is None:
        resolved = shutil.which("ffmpeg")
        if not resolved:
            resolved = r"E:\Auto YOUTUBE By ARABIAN AI SCHOOLt\ffmpeg\ffmpeg.exe"
            if not Path(resolved).is_file():
                resolved = None
        _FFMPEG = resolved
    return _FFMPEG


def _probe_duration(audio_path: Path) -> float:
    ffprobe = shutil.which("ffprobe") or str(Path(_ffmpeg()).parent / "ffprobe.exe")
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
        return float(out) if out else 0.0
    except (ValueError, TypeError):
        return 0.0


def _ken_burns_clip(image_path: Path, duration: float, output_path: Path) -> Path:
    ffmpeg = _ffmpeg()
    fps = 24
    nframes = max(1, int(duration * fps))
    zoom_inc = 0.1 / nframes
    output_path.parent.mkdir(parents=True, exist_ok=True)

    expr = f"z='min(if(eq(on,1),1,zoom+{zoom_inc}),1.1)':d={nframes}:s=1280x720:fps={fps}"
    cmd = [
        ffmpeg, "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", f"scale=1280:720,setsar=1,zoompan={expr}",
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    log.debug("Ken Burns: %s", " ".join(cmd[:6]) + " ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Ken Burns clip failed: {proc.stderr[-500:]}")
    return output_path


def run(
    board: StoryBoard,
    project_dir: Path,
    audio_paths: list[Path],
) -> StoryBoard:
    """Generate slideshow video clips with Ken Burns zoom for each scene.

    Each clip duration is set to match the corresponding TTS audio track.
    Output MP4 files are placed in ``project_dir / "videos"``, and
    ``scene.video_path`` is set on every scene (same contract as phase3_video).
    """
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(board.scenes):
        if not scene.image_path or not Path(scene.image_path).is_file():
            log.warning("Scene %d has no image; skipping slideshow clip.", scene.index)
            continue

        audio = audio_paths[i] if i < len(audio_paths) else None
        duration = _probe_duration(audio) if audio else 5.0
        if duration <= 0:
            duration = 5.0

        out_path = videos_dir / f"scene_{scene.index:02d}.mp4"
        log.info("Slideshow scene %d/%d — %s (%.1fs, Ken Burns zoom)",
                 scene.index + 1, len(board.scenes), scene.title, duration)

        _ken_burns_clip(Path(scene.image_path), duration, out_path)
        scene.video_path = str(out_path)

    board.save(project_dir / "storyboard.json")
    log.info("Slideshow complete: %d clips generated", len(board.scenes))
    return board

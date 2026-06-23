"""
phase4_assembly.py  --  ASSEMBLY
===============================
Finalizes the project under projects/<slug>/:
  - writes a manifest.json summarizing every artifact
  - concatenates per-scene video clips into a single clip
  - overlays narration audio (TTS) onto the final video
  - produces final.mp4 with audio
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ..models import StoryBoard

log = logging.getLogger("stickman_studio.phase4")

_FFMPEG: str | None = None
_BGM_PATH: Path = Path("assets/bgm.mp3")


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


def _probe_duration(path: Path) -> float:
    ff = _ffmpeg()
    if not ff:
        return 0.0
    probe = shutil.which("ffprobe") or str(Path(ff).parent / "ffprobe.exe")
    cmd = [probe, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
        return float(out) if out else 0.0
    except (ValueError, TypeError):
        return 0.0


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #

def _write_manifest(board: StoryBoard, project_dir: Path) -> Path:
    manifest = {
        "topic": board.topic,
        "slug": board.slug,
        "script_file": "script.txt",
        "storyboard_file": "storyboard.json",
        "character_reference": "images/character_reference.png",
        "scenes": [
            {
                "index": s.index,
                "title": s.title,
                "narration": s.narration,
                "image": Path(s.image_path).name if s.image_path else None,
                "video": Path(s.video_path).name if s.video_path else None,
            }
            for s in board.scenes
        ],
    }
    path = project_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Video concatenation
# --------------------------------------------------------------------------- #

def _concat_videos(board: StoryBoard, project_dir: Path) -> Path | None:
    """Concatenate scene clips into a temp file (no audio yet)."""
    ffmpeg = _ffmpeg()
    clips = [
        s.video_path for s in board.scenes
        if s.video_path and Path(s.video_path).is_file()
    ]
    if not clips:
        log.warning("No video clips to assemble.")
        return None
    if not ffmpeg:
        log.warning("ffmpeg not found; skipping concatenation.")
        return None

    list_file = project_dir / "videos" / "_concat.txt"
    list_file.write_text(
        "".join(f"file '{Path(c).resolve()}'\n" for c in clips), encoding="utf-8"
    )
    raw = project_dir / "videos" / "_concat_raw.mp4"
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_file), "-c", "copy", str(raw)]
    log.info("Concatenating %d clips -> %s", len(clips), raw)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("ffmpeg concat failed: %s", proc.stderr[-1000:])
        return None
    return raw


# --------------------------------------------------------------------------- #
# Audio overlay
# --------------------------------------------------------------------------- #

def _overlay_audio(
    video_path: Path,
    audio_paths: list[Path],
    output_path: Path,
    bgm_path: Path | None = None,
) -> Path | None:
    """Overlay concatenated narration audio + optional BGM onto the video.

    If multiple TTS audio files are provided they are concatenated first
    into a temporary mix, then overlaid together with an optional background
    music track (looped, ducked to 10 % volume, with 2 s fade-out).
    """
    ffmpeg = _ffmpeg()
    if not ffmpeg or not audio_paths:
        return None

    # Concatenate all TTS files into one track
    if len(audio_paths) == 1:
        merged_audio = audio_paths[0]
    else:
        audio_list = video_path.parent / "_audio_concat.txt"
        audio_list.write_text(
            "".join(f"file '{p.resolve()}'\n" for p in audio_paths),
            encoding="utf-8",
        )
        merged_audio = video_path.parent / "_audio_merged.mp3"
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0",
               "-i", str(audio_list), "-c", "copy", str(merged_audio)]
        subprocess.run(cmd, capture_output=True, text=True)

    log.info("Overlaying audio onto %s -> %s", video_path.name, output_path.name)

    # Resolve BGM: explicit path, default, or None
    bgm = bgm_path or _BGM_PATH
    if bgm and not bgm.is_file():
        bgm = None

    duration = _probe_duration(video_path)

    if bgm:
        fade = f",afade=t=out:st={max(0, duration - 2)}:d=2" if duration > 2 else ""
        filter_complex = (
            f"[1:a]volume=1.0[a1];"
            f"[2:a]volume=0.1,adelay=0|0,aloop=-1:size=44100,atrim=0:{duration}{fade}[a2];"
            f"[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[out]"
        )
        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-i", str(merged_audio),
            "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[out]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            str(output_path),
        ]
        log.info("  + BGM: %s (volume=0.1, looped, %.0fs)", bgm.name, duration)
    else:
        cmd = [
            ffmpeg, "-y",
            "-i", str(video_path),
            "-i", str(merged_audio),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_path),
        ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("Audio overlay failed: %s", proc.stderr[-1000:])
        return None
    return output_path


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

def run(
    board: StoryBoard,
    project_dir: Path,
    audio_paths: list[Path] | None = None,
) -> dict:
    """Assemble the project and optionally overlay narration audio.

    Args:
        board: Populated StoryBoard.
        project_dir: Project output directory.
        audio_paths: Optional list of MP3 files to overlay (one per scene).

    Returns:
        Summary dict with paths and counts.
    """
    _write_manifest(board, project_dir)
    raw_video = _concat_videos(board, project_dir)

    final = None
    if raw_video and audio_paths:
        final_path = project_dir / "final.mp4"
        result = _overlay_audio(raw_video, audio_paths, final_path)
        if result:
            final = result
        else:
            # Fallback: rename raw concat to final
            final = raw_video
            final.rename(project_dir / "final.mp4")
            final = project_dir / "final.mp4"
    elif raw_video:
        final = raw_video
        final.rename(project_dir / "final.mp4")
        final = project_dir / "final.mp4"

    summary = {
        "project_dir": str(project_dir),
        "manifest": str(project_dir / "manifest.json"),
        "final_video": str(final) if final else None,
        "scene_count": len(board.scenes),
        "images": sum(1 for s in board.scenes if s.image_path),
        "videos": sum(1 for s in board.scenes if s.video_path),
        "audio_tracks": len(audio_paths) if audio_paths else 0,
    }
    log.info("Phase 4 complete. Project assembled at %s", project_dir)
    return summary

# 🕴️ Stickman Studio

A Python CLI that turns a **topic** into a narrated **stickman animation** using
Google Cloud **Vertex AI** — orchestrating Gemini, Imagen 3, and Veo end-to-end.

```
Phase 1  Gemini 1.5 Pro  →  500-word script + scene-by-scene storyboard JSON
Phase 2  Imagen 3        →  character reference image, then consistent scene images
Phase 3  Veo             →  4–5s video clip per scene (image-to-video)
Phase 4  Assembly        →  manifest + optional stitched final.mp4
```

All outputs are written to `projects/<topic_slug>/`.

## Project layout

```
stickman_studio/
├── orchestrator.py            # CLI entrypoint (click)
├── requirements.txt
├── .env.example               # copy to .env and fill in
├── README.md
└── stickman_studio/
    ├── config.py              # .env loading + Vertex init (idempotent)
    ├── logging_setup.py       # console + per-run file logging
    ├── retry.py               # tenacity backoff for 429/503/500/timeouts
    ├── models.py              # Scene / StoryBoard dataclasses + JSON I/O
    └── phases/
        ├── phase1_script.py   # Gemini
        ├── phase2_images.py   # Imagen 3 (reference + scenes)
        ├── phase3_video.py    # Veo (long-running op polling)
        └── phase4_assembly.py # manifest + ffmpeg concat
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit GCP_PROJECT_ID, bucket, creds…

# Authenticate (either a service-account key in .env, or ADC):
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com
```

## Usage

```bash
# Validate config / connectivity
python orchestrator.py doctor

# Full run
python orchestrator.py run --topic "How photosynthesis works"

# Custom scene count
python orchestrator.py run --topic "Gravity" --scenes 6

# Run a subset of phases (great for iterating cheaply)
python orchestrator.py run --topic "Gravity" --until images   # stop after images
python orchestrator.py run --topic "Gravity" --from video     # reuse storyboard.json
```

## How character consistency works

1. **Phase 1** asks Gemini for a single canonical `character_reference_prompt`
   plus a per-scene `character_prompt` that restates the look.
2. **Phase 2A** renders the reference image from that canonical prompt.
3. **Phase 2B** feeds the reference into Imagen 3's **subject customization**
   (`imagen-3.0-capability-001`) so every scene keeps the same stickman.
   If the capability feature isn't enabled on your project, set
   `IMAGEN_USE_REFERENCE=0` to fall back to prompt-only generation.

## Resilience

- Every Vertex call is wrapped by `retry.with_retry`, which catches rate-limit
  (429 / `ResourceExhausted`), `503`, `500`, and deadline errors, then retries
  with **exponential backoff + jitter**. Attempts and rate-limit hits are logged.
- Veo jobs are long-running; Phase 3 polls the operation with backoff and a
  timeout, downloading from inline bytes or GCS as appropriate.

## Notes / requirements

- Veo and Imagen 3 customization are **allow-listed** features — make sure your
  project has access. Adjust model IDs in `.env` if your access differs.
- Set `GCS_STAGING_BUCKET` for Veo output staging (recommended).
- `ffmpeg` is optional; if present, Phase 4 stitches clips into `final.mp4`.
```

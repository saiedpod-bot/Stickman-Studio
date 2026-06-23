
<p align="center">
  <img src="https://img.shields.io/badge/Stickman-Studio-blue?style=for-the-badge&logo=python" alt="Stickman Studio">
  <br>
  <strong>🎬 Autonomous AI Video Production Pipeline</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#pipeline">Pipeline</a> •
  <a href="#dashboard">Dashboard</a> •
  <a href="#cost-optimization">Cost Optimization</a> •
  <a href="#youtube-automation">YouTube</a> •
  <a href="#scheduling">Scheduling</a>
</p>

<p align="center" dir="rtl">
  <strong>🇸🇦 أنتج فيديوهات رسوم متحركة تلقائيًا بالذكاء الاصطناعي وجهاً لوجه مع النشر على يوتيوب</strong>
</p>

---

## 📋 Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI Scriptwriting** | Gemini 2.5 Flash generates viral hooks + scene-by-scene storyboard |
| 🎨 **AI Image Generation** | Imagen 3.0 creates consistent stickman characters across scenes |
| 🎬 **Slideshow Mode** | Ken Burns zoom effect — **$0 cost** for video generation |
| 🎥 **Veo Mode** | Google Veo 2.0 AI video clips (premium, allow-listed) |
| 🗣️ **Free TTS** | `edge-tts` — neural voiceovers **100% free, no API key** |
| 🎵 **Background Music** | Loop + duck BGM from `assets/bgm.mp3` |
| 📝 **Subtitles** | Lower-thirds with drop-shadow via MoviePy |
| 📊 **Streamlit Dashboard** | Full GUI: generate, preview, download, publish |
| 📅 **Autonomous Scheduler** | 30-day monthly plan with randomised 5–7h intervals |
| 🚀 **YouTube Upload** | OAuth 2.0 → auto-publish as **public** |
| 💰 **Cost-Efficient** | Slideshow + edge-tts = **~$0.02/video** (Gemini + Imagen only) |
| 🔄 **Local Caching** | Re-runs skip all completed phases — 0s on cache hit |

---

## 🚀 Quick Start

```bash
# 1. Clone & setup
git clone https://github.com/saiedpod-bot/Stickman-Studio.git
cd Stickman-Studio
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install edge-tts        # free local TTS

# 3. Configure
cp .env.example .env
# Edit .env → GCP_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS

# 4. Authenticate with Google Cloud
gcloud auth application-default login

# 5. Run!
python orchestrator.py "How black holes work" --video-mode slideshow
```

### 🔐 YouTube Upload (optional)

1. Create OAuth 2.0 credentials at [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Download → save as `client_secrets.json` in project root
3. First upload opens a browser for OAuth consent
4. Token cached in `youtube_token.json`

---

## 🧠 Pipeline

```
Topic Input
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Phase 1: Script (Gemini 2.5 Flash)                 │
│  → Viral hook + scene-by-scene storyboard.json      │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Phase 2: Images (Imagen 3.0)                       │
│  → Character reference + consistent scene images    │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Phase 3: Video                                     │
│  ┌─ slideshow: ffmpeg Ken Burns zoom (FREE) ──────┐│
│  └─ animation:  Veo 2.0 image-to-video (premium)  ┘│
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Phase 3.5: Narration (edge-tts — FREE)             │
│  → Per-scene MP3 with neural voices                 │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Phase 4: Assembly (ffmpeg — local)                 │
│  → Concatenate + overlay audio + BGM → final.mp4   │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Phase 5: YouTube Upload (OAuth 2.0)                │
│  → Auto-publish as public with title, desc, tags    │
└─────────────────────────────────────────────────────┘
```

---

## 🎬 Sample Outputs

Pre-generated example videos showing the pipeline output:

| Video | Mode | Size | Description |
|-------|------|------|-------------|
| [`slideshow_how_gravity_works.mp4`](samples/slideshow_how_gravity_works.mp4) | Slideshow | 2.3 MB | 3-scene explainer on gravity with Ken Burns zoom |
| [`slideshow_how_magnets_works.mp4`](samples/slideshow_how_magnets_works.mp4) | Slideshow | 0.6 MB | 3-scene explainer on magnets with voiceover & subtitles |

All samples are in `samples/` directory. Generate your own with:

```bash
python orchestrator.py "Your topic here" --video-mode slideshow
```

---

## 📊 Dashboard

Launch the full GUI:

```bash
streamlit run app.py
```

Tabs:
| Tab | Purpose |
|-----|---------|
| **Studio** | Select an idea, generate video, preview, publish |
| **Gallery** | Browse all previously generated projects |
| **Ready to Upload** | Videos from batch production, ready for YouTube |
| **Schedule** | Autonomous mode toggle, random 5–7h intervals |
| **Monthly** | 30-day production plan with kill switch & health monitor |

### Dashboard Features
- **Live logs** — real-time pipeline output in `st.status`
- **Progress bars** — per-phase, per-video tracking
- **System Health** — 🟢 Green / 🟡 Yellow / 🔴 Red indicator
- **Kill Switch** — immediately halt all autonomous processes
- **Estimated API Usage** — remaining Gemini/Imagen calls
- **System Logs** — expandable panel with last 100 log lines

---

## 💰 Cost Optimization

| Feature | Cost | Notes |
|---------|------|-------|
| **Slideshow Mode** | **$0** | `--video-mode slideshow` — ffmpeg Ken Burns zoom |
| **edge-tts** | **$0** | Free neural TTS, no API key needed |
| **Local Caching** | **$0** | Re-runs skip completed phases entirely |
| **Gemini 2.5 Flash** | ~$0.0005/call | Script generation |
| **Imagen 3.0** | ~$0.02/image | Image generation |
| **Veo 2.0** | ~$0.05/clip | *Only when using `--video-mode animation`* |
| **YouTube Upload** | **$0** | Free via OAuth 2.0 |

**Default mode is slideshow** to minimize costs.

---

## 📅 Scheduling

### Autonomous Mode (5–7h intervals)
```bash
# Via dashboard: Schedule tab → Toggle On
```
Randomised intervals avoid YouTube pattern detection.

### Monthly Mode (30-day plan)
```bash
# Via dashboard: Monthly tab → Start Monthly Plan
```
- 1–3 videos/day, randomly assigned
- 5-day blocks with rotating publishing windows (08:00, 10:00, 14:00, 16:00, 20:00)
- Persists to `system_state.json` — survives server reboots
- Kill switch available in the UI

### Batch Production
```bash
# CLI: process all ideas in daily_plan.json
python -c "from scheduler import start_batch_production; start_batch_production()"

# Full autonomous cycle (plan → produce → upload)
python -c "from scheduler import run_autonomous_cycle; run_autonomous_cycle('Science')"
```

---

## 🏗️ Project Structure

```
stickman_studio/
├── app.py                    # Streamlit dashboard
├── orchestrator.py           # CLI + importable pipeline runner
├── content_planner.py        # Gemini → viral video ideas
├── scheduler.py              # Batch + autonomous + monthly scheduler
├── uploader.py               # YouTube OAuth 2.0 upload + auto-publish
├── tts_engine.py             # edge-tts (free local TTS)
├── storage.py                # GCS upload/download
├── ai_engine.py              # Module-level wrappers for all phases
├── requirements.txt
├── .env.example → .env       # Configuration
├── client_secrets.json       # YouTube OAuth (user-provided)
├── samples/                   # Pre-generated example videos
├── assets/
│   └── bgm.mp3               # Optional background music
├── stickman_studio/
│   ├── config.py             # .env loading + Vertex AI init
│   ├── logging_setup.py      # Console + file logging
│   ├── models.py             # Scene / StoryBoard dataclasses
│   ├── retry.py              # Tenacity retry decorator
│   └── phases/
│       ├── phase1_script.py      # Gemini storyboard
│       ├── phase2_images.py      # Imagen 3.0 images
│       ├── phase3_video.py       # Veo 2.0 video
│       ├── phase3_slideshow.py   # Ken Burns zoom
│       ├── phase4_assembly.py    # ffmpeg concat + audio
│       └── phase4_subtitles.py   # MoviePy subtitles
```

---

## 🛠️ Requirements

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Runtime |
| `google-cloud-aiplatform` | ≥1.158 | Vertex AI SDK |
| `google-genai` | ≥2.9 | Veo client |
| `edge-tts` | ≥7.2 | Free TTS |
| `streamlit` | ≥1.28 | Dashboard |
| `moviepy` | ≥2.1 | Subtitles |
| `google-api-python-client` | — | YouTube API |
| `google-auth-oauthlib` | — | YouTube OAuth |
| `ffmpeg` | ≥4.0 | Video assembly |

---

## 🔖 Topics / Hashtags

```
stickman-studio  ai-video-generation  google-vertex-ai
gemini  imagen  veo  youtube-automation  content-creator
python  streamlit  edge-tts  text-to-video
free-tts  ai-animation  video-pipeline
```

Add these to your GitHub repo → **Settings → Topics** for discoverability.

---

## 📄 License

MIT © 2026 — Free to use, modify, and distribute.

---

<p align="center">
  Made with ❤️ and 🤖<br>
  <sub>Automate your content. Own your audience.</sub>
</p>

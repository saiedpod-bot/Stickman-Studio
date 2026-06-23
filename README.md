
<p align="center">
  <img src="https://img.shields.io/badge/Stickman-Studio-blue?style=for-the-badge&logo=python" alt="Stickman Studio">
  <img src="https://img.shields.io/github/actions/workflow/status/saiedpod-bot/Stickman-Studio/ci.yml?style=for-the-badge&logo=github" alt="CI">
  <br>
  <strong>🎬 Autonomous AI Video Production Pipeline</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#-installation-guide-full">Installation Guide</a> •
  <a href="#pipeline">Pipeline</a> •
  <a href="#dashboard">Dashboard</a> •
  <a href="#cost-optimization">Cost Optimization</a> •
  <a href="#scheduling">Scheduling</a>
</p>

<p align="center">
  <strong>🤖 Automate AI-powered stickman animation production, from script to YouTube</strong>
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

## 🚀 Installation Guide (Full)

### 1. 📋 System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **OS** | Windows 10, macOS 12+, Linux (Ubuntu 20.04+) | Any 64-bit OS |
| **Python** | 3.10 | 3.11+ |
| **RAM** | 4 GB | 8 GB+ |
| **Disk Space** | 500 MB (project) + 2 GB (cached videos) | 10 GB free |
| **Internet** | Broadband (for API calls) | 10+ Mbps |
| **FFmpeg** | v4.0 | v6.0+ |

---

### 2. 🐍 Install Python

<details>
<summary><b>Windows</b></summary>

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download **Python 3.11 or 3.12**
3. **IMPORTANT**: Check ✅ **"Add Python to PATH"** during installation
4. Click **Install Now**
5. Verify:
   ```cmd
   python --version
   pip --version
   ```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
# Using Homebrew (recommended)
brew install python@3.11

# Verify
python3 --version
pip3 --version
```
</details>

<details>
<summary><b>Linux (Ubuntu/Debian)</b></summary>

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv -y
python3 --version
```
</details>

---

### 3. 🎬 Install FFmpeg

FFmpeg is required for video assembly and the slideshow effect.

<details>
<summary><b>Windows</b></summary>

1. Download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) → **ffmpeg-release-full.7z**
2. Extract to `C:\ffmpeg`
3. Add to PATH:
   - Search → **"Environment Variables"**
   - Under **System Variables** → **Path** → **Edit**
   - Add: `C:\ffmpeg\bin`
   - **OK** all windows
4. Verify:
   ```cmd
   ffmpeg -version
   ```

> **Alternative**: Install via `winget`:
> ```cmd
> winget install "FFmpeg (Essentials Build)"
> ```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install ffmpeg
ffmpeg -version
```
</details>

<details>
<summary><b>Linux</b></summary>

```bash
sudo apt install ffmpeg -y
ffmpeg -version
```
</details>

---

### 4. 📥 Clone the Repository

```bash
git clone https://github.com/saiedpod-bot/Stickman-Studio.git
cd Stickman-Studio
```

---

### 5. 🐍 Set Up Python Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate it:
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt
pip install edge-tts          # Free local TTS (neural voices)
```

---

### 6. ☁️ Google Cloud Account & Free $300 Credit

> **You need a Google Cloud account to use Gemini (AI script) and Imagen (AI images).**
> The $300 free trial gives you **90 days** of free credits — enough to produce **thousands of videos**.

1. Go to [cloud.google.com/free](https://cloud.google.com/free)
2. Click **"Get started for free"**
3. **Sign in** with your Google account (Gmail)
4. Fill in:
   - **Country**
   - **Name & address** (billing info — your card will NOT be charged, used only for verification)
   - **Credit/Debit card** (Google does a temporary $1 hold and refunds it)
5. ✅ You now have **$300 in free credits** + **90-day trial**

> ⚠️ **No charges without your consent**. The free tier also includes many always-free products. You can set budgets and alerts in the console.

---

### 7. 🏗️ Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. At the top bar, click the project dropdown → **New Project**
3. Enter project name (e.g. `stickman-studio`)
4. Note the **Project ID** (e.g. `stickman-studio-123456`) — you'll need it later
5. Click **Create**

---

### 8. 🔌 Enable Required APIs

Enable these APIs for your project:

| API | Purpose | Link |
|-----|---------|------|
| **Vertex AI API** | Gemini (scripts) + Imagen (images) | [Enable](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com) |
| **Cloud Storage** | Store generated assets (optional) | [Enable](https://console.cloud.google.com/apis/library/storage.googleapis.com) |
| **YouTube Data API v3** | Upload videos (optional) | [Enable](https://console.cloud.google.com/apis/library/youtube.googleapis.com) |

To enable each:
1. Click the **Enable** link above
2. Make sure your project is selected (top bar)
3. Click **Enable**

---

### 9. 🔑 Create a Service Account (API Key)

This is how the project authenticates with Google Cloud:

1. Go to [Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Click **+ Create Service Account**
3. Name: `stickman-studio-sa`
4. Click **Create and Continue**
5. Under **Grant access** → Add roles:
   - **Vertex AI User** (`roles/aiplatform.user`)
   - **Storage Object Admin** (`roles/storage.objectAdmin`)
6. Click **Done**

#### Download the Key:

1. In the service accounts list, click on the email of your new account
2. Go to **Keys** tab → **Add Key** → **Create New Key**
3. Choose **JSON** → **Create**
4. A `.json` file will download automatically — **keep it safe!**
5. Rename it if you like (e.g. `stickman-studio-key.json`)

---

### 10. ⚙️ Configure Environment (.env)

1. **Move the service account JSON key** to the project root folder (`Stickman-Studio/`)
2. Copy the example env file:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` in any text editor and fill in:

   ```ini
   # Your GCP project ID (from Step 7)
   GCP_PROJECT_ID=stickman-studio-123456

   # Path to the service account key (from Step 9)
   GOOGLE_APPLICATION_CREDENTIALS=stickman-studio-key.json

   # GCP region (keep default)
   GCP_LOCATION=us-central1
   ```

4. **Save the file**

---

### 11. 🎯 Optional: Install Google Cloud CLI

<details>
<summary><b>Why install gcloud CLI?</b></summary>

The `gcloud` CLI is helpful for:
- Debugging authentication issues
- Managing Google Cloud resources from the terminal
- Setting up Application Default Credentials (if not using a service account)

**Not required for basic usage** — the service account key is sufficient.
</details>

<details>
<summary><b>Windows</b></summary>

```cmd
# Download installer
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe
# Run the installer (follow GUI prompts)

# After installation, authenticate:
gcloud auth application-default login
```
</details>

<details>
<summary><b>macOS / Linux</b></summary>

```bash
# Install
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Authenticate
gcloud auth application-default login
```
</details>

---

### 12. ▶️ Run the Pipeline!

```bash
# Make sure virtual environment is activated
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# Generate a video with default slideshow mode:
python orchestrator.py "How black holes work" --video-mode slideshow

# Generate with Veo animation (premium, costs credits):
python orchestrator.py "Why the sky is blue" --video-mode animation
```

**What to expect:**
```
[1/4] ✍️ Script → Gemini generates storyboard (5-10 sec)
[2/4] 🎨 Images → Imagen generates scene images (30-60 sec)
[3/4] 🎬 Video → ffmpeg Ken Burns zoom (10-20 sec)
[3.5] 🗣️ TTS → edge-tts generates narration (10-30 sec)
[4/4] 🎞️ Assembly → ffmpeg combines everything (10-20 sec)
✅ Video saved to: projects/how_black_holes_work/final.mp4
```

---

### 13. ▶️ Launch the Dashboard

```bash
streamlit run app.py
```

Opens in your browser at `http://localhost:8501`

---

### 14. 🔐 YouTube Upload (Optional)

To enable automatic publishing to YouTube:

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **+ Create Credentials** → **OAuth Client ID**
3. Application type: **Desktop app**
4. Name: `Stickman Studio YouTube Uploader`
5. Click **Create**
6. Click **Download JSON** — rename it to `client_secrets.json`
7. **Move `client_secrets.json`** to the project root folder
8. First upload will open your browser for OAuth consent:
   - Sign in with your YouTube channel's Google account
   - Click **Advanced** → **Go to App** (unsafe) → **Allow**
9. Token is cached in `youtube_token.json` for future runs
10. ✅ Done! All future uploads will be automatic.

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

Pre-generated example videos showing the pipeline output (also available on the [Releases page](https://github.com/saiedpod-bot/Stickman-Studio/releases)):

<table>
  <tr>
    <th>Slideshow Mode — "How Gravity Works" (2.3 MB)</th>
    <th>Slideshow Mode — "How Magnets Work" (0.6 MB)</th>
  </tr>
  <tr>
    <td>
      <video src="samples/slideshow_how_gravity_works.mp4" controls width="360"></video>
    </td>
    <td>
      <video src="samples/slideshow_how_magnets_works.mp4" controls width="360"></video>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <em>3 scenes each — AI script (Gemini) + AI images (Imagen) + Ken Burns zoom (ffmpeg) + neural TTS (edge-tts) + subtitles (MoviePy)</em>
    </td>
  </tr>
</table>

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

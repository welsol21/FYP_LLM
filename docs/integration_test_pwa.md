# ELA PWA Integration Test Guide

## Overview

Before every deploy to el-a.uk, run this integration test to verify the full
analysis pipeline works end-to-end: file upload → Whisper transcription →
linguistic parsing → TTS synthesis → Canvas video render with subtitles.

The test uses **Playwright** with a real Chrome browser (non-headless) and a
real audio file to catch regressions that unit tests cannot.

---

## Prerequisites

1. **Vite dev server running** on port 5174:
   ```bash
   cd frontend && npm run dev -- --port 5174
   ```

2. **Backend API running** on port 8080:
   ```bash
   # Usually already running as a Docker container or via:
   python -m ela_pipeline.runtime.api_server
   ```

3. **AI models downloaded** to `frontend/public/models/`:
   ```bash
   cd frontend && python3 scripts/download_models.py
   ```
   Downloads ~220MB of ONNX models (Whisper base.en, opus-mt-en-ru, mms-tts-rus).
   Idempotent — skips already-downloaded files.

4. **Playwright installed** (available via `npx playwright`):
   ```bash
   # Check version:
   npx playwright --version
   ```

5. **Test audio file** — a large MP3 (~30+ min) to stress-test:
   ```
   /home/vlad/winshare/15.The Voice of Reason - VII.mp3
   ```

---

## Running the Test

```bash
node /tmp/test_render.mjs > /tmp/playwright_out.log 2>&1
# or in background:
node /tmp/test_render.mjs > /tmp/playwright_out.log 2>&1 &
```

The test script is at `/tmp/test_render.mjs`. Keep it maintained alongside
code changes (update button selectors, flow steps if UI changes).

Monitor progress:
```bash
tail -f /tmp/playwright_out.log
```

Screenshots are saved to `/tmp/ss_*.png` — inspect them if the test fails
or pipeline stalls.

---

## What the Test Does

### Step 1 — Navigate to app
Opens `http://localhost:5174/`, waits for page load. Captures
`beforeinstallprompt` event to attempt PWA installation.

### Step 2 — Wait for Service Worker
Verifies SW registered successfully via `navigator.serviceWorker.ready`.

### Step 3 — Attempt PWA Install
Calls `beforeinstallprompt.prompt()`. In automation Chrome often doesn't
fire the install prompt (`no-prompt` result is acceptable). In a real
browser the user must: open Chrome menu → "Install app" / "Add to Home
Screen". After install the SW pre-caches all model files from `/models/`.

### Step 4 — Create project
Handles `window.prompt('Enter project name:')` dialog via Playwright
interceptor, creates a project named "PW Test".

### Step 5 — Upload file
Sets the (hidden) `input[type="file"]` with the large MP3 file. Waits for
the file row to appear in the Files table.

### Step 6 — Open Analyze
Double-taps the file row (within 350ms) to trigger `openAnalyze()` which
navigates to `/analyze` with `location.state.selectedMedia`.

### Step 7 — Start pipeline
Waits for `button[type="submit"].start-btn` to become enabled
(`!disabled`), then clicks it. The button is disabled until
`selectedProject` and `mediaPath` are loaded.

### Step 8 — Monitor (up to 90 min)
Polls page body text every 30s, saves screenshots. Stops when:
- `video` or `a[download]` element appears → **SUCCESS**
- Text contains "render failed" or "processing failed" → **FAILURE**
- Text contains "install the ELA app" → **MODEL MISSING** (run
  `download_models.py` and re-test)

---

## Expected Pipeline Stages

| Stage | Expected log text | Approx time |
|---|---|---|
| Loading file | "Uploading media to backend... Media uploaded" | 5–15s |
| Transcribing audio | "[Whisper] model ready, starting inference" then "Transcribing… 25%" etc. | 5–20 min |
| Linguistic parsing | "Building sentence contracts... Translating sentences" | 2–10 min |
| Generating media | "Rendering translated video track 76%..." | real-time (= audio duration) |
| Exporting files | "Media artifacts exported" | 1–3 min |

---

## Key Things to Verify

- **No `RuntimeError: memory access out of bounds`** in console — was caused
  by FFmpeg drawtext with 400+ subtitle nodes. Fixed by switching to
  Canvas+MediaRecorder.
- **No `font.loaded :: {"size":0}`** — was caused by SW serving old cached
  JS. Fixed by bumping SW cache version and using `?url` import for font.
- **Whisper progress at 25% milestones** (not every token) — fixed by
  removing `token_callback_function`.
- **Translation progress shown in Linguistic parsing bar** — 0–45%
  contracts, 50–100% translation.
- **No re-transcription on second run** — `pipeline_settings.json` must be
  saved even if render fails.
- **"Loading Whisper model…" then progress** (not "install the ELA app") —
  confirms local models are present and loaded.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `net::ERR_CONNECTION_REFUSED` | Vite not running | `npm run dev -- --port 5174` |
| `Backend upload failed: HTTP 404` | No Vite proxy to backend | `VITE_API_BASE_URL` must be empty, Vite proxy must be configured |
| CORS error on `/api/` | API base URL set to absolute URL | Remove `VITE_API_BASE_URL` from `.env.local` |
| `"<!doctype "... is not valid JSON` | Missing tokenizer/vocab files | Run `python3 scripts/download_models.py` |
| `AI models are not installed` | `/models/` files missing | Run `download_models.py` |
| `RuntimeError: memory access out of bounds` | FFmpeg WASM OOM | Canvas renderer should be active — check `renderVideoWithCanvas` is called |
| Browser closed during test | User closed window or Chrome crashed | Restart test |
| `beforeinstallprompt: no-prompt` | Chrome automation blocks PWA install | Normal in Playwright — test manually in real browser |
| `ffmpeg.load()` hangs at "Loading local media renderer" for >1 min | No `SharedArrayBuffer` (missing COOP/COEP headers) | Add `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp` to `vite.config.ts` server.headers |
| `[Translation] No WebGPU adapter, using WASM q8` | Playwright Chrome lacks GPU access | Normal for automated test — real users with WebGPU GPU get GPU acceleration automatically |

---

## Vite Dev Config Required

`frontend/vite.config.ts` must have COOP/COEP headers **and** the proxy:
```ts
server: {
  headers: {
    // Required for SharedArrayBuffer (FFmpeg WASM multithreading).
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Embedder-Policy': 'require-corp',
  },
  proxy: {
    '/api': 'http://localhost:8080',
    '/uploads': 'http://localhost:8080',
  },
},
```

Without COOP/COEP headers `SharedArrayBuffer` is not available in Chrome and
`@ffmpeg/core` will hang indefinitely during `ffmpeg.load()`. This was already
set in `nginx.conf` for production; Vite dev server requires it too.

`frontend/.env.local` must NOT set `VITE_API_BASE_URL` (leave blank or
omit the file).

---

## After Successful Test → Deploy

```bash
# Merge dev → master
git checkout master && git merge dev && git push

# On server:
ssh ela
cd /opt/ela
docker compose down && docker compose up --build -d
```

The Docker build downloads models automatically (`DOWNLOAD_MODELS=1` default
in docker-compose.yml).

# Spooler — media downloader

A self-hosted downloader built on **yt-dlp**, with a FastAPI backend, SQLite
history/metadata store, and a React frontend.

Supports any site yt-dlp supports (YouTube, Vimeo, Twitter/X, SoundCloud,
TikTok, Twitch clips, and hundreds more). Note that downloading content you
don't have the rights to may violate a site's terms of service or copyright
law — this tool doesn't judge, that's on you.

## Features

- Paste a URL, preview title/thumbnail/duration before committing
- Download full video (choose quality up to 4K) or extract audio only
  (mp3/m4a/opus/wav/flac)
- Optional English subtitles
- Background job queue (2 concurrent downloads by default) with live
  progress, speed, and ETA
- Every job — queued, running, finished, or failed — is persisted to SQLite,
  so history survives restarts
- Cancel in-flight downloads, retry failed ones, delete history entries
  (and their files)
- Stats bar: active / completed / failed counts

## Project layout

```
backend/
  app/
    main.py         FastAPI routes
    downloader.py    yt-dlp wrapper + background worker queue
    models.py        SQLAlchemy models (Download table = history + metadata)
    database.py      SQLite engine/session setup
    schemas.py        Pydantic request models
    config.py          paths, CORS, concurrency
  requirements.txt
  run.py               dev entrypoint
  Dockerfile
frontend/
  src/
    App.jsx                  layout, polling, active/history split
    api.js                     fetch wrapper for the backend
    components/UrlForm.jsx     URL input, preview, format/quality options
    components/TrackCard.jsx    one row: thumbnail, VU-meter progress, actions
    index.css                    theme (tape-deck / mixing-console look)
  vite.config.js         dev server + /api proxy to the backend
  Dockerfile
  nginx.conf
docker-compose.yml
```

## Run it with Docker (one command)

```bash
docker compose up --build
```

Then open http://localhost:8080. The backend API is also reachable
directly at http://localhost:8000 if you want to hit it yourself.

This builds two images and runs them together:

- `backend` - Python + ffmpeg + yt-dlp, serving the API on :8000
- `frontend` - a Vite production build served by nginx on :80 (mapped to
  host :8080), which proxies `/api/*` requests straight to the backend
  container over the internal Docker network (see `frontend/nginx.conf`) -
  no CORS setup needed

The SQLite database and downloaded files live in a named volume
(`spooler-data`, mounted at `/data` in the backend container), so your
history and files survive `docker compose down` / restarts. To wipe
everything: `docker compose down -v`.

To run in the background: `docker compose up --build -d`, then
`docker compose logs -f` to tail logs.

### Docker files

```
backend/Dockerfile        Python 3.12-slim + ffmpeg + yt-dlp, runs uvicorn
backend/.dockerignore
frontend/Dockerfile        multi-stage: npm build then nginx:alpine to serve it
frontend/nginx.conf        SPA fallback + /api proxy to the backend service
frontend/.dockerignore
docker-compose.yml         wires both services + the persistent data volume
```

## Run it without Docker

## Requirements

- Python 3.10+
- Node.js 18+
- **ffmpeg** installed and on your `PATH` (required by yt-dlp for merging
  video+audio and for audio extraction)

## Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py                    # http://127.0.0.1:8000
```

This creates `backend/downloader.db` (SQLite) and `backend/downloads/`
(saved media files) on first run.

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://127.0.0.1:5173
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000`, so just
open the frontend URL — no CORS config needed in dev.

### Production build

```bash
cd frontend
npm run build                    # outputs frontend/dist
```

Serve `frontend/dist` with any static file server (nginx, Caddy, etc.) and
point it at the backend, or add a route in `main.py` to serve it directly.

## Configuration

Environment variables (all optional, read in `backend/app/config.py`):

| Variable                  | Default              | Purpose                          |
|----------------------------|-----------------------|-----------------------------------|
| `DOWNLOAD_DIR`             | `backend/downloads`   | Where finished files are saved   |
| `DB_PATH`                  | `backend/downloader.db` | SQLite file location           |
| `MAX_CONCURRENT_DOWNLOADS` | `2`                    | Worker thread pool size          |

## API summary

| Method & path                          | Purpose                             |
|-----------------------------------------|---------------------------------------|
| `POST /api/preview`                     | Fetch metadata for a URL, no download |
| `POST /api/downloads`                   | Queue a new download job              |
| `GET /api/downloads`                    | List all jobs (history + active)      |
| `GET /api/downloads/{id}`               | Get one job's current state           |
| `POST /api/downloads/{id}/cancel`       | Cancel an in-flight job                |
| `POST /api/downloads/{id}/retry`        | Re-queue a failed/cancelled job         |
| `DELETE /api/downloads/{id}`            | Delete a job + its file                 |
| `GET /api/downloads/{id}/file`          | Download the finished file              |
| `GET /api/stats`                        | Counts for the header stat bar          |

## Notes on the SQLite schema

Everything lives in one `downloads` table (see `backend/app/models.py`) so
the history view and the live-progress view are the same data — a row is
created the moment a URL is queued and updated in place through
`queued → fetching_info → downloading → processing → completed/failed`.
Stored per row: request params (url, media type, quality, subtitle flag),
live progress (percent, speed, eta), extracted metadata (title, uploader,
extractor, duration, thumbnail, upload date, view count), and the result
(file path, extension, size, timestamps, error message if it failed).

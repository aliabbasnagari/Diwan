# Crate — a library manager for Navidrome

A self-hosted web app that helps you build, tag, and organize a music
library for **[Navidrome](https://www.navidrome.org/)**. It has three
halves that work together:

- **Library** — browse your existing collection by artist/album, edit
  ID3/Vorbis/FLAC/MP4 tags, replace album art, and keep files organized
  into a clean `Artist/Album/NN - Title.ext` structure.
- **Spooler** — pull new tracks in from YouTube, SoundCloud, Bandcamp, and
  hundreds of other sites via yt-dlp, with an option to auto-tag and drop
  them straight into the library, then trigger a Navidrome rescan.
- **Convert** — re-encode any file into a different audio or video format
  with ffmpeg, whether it's an upload, an existing library track, or
  something the spooler already pulled down.

Note: downloading content you don't have the rights to may violate a
site's terms of service or copyright law — this tool doesn't judge, that's
on you.

## Features

- **Library browser** — artist → album → track tree, full-text search,
  per-track duration/bitrate/size
- **Tag editor** — title, artist, album, album artist, genre, year, track
  and disc number, read/written with Mutagen across mp3/flac/m4a/ogg/opus
- **Three levels of artwork**, matching how Navidrome actually resolves
  images:
  - *Track art* — embedded in a single file only (Mutagen)
  - *Album art* — written as `cover.jpg` in the album folder and embedded
    in every track in it (Navidrome's own default priority order)
  - *Artist pictures* — saved to a dedicated folder outside the music
    library, for use with Navidrome's `ArtistImageFolder` setting
  All three are resized/re-encoded with Pillow before writing.
- **Auto-organize** — editing tags can move the file to match; a
  library-wide "Organize all" pass tidies anything dropped in loose
- **Spooler** — Fetch a URL to see real available qualities pulled live
  from yt-dlp, then Download; video (up to whatever resolutions the source
  actually has) or audio-only (mp3/m4a/opus/wav/flac, always extracted at
  the best quality via ffmpeg)
- **Add to library** — audio downloads can be auto-tagged (from the
  source's metadata, or your own artist/album/title overrides), embedded
  with the source thumbnail as cover art, and moved into the library in
  one step
- **Convert** — pick a source (upload a file, an existing library track,
  or a completed spooler download) and a target format:
  - Audio: mp3, m4a, opus, ogg, flac, wav, with a bitrate picker (skipped
    for the lossless formats)
  - Video: mp4, webm, mkv, mov, with an optional resolution downscale
  - Audio outputs can optionally be tagged and dropped straight into the
    library, same as a spooler download
  - Runs as a background ffmpeg job with live progress, same queue/history
    pattern as the spooler
- **Navidrome integration** — test the connection, trigger a scan on
  demand, or have one fire automatically after every library addition
  (Subsonic API, so no Navidrome-side config needed beyond a username/
  password it already has)
- Every download and conversion is persisted to SQLite — queue, progress,
  and full history survive restarts

## Stack

| Backend | Purpose |
|---|---|
| FastAPI + Uvicorn | REST API |
| yt-dlp | Downloading from YouTube, SoundCloud, Bandcamp, etc. |
| Mutagen | Read/write audio tags (ID3, Vorbis, FLAC, MP4) |
| Pillow | Album art resize/convert before embedding |
| SQLAlchemy + SQLite | Download queue, job history, app settings |
| Pydantic | Request/response validation |
| httpx | Talks to Navidrome's Subsonic API |

| Frontend | Purpose |
|---|---|
| React + Vite | UI |
| Tailwind CSS | Styling |
| React Router | Library / Spooler / Settings pages |
| Axios | HTTP client |
| TanStack Query | Server state, caching, polling |
| Sonner | Toast notifications |
| Lucide React | Icons |

## Project layout

```
backend/
  app/
    main.py               FastAPI app, mounts routers, download endpoints
    routes_library.py      /api/library/* — browse, tag, art, organize
    routes_settings.py      /api/settings/*
    routes_navidrome.py      /api/navidrome/* — scan trigger/status
    routes_convert.py         /api/convert/* — format catalog, job queue
    downloader.py             yt-dlp worker queue: fetch, tag, organize, scan
    converter.py                ffmpeg worker queue: probe, encode, progress
    navidrome.py                  Subsonic API client (ping/scan/status)
    settings_service.py            reads/writes the AppSettings DB row
    models.py                       Download + ConversionJob + AppSettings
    schemas.py                       Pydantic request models
    database.py                       SQLite engine/session
    config.py                          env-var bootstrap defaults, format catalogs
    library/
      scanner.py             walks the library dir, builds the artist/album/track tree
      metadata.py              Mutagen tag + album-art read/write
      organizer.py               sanitizes paths, moves files into place
  requirements.txt
  run.py
  Dockerfile
frontend/
  src/
    App.jsx                   sidebar layout + routes
    api.js                      axios client for every endpoint
    pages/
      LibraryPage.jsx            search, artist/album tree, organize-all
      SpoolerPage.jsx              queue + history
      ConvertPage.jsx                source picker, format/options, queue + history
      SettingsPage.jsx                 paths, concurrency, Navidrome
    components/
      TrackEditDrawer.jsx        tag form, artwork upload, delete/organize
      UrlForm.jsx                  fetch → download flow, library options
      DownloadCard.jsx              queue/history row, segmented progress
      ConversionCard.jsx              same, for conversion jobs
      AlbumArt.jsx                   album thumbnail
      Sidebar.jsx
  tailwind.config.js
  vite.config.js              dev server + /api proxy to the backend
  Dockerfile
  nginx.conf
docker-compose.yml
```

## Run it with Docker (one command)

```bash
docker compose up --build
```

Then open http://localhost:8080. The API is also reachable directly at
http://localhost:8000.

Two named volumes are created:

- `crate-data` — SQLite DB + the download staging area
- `crate-music` — the library itself

**Point `crate-music` at wherever Navidrome reads its music from.** If
Navidrome runs elsewhere on the same host, edit the `crate-music` volume
line in `docker-compose.yml` to a bind mount of that same folder, e.g.:

```yaml
    volumes:
      - crate-data:/data
      - /home/you/music:/music
```

There's also a commented-out `navidrome` service in `docker-compose.yml`
if you'd rather run Navidrome itself as part of the same stack, sharing
the `crate-music` volume — uncomment it and you're set.

To run in the background: `docker compose up --build -d`, then
`docker compose logs -f`.

## Run it without Docker

### Requirements

- Python 3.10+
- Node.js 18+
- **ffmpeg** on your `PATH` (yt-dlp needs it for merging/extracting audio)

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py                    # http://127.0.0.1:8000
```

Creates `backend/downloader.db`, `backend/downloads/` (staging),
`backend/library/` (the music library), and `backend/conversions/`
(uploads + output for the Convert page) on first run. Override the first
three with the `DOWNLOAD_DIR` / `LIBRARY_DIR` / `DB_PATH` env vars, or
just change the paths later from the Settings page; the conversions
folder is controlled by `CONVERT_DIR` (not exposed in Settings, since it's
just scratch space).

### Frontend

```bash
cd frontend
npm install
npm run dev                      # http://127.0.0.1:5173
```

Vite proxies `/api/*` to `http://127.0.0.1:8000` in dev, so no CORS setup
needed.

### Production build

```bash
cd frontend
npm run build                    # outputs frontend/dist
```

## Configuring Navidrome

In the app's **Settings** page:

1. Set **Library directory** to the same folder your Navidrome server
   scans.
2. Enter your Navidrome **server URL**, **username**, and **password** —
   the same login you use in Navidrome's own web UI (auth goes through
   the Subsonic API, so no separate API key is needed).
3. **Test connection** to confirm it's reachable.
4. Optionally enable **auto-scan**, so Navidrome picks up new tracks the
   moment Crate adds them, without waiting for its own scan schedule.
5. To make artist pictures uploaded in Crate show up in Navidrome, set
   these two environment variables on the Navidrome server itself
   (Settings page shows the exact values, including your configured
   path):
   ```
   ND_ARTISTIMAGEFOLDER=<the artist image directory from Settings>
   ND_ARTISTARTPRIORITY=image-folder,artist.*,album/artist.*,last.fm
   ```
   Track art and album art need no Navidrome-side config — they're
   embedded/`cover.jpg` respectively, which Navidrome reads by default.

## API summary

**Downloads / spooler**
| Method & path | Purpose |
|---|---|
| `POST /api/preview` | Fetch metadata + real available formats for a URL |
| `POST /api/downloads` | Queue a download (optionally: tag + add to library) |
| `GET /api/downloads` | List all jobs |
| `GET /api/downloads/{id}` | One job's current state |
| `POST /api/downloads/{id}/cancel` | Cancel an in-flight job |
| `POST /api/downloads/{id}/retry` | Re-queue a failed/cancelled job |
| `DELETE /api/downloads/{id}` | Delete a job + its file |
| `GET /api/downloads/{id}/file` | Download the finished file |
| `GET /api/stats` | Header stat counts |

**Library**
| Method & path | Purpose |
|---|---|
| `GET /api/library/tree` | Artist → album → track tree |
| `GET /api/library/tracks?q=` | Flat list, or search |
| `GET /api/library/stats` | Artist/album/track counts, total size |
| `GET /api/library/tracks/{id}` | One track's tags |
| `PUT /api/library/tracks/{id}` | Update tags (optionally reorganize the file) |
| `DELETE /api/library/tracks/{id}` | Delete the file |
| `GET /api/library/tracks/{id}/artwork` | Track's embedded art (this file only) |
| `POST /api/library/tracks/{id}/artwork` | Replace this track's embedded art |
| `GET /api/library/albums/{id}/artwork` | Album cover (`cover.jpg`, or first embedded track art) |
| `POST /api/library/albums/{id}/artwork` | Write `cover.jpg` + embed into every track in the album |
| `GET /api/library/artists/{id}/picture` | Artist picture from the artist image folder |
| `POST /api/library/artists/{id}/picture` | Save an artist picture |
| `POST /api/library/tracks/{id}/organize` | Move one track to match its tags |
| `POST /api/library/organize` | Bulk-organize the whole library (or a track id list) |

**Convert**
| Method & path | Purpose |
|---|---|
| `GET /api/convert/formats` | Available target formats, bitrates, resolutions |
| `POST /api/convert/jobs` | Queue a conversion (multipart: upload a file, or reference a library track / download by id) |
| `GET /api/convert/jobs` | List all conversion jobs |
| `GET /api/convert/jobs/{id}` | One job's current state |
| `POST /api/convert/jobs/{id}/cancel` | Cancel an in-flight conversion |
| `DELETE /api/convert/jobs/{id}` | Delete a job + its output file |
| `GET /api/convert/jobs/{id}/file` | Download the converted file |
| `GET /api/convert/stats` | Header stat counts |

**Settings / Navidrome**
| Method & path | Purpose |
|---|---|
| `GET /api/settings` | Current settings (password never returned, just a flag) |
| `PUT /api/settings` | Update paths, concurrency, Navidrome credentials |
| `POST /api/settings/navidrome/test` | Ping Navidrome, return its version |
| `POST /api/navidrome/scan` | Trigger a library scan |
| `GET /api/navidrome/scan/status` | Poll scan progress |

## Notes on the data model

Everything lives in two tables. `downloads` is both the live job queue and
the permanent history — one row per URL, updated in place through
`queued → fetching_info → downloading → processing → tagging →
completed/failed`, storing the request params, live progress, extracted
metadata, and (if added to the library) the final relative path.
`app_settings` is a single-row table holding the editable paths, worker
concurrency, and Navidrome credentials.

The library itself isn't cached in the database — `/api/library/*`
scans the filesystem directly with Mutagen on every request (track ids
are just base64-encoded relative paths), so it's always accurate and
there's nothing to keep in sync after files are edited outside the app.
For very large libraries this means list/search calls do real disk I/O
each time; fine for a personal collection, worth knowing if you're
pointing it at tens of thousands of files.

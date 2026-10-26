# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Diwan: a self-hosted library manager for Navidrome. FastAPI backend (`backend/app`) + React/Vite/Tailwind frontend (`frontend/src`). Features: library browser/tag editor (Mutagen), "Spooler" (yt-dlp downloads) and "Bulk Spooler" (paced batch downloads), "Convert" (ffmpeg jobs), "Duplicates" (Chromaprint-based dedup scan), tag suggestions, Navidrome scan integration. See README.md for the full feature list and API tables.

## Commands

There is no linter configured. There is a small pytest/vitest suite (unit-level only, no DB/FastAPI integration tests yet).

Backend (Python 3.10+, ffmpeg on PATH, `fpcalc`/Chromaprint on PATH for the Duplicates scan, `NAVIDROME_URL` env var required):
```bash
cd backend
pip install -r requirements.txt
NAVIDROME_URL=http://localhost:4533 python run.py     # http://127.0.0.1:4534
pip install -r requirements-dev.txt && pytest         # run backend tests (backend/tests/)
```
Frontend:
```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:4535, Vite proxies /api/* to :4534
npm run build      # outputs frontend/dist
npm test           # run frontend tests (vitest, src/*.test.js)
```
Full stack: `cp .env.example .env && docker compose up --build` (UI on :8080, API on :8000).

## Architecture

**Auth is delegated to Navidrome.** `routes_auth.py` → `navidrome_auth.py` POSTs credentials to `{NAVIDROME_URL}/auth/login` and only accepts `isAdmin: true`. `auth.py` issues stateless HMAC-signed session tokens (30-day). In `main.py`, every router except auth (and `/api/health`) is mounted with `Depends(require_admin)` — new routers must be mounted the same way. The downloads router is the exception in `main.py`: it declares `require_admin` on itself in `routes_downloads.py`. Tokens may also come via `?token=` for `<img>`/`<a>` URLs.

**Configuration is two-tier.** `config.py` holds env-var bootstrap values read once at startup (`NAVIDROME_URL`, default dirs, `DB_PATH`, `CONVERT_DIR`, CORS origins). Runtime-editable preferences (library/download/artist-image paths, worker concurrency, Navidrome creds, yt-dlp cookies) live in a single-row `AppSettings` table accessed via `settings_service.py`. Read paths from settings, not `config.py`, at runtime.

**Background job queues.** `downloader.py` (yt-dlp) and `converter.py` (ffmpeg) each run worker threads started in `main.py`'s startup hook. `downloads` and the conversion-jobs table are both the live queue and permanent history (status state machine in `models.py`). On startup, jobs left mid-flight are reset to `QUEUED` and re-enqueued. Progress is polled by the frontend via TanStack Query. `bulk_spooler.py` layers a serial, randomly-delayed (3–6 min) queue on top of `downloader.py` for the Bulk Spooler page: each queued URL spawns a normal `Download` row and waits for it to finish before starting the next. `dedup_scanner.py` runs its own single-threaded worker the same way for the Duplicates scan.

**Library is filesystem-backed, not DB-cached.** `library/scanner.py` walks the library dir with Mutagen on every request; track/album/artist IDs are base64-encoded relative paths. `library/metadata.py` does tag/art read-write (multi-value artist tags via comma-split; album artist single-valued), `library/organizer.py` computes `Artist/Album/NN - Title.ext` paths (grouped by album artist) and moves files. Any code that moves a library file must call `library/tracking.py:sync_moved_path` so spooler/convert history rows (which store `filepath`/`library_path`) keep pointing at it. Artwork has three levels: embedded track art, `cover.jpg` + embedded album art, and artist pictures in a separate folder (named by album artist). The `.duplicates-trash/` folder at the library root (quarantined duplicates, see below) is excluded from every scan.

**Duplicate detection.** `dedup_scanner.py` / `routes_duplicates.py` implement the Duplicates page: a scan hashes (SHA-256) and acoustically fingerprints (Chromaprint via the `fpcalc` CLI, cached per-file in `TrackFingerprint` keyed by mtime+size) every library track, then groups them by a tiered pairwise score — `library/fingerprint.py` has the hashing/fingerprint-similarity primitives, `dedup_scanner.py` has the duration-bucketed candidate scoring, union-find grouping, and category thresholds (exact / audio match / near match / different recording). Resolving a group moves every non-keeper file into `.duplicates-trash/` (via `library/tracking.py:sync_moved_path`, same as any other library move) rather than deleting outright; "not a duplicate" persists a per-pair ignore row (`DuplicateIgnoredPair`) so re-scans don't regroup it.

**Audio trimmer.** `audio_editor.py` / `routes_editor.py` (mounted with `require_admin`) implement the Trimmer page (`/editor`). A session decodes a library track to a 16-bit WAV under `CONVERT_DIR/editor/<sid>/` and keeps a version stack (each edit — keep range, remove range, add silence, auto-trim silence — is one ffmpeg render; undo/redo = pointer move). The library file is only touched by `export` (overwrite or "(edited)" copy, tags/art copied from the original). Sessions are in memory; working files are wiped at startup.

**Tag suggestions.** `tag_suggestions.py` / `routes_suggestions.py` record previously used artist/album/genre/year values (`TagSuggestion` table) to autocomplete in the tag editor and spooler.

**Navidrome scan.** `navidrome.py` is a Subsonic API client; scans can auto-trigger after library additions (spooler/convert "add to library").

**Frontend.** `App.jsx` is the auth gate + sidebar layout + routes; `auth.jsx` holds session state; `api.js` is the axios client that attaches the token. Pages (Library, Spooler, BulkSpooler, Convert, Editor, Duplicates, Settings, TagSuggestions, Login) in `pages/`, shared pieces in `components/` (`TrackEditDrawer` is the tag/artwork editor; `UrlForm` is the spooler fetch→download flow).

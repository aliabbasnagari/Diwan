import { useState } from "react";
import { api } from "../api.js";

const AUDIO_FORMATS = ["mp3", "m4a", "opus", "wav", "flac"];

export default function UrlForm({ onQueued }) {
  const [url, setUrl] = useState("");
  const [mediaType, setMediaType] = useState("video");
  const [quality, setQuality] = useState("best");
  const [audioFormat, setAudioFormat] = useState("mp3");
  const [subtitles, setSubtitles] = useState(false);

  const [preview, setPreview] = useState(null);       // metadata + formats from yt-dlp
  const [fetched, setFetched] = useState(false);       // has this exact url been fetched?
  const [fetching, setFetching] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function handleUrlChange(e) {
    setUrl(e.target.value);
    // any edit invalidates the previous fetch — must re-fetch before downloading
    if (fetched) setFetched(false);
    setPreview(null);
    setError(null);
  }

  async function handleFetch() {
    if (!url.trim()) return;
    setError(null);
    setFetching(true);
    setPreview(null);
    try {
      const info = await api.preview(url.trim());
      setPreview(info);
      const qualities = info.video_qualities || [{ value: "best", label: "Best available" }];
      setQuality(qualities[0].value);
      setFetched(true);
    } catch (e) {
      setError(e.message || "Could not fetch that URL.");
      setFetched(false);
    } finally {
      setFetching(false);
    }
  }

  async function handleDownload() {
    if (!url.trim() || !fetched) return;
    setError(null);
    setSubmitting(true);
    try {
      await api.createDownload({
        url: url.trim(),
        media_type: mediaType,
        quality: mediaType === "video" ? quality : "best",
        audio_format: audioFormat,
        subtitles,
      });
      setUrl("");
      setPreview(null);
      setFetched(false);
      onQueued();
    } catch (e) {
      setError(e.message || "Could not queue that download.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key !== "Enter") return;
    if (fetched) handleDownload();
    else handleFetch();
  }

  const qualities = preview?.video_qualities || [];

  return (
    <div className="deck">
      <div className="deck-row">
        <input
          className="url-input"
          placeholder="Paste a video / audio URL…"
          value={url}
          onChange={handleUrlChange}
          onKeyDown={handleKeyDown}
        />

        {!fetched ? (
          <button className="pull-btn" onClick={handleFetch} disabled={fetching || !url.trim()}>
            {fetching ? "Fetching…" : "Fetch"}
          </button>
        ) : (
          <button className="pull-btn" onClick={handleDownload} disabled={submitting}>
            {submitting ? "Queuing…" : "Download"}
          </button>
        )}
      </div>

      {fetched && (
        <div className="deck-options">
          <div className="seg-toggle">
            <button className={mediaType === "video" ? "active" : ""} onClick={() => setMediaType("video")}>
              Video
            </button>
            <button className={mediaType === "audio" ? "active" : ""} onClick={() => setMediaType("audio")}>
              Audio only
            </button>
          </div>

          {mediaType === "video" ? (
            <select className="select" value={quality} onChange={(e) => setQuality(e.target.value)}>
              {qualities.map((q) => (
                <option key={q.value} value={q.value}>
                  {q.label}
                  {q.filesize ? ` · ${formatBytes(q.filesize)}` : ""}
                </option>
              ))}
            </select>
          ) : (
            <>
              <select className="select" value={audioFormat} onChange={(e) => setAudioFormat(e.target.value)}>
                {AUDIO_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f.toUpperCase()}
                  </option>
                ))}
              </select>
              <span className="checkbox-lbl" style={{ cursor: "default" }}>
                Best quality (via ffmpeg)
              </span>
            </>
          )}

          {mediaType === "video" && (
            <label className="checkbox-lbl">
              <input type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} />
              Subtitles (en)
            </label>
          )}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {preview && (
        <div className="preview-card">
          {preview.thumbnail && <img className="preview-thumb" src={preview.thumbnail} alt="" />}
          <div className="preview-meta">
            <p className="preview-title">{preview.title || "Untitled"}</p>
            <div className="preview-sub">
              {preview.uploader ? `${preview.uploader} · ` : ""}
              {preview.extractor || "unknown source"}
              {preview.duration ? ` · ${formatDuration(preview.duration)}` : ""}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatDuration(sec) {
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function formatBytes(bytes) {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(1)} ${units[i]}`;
}

export { formatDuration };

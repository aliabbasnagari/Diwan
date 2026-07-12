import { api } from "../api.js";
import { formatDuration } from "./UrlForm.jsx";

const SEGMENTS = 24;

const STATUS_LABEL = {
  queued: "Queued",
  fetching_info: "Reading",
  downloading: "Pulling",
  processing: "Finishing",
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function TrackCard({ item, onChanged }) {
  const pct = item.progress_percent || 0;
  const litSegments = Math.round((pct / 100) * SEGMENTS);
  const isError = item.status === "failed" || item.status === "cancelled";
  const isComplete = item.status === "completed";
  const active = ["queued", "fetching_info", "downloading", "processing"].includes(item.status);

  async function handleCancel() {
    await api.cancelDownload(item.id);
    onChanged();
  }
  async function handleRetry() {
    await api.retryDownload(item.id);
    onChanged();
  }
  async function handleDelete() {
    await api.deleteDownload(item.id);
    onChanged();
  }

  return (
    <div className="track">
      {item.thumbnail ? (
        <img className="track-thumb" src={item.thumbnail} alt="" />
      ) : (
        <div className="track-thumb audio-placeholder">
          {item.media_type === "audio" ? "♪" : "▶"}
        </div>
      )}

      <div className="track-body">
        <div className="track-top">
          <p className="track-title">{item.title || item.url}</p>
          <span className={`badge ${item.status}`}>{STATUS_LABEL[item.status] || item.status}</span>
        </div>

        <div className="track-meta">
          {item.uploader ? `${item.uploader} · ` : ""}
          {item.extractor || "—"}
          {item.duration ? ` · ${formatDuration(item.duration)}` : ""}
          {item.media_type === "audio" ? ` · audio/${item.audio_format}` : item.quality ? ` · ${item.quality === "best" ? "best quality" : item.quality + "p"}` : ""}
        </div>

        <div className="vu-bar">
          {Array.from({ length: SEGMENTS }).map((_, i) => (
            <div
              key={i}
              className={`vu-seg ${i < litSegments ? "on" : ""} ${isComplete ? "complete" : ""} ${isError ? "error" : ""}`}
            />
          ))}
        </div>

        <div className="track-stats-row">
          <span>{active ? `${pct.toFixed(0)}%` : isComplete ? formatBytes(item.filesize) : ""}</span>
          <span>
            {item.speed ? `${item.speed} ` : ""}
            {item.eta ? `ETA ${item.eta}` : ""}
          </span>
        </div>

        {item.error_message && <div className="track-error" title={item.error_message}>{item.error_message}</div>}
      </div>

      <div className="track-actions">
        {isComplete && (
          <a className="icon-btn" href={api.fileUrl(item.id)} download>
            Save file
          </a>
        )}
        {active && (
          <button className="icon-btn danger" onClick={handleCancel}>
            Cancel
          </button>
        )}
        {isError && (
          <button className="icon-btn" onClick={handleRetry}>
            Retry
          </button>
        )}
        <button className="icon-btn danger" onClick={handleDelete}>
          Remove
        </button>
      </div>
    </div>
  );
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

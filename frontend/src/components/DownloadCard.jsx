import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Library, ExternalLink } from "lucide-react";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";

const SEGMENTS = 24;

const STATUS_STYLE = {
  queued: "text-parchment-500 bg-white/5",
  fetching_info: "text-brass-400 bg-brass-900/40",
  downloading: "text-brass-400 bg-brass-900/40",
  processing: "text-brass-400 bg-brass-900/40",
  tagging: "text-teal-400 bg-teal-600/20",
  completed: "text-moss-400 bg-moss-500/10",
  failed: "text-rust-400 bg-rust-500/10",
  cancelled: "text-rust-400 bg-rust-500/10",
};

const STATUS_LABEL = {
  queued: "Queued",
  fetching_info: "Reading",
  downloading: "Pulling",
  processing: "Finishing",
  tagging: "Tagging",
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

const ACTIVE = new Set(["queued", "fetching_info", "downloading", "processing", "tagging"]);

export default function DownloadCard({ item }) {
  const qc = useQueryClient();
  const pct = item.progress_percent || 0;
  const lit = Math.round((pct / 100) * SEGMENTS);
  const isError = item.status === "failed" || item.status === "cancelled";
  const isComplete = item.status === "completed";
  const active = ACTIVE.has(item.status);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["downloads"] });
    qc.invalidateQueries({ queryKey: ["download-stats"] });
  };

  const cancelMutation = useMutation({ mutationFn: () => api.cancelDownload(item.id), onSuccess: invalidate });
  const retryMutation = useMutation({
    mutationFn: () => api.retryDownload(item.id),
    onSuccess: () => { toast.success("Retrying"); invalidate(); },
  });
  const deleteMutation = useMutation({ mutationFn: () => api.deleteDownload(item.id), onSuccess: invalidate });

  return (
    <div className="panel p-3.5 flex gap-3.5 items-center">
      {item.thumbnail ? (
        <img src={item.thumbnail} className="w-16 h-16 rounded-lg object-cover bg-ink-950 shrink-0" alt="" />
      ) : (
        <div className="w-16 h-16 rounded-lg bg-ink-950 shrink-0 flex items-center justify-center text-brass-600 font-display text-lg">
          {item.media_type === "audio" ? "♪" : "▶"}
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium truncate">{item.title || item.url}</p>
          <span className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded shrink-0 ${STATUS_STYLE[item.status] || ""}`}>
            {STATUS_LABEL[item.status] || item.status}
          </span>
        </div>

        <p className="text-xs font-mono text-parchment-700 truncate mt-0.5">
          {item.uploader ? `${item.uploader} · ` : ""}
          {item.extractor || "—"}
          {item.duration ? ` · ${formatDuration(item.duration)}` : ""}
          {item.media_type === "audio" ? ` · ${item.audio_format}` : item.quality && item.quality !== "best" ? ` · ${item.quality}p` : ""}
        </p>

        <div className="flex gap-[3px] h-2 mt-2.5">
          {Array.from({ length: SEGMENTS }).map((_, i) => (
            <div
              key={i}
              className={`flex-1 rounded-sm border ${
                i < lit
                  ? isComplete
                    ? "bg-moss-500 border-moss-500 shadow-[0_0_6px_rgba(127,174,131,0.5)]"
                    : isError
                    ? "bg-rust-500 border-rust-500 shadow-[0_0_6px_rgba(193,85,76,0.5)]"
                    : "bg-brass-500 border-brass-500 shadow-[0_0_6px_rgba(217,164,65,0.5)]"
                  : "bg-ink-950 border-ink-600"
              }`}
            />
          ))}
        </div>

        <div className="flex justify-between mt-1.5 text-[10.5px] font-mono text-parchment-700">
          <span>{active ? `${pct.toFixed(0)}%` : isComplete ? formatBytes(item.filesize) : ""}</span>
          <span>{item.speed ? `${item.speed} ` : ""}{item.eta ? `ETA ${item.eta}` : ""}</span>
        </div>

        {item.error_message && (
          <p className="text-[11px] font-mono text-rust-400 mt-1 truncate" title={item.error_message}>{item.error_message}</p>
        )}

        {isComplete && item.library_path && (
          <p className="flex items-center gap-1.5 text-[11px] font-mono text-teal-400 mt-1.5">
            <Library className="w-3 h-3" /> In library: {item.library_path}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 shrink-0">
        {isComplete && (
          <a href={api.fileUrl(item.id)} download className="btn-ghost flex items-center gap-1 justify-center">
            <ExternalLink className="w-3 h-3" /> Save
          </a>
        )}
        {active && (
          <button className="btn-ghost-danger" onClick={() => cancelMutation.mutate()}>Cancel</button>
        )}
        {isError && (
          <button className="btn-ghost" onClick={() => retryMutation.mutate()}>Retry</button>
        )}
        <button className="btn-ghost-danger" onClick={() => deleteMutation.mutate()}>Remove</button>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Library, ExternalLink, AlertTriangle } from "lucide-react";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";

const STATUS_STYLE = {
  completed: "text-moss-400 bg-moss-500/10",
  failed: "text-rust-400 bg-rust-500/10",
  cancelled: "text-rust-400 bg-rust-500/10",
};

const STATUS_LABEL = {
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function HistoryCard({ item }) {
  const qc = useQueryClient();
  const isError = item.status === "failed" || item.status === "cancelled";
  const isComplete = item.status === "completed";

  const [showConfirm, setShowConfirm] = useState(false);
  const [deleteFromDisk, setDeleteFromDisk] = useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["downloads"] });
    qc.invalidateQueries({ queryKey: ["download-stats"] });
  };

  const retryMutation = useMutation({
    mutationFn: () => api.retryDownload(item.id),
    onSuccess: () => { toast.success("Retrying"); invalidate(); },
  });

  const removeMutation = useMutation({
    mutationFn: (withDisk) => api.deleteDownload(item.id, withDisk),
    onSuccess: () => {
      invalidate();
      setShowConfirm(false);
      setDeleteFromDisk(false);
    },
  });

  const openConfirm = () => {
    setDeleteFromDisk(false);
    setShowConfirm(true);
  };

  const closeConfirm = () => {
    if (removeMutation.isPending) return;
    setShowConfirm(false);
    setDeleteFromDisk(false);
  };

  const confirmRemove = () => {
    removeMutation.mutate(deleteFromDisk);
  };

  return (
    <div className="panel p-3.5 flex gap-3.5 items-center relative">
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

        <div className="flex justify-between mt-1.5 text-[10.5px] font-mono text-parchment-700">
          <span>{isComplete ? formatBytes(item.filesize) : ""}</span>
          <span></span>
        </div>

        {item.error_message && (
          <p className="text-[11px] font-mono text-rust-400 mt-1 truncate" title={item.error_message}>{item.error_message}</p>
        )}

        {isComplete && item.file_exists && item.library_path && (
          <p className="flex items-center gap-1.5 text-[11px] font-mono text-teal-400 mt-1.5">
            <Library className="w-3 h-3" /> In library: {item.library_path}
          </p>
        )}

        {isComplete && !item.file_exists && (
          <p className="flex items-center gap-1.5 text-[11px] font-mono text-rust-400 mt-1.5">
            <AlertTriangle className="w-3 h-3" /> File missing on disk: {item.filepath}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 shrink-0">
        {isComplete && item.file_exists && (
          <a href={api.fileUrl(item.id)} download className="btn-ghost flex items-center gap-1 justify-center">
            <ExternalLink className="w-3 h-3" /> Save
          </a>
        )}
        {(isError || !item.file_exists) && (
          <button className="btn-ghost" onClick={() => retryMutation.mutate()}>Retry</button>
        )}
        <button className="btn-ghost-danger" onClick={openConfirm}>Remove</button>
      </div>

      {showConfirm && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-ink-950/80 rounded-lg">
          <div className="panel p-4 w-72 flex flex-col gap-3 shadow-lg">
            <p className="text-sm font-medium">Remove this download?</p>

            <label className="flex items-center gap-2 text-xs font-mono text-parchment-700 select-none cursor-pointer">
              <input
                type="checkbox"
                checked={deleteFromDisk}
                onChange={(e) => setDeleteFromDisk(e.target.checked)}
              />
              Delete from disk?
            </label>

            <div className="flex justify-end gap-2 mt-1">
              <button className="btn-ghost" onClick={closeConfirm} disabled={removeMutation.isPending}>
                Cancel
              </button>
              <button className="btn-ghost-danger" onClick={confirmRemove} disabled={removeMutation.isPending}>
                {removeMutation.isPending ? "Removing…" : "Remove"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Library } from "lucide-react";
import { api } from "../api.js";

const STATUS_STYLE = {
  completed: "text-moss-400 bg-moss-500/10",
  failed: "text-rust-400 bg-rust-500/10",
  cancelled: "text-rust-400 bg-rust-500/10",
  skipped_duplicate: "text-parchment-500 bg-white/5",
};

const STATUS_LABEL = {
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  skipped_duplicate: "Duplicate — skipped",
};

export default function BulkHistoryItem({ item }) {
  const qc = useQueryClient();
  const dl = item.download;
  const canRetry =
    item.status === "failed" ||
    item.status === "cancelled" ||
    item.status === "skipped_duplicate";

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["bulk-items"] });
    qc.invalidateQueries({ queryKey: ["bulk-stats"] });
  };

  const retryMutation = useMutation({
    mutationFn: () => api.retryBulkItem(item.id),
    onSuccess: () => {
      toast.success("Re-queued");
      invalidate();
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => api.deleteBulkItem(item.id),
    onSuccess: invalidate,
  });

  return (
    <div className="panel p-3.5 flex gap-3.5 items-center">
      {dl?.thumbnail ? (
        <img
          src={dl.thumbnail}
          className="w-14 h-14 rounded-lg object-cover bg-ink-950 shrink-0"
          alt=""
        />
      ) : (
        <div className="w-14 h-14 rounded-lg bg-ink-950 shrink-0 flex items-center justify-center text-brass-600 font-display text-base">
          {item.media_type === "audio" ? "♪" : "▶"}
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium truncate">
            {dl?.title || item.url}
          </p>
          <span
            className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded shrink-0 ${STATUS_STYLE[item.status] || ""}`}
          >
            {STATUS_LABEL[item.status] || item.status}
          </span>
        </div>

        <p className="text-xs font-mono text-parchment-700 truncate mt-0.5">
          {dl?.uploader || item.url}
        </p>

        {item.error_message && (
          <p
            className="text-[11px] font-mono text-rust-400 mt-1 truncate"
            title={item.error_message}
          >
            {item.error_message}
          </p>
        )}

        {item.status === "completed" && dl?.library_path && (
          <p className="flex items-center gap-1.5 text-[11px] font-mono text-teal-400 mt-1.5">
            <Library className="w-3 h-3" /> In library: {dl.library_path}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 shrink-0">
        {canRetry && (
          <button className="btn-ghost" onClick={() => retryMutation.mutate()}>
            Retry
          </button>
        )}
        <button
          className="btn-ghost-danger"
          onClick={() => removeMutation.mutate()}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

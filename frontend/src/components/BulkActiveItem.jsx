import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api.js";
import { formatDuration } from "../utils.js";

const SEGMENTS = 24;

export default function BulkActiveItem({ item }) {
  const qc = useQueryClient();
  const dl = item.download;
  const pct = dl?.progress_percent || 0;
  const lit = Math.round((pct / 100) * SEGMENTS);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["bulk-items"] });
    qc.invalidateQueries({ queryKey: ["bulk-stats"] });
  };

  const cancelMutation = useMutation({ mutationFn: () => api.cancelBulkItem(item.id), onSuccess: invalidate });

  return (
    <div className="panel p-3.5 flex gap-3.5 items-center border-brass-700/60">
      {dl?.thumbnail ? (
        <img src={dl.thumbnail} className="w-16 h-16 rounded-lg object-cover bg-ink-950 shrink-0" alt="" />
      ) : (
        <div className="w-16 h-16 rounded-lg bg-ink-950 shrink-0 flex items-center justify-center text-brass-600 font-display text-lg">
          {item.media_type === "audio" ? "♪" : "▶"}
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium truncate">{dl?.title || item.url}</p>
          <span className="text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded shrink-0 text-brass-400 bg-brass-900/40">
            Downloading
          </span>
        </div>

        <p className="text-xs font-mono text-parchment-700 truncate mt-0.5">
          {dl?.uploader ? `${dl.uploader} · ` : ""}
          {dl?.duration ? formatDuration(dl.duration) : item.url}
        </p>

        <div className="flex gap-[3px] h-2 mt-2.5">
          {Array.from({ length: SEGMENTS }).map((_, i) => (
            <div
              key={i}
              className={`flex-1 rounded-sm border ${
                i < lit
                  ? "bg-brass-500 border-brass-500 shadow-[0_0_6px_rgba(217,164,65,0.5)]"
                  : "bg-ink-950 border-ink-600"
              }`}
            />
          ))}
        </div>

        <div className="flex justify-between mt-1.5 text-[10.5px] font-mono text-parchment-700">
          <span>{pct.toFixed(0)}%</span>
          <span>{dl?.speed ? `${dl.speed} ` : ""}{dl?.eta ? `ETA ${dl.eta}` : ""}</span>
        </div>
      </div>

      <button className="btn-ghost-danger shrink-0" onClick={() => cancelMutation.mutate()}>Cancel</button>
    </div>
  );
}

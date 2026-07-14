import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Library, ExternalLink, FileAudio, FileVideo } from "lucide-react";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";

const SEGMENTS = 24;

const STATUS_STYLE = {
  queued: "text-parchment-500 bg-white/5",
  converting: "text-teal-400 bg-teal-600/20",
  completed: "text-moss-400 bg-moss-500/10",
  failed: "text-rust-400 bg-rust-500/10",
  cancelled: "text-rust-400 bg-rust-500/10",
};

const STATUS_LABEL = {
  queued: "Queued",
  converting: "Converting",
  completed: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

const ACTIVE = new Set(["queued", "converting"]);
const AUDIO_EXT = new Set(["mp3", "m4a", "opus", "ogg", "flac", "wav"]);

export default function ConversionCard({ item }) {
  const qc = useQueryClient();
  const pct = item.progress_percent || 0;
  const lit = Math.round((pct / 100) * SEGMENTS);
  const isError = item.status === "failed" || item.status === "cancelled";
  const isComplete = item.status === "completed";
  const active = ACTIVE.has(item.status);
  const isAudio = AUDIO_EXT.has(item.target_format);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["conversions"] });
    qc.invalidateQueries({ queryKey: ["conversion-stats"] });
  };

  const cancelMutation = useMutation({ mutationFn: () => api.cancelConversion(item.id), onSuccess: invalidate });
  const deleteMutation = useMutation({ mutationFn: () => api.deleteConversion(item.id), onSuccess: invalidate });

  return (
    <div className="panel p-3.5 flex gap-3.5 items-center">
      <div className="w-16 h-16 rounded-lg bg-ink-950 shrink-0 flex items-center justify-center text-brass-600">
        {isAudio ? <FileAudio className="w-6 h-6" strokeWidth={1.5} /> : <FileVideo className="w-6 h-6" strokeWidth={1.5} />}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium truncate">{item.source_filename}</p>
          <span className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded shrink-0 ${STATUS_STYLE[item.status] || ""}`}>
            {STATUS_LABEL[item.status] || item.status}
          </span>
        </div>

        <p className="text-xs font-mono text-parchment-700 truncate mt-0.5">
          {item.source_kind} → {item.target_format.toUpperCase()}
          {item.target_bitrate ? ` · ${item.target_bitrate}` : ""}
          {item.target_resolution && item.target_resolution !== "source" ? ` · ${item.target_resolution}p` : ""}
          {item.source_duration ? ` · ${formatDuration(item.source_duration)}` : ""}
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
                    : "bg-teal-500 border-teal-500 shadow-[0_0_6px_rgba(91,138,128,0.5)]"
                  : "bg-ink-950 border-ink-600"
              }`}
            />
          ))}
        </div>

        <div className="flex justify-between mt-1.5 text-[10.5px] font-mono text-parchment-700">
          <span>{active ? `${pct.toFixed(0)}%` : isComplete ? formatBytes(item.output_filesize) : ""}</span>
          <span>{item.speed ? `speed ${item.speed}` : ""}</span>
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
        {isComplete && !item.library_path && (
          <a href={api.conversionFileUrl(item.id)} download className="btn-ghost flex items-center gap-1 justify-center">
            <ExternalLink className="w-3 h-3" /> Save
          </a>
        )}
        {active && (
          <button className="btn-ghost-danger" onClick={() => cancelMutation.mutate()}>Cancel</button>
        )}
        <button className="btn-ghost-danger" onClick={() => deleteMutation.mutate()}>Remove</button>
      </div>
    </div>
  );
}

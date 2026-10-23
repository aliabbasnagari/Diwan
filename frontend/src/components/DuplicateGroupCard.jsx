import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Star, Library } from "lucide-react";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";

const CATEGORY_STYLE = {
  exact: "text-moss-400 bg-moss-500/10",
  audio_match: "text-teal-400 bg-teal-600/20",
  near_match: "text-brass-400 bg-brass-900/40",
  different_recording: "text-parchment-500 bg-white/5",
};

const CATEGORY_LABEL = {
  exact: "Exact duplicate",
  audio_match: "Audio match",
  near_match: "Near match",
  different_recording: "Different recording",
};

export default function DuplicateGroupCard({ group }) {
  const qc = useQueryClient();
  const suggested = group.members.find((m) => m.is_suggested_keeper) || group.members[0];
  const [keeperPath, setKeeperPath] = useState(suggested?.path);
  const [confirming, setConfirming] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["duplicate-groups"] });

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveDuplicateGroup(group.id, keeperPath),
    onSuccess: (res) => {
      toast.success(`Kept 1, quarantined ${res.quarantined.length}`);
      setConfirming(false);
      invalidate();
    },
    onError: (e) => toast.error(e.message),
  });

  const ignoreMutation = useMutation({
    mutationFn: () => api.ignoreDuplicateGroup(group.id),
    onSuccess: () => { toast.success("Marked as not duplicates"); invalidate(); },
    onError: (e) => toast.error(e.message),
  });

  const actionable = group.status === "pending";
  const isInformational = group.category === "different_recording";

  return (
    <div className="panel p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded ${CATEGORY_STYLE[group.category] || ""}`}>
          {CATEGORY_LABEL[group.category] || group.category}
        </span>
        <span className="text-[10.5px] font-mono text-parchment-700">{group.members.length} files</span>
      </div>

      <div className="space-y-2">
        {group.members.map((m) => (
          <div key={m.id} className="flex items-center gap-3 rounded-lg border border-ink-600 p-2.5">
            {!isInformational && (
              <input
                type="radio"
                className="shrink-0"
                checked={keeperPath === m.path}
                onChange={() => setKeeperPath(m.path)}
                disabled={!actionable}
              />
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <p className="text-sm font-medium truncate">{m.title || m.path}</p>
                {m.is_suggested_keeper && (
                  <span title="Suggested keeper"><Star className="w-3 h-3 text-brass-400 shrink-0" /></span>
                )}
              </div>
              <p className="text-[11px] font-mono text-parchment-700 truncate mt-0.5">
                {m.artist ? `${m.artist} · ` : ""}{m.album ? `${m.album} · ` : ""}{m.path}
              </p>
              <p className="text-[10.5px] font-mono text-parchment-700 mt-0.5">
                {m.duration ? formatDuration(m.duration) : "—"}
                {" · "}{(m.path.split(".").pop() || "").toUpperCase()}
                {m.bitrate ? ` · ${Math.round(m.bitrate / 1000)}kbps` : ""}
                {m.sample_rate ? ` · ${(m.sample_rate / 1000).toFixed(1)}kHz` : ""}
                {m.filesize ? ` · ${formatBytes(m.filesize)}` : ""}
              </p>
              <audio controls preload="none" className="w-full h-8 mt-1.5" src={api.trackAudioUrl(m.track_id)} />
            </div>
          </div>
        ))}
      </div>

      {actionable && (
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost" onClick={() => ignoreMutation.mutate()} disabled={ignoreMutation.isPending}>
            Not duplicates
          </button>
          {!isInformational && (
            confirming ? (
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-parchment-700">Quarantine the rest?</span>
                <button className="btn-ghost" onClick={() => setConfirming(false)} disabled={resolveMutation.isPending}>
                  Cancel
                </button>
                <button className="btn-ghost-danger" onClick={() => resolveMutation.mutate()} disabled={resolveMutation.isPending}>
                  {resolveMutation.isPending ? "Quarantining…" : "Confirm"}
                </button>
              </div>
            ) : (
              <button className="btn-primary flex items-center gap-1.5" onClick={() => setConfirming(true)}>
                <Library className="w-3.5 h-3.5" /> Keep selected
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}

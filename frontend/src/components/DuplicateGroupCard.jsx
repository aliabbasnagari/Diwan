import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Star, Trash2, EyeOff } from "lucide-react";
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

const LOSSLESS_EXTS = new Set(["flac", "wav", "alac", "ape"]);

function extOf(path) {
  return (path.split(".").pop() || "").toLowerCase();
}

export default function DuplicateGroupCard({ group }) {
  const qc = useQueryClient();
  const isInformational = group.category === "different_recording";

  // Which member paths are marked "keep" — everything else gets quarantined
  // on Apply. Exact/audio/near matches start with only the suggested keeper
  // kept; "different recording" starts with everyone kept (likely not a
  // real duplicate at all), so Apply is a no-op until the user says otherwise.
  const [keep, setKeep] = useState(() => {
    if (isInformational) return new Set(group.members.map((m) => m.path));
    const suggested = group.members.find((m) => m.is_suggested_keeper) || group.members[0];
    return new Set([suggested?.path]);
  });

  const removeCount = group.members.length - keep.size;
  const spaceToFree = useMemo(
    () => group.members.filter((m) => !keep.has(m.path)).reduce((sum, m) => sum + (m.filesize || 0), 0),
    [group.members, keep]
  );

  function toggle(path, nextKeep) {
    setKeep((prev) => {
      const next = new Set(prev);
      if (nextKeep) {
        next.add(path);
      } else {
        if (next.size <= 1 && next.has(path)) {
          toast.message("At least one file has to stay — use \"Not a duplicate\" to keep them all");
          return prev;
        }
        next.delete(path);
      }
      return next;
    });
  }

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["duplicate-groups"] });
    qc.invalidateQueries({ queryKey: ["duplicate-trash"] });
  };

  const resolveMutation = useMutation({
    mutationFn: () => api.resolveDuplicateGroup(group.id, Array.from(keep)),
    onSuccess: (res) => {
      toast.success(`Kept ${res.kept.length}, quarantined ${res.quarantined.length}`);
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
  const busy = resolveMutation.isPending || ignoreMutation.isPending;

  return (
    <div className="panel p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[10px] font-mono uppercase tracking-wide px-2 py-0.5 rounded ${CATEGORY_STYLE[group.category] || ""}`}>
          {CATEGORY_LABEL[group.category] || group.category}
        </span>
        <span className="text-[10.5px] font-mono text-parchment-700">{group.members.length} files</span>
      </div>

      {isInformational && (
        <p className="text-[11px] font-mono text-parchment-700 leading-relaxed">
          Same title/artist but the audio doesn't match closely — likely a live version, remaster,
          remix, or cover. Probably not a real duplicate; left as-is unless you say otherwise below.
        </p>
      )}

      <div className="space-y-2">
        {group.members.map((m) => {
          const isKeep = keep.has(m.path);
          const ext = extOf(m.path);
          return (
            <div
              key={m.id}
              className={`flex items-center gap-3 rounded-lg border p-2.5 transition ${
                isKeep ? "border-ink-600" : "border-rust-700/40 bg-rust-500/[0.04] opacity-80"
              }`}
            >
              {actionable && (
                <div className="shrink-0 flex rounded-md overflow-hidden border border-ink-600 text-[10px] font-mono uppercase">
                  <button
                    onClick={() => toggle(m.path, true)}
                    className={`px-2 py-1 transition ${isKeep ? "bg-moss-600 text-parchment-100" : "text-parchment-500 hover:text-parchment-100"}`}
                  >
                    Keep
                  </button>
                  <button
                    onClick={() => toggle(m.path, false)}
                    className={`px-2 py-1 transition ${!isKeep ? "bg-rust-600 text-parchment-100" : "text-parchment-500 hover:text-parchment-100"}`}
                  >
                    Remove
                  </button>
                </div>
              )}

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="text-sm font-medium truncate">{m.title || m.path}</p>
                  <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-ink-950 text-parchment-500 shrink-0">
                    {ext}
                  </span>
                  {m.is_suggested_keeper && (
                    <span title="Suggested keeper" className="shrink-0">
                      <Star className="w-3 h-3 text-brass-400 fill-brass-400" />
                    </span>
                  )}
                </div>
                <p className="text-[11px] font-mono text-parchment-700 truncate mt-0.5">
                  {m.artist ? `${m.artist} · ` : ""}{m.album ? `${m.album} · ` : ""}{m.path}
                </p>
                <p className="text-[10.5px] font-mono text-parchment-700 mt-0.5">
                  {m.duration ? formatDuration(m.duration) : "—"}
                  {LOSSLESS_EXTS.has(ext) ? " · lossless" : ""}
                  {m.bitrate ? ` · ${Math.round(m.bitrate / 1000)}kbps` : ""}
                  {m.sample_rate ? ` · ${(m.sample_rate / 1000).toFixed(1)}kHz` : ""}
                  {m.filesize ? ` · ${formatBytes(m.filesize)}` : ""}
                </p>
                <audio controls preload="none" className="w-full h-8 mt-1.5" src={api.trackAudioUrl(m.track_id)} />
              </div>
            </div>
          );
        })}
      </div>

      {actionable && (
        <div className="flex justify-end items-center gap-2 pt-1">
          <button
            className="btn-ghost flex items-center gap-1.5"
            onClick={() => ignoreMutation.mutate()}
            disabled={busy}
          >
            <EyeOff className="w-3.5 h-3.5" /> Not a duplicate
          </button>
          <button
            className="btn-primary flex items-center gap-1.5"
            onClick={() => resolveMutation.mutate()}
            disabled={busy || removeCount === 0}
            title={removeCount === 0 ? "Mark at least one file to remove, or use \"Not a duplicate\"" : undefined}
          >
            <Trash2 className="w-3.5 h-3.5" />
            {resolveMutation.isPending
              ? "Applying…"
              : removeCount === 0
                ? "Nothing to remove"
                : `Remove ${removeCount} · free ${formatBytes(spaceToFree)}`}
          </button>
        </div>
      )}
    </div>
  );
}

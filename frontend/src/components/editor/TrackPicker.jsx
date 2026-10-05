import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../../api.js";
import { formatDuration } from "../../utils.js";

export default function TrackPicker({ onPick, busy }) {
  const [q, setQ] = useState("");
  const { data: tracks = [], isLoading } = useQuery({
    queryKey: ["library-tracks-flat"],
    queryFn: () => api.libraryTracks(),
  });

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = needle
      ? tracks.filter((t) => `${t.title} ${t.artist} ${t.album}`.toLowerCase().includes(needle))
      : tracks;
    return list.slice(0, 200);
  }, [tracks, q]);

  return (
    <div className="panel p-5">
      <div className="relative mb-4">
        <Search className="w-4 h-4 text-parchment-700 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          className="input w-full !pl-9"
          placeholder="Search your library for a track to edit…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
      </div>

      {isLoading ? (
        <p className="text-sm font-mono text-parchment-700 py-8 text-center">Loading library…</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm font-mono text-parchment-700 py-8 text-center">No tracks match.</p>
      ) : (
        <div className="max-h-[28rem] overflow-y-auto divide-y divide-ink-600/60">
          {filtered.map((t) => (
            <button
              key={t.id}
              disabled={busy}
              onClick={() => onPick(t.id)}
              className="w-full flex items-center gap-3 px-2 py-2.5 text-left hover:bg-ink-700 rounded transition disabled:opacity-50"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-sm truncate">{t.title}</span>
                <span className="block text-xs font-mono text-parchment-500 truncate">{t.artist} · {t.album}</span>
              </span>
              <span className="text-xs font-mono text-parchment-700 shrink-0">
                {t.ext?.toUpperCase()} · {formatDuration(t.duration)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

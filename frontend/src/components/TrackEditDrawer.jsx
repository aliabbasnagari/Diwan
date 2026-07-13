import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Trash2, FolderTree, Upload } from "lucide-react";
import { toast } from "sonner";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";

const FIELDS = [
  { key: "title", label: "Title" },
  { key: "artist", label: "Artist" },
  { key: "album", label: "Album" },
  { key: "albumartist", label: "Album artist" },
  { key: "genre", label: "Genre" },
  { key: "date", label: "Year" },
  { key: "tracknumber", label: "Track #" },
  { key: "discnumber", label: "Disc #" },
];

export default function TrackEditDrawer({ track, onClose }) {
  const [form, setForm] = useState({});
  const [reorganize, setReorganize] = useState(true);
  const fileInputRef = useRef(null);
  const qc = useQueryClient();

  useEffect(() => {
    if (track) {
      setForm({
        title: track.title || "",
        artist: track.artist || "",
        album: track.album || "",
        albumartist: track.albumartist || "",
        genre: track.genre || "",
        date: track.date || "",
        tracknumber: track.tracknumber || "",
        discnumber: track.discnumber || "",
      });
    }
  }, [track]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["library-tree"] });
    qc.invalidateQueries({ queryKey: ["library-search"] });
    qc.invalidateQueries({ queryKey: ["library-stats"] });
  };

  const saveMutation = useMutation({
    mutationFn: () => api.updateTrack(track.id, { ...form, reorganize }),
    onSuccess: () => {
      toast.success("Tags saved");
      invalidate();
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteTrack(track.id),
    onSuccess: () => {
      toast.success("Track deleted");
      invalidate();
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });

  const organizeMutation = useMutation({
    mutationFn: () => api.organizeTrack(track.id),
    onSuccess: (updated) => {
      toast.success(updated.path === track.path ? "Already in the right place" : `Moved to ${updated.path}`);
      invalidate();
    },
    onError: (e) => toast.error(e.message),
  });

  const artworkMutation = useMutation({
    mutationFn: (file) => api.uploadArtwork(track.id, file),
    onSuccess: () => {
      toast.success("Artwork updated");
      invalidate();
    },
    onError: (e) => toast.error(e.message),
  });

  if (!track) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-md h-full bg-ink-800 border-l border-ink-600 flex flex-col animate-in slide-in-from-right">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <h2 className="font-display font-semibold text-sm">Edit track</h2>
          <button onClick={onClose} className="text-parchment-500 hover:text-parchment-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-6">
          <div className="flex items-center gap-4">
            <div
              className="w-20 h-20 rounded-lg bg-ink-950 ring-1 ring-black/40 bg-cover bg-center shrink-0 cursor-pointer relative group"
              style={track.has_art ? { backgroundImage: `url(${api.artworkUrl(track.id)})` } : {}}
              onClick={() => fileInputRef.current?.click()}
              title="Click to replace artwork"
            >
              {!track.has_art && (
                <div className="w-full h-full flex items-center justify-center text-parchment-700 font-display text-lg">♪</div>
              )}
              <div className="absolute inset-0 rounded-lg bg-black/0 group-hover:bg-black/50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                <Upload className="w-5 h-5 text-parchment-100" />
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) artworkMutation.mutate(file);
                e.target.value = "";
              }}
            />
            <div className="text-xs font-mono text-parchment-500 space-y-1 min-w-0">
              <p className="truncate" title={track.path}>{track.path}</p>
              <p>{formatDuration(track.duration)} · {formatBytes(track.filesize)} · {track.ext?.toUpperCase()}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {FIELDS.map((f) => (
              <label key={f.key} className={f.key === "title" || f.key === "artist" || f.key === "album" ? "col-span-2" : ""}>
                <span className="label-eyebrow block mb-1">{f.label}</span>
                <input
                  className="input w-full"
                  value={form[f.key] ?? ""}
                  onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                />
              </label>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs font-mono text-parchment-500 cursor-pointer">
            <input type="checkbox" checked={reorganize} onChange={(e) => setReorganize(e.target.checked)} />
            Move file to match Artist/Album/Title on save
          </label>
        </div>

        <div className="px-5 py-4 border-t border-ink-600 flex items-center gap-2">
          <button className="btn-primary flex-1" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? "Saving…" : "Save changes"}
          </button>
          <button
            className="btn-ghost flex items-center gap-1.5"
            onClick={() => organizeMutation.mutate()}
            disabled={organizeMutation.isPending}
            title="Re-organize file into Artist/Album/Title now"
          >
            <FolderTree className="w-3.5 h-3.5" />
          </button>
          <button
            className="btn-ghost-danger flex items-center gap-1.5"
            onClick={() => {
              if (confirm(`Delete "${track.title}"? This removes the file from disk.`)) deleteMutation.mutate();
            }}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

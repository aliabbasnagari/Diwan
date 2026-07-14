import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, RefreshCw, FolderTree, ChevronDown, ChevronRight, Music2, ImagePlus, User } from "lucide-react";
import { toast } from "sonner";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";
import AlbumArt from "../components/AlbumArt.jsx";
import TrackEditDrawer from "../components/TrackEditDrawer.jsx";

export default function LibraryPage() {
  const [search, setSearch] = useState("");
  const [openArtists, setOpenArtists] = useState(() => new Set());
  const [activeTrack, setActiveTrack] = useState(null);
  const qc = useQueryClient();

  const treeQuery = useQuery({
    queryKey: ["library-tree"],
    queryFn: api.libraryTree,
    enabled: !search.trim(),
  });

  const searchQuery = useQuery({
    queryKey: ["library-search", search],
    queryFn: () => api.libraryTracks(search.trim()),
    enabled: !!search.trim(),
  });

  const statsQuery = useQuery({ queryKey: ["library-stats"], queryFn: api.libraryStats });

  const organizeMutation = useMutation({
    mutationFn: () => api.organizeLibrary(),
    onSuccess: (res) => {
      toast.success(`Organized: ${res.moved} moved, ${res.unchanged} already tidy${res.errors.length ? `, ${res.errors.length} errors` : ""}`);
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["library-tree"] });
    qc.invalidateQueries({ queryKey: ["library-search"] });
    qc.invalidateQueries({ queryKey: ["library-stats"] });
  }

  function toggleArtist(name) {
    setOpenArtists((s) => {
      const next = new Set(s);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  const stats = statsQuery.data;
  const isSearching = !!search.trim();
  const tree = treeQuery.data;

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-6">
        <div>
          <h1 className="font-display font-bold text-2xl">Library</h1>
          <p className="text-sm text-parchment-500 mt-1">Browse and edit the music Navidrome serves.</p>
        </div>
        <div className="flex gap-4 font-mono text-right">
          <StatPill label="Artists" value={stats?.artist_count} />
          <StatPill label="Albums" value={stats?.album_count} />
          <StatPill label="Tracks" value={stats?.track_count} />
          <StatPill label="Size" value={stats ? formatBytes(stats.total_size) : "—"} />
        </div>
      </header>

      <div className="flex items-center gap-2 mb-6">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-parchment-700" />
          <input
            className="input w-full pl-10"
            placeholder="Search title, artist, album…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button className="btn-ghost flex items-center gap-1.5" onClick={refresh}>
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
        <button
          className="btn-ghost flex items-center gap-1.5"
          onClick={() => organizeMutation.mutate()}
          disabled={organizeMutation.isPending}
          title="Move every track to match its tags (Artist/Album/Title)"
        >
          <FolderTree className="w-3.5 h-3.5" /> {organizeMutation.isPending ? "Organizing…" : "Organize all"}
        </button>
      </div>

      {isSearching ? (
        <SearchResults data={searchQuery.data} loading={searchQuery.isLoading} onOpen={setActiveTrack} />
      ) : (
        <ArtistTree
          tree={tree}
          loading={treeQuery.isLoading}
          openArtists={openArtists}
          onToggleArtist={toggleArtist}
          onOpenTrack={setActiveTrack}
          onChanged={refresh}
        />
      )}

      <TrackEditDrawer track={activeTrack} onClose={() => setActiveTrack(null)} />
    </div>
  );
}

function StatPill({ label, value }) {
  return (
    <div>
      <div className="text-lg font-bold text-brass-400 leading-none">{value ?? "—"}</div>
      <div className="text-[10px] uppercase tracking-wider text-parchment-700 mt-1">{label}</div>
    </div>
  );
}

function SearchResults({ data, loading, onOpen }) {
  if (loading) return <EmptyState text="Searching…" />;
  if (!data || data.length === 0) return <EmptyState text="No matching tracks." />;
  return (
    <div className="panel divide-y divide-ink-600">
      {data.map((t) => (
        <TrackRow key={t.id} track={t} onOpen={() => onOpen(t)} showAlbum />
      ))}
    </div>
  );
}

function ArtistTree({ tree, loading, openArtists, onToggleArtist, onOpenTrack, onChanged }) {
  if (loading) return <EmptyState text="Reading your library…" />;
  if (!tree || tree.artist_count === 0) {
    return (
      <EmptyState text="Nothing here yet — grab something from the Spooler, or point Library path at an existing collection in Settings." />
    );
  }

  return (
    <div className="space-y-3">
      {tree.artists.map((artist) => {
        const open = openArtists.has(artist.name);
        return (
          <div key={artist.id} className="panel overflow-hidden">
            <div className="w-full flex items-center justify-between px-4 py-3 hover:bg-ink-700/50 transition">
              <button className="flex items-center gap-2.5 flex-1 min-w-0" onClick={() => onToggleArtist(artist.name)}>
                {open ? <ChevronDown className="w-4 h-4 text-parchment-500 shrink-0" /> : <ChevronRight className="w-4 h-4 text-parchment-500 shrink-0" />}
                <ArtistAvatar artist={artist} />
                <span className="font-display font-semibold text-sm truncate">{artist.name}</span>
              </button>
              <div className="flex items-center gap-3 shrink-0">
                <ArtUploadButton
                  title="Upload artist picture"
                  onUpload={(file) =>
                    api.uploadArtistPicture(artist.id, file).then(() => {
                      toast.success("Artist picture updated");
                      onChanged();
                    }).catch((e) => toast.error(e.message))
                  }
                />
                <span className="text-xs font-mono text-parchment-700">
                  {artist.album_count} album{artist.album_count === 1 ? "" : "s"} · {artist.track_count} track{artist.track_count === 1 ? "" : "s"}
                </span>
              </div>
            </div>

            {open && (
              <div className="border-t border-ink-600 divide-y divide-ink-600">
                {artist.albums.map((album) => (
                  <div key={album.id} className="px-4 py-3">
                    <div className="flex items-center gap-3 mb-2">
                      <AlbumArt
                        src={
                          album.has_folder_art || album.tracks[0]?.has_art
                            ? api.albumArtworkUrl(album.id)
                            : null
                        }
                        size="md"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{album.name}</p>
                        <p className="text-xs font-mono text-parchment-700">{album.track_count} track{album.track_count === 1 ? "" : "s"}</p>
                      </div>
                      <ArtUploadButton
                        title="Upload album art (writes cover.jpg + embeds into every track)"
                        onUpload={(file) =>
                          api.uploadAlbumArtwork(album.id, file).then((res) => {
                            toast.success(`Album art updated — embedded in ${res.tracks_embedded} track${res.tracks_embedded === 1 ? "" : "s"}`);
                            onChanged();
                          }).catch((e) => toast.error(e.message))
                        }
                      />
                    </div>
                    <div className="rounded-lg overflow-hidden border border-ink-600 divide-y divide-ink-600">
                      {album.tracks.map((t) => (
                        <TrackRow key={t.id} track={t} onOpen={() => onOpenTrack(t)} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ArtistAvatar({ artist }) {
  if (artist.has_picture) {
    return (
      <img
        src={api.artistPictureUrl(artist.id)}
        alt=""
        className="w-6 h-6 rounded-full object-cover ring-1 ring-black/40 shrink-0"
      />
    );
  }
  return (
    <div className="w-6 h-6 rounded-full bg-ink-700 flex items-center justify-center shrink-0">
      <User className="w-3.5 h-3.5 text-parchment-700" strokeWidth={1.75} />
    </div>
  );
}

function ArtUploadButton({ onUpload, title }) {
  const inputRef = useRef(null);
  return (
    <>
      <button
        className="text-parchment-700 hover:text-brass-400 transition p-1"
        title={title}
        onClick={(e) => {
          e.stopPropagation();
          inputRef.current?.click();
        }}
      >
        <ImagePlus className="w-4 h-4" strokeWidth={1.75} />
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
          e.target.value = "";
        }}
      />
    </>
  );
}

function TrackRow({ track, onOpen, showAlbum }) {
  return (
    <button
      onClick={onOpen}
      className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-ink-700/60 transition text-left bg-ink-800"
    >
      <span className="font-mono text-xs text-parchment-700 w-6 text-right shrink-0">
        {track.tracknumber ? String(track.tracknumber).split("/")[0].padStart(2, "0") : "—"}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm truncate">{track.title}</p>
        {showAlbum && (
          <p className="text-xs font-mono text-parchment-700 truncate">{track.artist} · {track.album}</p>
        )}
      </div>
      <span className="text-xs font-mono text-parchment-700 shrink-0">{formatDuration(track.duration)}</span>
    </button>
  );
}

function EmptyState({ text }) {
  return (
    <div className="text-center py-16 px-6 border border-dashed border-ink-600 rounded-xl text-parchment-700 font-mono text-sm">
      {text}
    </div>
  );
}

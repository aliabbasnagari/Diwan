import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search, Download as DownloadIcon, AlertTriangle } from "lucide-react";
import { api } from "../api.js";
import { formatDuration, formatBytes } from "../utils.js";

const AUDIO_FORMATS = ["mp3", "m4a", "opus", "wav", "flac"];

function normalizeUrl(u) {
  if (!u) return "";
  let s = u.trim().toLowerCase();
  s = s.replace(/\/+$/, ""); // trailing slash
  s = s.replace(/^https?:\/\/(www\.)?/, "");
  return s;
}

export default function UrlForm({ downloads = [] }) {
  const [url, setUrl] = useState("");
  const [mediaType, setMediaType] = useState("audio");
  const [quality, setQuality] = useState("best");
  const [audioFormat, setAudioFormat] = useState("mp3");
  const [subtitles, setSubtitles] = useState(false);
  const [addToLibrary, setAddToLibrary] = useState(true);

  const [tagTitle, setTagTitle] = useState("");
  const [tagArtist, setTagArtist] = useState("");
  const [tagAlbumArtist, setTagAlbumArtist] = useState("");
  const [tagAlbum, setTagAlbum] = useState("");
  const [tagGenre, setTagGenre] = useState("");
  const [tagYear, setTagYear] = useState("");

  const [preview, setPreview] = useState(null);
  const [fetched, setFetched] = useState(false);
  const qc = useQueryClient();

  const { data: suggestions } = useQuery({
    queryKey: ["tag-suggestions"],
    queryFn: api.getTagSuggestions,
    staleTime: 60_000,
  });

  const duplicate = useMemo(() => {
    const norm = normalizeUrl(url);
    if (!norm) return null;
    return downloads.find((d) => normalizeUrl(d.url) === norm || normalizeUrl(d.webpage_url) === norm) || null;
  }, [url, downloads]);

  const fetchMutation = useMutation({
    mutationFn: () => api.preview(url.trim()),
    onSuccess: (info) => {
      setPreview(info);
      const qualities = info.video_qualities || [{ value: "best", label: "Best available" }];
      setQuality(qualities[0].value);

      setTagTitle(info.track || info.title || "");
      setTagArtist(info.artist || "");
      setTagAlbumArtist(info.album_artist || info.artist || "");
      setTagAlbum(info.album || "");
      setTagGenre(info.genre || "");
      setTagYear(info.release_year || info.year || info.upload_date || "");

      setFetched(true);
    },
    onError: (e) => toast.error(e.message),
  });

  const downloadMutation = useMutation({
    mutationFn: () =>
      api.createDownload({
        url: url.trim(),
        media_type: mediaType,
        quality: mediaType === "video" ? quality : "best",
        audio_format: audioFormat,
        subtitles,
        add_to_library: mediaType === "audio" && addToLibrary,
        tag_title: tagTitle || null,
        tag_artist: tagArtist || null,
        tag_album_artist: tagAlbumArtist || null,
        tag_album: tagAlbum || null,
        tag_genre: tagGenre || null,
        tag_year: tagYear || null,
      }),
    onSuccess: () => {
      toast.success("Queued");
      setUrl("");
      setPreview(null);
      setFetched(false);
      qc.invalidateQueries({ queryKey: ["downloads"] });
      qc.invalidateQueries({ queryKey: ["download-stats"] });
      qc.invalidateQueries({ queryKey: ["tag-suggestions"] });
    },
    onError: (e) => toast.error(e.message),
  });

  function handleUrlChange(e) {
    setUrl(e.target.value);
    if (fetched) setFetched(false);
    setPreview(null);
  }

  function handleKeyDown(e) {
    if (e.key !== "Enter") return;
    if (fetched) downloadMutation.mutate();
    else if (url.trim()) fetchMutation.mutate();
  }

  const qualities = preview?.video_qualities || [];

  return (
    <div className="panel p-5">
      <div className="flex gap-2">
        <input
          className="input flex-1"
          placeholder="Paste a video / audio URL…"
          value={url}
          onChange={handleUrlChange}
          onKeyDown={handleKeyDown}
        />
        {!fetched ? (
          <button
            className="btn-primary flex items-center gap-1.5 shrink-0"
            onClick={() => fetchMutation.mutate()}
            disabled={fetchMutation.isPending || !url.trim()}
          >
            <Search className="w-3.5 h-3.5" /> {fetchMutation.isPending ? "Fetching…" : "Fetch"}
          </button>
        ) : (
          <button
            className="btn-primary flex items-center gap-1.5 shrink-0"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
          >
            <DownloadIcon className="w-3.5 h-3.5" /> {downloadMutation.isPending ? "Queuing…" : "Download"}
          </button>
        )}
      </div>

      {duplicate && (
        <div className="mt-2.5 flex items-center gap-2 text-xs font-mono px-3 py-2 rounded-lg bg-brass-900/30 border border-brass-700/50 text-brass-400">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">
            {duplicate.status === "completed"
              ? "Already downloaded"
              : duplicate.status === "failed" || duplicate.status === "cancelled"
                ? "Already in history (failed/cancelled)"
                : "Already in the spool"}
            {duplicate.title ? ` — “${duplicate.title}”` : ""}
          </span>
        </div>
      )}

      {fetched && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex border border-ink-600 rounded-lg overflow-hidden">
              {["video", "audio"].map((t) => (
                <button
                  key={t}
                  onClick={() => setMediaType(t)}
                  className={`px-4 py-2 text-xs font-semibold uppercase tracking-wide ${mediaType === t ? "bg-brass-600 text-parchment-100" : "text-parchment-500 hover:text-parchment-100"
                    }`}
                >
                  {t === "video" ? "Video" : "Audio only"}
                </button>
              ))}
            </div>

            {mediaType === "video" ? (
              <select className="select" value={quality} onChange={(e) => setQuality(e.target.value)}>
                {qualities.map((q) => (
                  <option key={q.value} value={q.value}>
                    {q.label}
                    {q.filesize ? ` · ${formatBytes(q.filesize)}` : ""}
                  </option>
                ))}
              </select>
            ) : (
              <select className="select" value={audioFormat} onChange={(e) => setAudioFormat(e.target.value)}>
                {AUDIO_FORMATS.map((f) => (
                  <option key={f} value={f}>{f.toUpperCase()}</option>
                ))}
              </select>
            )}

            {mediaType === "video" && (
              <label className="flex items-center gap-2 text-xs font-mono text-parchment-500 cursor-pointer">
                <input type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} />
                Subtitles (en)
              </label>
            )}
          </div>

          {mediaType === "audio" && (
            <div className="rounded-lg border border-ink-600 p-3.5 space-y-3">
              <label className="flex items-center gap-2 text-xs font-mono text-parchment-300 cursor-pointer">
                <input type="checkbox" checked={addToLibrary} onChange={(e) => setAddToLibrary(e.target.checked)} />
                Add to library after download (tagged &amp; organized for Navidrome)
              </label>
              {addToLibrary && (
                <div className="grid grid-cols-3 gap-2">
                  <input
                    className="input"
                    placeholder="Title"
                    value={tagTitle}
                    onChange={(e) => setTagTitle(e.target.value)}
                  />
                  <input
                    className="input"
                    placeholder="Artist"
                    list="artist-suggestions"
                    value={tagArtist}
                    onChange={(e) => setTagArtist(e.target.value)}
                  />
                  <input
                    className="input"
                    placeholder="Album Artist"
                    list="album-artist-suggestions"
                    value={tagAlbumArtist}
                    onChange={(e) => setTagAlbumArtist(e.target.value)}
                  />
                  <input
                    className="input"
                    placeholder="Album"
                    list="album-suggestions"
                    value={tagAlbum}
                    onChange={(e) => setTagAlbum(e.target.value)}
                  />
                  <input
                    className="input"
                    placeholder="Genre"
                    list="genre-suggestions"
                    value={tagGenre}
                    onChange={(e) => setTagGenre(e.target.value)}
                  />
                  <input
                    className="input"
                    type="number"
                    placeholder="Year"
                    list="year-suggestions"
                    value={tagYear}
                    onChange={(e) => setTagYear(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3 items-center bg-ink-950 border border-ink-600 rounded-lg p-3">
            {preview?.thumbnail && <img src={preview.thumbnail} alt="" className="w-24 h-14 object-cover rounded-md shrink-0" />}
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{preview?.title || "Untitled"}</p>
              <p className="text-xs font-mono text-parchment-500">
                {preview?.uploader ? `${preview.uploader} · ` : ""}
                {preview?.extractor || "unknown source"}
                {preview?.duration ? ` · ${formatDuration(preview.duration)}` : ""}
              </p>
            </div>
          </div>
        </div>
      )}

      <datalist id="artist-suggestions">
        {(suggestions?.artist || []).map((v) => <option key={v} value={v} />)}
      </datalist>
      <datalist id="album-artist-suggestions">
        {(suggestions?.album_artist || []).map((v) => <option key={v} value={v} />)}
      </datalist>
      <datalist id="album-suggestions">
        {(suggestions?.album || []).map((v) => <option key={v} value={v} />)}
      </datalist>
      <datalist id="genre-suggestions">
        {(suggestions?.genre || []).map((v) => <option key={v} value={v} />)}
      </datalist>
      <datalist id="year-suggestions">
        {(suggestions?.year || []).map((v) => <option key={v} value={v} />)}
      </datalist>
    </div>
  );
}
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ListPlus } from "lucide-react";
import { api } from "../api.js";
import SuggestInput from "./SuggestInput.jsx";
import Labeled from "./Labeled.jsx";

const AUDIO_FORMATS = ["mp3", "m4a", "opus", "wav", "flac"];

export default function BulkUrlForm() {
  const [urlsText, setUrlsText] = useState("");
  const [mediaType, setMediaType] = useState("audio");
  const [quality, setQuality] = useState("best");
  const [audioFormat, setAudioFormat] = useState("mp3");
  const [subtitles, setSubtitles] = useState(false);
  const [addToLibrary, setAddToLibrary] = useState(true);

  const [tagArtist, setTagArtist] = useState("");
  const [tagAlbumArtist, setTagAlbumArtist] = useState("");
  const [tagAlbum, setTagAlbum] = useState("");
  const [tagGenre, setTagGenre] = useState("");
  const [tagYear, setTagYear] = useState("");

  const qc = useQueryClient();

  const { data: suggestions } = useQuery({
    queryKey: ["tag-suggestions"],
    queryFn: api.getTagSuggestions,
    staleTime: 60_000,
  });

  const urlCount = urlsText.split("\n").map((s) => s.trim()).filter(Boolean).length;

  const submitMutation = useMutation({
    mutationFn: () =>
      api.createBulkItems({
        urls: urlsText.split("\n"),
        media_type: mediaType,
        quality: mediaType === "video" ? quality : "best",
        audio_format: audioFormat,
        subtitles,
        add_to_library: mediaType === "audio" && addToLibrary,
        tag_artist: tagArtist || null,
        tag_album_artist: tagAlbumArtist || null,
        tag_album: tagAlbum || null,
        tag_genre: tagGenre || null,
        tag_year: tagYear || null,
      }),
    onSuccess: (res) => {
      if (res.created) toast.success(`Queued ${res.created} URL${res.created === 1 ? "" : "s"}`);
      if (res.skipped_duplicates) toast.message(`Skipped ${res.skipped_duplicates} duplicate${res.skipped_duplicates === 1 ? "" : "s"}`);
      setUrlsText("");
      qc.invalidateQueries({ queryKey: ["bulk-items"] });
      qc.invalidateQueries({ queryKey: ["bulk-stats"] });
      qc.invalidateQueries({ queryKey: ["tag-suggestions"] });
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <div className="panel p-5 space-y-4">
      <Labeled label={`URLs (one per line)${urlCount ? ` · ${urlCount} queued` : ""}`}>
        <textarea
          className="input w-full font-mono text-xs min-h-[96px] resize-y"
          placeholder={"https://example.com/watch?v=...\nhttps://example.com/watch?v=...\n…"}
          value={urlsText}
          onChange={(e) => setUrlsText(e.target.value)}
        />
      </Labeled>

      <div className="flex items-end gap-3 flex-wrap">
        <div className="flex border border-ink-600 rounded-lg overflow-hidden">
          {["video", "audio"].map((t) => (
            <button
              key={t}
              onClick={() => setMediaType(t)}
              className={`px-4 py-2 text-xs font-semibold uppercase tracking-wide ${
                mediaType === t ? "bg-brass-600 text-parchment-100" : "text-parchment-500 hover:text-parchment-100"
              }`}
            >
              {t === "video" ? "Video" : "Audio only"}
            </button>
          ))}
        </div>

        {mediaType === "video" ? (
          <Labeled label="Quality">
            <select className="select" value={quality} onChange={(e) => setQuality(e.target.value)}>
              <option value="best">Best available</option>
              <option value="1080">1080p</option>
              <option value="720">720p</option>
              <option value="480">480p</option>
            </select>
          </Labeled>
        ) : (
          <Labeled label="Audio format">
            <select className="select" value={audioFormat} onChange={(e) => setAudioFormat(e.target.value)}>
              {AUDIO_FORMATS.map((f) => (
                <option key={f} value={f}>{f.toUpperCase()}</option>
              ))}
            </select>
          </Labeled>
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
            Add to library after each download (tagged &amp; organized for Navidrome)
          </label>
          {addToLibrary && (
            <>
              <p className="text-[10.5px] font-mono text-parchment-700">
                Optional — applied to every URL in this batch. Leave blank to use each track's own metadata.
              </p>
              <div className="grid grid-cols-4 gap-2">
                <SuggestInput
                  label="Artist"
                  placeholder="Artist"
                  suggestions={suggestions?.artist || []}
                  multi
                  value={tagArtist}
                  onChange={(e) => setTagArtist(e.target.value)}
                />
                <SuggestInput
                  label="Album artist"
                  placeholder="Album Artist"
                  suggestions={suggestions?.album_artist || []}
                  value={tagAlbumArtist}
                  onChange={(e) => setTagAlbumArtist(e.target.value)}
                />
                <SuggestInput
                  label="Album"
                  placeholder="Album"
                  suggestions={suggestions?.album || []}
                  value={tagAlbum}
                  onChange={(e) => setTagAlbum(e.target.value)}
                />
                <SuggestInput
                  label="Genre"
                  placeholder="Genre"
                  suggestions={suggestions?.genre || []}
                  value={tagGenre}
                  onChange={(e) => setTagGenre(e.target.value)}
                />
              </div>
            </>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <button
          className="btn-primary flex items-center gap-1.5"
          onClick={() => submitMutation.mutate()}
          disabled={submitMutation.isPending || urlCount === 0}
        >
          <ListPlus className="w-3.5 h-3.5" />
          {submitMutation.isPending ? "Queuing…" : `Add to bulk queue${urlCount ? ` (${urlCount})` : ""}`}
        </button>
      </div>
    </div>
  );
}

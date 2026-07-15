import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload, RefreshCcw as ConvertIcon } from "lucide-react";
import { api } from "../api.js";
import ConversionCard from "../components/ConversionCard.jsx";

const AUDIO_EXT = new Set(["mp3", "flac", "m4a", "ogg", "opus", "wav", "wma", "aac"]);
const ACTIVE = new Set(["queued", "converting"]);

export default function ConvertPage() {
  const qc = useQueryClient();
  const [sourceKind, setSourceKind] = useState("upload");
  const [file, setFile] = useState(null);
  const [libraryTrackId, setLibraryTrackId] = useState("");
  const [downloadId, setDownloadId] = useState("");
  const [targetFormat, setTargetFormat] = useState("mp3");
  const [targetBitrate, setTargetBitrate] = useState("192k");
  const [targetResolution, setTargetResolution] = useState("source");
  const [saveToLibrary, setSaveToLibrary] = useState(false);

  const formatsQuery = useQuery({ queryKey: ["convert-formats"], queryFn: api.convertFormats });
  const libraryQuery = useQuery({ queryKey: ["library-tracks-flat"], queryFn: () => api.libraryTracks(), enabled: sourceKind === "library" });
  const downloadsQuery = useQuery({ queryKey: ["downloads"], queryFn: api.listDownloads, enabled: sourceKind === "download" });

  const jobsQuery = useQuery({ queryKey: ["conversions"], queryFn: api.listConversions, refetchInterval: 1500 });
  const statsQuery = useQuery({ queryKey: ["conversion-stats"], queryFn: api.conversionStats, refetchInterval: 1500 });

  const completedDownloads = (downloadsQuery.data || []).filter((d) => d.status === "completed");

  // figure out whether the chosen source is audio or video, to pick which format list to show
  const isAudioSource = useMemo(() => {
    if (sourceKind === "library") return true;
    if (sourceKind === "upload" && file) {
      const ext = file.name.split(".").pop()?.toLowerCase();
      return AUDIO_EXT.has(ext);
    }
    if (sourceKind === "download" && downloadId) {
      const d = completedDownloads.find((x) => String(x.id) === downloadId);
      return d?.media_type === "audio";
    }
    return true;
  }, [sourceKind, file, downloadId, completedDownloads]);

  const audioFormats = Object.keys(formatsQuery.data?.audio || {});
  const videoFormats = formatsQuery.data?.video || [];
  const bitrates = formatsQuery.data?.audio_bitrates || [];
  const resolutions = formatsQuery.data?.video_resolutions || [];
  const isLossless = formatsQuery.data?.audio?.[targetFormat]?.lossless;

  function pickSourceKind(kind) {
    setSourceKind(kind);
    const defaults = kind === "library" ? audioFormats[0] : (isAudioSource ? audioFormats[0] : videoFormats[0]);
    if (defaults) setTargetFormat(defaults);
  }

  const convertMutation = useMutation({
    mutationFn: () => {
      const fields = {
        source_kind: sourceKind,
        target_format: targetFormat,
        target_bitrate: audioFormats.includes(targetFormat) && !isLossless ? targetBitrate : null,
        target_resolution: videoFormats.includes(targetFormat) ? targetResolution : null,
        save_to_library: audioFormats.includes(targetFormat) ? saveToLibrary : false,
      };
      if (sourceKind === "upload") fields.file = file;
      if (sourceKind === "library") fields.source_ref = libraryTrackId;
      if (sourceKind === "download") fields.source_ref = downloadId;
      return api.createConversion(fields);
    },
    onSuccess: () => {
      toast.success("Conversion queued");
      setFile(null);
      qc.invalidateQueries({ queryKey: ["conversions"] });
      qc.invalidateQueries({ queryKey: ["conversion-stats"] });
    },
    onError: (e) => toast.error(e.message),
  });

  const canSubmit =
    (sourceKind === "upload" && !!file) ||
    (sourceKind === "library" && !!libraryTrackId) ||
    (sourceKind === "download" && !!downloadId);

  const jobs = jobsQuery.data || [];
  const active = jobs.filter((j) => ACTIVE.has(j.status));
  const history = jobs.filter((j) => !ACTIVE.has(j.status));
  const stats = statsQuery.data;
  const formatList = isAudioSource ? audioFormats : videoFormats;

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-6">
        <div>
          <h1 className="font-display font-bold text-2xl">Convert</h1>
          <p className="text-sm text-parchment-500 mt-1">Re-encode a file into a different format.</p>
        </div>
        <div className="flex gap-4 font-mono text-right">
          <StatPill label="Active" value={stats?.active} />
          <StatPill label="Done" value={stats?.completed} />
          <StatPill label="Failed" value={stats?.failed} />
        </div>
      </header>

      <div className="panel p-5 space-y-4">
        <div className="flex border border-ink-600 rounded-lg overflow-hidden w-fit">
          {[
            { key: "upload", label: "Upload a file" },
            { key: "library", label: "From library" },
            { key: "download", label: "From spooler" },
          ].map((t) => (
            <button
              key={t.key}
              onClick={() => pickSourceKind(t.key)}
              className={`px-4 py-2 text-xs font-semibold uppercase tracking-wide ${
                sourceKind === t.key ? "bg-brass-600 text-parchment-100" : "text-parchment-500 hover:text-parchment-100"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {sourceKind === "upload" && (
          <label className="flex items-center gap-3 border border-dashed border-ink-600 rounded-lg px-4 py-4 cursor-pointer hover:border-brass-600 transition">
            <Upload className="w-5 h-5 text-parchment-700 shrink-0" />
            <span className="text-sm text-parchment-500 truncate">
              {file ? file.name : "Click to choose an audio or video file…"}
            </span>
            <input
              type="file"
              accept="audio/*,video/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                setFile(f || null);
                if (f) {
                  const ext = f.name.split(".").pop()?.toLowerCase();
                  const audio = AUDIO_EXT.has(ext);
                  const list = audio ? audioFormats : videoFormats;
                  if (list[0]) setTargetFormat(list[0]);
                }
              }}
            />
          </label>
        )}

        {sourceKind === "library" && (
          <select className="select w-full" value={libraryTrackId} onChange={(e) => setLibraryTrackId(e.target.value)}>
            <option value="">Select a track…</option>
            {(libraryQuery.data || []).map((t) => (
              <option key={t.id} value={t.id}>{t.artist} — {t.title} ({t.ext})</option>
            ))}
          </select>
        )}

        {sourceKind === "download" && (
          <select
            className="select w-full"
            value={downloadId}
            onChange={(e) => {
              setDownloadId(e.target.value);
              const d = completedDownloads.find((x) => String(x.id) === e.target.value);
              const list = d?.media_type === "audio" ? audioFormats : videoFormats;
              if (list[0]) setTargetFormat(list[0]);
            }}
          >
            <option value="">Select a completed download…</option>
            {completedDownloads.map((d) => (
              <option key={d.id} value={d.id}>{d.title || d.url} ({d.media_type})</option>
            ))}
          </select>
        )}

        <div className="flex items-center gap-3 flex-wrap pt-1">
          <select className="select" value={targetFormat} onChange={(e) => setTargetFormat(e.target.value)}>
            {formatList.map((f) => (
              <option key={f} value={f}>{f.toUpperCase()}</option>
            ))}
          </select>

          {audioFormats.includes(targetFormat) && !isLossless && (
            <select className="select" value={targetBitrate} onChange={(e) => setTargetBitrate(e.target.value)}>
              {bitrates.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          )}

          {videoFormats.includes(targetFormat) && (
            <select className="select" value={targetResolution} onChange={(e) => setTargetResolution(e.target.value)}>
              {resolutions.map((r) => (
                <option key={r} value={r}>{r === "source" ? "Original resolution" : `${r}p`}</option>
              ))}
            </select>
          )}

          {audioFormats.includes(targetFormat) && (
            <label className="flex items-center gap-2 text-xs font-mono text-parchment-300 cursor-pointer">
              <input type="checkbox" checked={saveToLibrary} onChange={(e) => setSaveToLibrary(e.target.checked)} />
              Save result to library
            </label>
          )}

          <button
            className="btn-primary flex items-center gap-1.5 ml-auto"
            onClick={() => convertMutation.mutate()}
            disabled={!canSubmit || convertMutation.isPending}
          >
            <ConvertIcon className="w-3.5 h-3.5" /> {convertMutation.isPending ? "Queuing…" : "Convert"}
          </button>
        </div>
      </div>

      {active.length > 0 && (
        <>
          <p className="label-eyebrow mt-8 mb-3">Converting</p>
          <div className="space-y-2.5">
            {active.map((item) => (
              <ConversionCard key={item.id} item={item} />
            ))}
          </div>
        </>
      )}

      <p className="label-eyebrow mt-8 mb-3">History</p>
      {history.length === 0 ? (
        <div className="text-center py-16 px-6 border border-dashed border-ink-600 rounded-xl text-parchment-700 font-mono text-sm">
          No conversions yet.
        </div>
      ) : (
        <div className="space-y-2.5">
          {history.map((item) => (
            <ConversionCard key={item.id} item={item} />
          ))}
        </div>
      )}
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

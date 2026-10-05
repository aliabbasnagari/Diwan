import { useEffect, useState } from "react";
import { Save } from "lucide-react";

export default function SavePanel({ info, formats, bitrates, busy, onSave }) {
  const formatKeys = Object.keys(formats || {});
  const canOverwrite = formatKeys.includes(info.source_ext);

  const [mode, setMode] = useState("new");
  const [format, setFormat] = useState(canOverwrite ? info.source_ext : "mp3");
  const [bitrate, setBitrate] = useState("256k");
  const [title, setTitle] = useState("");

  useEffect(() => {
    setFormat(formatKeys.includes(info.source_ext) ? info.source_ext : "mp3");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info.source_ext, formatKeys.length]);

  const lossless = formats?.[format]?.lossless;

  return (
    <div className="panel p-5 space-y-4">
      <p className="label-eyebrow">Save to library</p>

      <div className="space-y-2 text-xs font-mono text-parchment-300">
        <label className="flex items-start gap-2 cursor-pointer">
          <input type="radio" className="mt-0.5" checked={mode === "new"} onChange={() => setMode("new")} />
          <span>Save as a new copy <span className="text-parchment-700">— "{info.source_filename.replace(/\.[^.]+$/, "")} (edited)" next to the original</span></span>
        </label>
        <label className={`flex items-start gap-2 ${canOverwrite ? "cursor-pointer" : "opacity-50"}`}>
          <input type="radio" className="mt-0.5" disabled={!canOverwrite} checked={mode === "replace"} onChange={() => setMode("replace")} />
          <span>Overwrite the original <span className="text-parchment-700">— same format, tags and cover art kept{!canOverwrite && " (not available for this file type)"}</span></span>
        </label>
      </div>

      {mode === "new" && (
        <div className="space-y-3">
          <label className="block">
            <span className="label-eyebrow block mb-1">Title tag (optional)</span>
            <input className="input w-full !py-2" placeholder="Original title + (edited)" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <div className="flex gap-3">
            <label className="block flex-1">
              <span className="label-eyebrow block mb-1">Format</span>
              <select className="select w-full" value={format} onChange={(e) => setFormat(e.target.value)}>
                {formatKeys.map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
              </select>
            </label>
            {!lossless && (
              <label className="block flex-1">
                <span className="label-eyebrow block mb-1">Bitrate</span>
                <select className="select w-full" value={bitrate} onChange={(e) => setBitrate(e.target.value)}>
                  {bitrates.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </label>
            )}
          </div>
        </div>
      )}

      <button
        className="btn-primary w-full flex items-center justify-center gap-1.5 !py-2"
        disabled={busy}
        onClick={() => onSave({
          mode,
          format: mode === "new" ? format : null,
          bitrate: mode === "new" && !lossless ? bitrate : null,
          title: mode === "new" ? title : null,
        })}
      >
        <Save className="w-3.5 h-3.5" /> {busy ? "Working…" : mode === "replace" ? "Overwrite original" : "Save copy"}
      </button>
      <p className="text-[11px] text-parchment-700 leading-snug">
        Editing happens on a 16-bit working copy; the library file isn't touched until you save. Lossy formats are re-encoded on save.
      </p>
    </div>
  );
}

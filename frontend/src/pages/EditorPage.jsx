import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Play, Pause, Square, Repeat, Undo2, Redo2, Crop, Scissors, RotateCcw, ZoomIn, ZoomOut,
  Maximize2, Plus, X, Loader2, Ear, Sparkles, MapPin,
} from "lucide-react";
import { api } from "../api.js";
import Waveform, { formatTime, parseTime, zoomView } from "../components/editor/Waveform.jsx";
import SavePanel from "../components/editor/SavePanel.jsx";
import TrackPicker from "../components/editor/TrackPicker.jsx";

const SESSION_KEY = "diwan_editor_session";
const MIN_RANGE = 0.01;
const HEAR_SECONDS = 3;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function ToolBtn({ icon: Icon, label, onClick, disabled, active }) {
  return (
    <button
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={`p-2 rounded-lg border text-parchment-300 transition disabled:opacity-35 disabled:cursor-not-allowed ${
        active ? "border-brass-600 text-brass-400 bg-brass-900" : "border-ink-600 hover:border-brass-600 hover:text-brass-400"
      }`}
    >
      <Icon className="w-4 h-4" strokeWidth={1.75} />
    </button>
  );
}

const Divider = () => <span className="w-px h-6 bg-ink-600 mx-1" />;

// Shows the live playback position without re-rendering the page every frame.
function CursorReadout({ audioRef }) {
  const ref = useRef(null);
  useEffect(() => {
    let raf;
    const tick = () => {
      if (ref.current && audioRef.current) ref.current.textContent = formatTime(audioRef.current.currentTime, 2);
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [audioRef]);
  return <span ref={ref}>0:00.00</span>;
}

// A start/end time box: type a time ("1:23.4" or seconds), or grab it from the playhead.
function TimeField({ label, value, onCommit, onSetHere, onHear, hearLabel }) {
  const [text, setText] = useState(formatTime(value, 3));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setText(formatTime(value, 3));
  }, [value, editing]);

  function commit() {
    setEditing(false);
    const t = parseTime(text);
    if (t == null) setText(formatTime(value, 3));
    else onCommit(t);
  }

  return (
    <div>
      <span className="label-eyebrow block mb-1">{label}</span>
      <div className="flex items-center gap-2">
        <input
          className="input !py-2 w-32"
          value={text}
          onFocus={() => setEditing(true)}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
        />
        <button className="btn-ghost flex items-center gap-1.5" onClick={onSetHere} title="Set to the current playhead position">
          <MapPin className="w-3.5 h-3.5" /> Playhead
        </button>
        <button className="btn-ghost flex items-center gap-1.5" onClick={onHear} title={hearLabel}>
          <Ear className="w-3.5 h-3.5" /> Hear
        </button>
      </div>
    </div>
  );
}

export default function EditorPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();

  const [info, setInfo] = useState(null);        // session info from the server
  const [loading, setLoading] = useState(false); // opening / resuming a session
  const [busy, setBusy] = useState(false);       // an edit is rendering
  const [view, setView] = useState({ start: 0, end: 1 });
  const [range, setRange] = useState({ start: 0, end: 1 }); // the part you're keeping / removing
  const [loop, setLoop] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [silenceSeconds, setSilenceSeconds] = useState(1);
  const [silenceWhere, setSilenceWhere] = useState("start");

  const audioRef = useRef(null);
  const restoreRef = useRef(null);  // playback position to restore once a new version has loaded
  const planRef = useRef(null);     // { from, to, loop } while playing a span

  const { data: options } = useQuery({ queryKey: ["editor-options"], queryFn: api.editorOptions, staleTime: Infinity });

  const sid = info?.id;
  const duration = info?.duration ?? 0;
  const cursor = () => audioRef.current?.currentTime ?? 0;
  const isWhole = range.start <= 0.001 && range.end >= duration - 0.001;
  const rangeLen = range.end - range.start;

  // ---- session lifecycle ----
  useEffect(() => {
    // resume a session left open when the user navigated away
    const saved = sessionStorage.getItem(SESSION_KEY);
    if (!saved) return;
    setLoading(true);
    api.editorGet(saved)
      .then(setInfo)
      .catch(() => sessionStorage.removeItem(SESSION_KEY))
      .finally(() => setLoading(false));
  }, []);

  const lastSid = useRef(null);
  useEffect(() => {
    if (sid && sid !== lastSid.current) {
      lastSid.current = sid;
      fitAll(duration);
      sessionStorage.setItem(SESSION_KEY, sid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, duration]);

  function fitAll(total) {
    const end = Math.max(total, 0.001);
    setView({ start: 0, end });
    setRange({ start: 0, end });
  }

  async function discardSession() {
    if (!info) return;
    await api.editorClose(info.id).catch(() => {});
    sessionStorage.removeItem(SESSION_KEY);
    lastSid.current = null;
    setInfo(null);
  }

  async function openTrack(trackId) {
    if (info?.dirty && !confirm("Discard unsaved edits to the current track?")) return;
    setLoading(true);
    try {
      await discardSession();
      setInfo(await api.editorOpen(trackId));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }

  // /editor?track=<id> (linked from the Library's track editor)
  const wantedTrack = params.get("track");
  useEffect(() => {
    if (!wantedTrack) return;
    setParams({}, { replace: true });
    openTrack(wantedTrack);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedTrack]);

  // ---- edits (every edit changes the length, so the range and zoom reset to the whole track) ----
  async function exec(fn, { cursorTo = 0, success } = {}) {
    if (busy || !info) return;
    setBusy(true);
    audioRef.current?.pause();
    planRef.current = null;
    try {
      const next = await fn();
      restoreRef.current = clamp(cursorTo, 0, next.duration);
      setInfo(next);
      fitAll(next.duration);
      if (success) toast.success(success);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  const edit = (body, opts) => exec(() => api.editorEdit(sid, body), opts);
  const keepRange = () => !isWhole && edit({ op: "trim", start: range.start, end: range.end });
  const removeRange = () => !isWhole && edit({ op: "delete", start: range.start, end: range.end }, { cursorTo: range.start });
  const autoTrimSilence = () => edit({ op: "trim_silence" }, { success: "Silence trimmed from the start and end" });
  const undo = () => exec(() => api.editorUndo(sid));
  const redo = () => exec(() => api.editorRedo(sid));

  function addSilence() {
    const position = silenceWhere === "start" ? 0 : silenceWhere === "end" ? duration : cursor();
    const seconds = Number(silenceSeconds);
    if (!(seconds > 0)) return toast.error("Enter how many seconds of silence to add");
    edit({ op: "insert_silence", position, seconds }, { cursorTo: position });
  }

  async function save(opts) {
    if (opts.mode === "replace" && !confirm("Overwrite the original file with the trimmed audio? This can't be undone.")) return;
    setBusy(true);
    try {
      const res = await api.editorSave(sid, opts);
      setInfo(res.session);
      toast.success(opts.mode === "replace" ? "Original overwritten" : `Saved as ${res.track.path}`);
      ["library-tree", "library-search", "library-stats", "library-tracks-flat"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  // ---- range editing ----
  const setStart = (t) => setRange((r) => ({ start: clamp(t, 0, r.end - MIN_RANGE), end: r.end }));
  const setEnd = (t) => setRange((r) => ({ start: r.start, end: clamp(t, r.start + MIN_RANGE, duration) }));

  // ---- transport ----
  function playSpan(from, to, loopable = false) {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = from;
    planRef.current = { from, to, loop: loopable };
    a.play().catch(() => {});
  }

  function togglePlay() {
    const a = audioRef.current;
    if (!a || !info) return;
    if (!a.paused) {
      a.pause();
      return;
    }
    planRef.current = null;
    if (a.currentTime >= duration - 0.02) a.currentTime = 0;
    a.play().catch(() => {});
  }

  function stop() {
    const a = audioRef.current;
    if (!a) return;
    a.pause();
    planRef.current = null;
    a.currentTime = range.start;
  }

  const live = useRef({});
  live.current = { loop };
  useEffect(() => {
    let raf;
    const tick = () => {
      const a = audioRef.current;
      const plan = planRef.current;
      if (a && plan && !a.paused && a.currentTime >= plan.to) {
        if (plan.loop && live.current.loop) a.currentTime = plan.from;
        else {
          a.pause();
          a.currentTime = plan.to;
          planRef.current = null;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  // ---- zoom ----
  const zoomAnchor = () => (isWhole ? (view.start + view.end) / 2 : (range.start + range.end) / 2);
  const zoomIn = () => setView(zoomView(view, duration, 0.5, zoomAnchor()));
  const zoomOut = () => setView(zoomView(view, duration, 2, zoomAnchor()));
  const zoomFit = () => setView({ start: 0, end: Math.max(duration, 0.001) });
  const zoomRange = () => setView(zoomView({ start: range.start, end: range.end }, duration, 1.15, (range.start + range.end) / 2));

  // ---- keyboard shortcuts ----
  const keys = useRef({});
  keys.current = {
    togglePlay, undo, redo,
    markStart: () => setStart(cursor()),
    markEnd: () => setEnd(cursor()),
  };
  useEffect(() => {
    const onKey = (e) => {
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const k = keys.current;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      let handled = true;
      if (e.key === " ") k.togglePlay();
      else if (mod && key === "z" && !e.shiftKey) k.undo();
      else if (mod && (key === "y" || (key === "z" && e.shiftKey))) k.redo();
      else if (e.key === "[") k.markStart();
      else if (e.key === "]") k.markEnd();
      else handled = false;
      if (handled) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!info?.dirty) return;
    const warn = (e) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [info?.dirty]);

  // ---- render ----
  if (!info) {
    return (
      <div>
        <header className="mb-6">
          <h1 className="font-display font-bold text-2xl">Trimmer</h1>
          <p className="text-sm text-parchment-500 mt-1">
            Pick a track to trim, cut or pad with silence. Nothing changes on disk until you save.
          </p>
        </header>
        {loading ? (
          <div className="panel p-10 flex items-center justify-center gap-3 text-sm font-mono text-parchment-500">
            <Loader2 className="w-4 h-4 animate-spin" /> Decoding track…
          </div>
        ) : (
          <TrackPicker onPick={openTrack} busy={loading} />
        )}
      </div>
    );
  }

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-5">
        <div className="min-w-0">
          <h1 className="font-display font-bold text-2xl">Trimmer</h1>
          <p className="text-sm text-parchment-500 mt-1 truncate">
            {info.source_filename}
            {info.dirty && <span className="text-brass-400"> · unsaved changes</span>}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <p className="text-xs font-mono text-parchment-500 text-right leading-relaxed">
            {formatTime(duration, 2)} · {(info.sample_rate / 1000).toFixed(1)} kHz · {info.channels === 1 ? "mono" : "stereo"}
          </p>
          <button
            className="btn-ghost flex items-center gap-1.5"
            onClick={() => {
              if (info.dirty && !confirm("Close this track and discard unsaved edits?")) return;
              discardSession();
            }}
          >
            <X className="w-3.5 h-3.5" /> Close
          </button>
        </div>
      </header>

      <div className="panel p-4 space-y-3">
        <div className="flex items-center gap-1 flex-wrap">
          <ToolBtn icon={playing ? Pause : Play} label="Play / pause (Space)" onClick={togglePlay} disabled={busy} active={playing} />
          <ToolBtn icon={Square} label="Stop" onClick={stop} disabled={busy} />
          <button
            className="btn-ghost flex items-center gap-1.5 !py-2"
            onClick={() => playSpan(range.start, range.end, true)}
            disabled={busy}
            title="Play only the highlighted range"
          >
            <Play className="w-3.5 h-3.5" /> Play range
          </button>
          <ToolBtn icon={Repeat} label="Loop 'Play range'" onClick={() => setLoop((l) => !l)} active={loop} />
          <Divider />
          <ToolBtn icon={Undo2} label="Undo (Ctrl+Z)" onClick={undo} disabled={busy || !info.can_undo} />
          <ToolBtn icon={Redo2} label="Redo (Ctrl+Y)" onClick={redo} disabled={busy || !info.can_redo} />
          <Divider />
          <ToolBtn icon={ZoomIn} label="Zoom in" onClick={zoomIn} />
          <ToolBtn icon={ZoomOut} label="Zoom out" onClick={zoomOut} />
          <ToolBtn icon={Maximize2} label="Fit whole track" onClick={zoomFit} />
          <button className="btn-ghost !py-2" onClick={zoomRange} disabled={isWhole} title="Zoom to the highlighted range">Zoom range</button>
          {busy && <Loader2 className="w-4 h-4 animate-spin text-brass-400 ml-2" />}
        </div>

        <div className={busy ? "opacity-60 pointer-events-none" : ""}>
          <Waveform
            sessionId={sid}
            version={info.version}
            duration={duration}
            channels={info.channels}
            view={view}
            onViewChange={setView}
            range={range}
            onRangeChange={setRange}
            onSeek={(t) => {
              planRef.current = null;
              if (audioRef.current) audioRef.current.currentTime = t;
            }}
            audioRef={audioRef}
          />
        </div>

        <p className="text-xs font-mono text-parchment-700">
          Drag the gold handles (or drag on the waveform) to choose a range · Click to place the playhead · Ctrl+wheel zooms, wheel pans ·
          <span className="text-parchment-500"> [ </span>/<span className="text-parchment-500"> ] </span>
          set start/end at the playhead
        </p>
      </div>

      <div className="grid gap-5 mt-5 lg:grid-cols-3">
        <div className="panel p-5 space-y-4">
          <p className="label-eyebrow">Trim</p>

          <TimeField
            label="Start"
            value={range.start}
            onCommit={setStart}
            onSetHere={() => setStart(cursor())}
            onHear={() => playSpan(range.start, Math.min(range.start + HEAR_SECONDS, duration))}
            hearLabel={`Play ${HEAR_SECONDS} seconds from the start point`}
          />
          <TimeField
            label="End"
            value={range.end}
            onCommit={setEnd}
            onSetHere={() => setEnd(cursor())}
            onHear={() => playSpan(Math.max(range.end - HEAR_SECONDS, 0), range.end)}
            hearLabel={`Play the ${HEAR_SECONDS} seconds before the end point`}
          />

          <p className="text-xs font-mono text-parchment-500">
            Range <span className="text-parchment-100">{formatTime(rangeLen, 2)}</span> of {formatTime(duration, 2)}
            {" · "}
            Cursor <span className="text-parchment-100"><CursorReadout audioRef={audioRef} /></span>
          </p>

          <div className="space-y-2">
            <button className="btn-primary w-full flex items-center justify-center gap-1.5 !py-2" onClick={keepRange} disabled={busy || isWhole}>
              <Crop className="w-3.5 h-3.5" /> Keep range
              {!isWhole && <span className="font-mono normal-case opacity-70">→ {formatTime(rangeLen, 1)}</span>}
            </button>
            <button className="btn-ghost w-full flex items-center justify-center gap-1.5 !py-2" onClick={removeRange} disabled={busy || isWhole}>
              <Scissors className="w-3.5 h-3.5" /> Remove range
              {!isWhole && <span className="opacity-70">→ {formatTime(duration - rangeLen, 1)}</span>}
            </button>
            <button className="btn-ghost w-full flex items-center justify-center gap-1.5 !py-2" onClick={() => setRange({ start: 0, end: duration })} disabled={isWhole}>
              <RotateCcw className="w-3.5 h-3.5" /> Reset range
            </button>
          </div>
        </div>

        <div className="panel p-5 space-y-4">
          <p className="label-eyebrow">Silence</p>

          <div className="space-y-3">
            <p className="text-sm text-parchment-300">Add space</p>
            <div className="flex gap-2 items-end">
              <label className="block w-24">
                <span className="label-eyebrow block mb-1">Seconds</span>
                <input
                  type="number" min="0.1" max="600" step="0.5"
                  className="input !py-2 w-full"
                  value={silenceSeconds}
                  onChange={(e) => setSilenceSeconds(e.target.value)}
                />
              </label>
              <label className="block flex-1">
                <span className="label-eyebrow block mb-1">Where</span>
                <select className="select w-full" value={silenceWhere} onChange={(e) => setSilenceWhere(e.target.value)}>
                  <option value="start">Start of track</option>
                  <option value="end">End of track</option>
                  <option value="cursor">At the playhead</option>
                </select>
              </label>
            </div>
            <button className="btn-ghost w-full flex items-center justify-center gap-1.5 !py-2" onClick={addSilence} disabled={busy}>
              <Plus className="w-3.5 h-3.5" /> Add silence
            </button>
          </div>

          <div className="border-t border-ink-600 pt-4 space-y-2">
            <p className="text-sm text-parchment-300">Auto-trim</p>
            <p className="text-[11px] text-parchment-700 leading-snug">
              Removes quiet lead-in and tail (below −50 dB). Doesn't touch silence in the middle.
            </p>
            <button className="btn-ghost w-full flex items-center justify-center gap-1.5 !py-2" onClick={autoTrimSilence} disabled={busy}>
              <Sparkles className="w-3.5 h-3.5" /> Trim silence at both ends
            </button>
          </div>
        </div>

        <div className="space-y-5">
          {options && (
            <SavePanel info={info} formats={options.formats} bitrates={options.bitrates} busy={busy} onSave={save} />
          )}
          {info.history.length > 0 && (
            <div className="panel p-4">
              <p className="label-eyebrow mb-2">History</p>
              <ol className="flex flex-wrap gap-2 text-xs font-mono text-parchment-300">
                {info.history.map((h, i) => (
                  <li key={i} className="px-2 py-1 rounded bg-ink-700 border border-ink-600">{i + 1}. {h}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </div>

      <audio
        ref={audioRef}
        src={api.editorAudioUrl(sid, info.version)}
        preload="auto"
        onLoadedMetadata={() => {
          if (restoreRef.current != null && audioRef.current) {
            audioRef.current.currentTime = restoreRef.current;
            restoreRef.current = null;
          }
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
    </div>
  );
}

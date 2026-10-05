import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Play, Pause, Square, Repeat, Undo2, Redo2, Scissors, Copy, ClipboardPaste, Trash2, Crop,
  ZoomIn, ZoomOut, Maximize2, BoxSelect, VolumeX, Plus, X, Loader2,
} from "lucide-react";
import { api } from "../api.js";
import Waveform, { formatTime, zoomView } from "../components/editor/Waveform.jsx";
import EffectsPanel from "../components/editor/EffectsPanel.jsx";
import SavePanel from "../components/editor/SavePanel.jsx";
import TrackPicker from "../components/editor/TrackPicker.jsx";

const SESSION_KEY = "diwan_editor_session";
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

export default function EditorPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();

  const [info, setInfo] = useState(null);       // session info from the server
  const [loading, setLoading] = useState(false); // opening / resuming a session
  const [busy, setBusy] = useState(false);       // an edit is rendering
  const [view, setView] = useState({ start: 0, end: 1 });
  const [selection, setSelection] = useState(null);
  const [loop, setLoop] = useState(false);
  const [playing, setPlaying] = useState(false);

  const audioRef = useRef(null);
  const previewRef = useRef(null);
  const restoreRef = useRef(null);   // playback position to restore once a new version has loaded
  const playModeRef = useRef("all"); // "selection" stops at the selection end

  const { data: catalog } = useQuery({ queryKey: ["editor-effects"], queryFn: api.editorEffects, staleTime: Infinity });

  const sid = info?.id;
  const duration = info?.duration ?? 0;
  const cursor = () => audioRef.current?.currentTime ?? 0;

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
      setView({ start: 0, end: Math.max(duration, 0.001) });
      setSelection(null);
      sessionStorage.setItem(SESSION_KEY, sid);
    }
  }, [sid, duration]);

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

  // ---- applying server edits ----
  function applyInfo(next, { clearSel = false, cursorTo = null } = {}) {
    const durationChanged = Math.abs(next.duration - (info?.duration ?? 0)) > 0.001;
    if (next.version === info?.version) {
      restoreRef.current = null; // same audio file: no reload, nothing to restore
    } else {
      restoreRef.current = clamp(cursorTo ?? restoreRef.current ?? 0, 0, next.duration);
    }
    setInfo(next);
    if (clearSel) setSelection(null);
    else if (selection && durationChanged) {
      setSelection(selection.start >= next.duration ? null : { start: selection.start, end: Math.min(selection.end, next.duration) });
    }
    if (durationChanged) setView({ start: 0, end: Math.max(next.duration, 0.001) });
  }

  async function exec(fn, opts) {
    if (busy || !info) return;
    setBusy(true);
    audioRef.current?.pause();
    previewRef.current?.pause();
    restoreRef.current = cursor();
    try {
      applyInfo(await fn(), opts);
      return true;
    } catch (e) {
      restoreRef.current = null;
      toast.error(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const selBody = () => ({ start: selection?.start, end: selection?.end });

  const doEdit = (op, extra = {}, opts) => exec(() => api.editorEdit(sid, { op, ...extra }), opts);
  const doCut = () => selection && doEdit("cut", selBody(), { clearSel: true, cursorTo: selection.start });
  const doDelete = () => selection && doEdit("delete", selBody(), { clearSel: true, cursorTo: selection.start });
  const doTrim = () => selection && doEdit("trim", selBody(), { clearSel: true, cursorTo: 0 });
  const doCopy = () => selection && doEdit("copy", selBody()).then((ok) => ok && toast.success("Copied"));
  const doPaste = () => doEdit("paste", { position: cursor() }, { clearSel: true, cursorTo: cursor() + (info?.clipboard_seconds ?? 0) });
  const doSilence = () => selection && exec(() => api.editorEffect(sid, { effect: "silence", params: {}, ...selBody() }));
  const doUndo = () => exec(() => api.editorUndo(sid));
  const doRedo = () => exec(() => api.editorRedo(sid));
  function doInsertSilence() {
    const raw = window.prompt("Seconds of silence to insert at the cursor:", "1");
    const seconds = Number(raw);
    if (raw && seconds > 0) doEdit("insert_silence", { position: cursor(), seconds }, { cursorTo: cursor() });
  }

  const applyEffect = (payload, label) =>
    exec(() => api.editorEffect(sid, payload)).then((ok) => ok && toast.success(`${label} applied`));

  async function previewEffect(payload) {
    if (busy) return;
    setBusy(true);
    audioRef.current?.pause();
    try {
      await api.editorPreview(sid, payload);
      const p = previewRef.current;
      p.src = api.editorPreviewUrl(sid, Date.now());
      await p.play();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function save(opts) {
    if (opts.mode === "replace" && !confirm("Overwrite the original file with the edited audio? This can't be undone.")) return;
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

  // ---- transport ----
  function togglePlay() {
    const a = audioRef.current;
    if (!a || !info) return;
    previewRef.current?.pause();
    if (!a.paused) {
      a.pause();
      return;
    }
    if (selection) {
      if (a.currentTime < selection.start || a.currentTime >= selection.end - 0.02) a.currentTime = selection.start;
      playModeRef.current = "selection";
    } else {
      if (a.currentTime >= duration - 0.02) a.currentTime = 0;
      playModeRef.current = "all";
    }
    a.play().catch(() => {});
  }

  function stop() {
    const a = audioRef.current;
    if (!a) return;
    a.pause();
    previewRef.current?.pause();
    a.currentTime = selection?.start ?? 0;
  }

  // stop / loop at the end of a played selection
  const live = useRef({});
  live.current = { selection, loop };
  useEffect(() => {
    let raf;
    const tick = () => {
      const a = audioRef.current;
      const { selection: sel, loop: looping } = live.current;
      if (a && !a.paused && playModeRef.current === "selection" && sel && a.currentTime >= sel.end) {
        if (looping) a.currentTime = sel.start;
        else {
          a.pause();
          a.currentTime = sel.end;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  // ---- zoom ----
  const zoomAnchor = () => (selection ? (selection.start + selection.end) / 2 : (view.start + view.end) / 2);
  const zoomIn = () => setView(zoomView(view, duration, 0.5, zoomAnchor()));
  const zoomOut = () => setView(zoomView(view, duration, 2, zoomAnchor()));
  const zoomFit = () => setView({ start: 0, end: Math.max(duration, 0.001) });
  const zoomSel = () => selection && setView(zoomView({ start: selection.start, end: selection.end }, duration, 1, selection.start));

  // ---- keyboard shortcuts ----
  const keys = useRef({});
  keys.current = { togglePlay, doUndo, doRedo, doCut, doCopy, doPaste, doDelete, selectAll: () => setSelection({ start: 0, end: duration }) };
  useEffect(() => {
    const onKey = (e) => {
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const k = keys.current;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      let handled = true;
      if (e.key === " ") k.togglePlay();
      else if (mod && key === "z" && !e.shiftKey) k.doUndo();
      else if (mod && (key === "y" || (key === "z" && e.shiftKey))) k.doRedo();
      else if (mod && key === "x") k.doCut();
      else if (mod && key === "c") k.doCopy();
      else if (mod && key === "v") k.doPaste();
      else if (mod && key === "a") k.selectAll();
      else if (e.key === "Delete" || e.key === "Backspace") k.doDelete();
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
          <h1 className="font-display font-bold text-2xl">Editor</h1>
          <p className="text-sm text-parchment-500 mt-1">
            Trim, cut and add effects to a track from your library. Nothing changes on disk until you save.
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

  const selLen = selection ? selection.end - selection.start : 0;

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-5">
        <div className="min-w-0">
          <h1 className="font-display font-bold text-2xl">Editor</h1>
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

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="space-y-4 min-w-0">
          <div className="panel p-4 space-y-3">
            <div className="flex items-center gap-1 flex-wrap">
              <ToolBtn icon={playing ? Pause : Play} label="Play / pause (Space)" onClick={togglePlay} disabled={busy} active={playing} />
              <ToolBtn icon={Square} label="Stop" onClick={stop} disabled={busy} />
              <ToolBtn icon={Repeat} label="Loop playback" onClick={() => setLoop((l) => !l)} active={loop} />
              <Divider />
              <ToolBtn icon={Undo2} label="Undo (Ctrl+Z)" onClick={doUndo} disabled={busy || !info.can_undo} />
              <ToolBtn icon={Redo2} label="Redo (Ctrl+Y)" onClick={doRedo} disabled={busy || !info.can_redo} />
              <Divider />
              <ToolBtn icon={Scissors} label="Cut (Ctrl+X)" onClick={doCut} disabled={busy || !selection} />
              <ToolBtn icon={Copy} label="Copy (Ctrl+C)" onClick={doCopy} disabled={busy || !selection} />
              <ToolBtn icon={ClipboardPaste} label="Paste at cursor (Ctrl+V)" onClick={doPaste} disabled={busy || !info.clipboard_seconds} />
              <ToolBtn icon={Trash2} label="Delete selection (Del)" onClick={doDelete} disabled={busy || !selection} />
              <ToolBtn icon={Crop} label="Trim to selection" onClick={doTrim} disabled={busy || !selection} />
              <ToolBtn icon={VolumeX} label="Silence selection" onClick={doSilence} disabled={busy || !selection} />
              <ToolBtn icon={Plus} label="Insert silence at cursor…" onClick={doInsertSilence} disabled={busy} />
              <Divider />
              <ToolBtn icon={BoxSelect} label="Select all (Ctrl+A)" onClick={() => setSelection({ start: 0, end: duration })} />
              <ToolBtn icon={ZoomIn} label="Zoom in" onClick={zoomIn} />
              <ToolBtn icon={ZoomOut} label="Zoom out" onClick={zoomOut} />
              <ToolBtn icon={Maximize2} label="Fit whole track" onClick={zoomFit} />
              <button className="btn-ghost !py-1.5" onClick={zoomSel} disabled={!selection} title="Zoom to selection">Sel</button>
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
                selection={selection}
                onSelect={setSelection}
                onSeek={(t) => { if (audioRef.current) audioRef.current.currentTime = t; }}
                audioRef={audioRef}
              />
            </div>

            <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs font-mono text-parchment-500">
              <span>Cursor <span className="text-parchment-100"><CursorReadout audioRef={audioRef} /></span></span>
              <span>
                Selection{" "}
                <span className="text-parchment-100">
                  {selection ? `${formatTime(selection.start, 2)} – ${formatTime(selection.end, 2)} (${selLen.toFixed(2)} s)` : "none"}
                </span>
              </span>
              <span className="text-parchment-700">Click: place cursor · Drag: select · Shift+click: extend · Ctrl+wheel: zoom · Wheel: pan</span>
            </div>
          </div>

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

        <div className="space-y-4">
          {catalog && (
            <EffectsPanel
              catalog={catalog.effects}
              channels={info.channels}
              selection={selection}
              busy={busy}
              onPreview={previewEffect}
              onApply={applyEffect}
            />
          )}
          {catalog && (
            <SavePanel info={info} formats={catalog.formats} bitrates={catalog.bitrates} busy={busy} onSave={save} />
          )}
        </div>
      </div>

      <audio
        ref={audioRef}
        src={api.editorAudioUrl(sid, info.version)}
        preload="auto"
        loop={loop && !selection}
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
      <audio ref={previewRef} preload="auto" />
    </div>
  );
}

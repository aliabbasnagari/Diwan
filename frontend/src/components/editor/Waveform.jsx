import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api.js";

const RULER_H = 22;
const LANE_GAP = 6;
const MIN_VIEW = 0.02; // seconds — deepest zoom
const TICK_STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];

const COLORS = {
  bg: "#141310",
  center: "#3a352a",
  wave: "#d9a441",
  waveSelected: "#efe9df",
  selection: "rgba(230, 180, 92, 0.22)",
  tick: "#5a5342",
  label: "#9a9284",
};

export function formatTime(t, decimals = 1) {
  if (t == null || Number.isNaN(t)) return "–:––";
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0")}`;
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

/** Zoom `view` by `factor` (<1 zooms in) keeping `anchor` (seconds) under the same pixel. */
export function zoomView(view, duration, factor, anchor) {
  const len = view.end - view.start;
  const newLen = clamp(len * factor, Math.min(MIN_VIEW, duration), duration);
  const ratio = len > 0 ? (anchor - view.start) / len : 0.5;
  const start = clamp(anchor - ratio * newLen, 0, duration - newLen);
  return { start, end: start + newLen };
}

export default function Waveform({
  sessionId, version, duration, channels, view, onViewChange,
  selection, onSelect, onSeek, audioRef, height = 260,
}) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const headRef = useRef(null);
  const [width, setWidth] = useState(800);

  const viewLen = Math.max(view.end - view.start, 1e-6);

  // keep canvas width in sync with its container
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.max(200, Math.floor(el.clientWidth))));
    ro.observe(el);
    setWidth(Math.max(200, Math.floor(el.clientWidth)));
    return () => ro.disconnect();
  }, []);

  const { data } = useQuery({
    queryKey: ["editor-peaks", sessionId, version, view.start.toFixed(3), view.end.toFixed(3), width],
    queryFn: () => api.editorPeaks(sessionId, { start: view.start, end: view.end, buckets: width }),
    placeholderData: (prev) => prev,
    staleTime: Infinity,
  });

  // ---- drawing ----
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, width, height);

    const xOf = (t) => ((t - view.start) / viewLen) * width;

    // ruler
    const pxPerSec = width / viewLen;
    const step = TICK_STEPS.find((s) => s * pxPerSec >= 90) ?? TICK_STEPS[TICK_STEPS.length - 1];
    const decimals = step < 0.1 ? 2 : step < 1 ? 1 : 0;
    ctx.font = "10px JetBrains Mono, monospace";
    ctx.textBaseline = "top";
    for (let t = Math.ceil(view.start / step) * step; t <= view.end; t += step) {
      const x = Math.round(xOf(t)) + 0.5;
      ctx.strokeStyle = COLORS.tick;
      ctx.beginPath();
      ctx.moveTo(x, RULER_H - 6);
      ctx.lineTo(x, RULER_H);
      ctx.stroke();
      ctx.fillStyle = COLORS.label;
      ctx.fillText(formatTime(t, decimals), x + 3, 4);
    }

    // lanes
    const lanes = Math.max(1, channels);
    const laneH = (height - RULER_H - LANE_GAP * (lanes - 1)) / lanes;
    for (let c = 0; c < lanes; c++) {
      const top = RULER_H + c * (laneH + LANE_GAP);
      const mid = top + laneH / 2;
      ctx.strokeStyle = COLORS.center;
      ctx.beginPath();
      ctx.moveTo(0, Math.round(mid) + 0.5);
      ctx.lineTo(width, Math.round(mid) + 0.5);
      ctx.stroke();

      const lane = data?.peaks?.[c];
      if (!lane) continue;
      const n = data.buckets;
      const span = (data.end - data.start) / n;
      for (let i = 0; i < n; i++) {
        const t0 = data.start + i * span;
        const x0 = xOf(t0);
        const x1 = xOf(t0 + span);
        const mn = lane[i * 2];
        const mx = lane[i * 2 + 1];
        const inSel = selection && t0 + span / 2 >= selection.start && t0 + span / 2 <= selection.end;
        ctx.fillStyle = inSel ? COLORS.waveSelected : COLORS.wave;
        const y0 = mid - mx * (laneH / 2);
        const y1 = mid - mn * (laneH / 2);
        ctx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
      }
    }

    // selection overlay
    if (selection) {
      const x0 = clamp(xOf(selection.start), 0, width);
      const x1 = clamp(xOf(selection.end), 0, width);
      ctx.fillStyle = COLORS.selection;
      ctx.fillRect(x0, RULER_H, x1 - x0, height - RULER_H);
      ctx.fillStyle = COLORS.wave;
      ctx.fillRect(x0, RULER_H, 1, height - RULER_H);
      ctx.fillRect(x1 - 1, RULER_H, 1, height - RULER_H);
    }
  }, [data, view, viewLen, selection, width, height, channels]);

  // keep the latest props reachable from the non-React event handlers below
  const latest = useRef({});
  latest.current = { view, viewLen, duration, onViewChange, selection, onSelect, onSeek, width };

  // ---- playhead (updated outside React so it doesn't re-render at 60fps) ----
  useEffect(() => {
    let raf;
    const tick = () => {
      const a = audioRef.current;
      const el = headRef.current;
      const { view: v, viewLen: len, width: w, onViewChange: change, duration: dur } = latest.current;
      if (a && el) {
        const t = a.currentTime;
        // follow the playhead when it runs off the right edge during playback
        if (!a.paused && t > v.end && len < dur) {
          const start = clamp(t, 0, dur - len);
          change({ start, end: start + len });
        }
        const x = ((t - v.start) / len) * w;
        el.style.transform = `translateX(${x}px)`;
        el.style.display = x < 0 || x > w ? "none" : "block";
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [audioRef]);

  // ---- wheel: ctrl/cmd = zoom, otherwise pan ----
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e) => {
      const { view: v, viewLen: len, duration: dur, onViewChange: change } = latest.current;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      if (e.ctrlKey || e.metaKey) {
        const anchor = v.start + ((e.clientX - rect.left) / rect.width) * len;
        change(zoomView(v, dur, e.deltaY < 0 ? 0.8 : 1.25, anchor));
      } else if (len < dur) {
        const shift = ((e.deltaX || e.deltaY) / rect.width) * len;
        const start = clamp(v.start + shift, 0, dur - len);
        change({ start, end: start + len });
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // ---- click = move cursor, drag = select, shift+click = extend selection ----
  function onMouseDown(e) {
    if (e.button !== 0) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const timeAt = (clientX) => {
      const { view: v, viewLen: len, duration: dur } = latest.current;
      return clamp(v.start + ((clientX - rect.left) / rect.width) * len, 0, dur);
    };
    const t0 = timeAt(e.clientX);
    const startX = e.clientX;
    const sel = latest.current.selection;
    const extending = e.shiftKey && !!sel;
    const anchor = extending ? (Math.abs(t0 - sel.start) < Math.abs(t0 - sel.end) ? sel.end : sel.start) : t0;
    let dragging = extending;

    const apply = (t) => latest.current.onSelect({ start: Math.min(anchor, t), end: Math.max(anchor, t) });
    if (extending) apply(t0);

    const move = (ev) => {
      if (!dragging && Math.abs(ev.clientX - startX) < 3) return;
      dragging = true;
      apply(timeAt(ev.clientX));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      if (!dragging) {
        latest.current.onSelect(null);
        latest.current.onSeek(t0);
      }
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  const canScroll = viewLen < duration - 1e-6;

  return (
    <div>
      <div ref={wrapRef} className="relative w-full rounded-lg overflow-hidden ring-1 ring-black/40 select-none" style={{ height }}>
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height, display: "block", cursor: "text" }}
          onMouseDown={onMouseDown}
        />
        <div
          ref={headRef}
          className="absolute top-0 left-0 w-px bg-parchment-100 pointer-events-none"
          style={{ height }}
        />
      </div>
      {canScroll && (
        <input
          type="range"
          className="w-full mt-2 accent-brass-500"
          min={0}
          max={duration - viewLen}
          step={Math.max(viewLen / 200, 0.001)}
          value={view.start}
          onChange={(e) => {
            const start = Number(e.target.value);
            onViewChange({ start, end: start + viewLen });
          }}
        />
      )}
    </div>
  );
}

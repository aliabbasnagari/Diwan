import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api.js";

const RULER_H = 22;
const LANE_GAP = 6;
const MIN_VIEW = 0.02;    // seconds — deepest zoom
const MIN_RANGE = 0.01;   // seconds — smallest allowed trim range
const HANDLE_HIT = 8;     // px either side of a handle that grabs it
const TICK_STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800];

const COLORS = {
  bg: "#141310",
  center: "#3a352a",
  wave: "#d9a441",
  dim: "rgba(20, 19, 16, 0.62)",
  handle: "#e6b45c",
  tick: "#5a5342",
  label: "#9a9284",
};

export function formatTime(t, decimals = 1) {
  if (t == null || Number.isNaN(t)) return "–:––";
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0")}`;
}

/** "1:23.4", "83.4" or "1:02:03" -> seconds, or null if it doesn't parse. */
export function parseTime(text) {
  const parts = String(text).trim().split(":");
  if (parts.length > 3 || parts.some((p) => p === "" || Number.isNaN(Number(p)))) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
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
  range, onRangeChange, onSeek, audioRef, height = 240,
}) {
  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const headRef = useRef(null);
  const [width, setWidth] = useState(800);

  const viewLen = Math.max(view.end - view.start, 1e-6);

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
      ctx.fillStyle = COLORS.wave;
      for (let i = 0; i < n; i++) {
        const t0 = data.start + i * span;
        const x0 = xOf(t0);
        const x1 = xOf(t0 + span);
        const y0 = mid - lane[i * 2 + 1] * (laneH / 2);
        const y1 = mid - lane[i * 2] * (laneH / 2);
        ctx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
      }
    }

    // dim everything outside the kept range, then draw the two handles
    const xs = xOf(range.start);
    const xe = xOf(range.end);
    ctx.fillStyle = COLORS.dim;
    if (xs > 0) ctx.fillRect(0, RULER_H, Math.min(xs, width), height - RULER_H);
    if (xe < width) ctx.fillRect(Math.max(xe, 0), RULER_H, width - Math.max(xe, 0), height - RULER_H);

    ctx.fillStyle = COLORS.handle;
    [[xs, -1], [xe, 1]].forEach(([x, dir]) => {
      if (x < -6 || x > width + 6) return;
      ctx.fillRect(x - (dir < 0 ? 0 : 2), RULER_H, 2, height - RULER_H);
      // grip tab on the side facing the kept region
      const tabX = dir < 0 ? x : x - 10;
      ctx.fillRect(tabX, RULER_H, 10, 18);
      ctx.fillStyle = COLORS.bg;
      ctx.fillRect(tabX + 3 + (dir < 0 ? 0 : 1), RULER_H + 4, 1, 10);
      ctx.fillRect(tabX + 6 + (dir < 0 ? 0 : 1), RULER_H + 4, 1, 10);
      ctx.fillStyle = COLORS.handle;
    });
  }, [data, view, viewLen, range, width, height, channels]);

  // keep the latest props reachable from the non-React event handlers below
  const latest = useRef({});
  latest.current = { view, viewLen, duration, onViewChange, range, onRangeChange, onSeek, width };

  // ---- playhead (updated outside React so it doesn't re-render at 60fps) ----
  useEffect(() => {
    let raf;
    const tick = () => {
      const a = audioRef.current;
      const el = headRef.current;
      const { view: v, viewLen: len, width: w, onViewChange: change, duration: dur } = latest.current;
      if (a && el) {
        const t = a.currentTime;
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

  // which handle (if any) is under this x position
  function handleAt(clientX) {
    const rect = canvasRef.current.getBoundingClientRect();
    const { view: v, viewLen: len, range: r } = latest.current;
    const xOf = (t) => rect.left + ((t - v.start) / len) * rect.width;
    const ds = Math.abs(clientX - xOf(r.start));
    const de = Math.abs(clientX - xOf(r.end));
    if (Math.min(ds, de) > HANDLE_HIT) return null;
    return ds <= de ? "start" : "end";
  }

  function onMouseMove(e) {
    if (e.buttons) return;
    canvasRef.current.style.cursor = handleAt(e.clientX) ? "col-resize" : "text";
  }

  // click = move cursor · drag = new range · drag a handle = adjust · shift+click = move nearest handle
  function onMouseDown(e) {
    if (e.button !== 0) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const timeAt = (clientX) => {
      const { view: v, viewLen: len, duration: dur } = latest.current;
      return clamp(v.start + ((clientX - rect.left) / rect.width) * len, 0, dur);
    };
    const setEdge = (edge, t) => {
      const { range: r, duration: dur } = latest.current;
      latest.current.onRangeChange(edge === "start"
        ? { start: clamp(t, 0, r.end - MIN_RANGE), end: r.end }
        : { start: r.start, end: clamp(t, r.start + MIN_RANGE, dur) });
    };

    const t0 = timeAt(e.clientX);
    const grabbed = handleAt(e.clientX);

    if (grabbed || e.shiftKey) {
      const { range: r } = latest.current;
      const edge = grabbed ?? (Math.abs(t0 - r.start) < Math.abs(t0 - r.end) ? "start" : "end");
      setEdge(edge, t0);
      const move = (ev) => setEdge(edge, timeAt(ev.clientX));
      const up = () => {
        window.removeEventListener("mousemove", move);
        window.removeEventListener("mouseup", up);
      };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
      return;
    }

    const startX = e.clientX;
    let dragging = false;
    const move = (ev) => {
      if (!dragging && Math.abs(ev.clientX - startX) < 3) return;
      dragging = true;
      const t = timeAt(ev.clientX);
      if (Math.abs(t - t0) >= MIN_RANGE) latest.current.onRangeChange({ start: Math.min(t0, t), end: Math.max(t0, t) });
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      if (!dragging) latest.current.onSeek(t0);
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
          onMouseMove={onMouseMove}
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

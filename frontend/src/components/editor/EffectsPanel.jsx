import { useEffect, useMemo, useState } from "react";
import { Play, Check } from "lucide-react";
import { formatTime } from "./Waveform.jsx";

function defaultsFor(effect) {
  return Object.fromEntries((effect?.params || []).map((p) => [p.key, p.default]));
}

function ParamField({ param, value, onChange }) {
  if (param.type === "select") {
    return (
      <label className="block">
        <span className="label-eyebrow block mb-1">{param.label}</span>
        <select className="select w-full" value={value} onChange={(e) => onChange(e.target.value)}>
          {param.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  return (
    <label className="block">
      <span className="label-eyebrow flex justify-between mb-1">
        <span>{param.label}</span>
        <span className="font-mono normal-case tracking-normal text-parchment-500">{param.unit}</span>
      </span>
      <div className="flex items-center gap-3">
        <input
          type="range"
          className="flex-1 accent-brass-500"
          min={param.min} max={param.max} step={param.step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <input
          type="number"
          className="input !w-24 !py-1.5"
          min={param.min} max={param.max} step={param.step}
          value={value}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        />
      </div>
    </label>
  );
}

export default function EffectsPanel({ catalog, channels, selection, busy, onPreview, onApply }) {
  const [name, setName] = useState("amplify");
  const effect = useMemo(() => catalog.find((e) => e.name === name), [catalog, name]);
  const [values, setValues] = useState(() => defaultsFor(effect));

  useEffect(() => setValues(defaultsFor(effect)), [effect]);

  const groups = useMemo(() => {
    const map = new Map();
    catalog.forEach((e) => {
      if (!map.has(e.group)) map.set(e.group, []);
      map.get(e.group).push(e);
    });
    return [...map.entries()];
  }, [catalog]);

  if (!effect) return null;

  const wholeOnly = effect.whole_only;
  const needsSelectionMissing = effect.needs_selection && !selection;
  const stereoMissing = effect.stereo_only && channels !== 2;
  const disabled = busy || needsSelectionMissing || stereoMissing;

  let scope = "the whole track";
  if (wholeOnly) scope = "the whole track (this effect can't target a selection)";
  else if (selection) scope = `the selection (${formatTime(selection.start)} – ${formatTime(selection.end)})`;

  const payload = () => ({
    effect: effect.name,
    params: values,
    start: wholeOnly ? null : selection?.start ?? null,
    end: wholeOnly ? null : selection?.end ?? null,
  });

  return (
    <div className="panel p-5 space-y-4">
      <div>
        <p className="label-eyebrow mb-2">Effect</p>
        <select className="select w-full" value={name} onChange={(e) => setName(e.target.value)}>
          {groups.map(([group, items]) => (
            <optgroup key={group} label={group}>
              {items.map((e) => <option key={e.name} value={e.name}>{e.label}</option>)}
            </optgroup>
          ))}
        </select>
      </div>

      {effect.params.length > 0 && (
        <div className="space-y-3">
          {effect.params.map((p) => (
            <ParamField
              key={p.key}
              param={p}
              value={values[p.key] ?? p.default}
              onChange={(v) => setValues((s) => ({ ...s, [p.key]: v }))}
            />
          ))}
        </div>
      )}

      <p className="text-[11px] font-mono text-parchment-700 leading-snug">
        Applies to {scope}.
        {needsSelectionMissing && <span className="text-rust-400"> Select a region first.</span>}
        {stereoMissing && <span className="text-rust-400"> Needs a stereo track.</span>}
      </p>

      <div className="flex gap-2">
        <button className="btn-ghost flex items-center gap-1.5" disabled={disabled} onClick={() => onPreview(payload())}
          title="Render a short sample of the effect and play it — nothing is changed">
          <Play className="w-3.5 h-3.5" /> Preview
        </button>
        <button className="btn-primary flex-1 flex items-center justify-center gap-1.5 !py-2" disabled={disabled}
          onClick={() => onApply(payload(), effect.label)}>
          <Check className="w-3.5 h-3.5" /> Apply
        </button>
      </div>
    </div>
  );
}

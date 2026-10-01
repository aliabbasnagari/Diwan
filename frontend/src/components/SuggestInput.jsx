import { useEffect, useId, useMemo, useRef, useState } from "react";

const MAX_VISIBLE = 50;

// Text input with a themed suggestion dropdown (replaces the native <datalist>).
// With `multi`, the value is a comma-separated list and suggestions apply to
// the segment being typed (used for multi-value artist tags).
export default function SuggestInput({ value, onChange, suggestions = [], multi = false, label, className = "input", ...rest }) {
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const wrapRef = useRef(null);
  const listRef = useRef(null);

  const text = value ?? "";
  const lastComma = multi ? text.lastIndexOf(",") : -1;
  const head = lastComma >= 0 ? text.slice(0, lastComma + 1) : "";
  const query = text.slice(lastComma + 1).trim().toLowerCase();

  const options = useMemo(() => {
    const taken = multi
      ? new Set(head.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean))
      : new Set();
    const seen = new Set();
    const out = [];
    for (const raw of suggestions) {
      const s = String(raw);
      const key = s.toLowerCase();
      if (seen.has(key) || taken.has(key)) continue;
      seen.add(key);
      if (query && !key.includes(query)) continue;
      if (key === query) continue; // already fully typed
      out.push(s);
    }
    // prefix matches first
    out.sort((a, b) => Number(!a.toLowerCase().startsWith(query)) - Number(!b.toLowerCase().startsWith(query)));
    return out.slice(0, MAX_VISIBLE);
  }, [suggestions, query, head, multi]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (active >= 0) listRef.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const pick = (s) => {
    const next = multi ? `${head}${head ? " " : ""}${s}` : s;
    onChange({ target: { value: next } });
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e) => {
    if (!open || options.length === 0) {
      if (e.key === "ArrowDown" && options.length) {
        setOpen(true);
        e.preventDefault();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === "Escape") {
      e.stopPropagation();
      setOpen(false);
    }
  };

  return (
    <div>
      {label && (
        <label htmlFor={inputId} className="label-eyebrow block mb-1">{label}</label>
      )}
    <div ref={wrapRef} className="relative">
      <input
        {...rest}
        id={inputId}
        className={`${className} w-full`}
        value={text}
        autoComplete="off"
        onChange={(e) => {
          onChange(e);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && options.length > 0 && (
        <ul
          ref={listRef}
          role="listbox"
          className="absolute z-50 left-0 right-0 mt-1 max-h-56 overflow-y-auto rounded-lg border border-ink-600 bg-ink-900 shadow-panel py-1"
        >
          {options.map((s, i) => (
            <li
              key={s}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault(); // keep input focus
                pick(s);
              }}
              onMouseEnter={() => setActive(i)}
              className={`px-3 py-1.5 text-xs font-mono cursor-pointer truncate ${
                i === active ? "bg-brass-900 text-brass-400" : "text-parchment-300 hover:bg-ink-700"
              }`}
            >
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
    </div>
  );
}

/** Square "sleeve" thumbnail with a record disc peeking from behind —
 * used once per album header so it reads as a deliberate motif, not noise. */
export default function AlbumArt({ src, size = "md", alt = "" }) {
  const dims = size === "lg" ? "w-16 h-16" : size === "md" ? "w-12 h-12" : "w-9 h-9";
  const peek = size === "lg" ? "w-10 h-10 -right-3" : size === "md" ? "w-8 h-8 -right-2" : "w-6 h-6 -right-1.5";

  return (
    <div className={`relative ${dims} shrink-0`}>
      <div
        className={`absolute top-1/2 -translate-y-1/2 ${peek} rounded-full`}
        style={{
          background:
            "radial-gradient(circle at 35% 35%, #3a352a 0%, #1b1a17 55%, #0e0d0a 100%)",
          boxShadow: "0 0 0 1px rgba(0,0,0,0.4)",
        }}
      />
      {src ? (
        <img
          src={src}
          alt={alt}
          className={`relative ${dims} rounded-md object-cover bg-ink-950 ring-1 ring-black/40`}
        />
      ) : (
        <div className={`relative ${dims} rounded-md bg-ink-700 ring-1 ring-black/40 flex items-center justify-center text-parchment-700 font-display text-xs`}>
          ♪
        </div>
      )}
    </div>
  );
}

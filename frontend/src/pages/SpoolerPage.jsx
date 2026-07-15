import { useQuery } from "@tanstack/react-query";
import { api } from "../api.js";
import UrlForm from "../components/UrlForm.jsx";
import DownloadCard from "../components/DownloadCard.jsx";
import HistoryCard from "../components/HistoryCard.jsx";

const ACTIVE = new Set(["queued", "fetching_info", "downloading", "processing", "tagging"]);

export default function SpoolerPage() {
  const downloadsQuery = useQuery({
    queryKey: ["downloads"],
    queryFn: api.listDownloads,
    refetchInterval: 1500,
  });

  const statsQuery = useQuery({
    queryKey: ["download-stats"],
    queryFn: api.downloadStats,
    refetchInterval: 1500,
  });

  const downloads = downloadsQuery.data || [];
  const active = downloads.filter((d) => ACTIVE.has(d.status));
  const history = downloads.filter((d) => !ACTIVE.has(d.status));
  const stats = statsQuery.data;

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-6">
        <div>
          <h1 className="font-display font-bold text-2xl">Spooler</h1>
          <p className="text-sm text-parchment-500 mt-1">
            Pull video &amp; audio from the web straight into your library.
          </p>
        </div>
        <div className="flex gap-4 font-mono text-right">
          <StatPill label="Active" value={stats?.active} />
          <StatPill label="Done" value={stats?.completed} />
          <StatPill label="Failed" value={stats?.failed} />
        </div>
      </header>

      <UrlForm downloads={downloads} />

      {active.length > 0 && (
        <>
          <p className="label-eyebrow mt-8 mb-3">On the spool</p>
          <div className="space-y-2.5">
            {active.map((item) => (
              <DownloadCard key={item.id} item={item} />
            ))}
          </div>
        </>
      )}

      <p className="label-eyebrow mt-8 mb-3">History</p>
      {history.length === 0 ? (
        <div className="text-center py-16 px-6 border border-dashed border-ink-600 rounded-xl text-parchment-700 font-mono text-sm">
          Nothing downloaded yet — paste a URL above to get started.
        </div>
      ) : (
        <div className="space-y-2.5">
          {history.map((item) => (
            <HistoryCard key={item.id} item={item} />
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

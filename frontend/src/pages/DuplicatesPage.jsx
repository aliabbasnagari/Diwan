import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ScanSearch, AlertTriangle } from "lucide-react";
import { api } from "../api.js";
import DuplicateGroupCard from "../components/DuplicateGroupCard.jsx";

const ACTIVE_STATUSES = new Set(["queued", "hashing", "fingerprinting", "scoring"]);

const TABS = [
  { value: "exact", label: "Exact" },
  { value: "audio_match", label: "Audio match" },
  { value: "near_match", label: "Near match" },
  { value: "different_recording", label: "Different recording" },
];

const STATUS_LABEL = {
  queued: "Queued…",
  hashing: "Hashing files…",
  fingerprinting: "Fingerprinting audio…",
  scoring: "Scoring & grouping…",
};

export default function DuplicatesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState("exact");

  const statusQuery = useQuery({
    queryKey: ["duplicate-scan-status"],
    queryFn: api.duplicateScanStatus,
    refetchInterval: (query) => (ACTIVE_STATUSES.has(query.state.data?.status) ? 1500 : 4000),
  });

  const groupsQuery = useQuery({
    queryKey: ["duplicate-groups", tab],
    queryFn: () => api.listDuplicateGroups(tab),
  });

  const scanMutation = useMutation({
    mutationFn: api.startDuplicateScan,
    onSuccess: () => {
      toast.success("Scan started");
      qc.invalidateQueries({ queryKey: ["duplicate-scan-status"] });
    },
    onError: (e) => toast.error(e.message),
  });

  const cancelMutation = useMutation({
    mutationFn: api.cancelDuplicateScan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["duplicate-scan-status"] }),
  });

  const job = statusQuery.data;
  const isActive = job && ACTIVE_STATUSES.has(job.status);
  const pct = job?.total ? Math.round((job.processed / job.total) * 100) : 0;
  const groups = groupsQuery.data || [];

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-6">
        <div>
          <h1 className="font-display font-bold text-2xl">Duplicates</h1>
          <p className="text-sm text-parchment-500 mt-1">
            Finds exact copies, re-encodes, trimmed/edited near-duplicates, and flags different
            recordings (live, remaster, remix) of the same song.
          </p>
        </div>
        {isActive ? (
          <button className="btn-ghost-danger shrink-0" onClick={() => cancelMutation.mutate()} disabled={cancelMutation.isPending}>
            Cancel scan
          </button>
        ) : (
          <button
            className="btn-primary flex items-center gap-1.5 shrink-0"
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
          >
            <ScanSearch className="w-3.5 h-3.5" /> Scan for duplicates
          </button>
        )}
      </header>

      {job && (isActive || job.status === "failed") && (
        <div className="panel p-4 mb-6 space-y-2">
          <div className="flex justify-between text-xs font-mono text-parchment-500">
            <span>{STATUS_LABEL[job.status] || job.status}</span>
            <span>{job.total ? `${job.processed} / ${job.total}` : ""}</span>
          </div>
          {isActive && (
            <div className="h-1.5 rounded-full bg-ink-950 overflow-hidden">
              <div className="h-full bg-brass-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
          )}
          {job.phase_detail && <p className="text-[11px] font-mono text-parchment-700 truncate">{job.phase_detail}</p>}
          {job.status === "failed" && job.error_message && (
            <p className="flex items-center gap-1.5 text-[11px] font-mono text-rust-400">
              <AlertTriangle className="w-3 h-3 shrink-0" /> {job.error_message}
            </p>
          )}
        </div>
      )}

      {job?.status === "completed" && job.fingerprint_failures > 0 && (
        <div className="mb-6 flex items-center gap-2 text-xs font-mono px-3 py-2 rounded-lg bg-brass-900/30 border border-brass-700/50 text-brass-400">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          {job.fingerprint_failures} file{job.fingerprint_failures === 1 ? "" : "s"} could not be acoustically
          fingerprinted (only exact-hash duplicates checked for them) — is <code className="font-mono">fpcalc</code> (Chromaprint) installed on PATH?
        </div>
      )}

      <div className="flex gap-1 border-b border-ink-600 mb-5">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={`px-3.5 py-2 text-xs font-mono uppercase tracking-wide border-b-2 -mb-px ${
              tab === t.value ? "border-brass-500 text-brass-400" : "border-transparent text-parchment-500 hover:text-parchment-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {groupsQuery.isLoading ? (
        <p className="text-sm text-parchment-500 font-mono">Loading…</p>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 px-6 border border-dashed border-ink-600 rounded-xl text-parchment-700 font-mono text-sm">
          Nothing here — run a scan to look for duplicates.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {groups.map((g) => (
            <DuplicateGroupCard key={g.id} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}

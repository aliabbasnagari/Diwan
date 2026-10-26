import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ScanSearch, AlertTriangle, Sparkles, HardDrive } from "lucide-react";
import { api } from "../api.js";
import { formatBytes } from "../utils.js";
import DuplicateGroupCard from "../components/DuplicateGroupCard.jsx";

const ACTIVE_STATUSES = new Set([
  "queued",
  "hashing",
  "fingerprinting",
  "scoring",
]);

const CATEGORIES = [
  { value: "exact", label: "Exact", dot: "bg-moss-400" },
  { value: "audio_match", label: "Audio match", dot: "bg-teal-400" },
  { value: "near_match", label: "Near match", dot: "bg-brass-400" },
  {
    value: "different_recording",
    label: "Different recording",
    dot: "bg-parchment-500",
  },
];

const AUTO_RESOLVABLE = new Set(["exact", "audio_match"]);

const STATUS_LABEL = {
  queued: "Queued…",
  hashing: "Hashing files…",
  fingerprinting: "Fingerprinting audio…",
  scoring: "Scoring & grouping…",
};

function reclaimableBytes(group) {
  if (group.category === "different_recording") return 0;
  const suggested = group.members.find((m) => m.is_suggested_keeper);
  return group.members
    .filter((m) => m !== suggested)
    .reduce((sum, m) => sum + (m.filesize || 0), 0);
}

export default function DuplicatesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState("exact");

  const statusQuery = useQuery({
    queryKey: ["duplicate-scan-status"],
    queryFn: api.duplicateScanStatus,
    refetchInterval: (query) =>
      ACTIVE_STATUSES.has(query.state.data?.status) ? 1500 : 4000,
  });

  const groupsQuery = useQuery({
    queryKey: ["duplicate-groups"],
    queryFn: () => api.listDuplicateGroups(),
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
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["duplicate-scan-status"] }),
  });

  const bulkResolveMutation = useMutation({
    mutationFn: async (groups) => {
      let kept = 0,
        removed = 0,
        failed = 0;
      for (const g of groups) {
        const suggested =
          g.members.find((m) => m.is_suggested_keeper) || g.members[0];
        try {
          const res = await api.resolveDuplicateGroup(g.id, [suggested.path]);
          kept += res.kept.length;
          removed += res.quarantined.length;
        } catch {
          failed += 1;
        }
      }
      return { kept, removed, failed };
    },
    onSuccess: (res) => {
      toast.success(
        `Resolved — kept ${res.kept}, quarantined ${res.removed}${res.failed ? `, ${res.failed} failed` : ""}`,
      );
      qc.invalidateQueries({ queryKey: ["duplicate-groups"] });
      qc.invalidateQueries({ queryKey: ["duplicate-trash"] });
    },
  });

  const allGroups = groupsQuery.data || [];
  const byCategory = useMemo(() => {
    const map = {
      exact: [],
      audio_match: [],
      near_match: [],
      different_recording: [],
    };
    for (const g of allGroups) {
      (map[g.category] || (map[g.category] = [])).push(g);
    }
    return map;
  }, [allGroups]);

  const totalReclaimable = useMemo(
    () => allGroups.reduce((sum, g) => sum + reclaimableBytes(g), 0),
    [allGroups],
  );

  const job = statusQuery.data;
  const isActive = job && ACTIVE_STATUSES.has(job.status);
  const pct = job?.total ? Math.round((job.processed / job.total) * 100) : 0;
  const groups = byCategory[tab] || [];
  const showBulkResolve = AUTO_RESOLVABLE.has(tab) && groups.length > 0;

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-6">
        <div>
          <h1 className="font-display font-bold text-2xl">Duplicates</h1>
          <p className="text-sm text-parchment-500 mt-1">
            Finds exact copies, re-encodes, trimmed/edited near-duplicates, and
            flags different recordings (live, remaster, remix) of the same song.
          </p>
        </div>
        {isActive ? (
          <button
            className="btn-ghost-danger shrink-0"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
          >
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
              <div
                className="h-full bg-brass-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
          {job.phase_detail && (
            <p className="text-[11px] font-mono text-parchment-700 truncate">
              {job.phase_detail}
            </p>
          )}
          {job.status === "failed" && job.error_message && (
            <p className="flex items-center gap-1.5 text-[11px] font-mono text-rust-400">
              <AlertTriangle className="w-3 h-3 shrink-0" /> {job.error_message}
            </p>
          )}
        </div>
      )}

      {job?.status === "completed" && job.fingerprint_failures > 0 && (
        <div className="mb-6 flex flex-col gap-1.5 text-xs font-mono px-3 py-2.5 rounded-lg bg-brass-900/30 border border-brass-700/50 text-brass-400">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            {job.fingerprint_failures} file
            {job.fingerprint_failures === 1 ? "" : "s"} could not be
            acoustically fingerprinted (only exact-hash duplicates checked for{" "}
            {job.fingerprint_failures === 1 ? "it" : "them"})
          </div>
          {job.error_message && (
            <pre className="whitespace-pre-wrap text-[10.5px] text-parchment-500 pl-5">
              {job.error_message}
            </pre>
          )}
        </div>
      )}

      {allGroups.length > 0 && (
        <div className="panel p-4 mb-6 flex items-center gap-3">
          <HardDrive className="w-4 h-4 text-brass-400 shrink-0" />
          <div>
            <p className="text-sm font-medium">
              Up to{" "}
              <span className="text-brass-400">
                {formatBytes(totalReclaimable)}
              </span>{" "}
              reclaimable
            </p>
            <p className="text-[11px] font-mono text-parchment-700">
              {allGroups.length} group{allGroups.length === 1 ? "" : "s"}{" "}
              waiting for review, using each group's suggested keeper
            </p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
        <div className="flex gap-2 flex-wrap">
          {CATEGORIES.map((c) => {
            const count = (byCategory[c.value] || []).length;
            const active = tab === c.value;
            return (
              <button
                key={c.value}
                onClick={() => setTab(c.value)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono border transition ${
                  active
                    ? "bg-brass-900 border-brass-700 text-brass-400"
                    : "border-ink-600 text-parchment-500 hover:text-parchment-100 hover:border-ink-400"
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
                {c.label}
                <span className="text-[10px] text-parchment-700">{count}</span>
              </button>
            );
          })}
        </div>

        {showBulkResolve && (
          <button
            className="btn-ghost flex items-center gap-1.5 text-xs"
            onClick={() => bulkResolveMutation.mutate(groups)}
            disabled={bulkResolveMutation.isPending}
          >
            <Sparkles className="w-3.5 h-3.5" />
            {bulkResolveMutation.isPending
              ? "Resolving…"
              : `Auto-resolve all ${groups.length} using suggested keeper`}
          </button>
        )}
      </div>

      {groupsQuery.isLoading ? (
        <p className="text-sm text-parchment-500 font-mono">Loading…</p>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 px-6 border border-dashed border-ink-600 rounded-xl text-parchment-700 font-mono text-sm">
          {allGroups.length === 0
            ? "Nothing here — run a scan to look for duplicates."
            : "Nothing in this category."}
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <DuplicateGroupCard key={g.id} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}

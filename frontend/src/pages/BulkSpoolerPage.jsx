import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, arrayMove } from "@dnd-kit/sortable";
import { api } from "../api.js";
import BulkUrlForm from "../components/BulkUrlForm.jsx";
import BulkPendingItem from "../components/BulkPendingItem.jsx";
import BulkActiveItem from "../components/BulkActiveItem.jsx";
import BulkHistoryItem from "../components/BulkHistoryItem.jsx";

const HISTORY_STATUSES = new Set(["completed", "failed", "cancelled", "skipped_duplicate"]);

function Countdown({ iso }) {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!iso) return;
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [iso]);

  if (!iso) return null;
  const remaining = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 1000));
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  return (
    <span>
      Next download in {m}:{String(s).padStart(2, "0")}
    </span>
  );
}

export default function BulkSpoolerPage() {
  const qc = useQueryClient();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const itemsQuery = useQuery({ queryKey: ["bulk-items"], queryFn: api.listBulkItems, refetchInterval: 2000 });
  const statsQuery = useQuery({ queryKey: ["bulk-stats"], queryFn: api.bulkSpoolerStats, refetchInterval: 2000 });
  const statusQuery = useQuery({ queryKey: ["bulk-status"], queryFn: api.bulkSpoolerStatus, refetchInterval: 2000 });

  const items = itemsQuery.data || [];
  const stats = statsQuery.data;
  const status = statusQuery.data;

  const active = items.filter((i) => i.status === "downloading");
  const pending = useMemo(
    () => items.filter((i) => i.status === "pending").sort((a, b) => a.position - b.position),
    [items]
  );
  const history = items.filter((i) => HISTORY_STATUSES.has(i.status)).slice().reverse();

  const [localPending, setLocalPending] = useState(pending);
  useEffect(() => setLocalPending(pending), [pending]);

  const reorderMutation = useMutation({
    mutationFn: (order) => api.reorderBulkItems(order),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bulk-items"] }),
  });

  const removeMutation = useMutation({
    mutationFn: (id) => api.deleteBulkItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bulk-items"] }),
  });

  function handleDragEnd(e) {
    const { active: dragged, over } = e;
    if (!over || dragged.id === over.id) return;
    const oldIndex = localPending.findIndex((i) => i.id === dragged.id);
    const newIndex = localPending.findIndex((i) => i.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    const next = arrayMove(localPending, oldIndex, newIndex);
    setLocalPending(next);
    reorderMutation.mutate(next.map((i) => i.id));
  }

  return (
    <div>
      <header className="flex items-start justify-between gap-6 mb-6">
        <div>
          <h1 className="font-display font-bold text-2xl">Bulk Spooler</h1>
          <p className="text-sm text-parchment-500 mt-1">
            Queue a batch of URLs; they download one at a time with a random 3–6 minute pause between each.
          </p>
        </div>
        <div className="flex gap-4 font-mono text-right">
          <StatPill label="Queued" value={stats?.pending} />
          <StatPill label="Done" value={stats?.completed} />
          <StatPill label="Failed" value={stats?.failed} />
          <StatPill label="Skipped" value={stats?.skipped_duplicates} />
        </div>
      </header>

      <BulkUrlForm />

      {active.length > 0 && (
        <>
          <p className="label-eyebrow mt-8 mb-3">Downloading now</p>
          <div className="space-y-2.5">
            {active.map((item) => (
              <BulkActiveItem key={item.id} item={item} />
            ))}
          </div>
        </>
      )}

      {status?.next_run_at && (
        <p className="mt-4 text-xs font-mono text-brass-400 flex items-center gap-1.5">
          <Countdown iso={status.next_run_at} />
        </p>
      )}

      <p className="label-eyebrow mt-8 mb-3">
        Up next {pending.length > 0 ? `(${pending.length}) — drag to reorder` : ""}
      </p>
      {localPending.length === 0 ? (
        <div className="text-center py-10 px-6 border border-dashed border-ink-600 rounded-xl text-parchment-700 font-mono text-sm">
          Nothing queued — paste URLs above to get started.
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={localPending.map((i) => i.id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-2">
              {localPending.map((item) => (
                <BulkPendingItem
                  key={item.id}
                  item={item}
                  pending={removeMutation.isPending}
                  onRemove={(id) => removeMutation.mutate(id)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {history.length > 0 && (
        <>
          <p className="label-eyebrow mt-8 mb-3">History</p>
          <div className="space-y-2.5">
            {history.map((item) => (
              <BulkHistoryItem key={item.id} item={item} />
            ))}
          </div>
        </>
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

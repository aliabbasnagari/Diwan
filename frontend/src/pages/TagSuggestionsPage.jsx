import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Pencil, Trash2, X, Check, FolderSync } from "lucide-react";
import { api } from "../api.js";

const FIELDS = [
    { value: "artist", label: "Artist" },
    { value: "album_artist", label: "Album Artist" },
    { value: "album", label: "Album" },
    { value: "genre", label: "Genre" },
    { value: "year", label: "Year" },
];

export default function TagSuggestionsPage() {
    const qc = useQueryClient();
    const { data: suggestions, isLoading } = useQuery({
        queryKey: ["tag-suggestions-all"],
        queryFn: api.getAllTagSuggestions,
    });

    const [activeTab, setActiveTab] = useState("artist");
    const [addingValue, setAddingValue] = useState("");
    const [editingId, setEditingId] = useState(null);
    const [editingValue, setEditingValue] = useState("");

    const invalidate = () => {
        qc.invalidateQueries({ queryKey: ["tag-suggestions-all"] });
        qc.invalidateQueries({ queryKey: ["tag-suggestions"] });
    };

    const createMut = useMutation({
        mutationFn: () => api.createTagSuggestion(activeTab, addingValue),
        onSuccess: () => {
            toast.success("Suggestion added");
            setAddingValue("");
            invalidate();
        },
        onError: (e) => toast.error(e.message),
    });

    const updateMut = useMutation({
        mutationFn: ({ id, value }) => api.updateTagSuggestion(id, { value }),
        onSuccess: () => {
            toast.success("Suggestion updated");
            setEditingId(null);
            invalidate();
        },
        onError: (e) => toast.error(e.message),
    });

    const deleteMut = useMutation({
        mutationFn: (id) => api.deleteTagSuggestion(id),
        onSuccess: () => {
            toast.success("Suggestion deleted");
            invalidate();
        },
        onError: (e) => toast.error(e.message),
    });

    const populateMut = useMutation({
        mutationFn: () => api.populateTagSuggestions(),
        onSuccess: (data) => {
            toast.success(`Scanned ${data.scanned} files — ${data.added} new`);
            invalidate();
        },
        onError: (e) => toast.error(e.message),
    });

    // Group all suggestions by field
    const grouped = {};
    for (const f of FIELDS) grouped[f.value] = [];
    for (const s of (suggestions || [])) {
        if (!grouped[s.field]) grouped[s.field] = [];
        grouped[s.field].push(s);
    }

    const activeItems = grouped[activeTab] || [];

    if (isLoading) {
        return <p className="text-sm text-parchment-500 font-mono">Loading tag suggestions…</p>;
    }

    return (
        <div className="max-w-4xl">
            {/* Header */}
            <header className="mb-6 flex items-start justify-between gap-4">
                <div>
                    <h1 className="font-display font-bold text-2xl">Tag Suggestions</h1>
                    <p className="text-sm text-parchment-500 mt-1">
                        Manage the autocomplete values that appear when tagging music.
                    </p>
                </div>
                <button
                    className="btn-ghost flex items-center gap-1.5 shrink-0 mt-1"
                    disabled={populateMut.isPending}
                    onClick={() => populateMut.mutate()}
                >
                    <FolderSync className={`w-3.5 h-3.5 ${populateMut.isPending ? "animate-spin" : ""}`} />
                    {populateMut.isPending ? "Scanning…" : "Populate from Library"}
                </button>
            </header>

            {/* Tabs + Content in one panel */}
            <section className="panel overflow-hidden">
                {/* Tab bar */}
                <div className="flex border-b border-ink-600 overflow-x-auto">
                    {FIELDS.map((f) => (
                        <button
                            key={f.value}
                            onClick={() => { setActiveTab(f.value); setEditingId(null); }}
                            className={`relative px-4 py-3 text-xs font-display uppercase tracking-[0.12em] whitespace-nowrap transition-colors ${activeTab === f.value
                                ? "text-brass-400"
                                : "text-parchment-700 hover:text-parchment-300"
                                }`}
                        >
                            {f.label}
                            {grouped[f.value].length > 0 && (
                                <span className={`ml-1.5 text-[10px] font-mono px-1.5 py-0.5 rounded-full ${activeTab === f.value
                                    ? "bg-brass-900 text-brass-400"
                                    : "bg-ink-700 text-parchment-500"
                                    }`}>
                                    {grouped[f.value].length}
                                </span>
                            )}
                            {activeTab === f.value && (
                                <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-brass-500 rounded-full" />
                            )}
                        </button>
                    ))}
                </div>

                {/* Add bar */}
                <div className="flex items-center gap-3 px-5 py-3 border-b border-ink-600 bg-ink-800/60">
                    <input
                        className="input flex-1"
                        placeholder={`Add ${FIELDS.find(f => f.value === activeTab)?.label.toLowerCase()}…`}
                        value={addingValue}
                        onChange={(e) => setAddingValue(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && addingValue.trim()) createMut.mutate();
                        }}
                    />
                    <button
                        className="btn-primary flex items-center gap-1.5 py-2"
                        disabled={!addingValue.trim() || createMut.isPending}
                        onClick={() => createMut.mutate()}
                    >
                        <Plus className="w-3.5 h-3.5" />
                        {createMut.isPending ? "Adding…" : "Add"}
                    </button>
                </div>

                {/* Chips area */}
                <div className="p-5 min-h-[200px]">
                    {activeItems.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                            {activeItems.map((s) => (
                                <div key={s.id} className="group">
                                    {editingId === s.id ? (
                                        /* ---- inline edit ---- */
                                        <div className="flex items-center gap-1 bg-ink-700 border border-brass-600 rounded-lg px-1 py-1">
                                            <input
                                                className="bg-transparent text-sm font-mono text-parchment-100 outline-none px-2 py-0.5 w-40"
                                                autoFocus
                                                value={editingValue}
                                                onChange={(e) => setEditingValue(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === "Enter" && editingValue.trim())
                                                        updateMut.mutate({ id: s.id, value: editingValue });
                                                    if (e.key === "Escape") setEditingId(null);
                                                }}
                                            />
                                            <button
                                                className="text-moss-400 hover:text-moss-500 p-0.5"
                                                title="Save"
                                                disabled={!editingValue.trim() || updateMut.isPending}
                                                onClick={() => updateMut.mutate({ id: s.id, value: editingValue })}
                                            >
                                                <Check className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                className="text-parchment-500 hover:text-parchment-100 p-0.5"
                                                title="Cancel"
                                                onClick={() => setEditingId(null)}
                                            >
                                                <X className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    ) : (
                                        /* ---- display chip ---- */
                                        <div className="flex items-center gap-1.5 bg-ink-700 border border-ink-600 rounded-lg px-3 py-1.5 hover:border-ink-500 transition-colors">
                                            <span className="text-sm font-mono text-parchment-100">
                                                {s.value}
                                            </span>
                                            <span className="text-[10px] font-mono text-parchment-700">
                                                {s.use_count}×
                                            </span>
                                            <button
                                                className="text-parchment-700 hover:text-brass-400 transition p-0.5 opacity-0 group-hover:opacity-100"
                                                title="Edit"
                                                onClick={() => {
                                                    setEditingId(s.id);
                                                    setEditingValue(s.value);
                                                }}
                                            >
                                                <Pencil className="w-3 h-3" />
                                            </button>
                                            <button
                                                className="text-parchment-700 hover:text-rust-400 transition p-0.5 opacity-0 group-hover:opacity-100"
                                                title="Delete"
                                                onClick={() => deleteMut.mutate(s.id)}
                                            >
                                                <X className="w-3 h-3" />
                                            </button>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex items-center justify-center h-32 text-center">
                            <div>
                                <p className="text-sm text-parchment-500 font-mono">
                                    No {FIELDS.find(f => f.value === activeTab)?.label.toLowerCase()} suggestions yet.
                                </p>
                                <p className="text-xs text-parchment-700 mt-1">
                                    Add one above, or use "Populate from Library" to scan your files.
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer stats */}
                {(suggestions || []).length > 0 && (
                    <div className="px-5 py-2.5 border-t border-ink-600 flex items-center justify-between">
                        <span className="text-[11px] font-mono text-parchment-700">
                            {activeItems.length} in this tab
                        </span>
                        <span className="text-[11px] font-mono text-parchment-700">
                            {(suggestions || []).length} total across all fields
                        </span>
                    </div>
                )}
            </section>
        </div>
    );
}

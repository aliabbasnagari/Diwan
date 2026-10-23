import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, X } from "lucide-react";

export default function BulkPendingItem({ item, onRemove, pending }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} className="panel p-3 flex items-center gap-3">
      <button
        className="shrink-0 text-parchment-700 hover:text-parchment-300 cursor-grab active:cursor-grabbing touch-none"
        title="Drag to reorder"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="w-4 h-4" />
      </button>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-mono truncate">{item.url}</p>
        <p className="text-[10.5px] font-mono text-parchment-700 mt-0.5">
          {item.media_type === "audio" ? item.audio_format : `${item.quality}${item.quality !== "best" ? "p" : ""}`}
          {item.add_to_library ? " · library" : ""}
          {item.tag_artist ? ` · ${item.tag_artist}` : ""}
        </p>
      </div>

      <button
        className="shrink-0 text-parchment-700 hover:text-rust-400 transition p-1"
        title="Remove from queue"
        onClick={() => onRemove(item.id)}
        disabled={pending}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

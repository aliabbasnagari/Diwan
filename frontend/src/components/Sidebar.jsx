import { NavLink } from "react-router-dom";
import { Disc3, Library, DownloadCloud, Settings } from "lucide-react";

const links = [
  { to: "/", label: "Library", icon: Library, end: true },
  { to: "/spooler", label: "Spooler", icon: DownloadCloud },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 border-r border-ink-600 flex flex-col">
      <div className="px-5 py-6 flex items-center gap-2.5 border-b border-ink-600">
        <Disc3 className="w-6 h-6 text-brass-500" strokeWidth={1.75} />
        <span className="font-display font-bold text-lg tracking-tight">Crate</span>
      </div>

      <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                isActive
                  ? "bg-brass-900 text-brass-400"
                  : "text-parchment-500 hover:text-parchment-100 hover:bg-ink-800"
              }`
            }
          >
            <Icon className="w-4 h-4" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-ink-600">
        <p className="text-[11px] font-mono text-parchment-700 leading-relaxed">
          Library manager &amp; media spooler for Navidrome.
        </p>
      </div>
    </aside>
  );
}

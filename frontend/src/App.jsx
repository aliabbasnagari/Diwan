import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import UrlForm from "./components/UrlForm.jsx";
import TrackCard from "./components/TrackCard.jsx";

const ACTIVE_STATUSES = new Set(["queued", "fetching_info", "downloading", "processing"]);

export default function App() {
  const [downloads, setDownloads] = useState([]);
  const [stats, setStats] = useState({ total: 0, completed: 0, failed: 0, active: 0 });
  const pollRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [list, s] = await Promise.all([api.listDownloads(), api.stats()]);
      setDownloads(list);
      setStats(s);
    } catch (e) {
      // backend not reachable yet; ignore, next poll will retry
    }
  }, []);

  useEffect(() => {
    refresh();
    pollRef.current = setInterval(() => {
      refresh();
    }, 1500);
    return () => clearInterval(pollRef.current);
  }, [refresh]);

  const active = downloads.filter((d) => ACTIVE_STATUSES.has(d.status));
  const history = downloads.filter((d) => !ACTIVE_STATUSES.has(d.status));

  return (
    <div className="app">
      <header className="masthead">
        <div>
          <h1 className="masthead-title">
            <span className="dot" />
            Spooler
          </h1>
          <p className="masthead-tagline">Pull video &amp; audio from the web, keep a spool of everything you've grabbed.</p>
        </div>
        <div className="tape-counter">
          <div className="stat">
            <div className="val">{stats.active}</div>
            <div className="lbl">Active</div>
          </div>
          <div className="stat">
            <div className="val">{stats.completed}</div>
            <div className="lbl">Done</div>
          </div>
          <div className="stat">
            <div className="val">{stats.failed}</div>
            <div className="lbl">Failed</div>
          </div>
        </div>
      </header>

      <UrlForm onQueued={refresh} />

      {active.length > 0 && (
        <>
          <p className="section-label">On the spool</p>
          <div className="queue" style={{ marginBottom: 28 }}>
            {active.map((item) => (
              <TrackCard key={item.id} item={item} onChanged={refresh} />
            ))}
          </div>
        </>
      )}

      <p className="section-label">History</p>
      {history.length === 0 ? (
        <div className="empty-state">Nothing downloaded yet — paste a URL above to get started.</div>
      ) : (
        <div className="queue">
          {history.map((item) => (
            <TrackCard key={item.id} item={item} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import { Disc3, ShieldAlert } from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [config, setConfig] = useState(null);

  useEffect(() => {
    api.authConfig().then(setConfig).catch(() => setConfig({ configured: false }));
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const notConfigured = config && !config.configured;

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5 justify-center mb-8">
          <Disc3 className="w-7 h-7 text-brass-500" strokeWidth={1.75} />
          <span className="font-display font-bold text-xl tracking-tight">Diwan</span>
        </div>

        {notConfigured ? (
          <div className="panel p-5 flex gap-3">
            <ShieldAlert className="w-5 h-5 text-rust-400 shrink-0 mt-0.5" />
            <div className="text-sm text-parchment-300">
              <p className="font-medium mb-1">Server not configured</p>
              <p className="text-parchment-500 text-xs leading-relaxed">
                <code className="font-mono text-brass-400">NAVIDROME_URL</code> isn't set on the
                backend. Add it to the environment (e.g. in <code className="font-mono">docker-compose.yml</code>{" "}
                or a <code className="font-mono">.env</code> file) and restart the server.
              </p>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="panel p-5 space-y-4">
            <p className="text-xs text-parchment-500 text-center -mt-1 mb-1">
              Sign in with a Navidrome admin account
              {config?.navidrome_url ? (
                <span className="block font-mono text-parchment-700 mt-1 truncate">{config.navidrome_url}</span>
              ) : null}
            </p>

            <label className="block">
              <span className="label-eyebrow block mb-1.5">Username</span>
              <input
                className="input w-full"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
              />
            </label>

            <label className="block">
              <span className="label-eyebrow block mb-1.5">Password</span>
              <input
                type="password"
                className="input w-full"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>

            {error && <div className="text-xs text-rust-400 font-mono">{error}</div>}

            <button type="submit" className="btn-primary w-full" disabled={submitting || !username || !password}>
              {submitting ? "Signing in…" : "Sign in"}
            </button>

            <p className="text-[11px] text-parchment-700 text-center leading-relaxed">
              Only admin accounts can access Diwan.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

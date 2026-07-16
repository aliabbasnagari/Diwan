import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, XCircle, RadioTower, RefreshCw, Upload, Trash2, Cookie } from "lucide-react";
import { api } from "../api.js";

export default function SettingsPage() {
  const qc = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const [form, setForm] = useState(null);
  const [password, setPassword] = useState("");
  const cookieInputRef = useRef(null);
  const [cookieText, setCookieText] = useState("");
  const [showPasteArea, setShowPasteArea] = useState(false);


  useEffect(() => {
    if (settingsQuery.data && !form) setForm(settingsQuery.data);
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const patch = { ...form };
      delete patch.navidrome_password_set;
      if (password) patch.navidrome_password = password;
      return api.updateSettings(patch);
    },
    onSuccess: (data) => {
      toast.success("Settings saved");
      setForm(data);
      setPassword("");
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => toast.error(e.message),
  });

  const testMutation = useMutation({
    mutationFn: api.testNavidrome,
    onSuccess: (res) => toast.success(`Connected — Navidrome v${res.server_version}`),
    onError: (e) => toast.error(e.message),
  });

  const scanMutation = useMutation({
    mutationFn: api.triggerScan,
    onSuccess: () => toast.success("Navidrome scan triggered"),
    onError: (e) => toast.error(e.message),
  });

  const cookieUploadMutation = useMutation({
    mutationFn: (file) => api.uploadCookies(file),
    onSuccess: (data) => {
      toast.success("Cookies file uploaded");
      setForm(data);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => toast.error(e.message),
  });

  const cookieDeleteMutation = useMutation({
    mutationFn: api.deleteCookies,
    onSuccess: (data) => {
      toast.success("Cookies file removed");
      setForm(data);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => toast.error(e.message),
  });

  const cookieTextMutation = useMutation({
    mutationFn: () => api.saveCookiesText(cookieText),
    onSuccess: (data) => {
      toast.success("Cookies saved from pasted text");
      setForm(data);
      setCookieText("");
      setShowPasteArea(false);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e) => toast.error(e.message),
  });



  const scanStatusQuery = useQuery({
    queryKey: ["scan-status"],
    queryFn: api.scanStatus,
    enabled: !!form?.navidrome_url,
    refetchInterval: (query) => (query.state.data?.scanning ? 2000 : false),
    retry: false,
  });

  if (!form) {
    return <p className="text-sm text-parchment-500 font-mono">Loading settings…</p>;
  }

  return (
    <div className="max-w-2xl">
      <header className="mb-6">
        <h1 className="font-display font-bold text-2xl">Settings</h1>
        <p className="text-sm text-parchment-500 mt-1">Storage locations, worker concurrency, and Navidrome connection.</p>
      </header>

      <div className="space-y-6">
        <section className="panel p-5 space-y-4">
          <p className="label-eyebrow">Storage</p>
          <Field label="Download staging directory" hint="Where the spooler puts video downloads and un-organized audio.">
            <input className="input w-full" value={form.download_dir} onChange={(e) => setForm({ ...form, download_dir: e.target.value })} />
          </Field>
          <Field label="Library directory" hint="Navidrome's music root — point this at the same folder Navidrome scans.">
            <input className="input w-full" value={form.library_dir} onChange={(e) => setForm({ ...form, library_dir: e.target.value })} />
          </Field>
          <Field
            label="Artist image directory"
            hint={`Artist pictures live outside the music library. Point Navidrome at this same folder to use them — see the note below.`}
          >
            <input className="input w-full" value={form.artist_image_dir || ""} onChange={(e) => setForm({ ...form, artist_image_dir: e.target.value })} />
          </Field>
          <Field label="Concurrent downloads">
            <input
              type="number"
              min={1}
              max={8}
              className="input w-24"
              value={form.max_concurrent_downloads}
              onChange={(e) => setForm({ ...form, max_concurrent_downloads: Number(e.target.value) })}
            />
          </Field>
        </section>

        <section className="panel p-5 space-y-4">
          <p className="label-eyebrow">Cookies</p>
          <p className="text-xs text-parchment-500 leading-relaxed">
            Some sites (YouTube, etc.) require cookies for age-restricted or members-only content.
            Upload a <code className="font-mono text-brass-400">cookies.txt</code> file exported from your browser
            (Netscape format), or paste the contents directly.
          </p>

          <div className="flex items-center gap-3">
            {form.cookies_file_path ? (
              <>
                <span className="flex items-center gap-1.5 text-xs font-mono text-moss-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> cookies.txt uploaded
                </span>
                <button
                  className="btn-ghost-danger flex items-center gap-1.5 text-xs"
                  onClick={() => cookieDeleteMutation.mutate()}
                  disabled={cookieDeleteMutation.isPending}
                >
                  <Trash2 className="w-3.5 h-3.5" /> Remove
                </button>
              </>
            ) : (
              <span className="text-xs font-mono text-parchment-500">No cookies file uploaded</span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              className="btn-ghost flex items-center gap-1.5"
              onClick={() => cookieInputRef.current?.click()}
              disabled={cookieUploadMutation.isPending}
            >
              <Upload className="w-3.5 h-3.5" />
              {cookieUploadMutation.isPending ? "Uploading…" : form.cookies_file_path ? "Replace file" : "Upload file"}
            </button>
            <input
              ref={cookieInputRef}
              type="file"
              accept=".txt"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) cookieUploadMutation.mutate(file);
                e.target.value = "";
              }}
            />
            <button
              className="btn-ghost flex items-center gap-1.5"
              onClick={() => setShowPasteArea(!showPasteArea)}
            >
              <Cookie className="w-3.5 h-3.5" />
              {showPasteArea ? "Cancel paste" : "Paste text"}
            </button>
          </div>

          {showPasteArea && (
            <div className="space-y-2">
              <textarea
                className="input w-full h-32 font-mono text-xs resize-y"
                placeholder={"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tCOOKIE_NAME\tvalue"}
                value={cookieText}
                onChange={(e) => setCookieText(e.target.value)}
              />
              <button
                className="btn-primary text-xs"
                onClick={() => cookieTextMutation.mutate()}
                disabled={cookieTextMutation.isPending || !cookieText.trim()}
              >
                {cookieTextMutation.isPending ? "Saving…" : "Save cookies"}
              </button>
            </div>
          )}

          {form.cookies_file_path && (
            <label className="flex items-center gap-2 text-xs font-mono text-parchment-300 cursor-pointer">
              <input
                type="checkbox"
                checked={!!form.cookies_enabled}
                onChange={(e) => setForm({ ...form, cookies_enabled: e.target.checked })}
              />
              Use cookies.txt for downloads (disable to skip without deleting the file)
            </label>
          )}
        </section>


        <section className="panel p-5 space-y-3">
          <p className="label-eyebrow">Artwork &amp; Navidrome config</p>
          <ul className="text-xs text-parchment-500 space-y-2 leading-relaxed">
            <li>
              <span className="text-parchment-100 font-medium">Track art</span> is embedded directly in a
              single audio file — nothing to configure, every player reads it.
            </li>
            <li>
              <span className="text-parchment-100 font-medium">Album art</span> is written as{" "}
              <code className="font-mono text-brass-400">cover.jpg</code> in the album folder (and embedded
              in every track in it) — this is Navidrome's default, so nothing to configure either.
            </li>
            <li>
              <span className="text-parchment-100 font-medium">Artist pictures</span> are saved outside the
              music library, so Navidrome needs to be told where to find them. Set these two environment
              variables on your Navidrome server, pointing at the artist image directory above:
              <code className="block font-mono text-brass-400 mt-1.5 bg-ink-950 rounded px-2 py-1.5">
                ND_ARTISTIMAGEFOLDER={form.artist_image_dir || "<artist image directory>"}
                <br />
                ND_ARTISTARTPRIORITY=image-folder,artist.*,album/artist.*,last.fm
              </code>
            </li>
          </ul>
        </section>

        <section className="panel p-5 space-y-4">
          <div className="flex items-center justify-between">
            <p className="label-eyebrow">Navidrome connection</p>
            {form.navidrome_url && (
              scanStatusQuery.data ? (
                <span className="flex items-center gap-1.5 text-xs font-mono text-moss-400">
                  <CheckCircle2 className="w-3.5 h-3.5" /> reachable
                </span>
              ) : scanStatusQuery.isError ? (
                <span className="flex items-center gap-1.5 text-xs font-mono text-rust-400">
                  <XCircle className="w-3.5 h-3.5" /> unreachable
                </span>
              ) : null
            )}
          </div>

          <Field
            label="Server URL"
            hint={
              form.navidrome_url_locked
                ? "Set via NAVIDROME_URL in the server's environment — this is also what you log in against."
                : "e.g. http://localhost:4533"
            }
          >
            <input
              className="input w-full disabled:opacity-60 disabled:cursor-not-allowed"
              placeholder="http://localhost:4533"
              value={form.navidrome_url || ""}
              disabled={form.navidrome_url_locked}
              onChange={(e) => setForm({ ...form, navidrome_url: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Username" hint="Synced automatically from your last login.">
              <input
                className="input w-full"
                value={form.navidrome_username || ""}
                onChange={(e) => setForm({ ...form, navidrome_username: e.target.value })}
              />
            </Field>
            <Field label={form.navidrome_password_set ? "Password (set — leave blank to keep)" : "Password"}>
              <input
                type="password"
                className="input w-full"
                placeholder={form.navidrome_password_set ? "••••••••" : ""}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </div>

          <label className="flex items-center gap-2 text-xs font-mono text-parchment-300 cursor-pointer">
            <input
              type="checkbox"
              checked={!!form.navidrome_auto_scan}
              onChange={(e) => setForm({ ...form, navidrome_auto_scan: e.target.checked })}
            />
            Trigger a Navidrome scan automatically after each library addition
          </label>

          <div className="flex gap-2 pt-1">
            <button className="btn-ghost flex items-center gap-1.5" onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
              <RadioTower className="w-3.5 h-3.5" /> {testMutation.isPending ? "Testing…" : "Test connection"}
            </button>
            <button className="btn-ghost flex items-center gap-1.5" onClick={() => scanMutation.mutate()} disabled={scanMutation.isPending}>
              <RefreshCw className="w-3.5 h-3.5" /> {scanMutation.isPending ? "Starting…" : "Scan now"}
            </button>
          </div>
        </section>

        <button className="btn-primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          {saveMutation.isPending ? "Saving…" : "Save settings"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="label-eyebrow block mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-parchment-700 mt-1">{hint}</span>}
    </label>
  );
}

const BASE = "/api";

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  preview: (url) =>
    fetch(`${BASE}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }).then(handle),

  createDownload: (payload) =>
    fetch(`${BASE}/downloads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(handle),

  listDownloads: () => fetch(`${BASE}/downloads`).then(handle),

  getDownload: (id) => fetch(`${BASE}/downloads/${id}`).then(handle),

  cancelDownload: (id) =>
    fetch(`${BASE}/downloads/${id}/cancel`, { method: "POST" }).then(handle),

  retryDownload: (id) =>
    fetch(`${BASE}/downloads/${id}/retry`, { method: "POST" }).then(handle),

  deleteDownload: (id) =>
    fetch(`${BASE}/downloads/${id}`, { method: "DELETE" }).then(handle),

  fileUrl: (id) => `${BASE}/downloads/${id}/file`,

  stats: () => fetch(`${BASE}/stats`).then(handle),
};

import axios from "axios";

const client = axios.create({ baseURL: "/api" });

function unwrap(promise) {
  return promise.then((r) => r.data).catch((err) => {
    const detail = err?.response?.data?.detail || err.message || "Request failed";
    throw new Error(detail);
  });
}

export const api = {
  // --- downloads / spooler ---
  preview: (url) => unwrap(client.post("/preview", { url })),
  createDownload: (payload) => unwrap(client.post("/downloads", payload)),
  listDownloads: () => unwrap(client.get("/downloads")),
  getDownload: (id) => unwrap(client.get(`/downloads/${id}`)),
  cancelDownload: (id) => unwrap(client.post(`/downloads/${id}/cancel`)),
  retryDownload: (id) => unwrap(client.post(`/downloads/${id}/retry`)),
  deleteDownload: (id) => unwrap(client.delete(`/downloads/${id}`)),
  fileUrl: (id) => `/api/downloads/${id}/file`,
  downloadStats: () => unwrap(client.get("/stats")),

  // --- library ---
  libraryTree: () => unwrap(client.get("/library/tree")),
  libraryTracks: (q) => unwrap(client.get("/library/tracks", { params: q ? { q } : {} })),
  libraryStats: () => unwrap(client.get("/library/stats")),
  getTrack: (id) => unwrap(client.get(`/library/tracks/${id}`)),
  updateTrack: (id, patch) => unwrap(client.put(`/library/tracks/${id}`, patch)),
  deleteTrack: (id) => unwrap(client.delete(`/library/tracks/${id}`)),
  artworkUrl: (id) => `/api/library/tracks/${id}/artwork?_=${Date.now()}`,
  uploadArtwork: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(client.post(`/library/tracks/${id}/artwork`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },
  organizeTrack: (id) => unwrap(client.post(`/library/tracks/${id}/organize`)),
  organizeLibrary: (trackIds) => unwrap(client.post("/library/organize", { track_ids: trackIds || null })),

  // --- settings ---
  getSettings: () => unwrap(client.get("/settings")),
  updateSettings: (patch) => unwrap(client.put("/settings", patch)),
  testNavidrome: () => unwrap(client.post("/settings/navidrome/test")),

  // --- navidrome ---
  triggerScan: () => unwrap(client.post("/navidrome/scan")),
  scanStatus: () => unwrap(client.get("/navidrome/scan/status")),
};

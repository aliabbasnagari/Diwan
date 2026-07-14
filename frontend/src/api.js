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

  // --- library: tracks ---
  libraryTree: () => unwrap(client.get("/library/tree")),
  libraryTracks: (q) => unwrap(client.get("/library/tracks", { params: q ? { q } : {} })),
  libraryStats: () => unwrap(client.get("/library/stats")),
  getTrack: (id) => unwrap(client.get(`/library/tracks/${id}`)),
  updateTrack: (id, patch) => unwrap(client.put(`/library/tracks/${id}`, patch)),
  deleteTrack: (id) => unwrap(client.delete(`/library/tracks/${id}`)),
  organizeTrack: (id) => unwrap(client.post(`/library/tracks/${id}/organize`)),
  organizeLibrary: (trackIds) => unwrap(client.post("/library/organize", { track_ids: trackIds || null })),

  // --- library: track-level art (embedded in that one file only) ---
  trackArtworkUrl: (id) => `/api/library/tracks/${id}/artwork?_=${Date.now()}`,
  uploadTrackArtwork: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(client.post(`/library/tracks/${id}/artwork`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },

  // --- library: album-level art (cover.jpg in the folder + embedded in every track) ---
  albumArtworkUrl: (albumId) => `/api/library/albums/${albumId}/artwork?_=${Date.now()}`,
  uploadAlbumArtwork: (albumId, file) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(client.post(`/library/albums/${albumId}/artwork`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },

  // --- library: artist pictures (saved to a dedicated folder for Navidrome's ArtistImageFolder) ---
  artistPictureUrl: (artistId) => `/api/library/artists/${artistId}/picture?_=${Date.now()}`,
  uploadArtistPicture: (artistId, file) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(client.post(`/library/artists/${artistId}/picture`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },

  // --- settings ---
  getSettings: () => unwrap(client.get("/settings")),
  updateSettings: (patch) => unwrap(client.put("/settings", patch)),
  testNavidrome: () => unwrap(client.post("/settings/navidrome/test")),

  // --- navidrome ---
  triggerScan: () => unwrap(client.post("/navidrome/scan")),
  scanStatus: () => unwrap(client.get("/navidrome/scan/status")),

  // --- convert ---
  convertFormats: () => unwrap(client.get("/convert/formats")),
  listConversions: () => unwrap(client.get("/convert/jobs")),
  getConversion: (id) => unwrap(client.get(`/convert/jobs/${id}`)),
  createConversion: (fields) => {
    const form = new FormData();
    Object.entries(fields).forEach(([k, v]) => {
      if (v !== null && v !== undefined) form.append(k, v);
    });
    return unwrap(client.post("/convert/jobs", form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },
  cancelConversion: (id) => unwrap(client.post(`/convert/jobs/${id}/cancel`)),
  deleteConversion: (id) => unwrap(client.delete(`/convert/jobs/${id}`)),
  conversionFileUrl: (id) => `/api/convert/jobs/${id}/file`,
  conversionStats: () => unwrap(client.get("/convert/stats")),
};

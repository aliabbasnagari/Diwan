import axios from "axios";

const client = axios.create({ baseURL: "/api" });

const TOKEN_KEY = "diwan_token";

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    client.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    localStorage.removeItem(TOKEN_KEY);
    delete client.defaults.headers.common["Authorization"];
  }
}

// re-attach on page load if a token is already stored
const stored = localStorage.getItem(TOKEN_KEY);
if (stored) setAuthToken(stored);

// plain <img>/<a> tags can't send custom headers, so URL-returning
// helpers below append the token as a query param instead
function tokenParam() {
  const t = localStorage.getItem(TOKEN_KEY);
  return t ? `token=${encodeURIComponent(t)}` : "";
}

// let the app react globally to an expired/invalid session
client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      window.dispatchEvent(new Event("diwan:unauthorized"));
    }
    return Promise.reject(err);
  }
);

function unwrap(promise) {
  return promise.then((r) => r.data).catch((err) => {
    const detail = err?.response?.data?.detail || err.message || "Request failed";
    throw new Error(detail);
  });
}

export const api = {
  // --- auth ---
  authConfig: () => unwrap(client.get("/auth/config")),
  login: (username, password) => unwrap(client.post("/auth/login", { username, password })),
  me: () => unwrap(client.get("/auth/me")),
  logout: () => unwrap(client.post("/auth/logout")),

  // --- downloads / spooler ---
  preview: (url) => unwrap(client.post("/preview", { url })),
  createDownload: (payload) => unwrap(client.post("/downloads", payload)),
  listDownloads: () => unwrap(client.get("/downloads")),
  getDownload: (id) => unwrap(client.get(`/downloads/${id}`)),
  cancelDownload: (id) => unwrap(client.post(`/downloads/${id}/cancel`)),
  retryDownload: (id) => unwrap(client.post(`/downloads/${id}/retry`)),
  deleteDownload: (id, deleteFile = false) =>
    unwrap(
      client.delete(`/downloads/${id}`, {
        params: {
          delete_file: deleteFile,
        },
      })
    ),
  fileUrl: (id) => `/api/downloads/${id}/file?${tokenParam()}`,
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
  trackArtworkUrl: (id) => `/api/library/tracks/${id}/artwork?_=${Date.now()}&${tokenParam()}`,
  uploadTrackArtwork: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(client.post(`/library/tracks/${id}/artwork`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },

  // --- library: album-level art (cover.jpg in the folder + embedded in every track) ---
  albumArtworkUrl: (albumId) => `/api/library/albums/${albumId}/artwork?_=${Date.now()}&${tokenParam()}`,
  uploadAlbumArtwork: (albumId, file) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(client.post(`/library/albums/${albumId}/artwork`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    }));
  },

  // --- library: artist pictures (saved to a dedicated folder for Navidrome's ArtistImageFolder) ---
  artistPictureUrl: (artistId) => `/api/library/artists/${artistId}/picture?_=${Date.now()}&${tokenParam()}`,
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

  // --- suggestions ---
  getTagSuggestions: () => unwrap(client.get("/suggestions")),
  getAllTagSuggestions: () => unwrap(client.get("/suggestions/all")),
  createTagSuggestion: (field, value) => unwrap(client.post("/suggestions", { field, value })),
  updateTagSuggestion: (id, patch) => unwrap(client.put(`/suggestions/${id}`, patch)),
  deleteTagSuggestion: (id) => unwrap(client.delete(`/suggestions/${id}`)),
  populateTagSuggestions: () => unwrap(client.post("/suggestions/populate")),

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
  conversionFileUrl: (id) => `/api/convert/jobs/${id}/file?${tokenParam()}`,
  conversionStats: () => unwrap(client.get("/convert/stats")),
};

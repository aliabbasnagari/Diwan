import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockClient } = vi.hoisted(() => {
  const mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    defaults: { headers: { common: {} } },
    interceptors: { response: { use: vi.fn() } },
  };
  return { mockClient };
});

vi.mock("axios", () => ({
  default: { create: vi.fn(() => mockClient) },
}));

const { api } = await import("./api.js");

beforeEach(() => {
  vi.resetAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

describe("library: rename", () => {
  it("renameArtist posts the new name to the artist rename endpoint", async () => {
    mockClient.post.mockResolvedValue({ data: { renamed: 3, errors: [] } });

    const result = await api.renameArtist("QXJ0aXN0", "New Name");

    expect(mockClient.post).toHaveBeenCalledWith("/library/artists/QXJ0aXN0/rename", {
      new_name: "New Name",
    });
    expect(result).toEqual({ renamed: 3, errors: [] });
  });

  it("renameAlbum posts the new name to the album rename endpoint", async () => {
    mockClient.post.mockResolvedValue({ data: { renamed: 5, errors: [] } });

    const result = await api.renameAlbum("QWxidW0", "New Album");

    expect(mockClient.post).toHaveBeenCalledWith("/library/albums/QWxidW0/rename", {
      new_name: "New Album",
    });
    expect(result).toEqual({ renamed: 5, errors: [] });
  });
});

describe("library: lyrics", () => {
  it("getLyrics fetches the track's lyrics endpoint", async () => {
    mockClient.get.mockResolvedValue({ data: { text: "la la la" } });

    const result = await api.getLyrics("track123");

    expect(mockClient.get).toHaveBeenCalledWith("/library/tracks/track123/lyrics");
    expect(result).toEqual({ text: "la la la" });
  });

  it("updateLyrics puts the given text to the track's lyrics endpoint", async () => {
    mockClient.put.mockResolvedValue({ data: { text: "new lyrics" } });

    const result = await api.updateLyrics("track123", "new lyrics");

    expect(mockClient.put).toHaveBeenCalledWith("/library/tracks/track123/lyrics", {
      text: "new lyrics",
    });
    expect(result).toEqual({ text: "new lyrics" });
  });
});

describe("unwrap error handling", () => {
  it("rejects with the server's detail message", async () => {
    mockClient.get.mockRejectedValue({ response: { data: { detail: "Track not found" } } });

    await expect(api.getLyrics("missing")).rejects.toThrow("Track not found");
  });

  it("falls back to the raw error message when there is no response detail", async () => {
    mockClient.get.mockRejectedValue(new Error("Network error"));

    await expect(api.getLyrics("missing")).rejects.toThrow("Network error");
  });
});

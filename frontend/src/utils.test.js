import { describe, expect, it } from "vitest";
import { formatDuration, formatBytes } from "./utils.js";

describe("formatDuration", () => {
  it("returns empty string for null/undefined", () => {
    expect(formatDuration(null)).toBe("");
    expect(formatDuration(undefined)).toBe("");
  });

  it("formats zero seconds", () => {
    expect(formatDuration(0)).toBe("0:00");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(125)).toBe("2:05");
  });

  it("formats hours when present", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
  });

  it("rounds fractional seconds", () => {
    expect(formatDuration(59.6)).toBe("1:00");
  });
});

describe("formatBytes", () => {
  it("returns an em dash for falsy input", () => {
    expect(formatBytes(0)).toBe("—");
    expect(formatBytes(null)).toBe("—");
  });

  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512.0 B");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("caps out at gigabytes", () => {
    expect(formatBytes(2 * 1024 * 1024 * 1024)).toBe("2.0 GB");
  });
});

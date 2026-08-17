import { describe, expect, it } from "vitest";
import { cn, scoreColor } from "./utils";

describe("scoreColor", () => {
  it("returns success color for high scores", () => {
    expect(scoreColor(90)).toBe("text-success-text");
    expect(scoreColor(80)).toBe("text-success-text");
  });

  it("returns warning color for medium scores", () => {
    expect(scoreColor(65)).toBe("text-warning-text");
    expect(scoreColor(50)).toBe("text-warning-text");
  });

  it("returns destructive color for low scores", () => {
    expect(scoreColor(20)).toBe("text-destructive-text");
    expect(scoreColor(0)).toBe("text-destructive-text");
  });
});

describe("cn", () => {
  it("merges class names and resolves tailwind conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-sm", undefined, "font-bold")).toBe("text-sm font-bold");
  });
});

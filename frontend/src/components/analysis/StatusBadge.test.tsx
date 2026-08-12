import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each([
    ["queued", "Na fila"],
    ["running", "Analisando…"],
    ["done", "Concluída"],
    ["failed", "Falhou"],
  ] as const)("renders the correct label for status=%s", (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

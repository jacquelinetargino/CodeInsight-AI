import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FindingsList } from "./FindingsList";
import type { Finding } from "@/types";

describe("FindingsList", () => {
  it("shows an empty state when there are no findings", () => {
    render(<FindingsList findings={[]} />);
    expect(screen.getByText(/nenhum problema relevante/i)).toBeInTheDocument();
  });

  it("renders each finding with its title and severity", () => {
    const findings: Finding[] = [
      { title: "Segredo exposto", description: "Chave de API em texto plano", severity: "critical", file_path: "config.py" },
      { title: "Nome pouco descritivo", description: "Variável 'x' usada em vários lugares", severity: "low", file_path: null },
    ];
    render(<FindingsList findings={findings} />);

    expect(screen.getByText("Segredo exposto")).toBeInTheDocument();
    expect(screen.getByText("Nome pouco descritivo")).toBeInTheDocument();
    expect(screen.getByText("config.py")).toBeInTheDocument();
  });
});

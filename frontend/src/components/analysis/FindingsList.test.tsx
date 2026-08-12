import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { FindingsList } from "./FindingsList";
import type { Finding } from "@/types";

function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("FindingsList", () => {
  it("shows an empty state when there are no findings", () => {
    renderWithQueryClient(<FindingsList findings={[]} analysisId="analysis-1" />);
    expect(screen.getByText(/nenhum problema relevante/i)).toBeInTheDocument();
  });

  it("renders each finding with its title and severity", () => {
    const findings: Finding[] = [
      {
        title: "Segredo exposto",
        description: "Chave de API em texto plano",
        suggestion: "Mova a chave para uma variável de ambiente",
        severity: "critical",
        file_path: "config.py",
        line: 12,
      },
      {
        title: "Nome pouco descritivo",
        description: "Variável 'x' usada em vários lugares",
        suggestion: null,
        severity: "low",
        file_path: null,
        line: null,
      },
    ];
    renderWithQueryClient(<FindingsList findings={findings} analysisId="analysis-1" />);

    expect(screen.getByText("Segredo exposto")).toBeInTheDocument();
    expect(screen.getByText("Nome pouco descritivo")).toBeInTheDocument();
    expect(screen.getByText("config.py:12")).toBeInTheDocument();
  });
});

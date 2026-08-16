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

describe("FindingsList com dados do motor", () => {
  const doMotor: Finding = {
    title: "Argumento padrão mutável",
    description: "O valor padrão é compartilhado entre chamadas",
    suggestion: "Use None como padrão",
    severity: "medium",
    file_path: "app/servico.py",
    line: 12,
    rule_id: "QUA-005",
    category: "quality",
    evidence: "def f(itens=[]):",
    confidence: 0.9,
    analyzer: "quality",
  };

  it("mostra o identificador da regra", () => {
    renderWithQueryClient(<FindingsList findings={[doMotor]} analysisId="a1" />);
    expect(screen.getByText("QUA-005")).toBeInTheDocument();
  });

  it("traduz a confiança para linguagem em vez de mostrar o número", () => {
    // "0.9" não diz nada a quem lê o relatório; "detecção confirmada" diz.
    renderWithQueryClient(<FindingsList findings={[doMotor]} analysisId="a1" />);
    expect(screen.getByText(/detecção confirmada/i)).toBeInTheDocument();
    expect(screen.queryByText("0.9")).not.toBeInTheDocument();
  });

  it("declara a dúvida quando a detecção é heurística", () => {
    const incerto = { ...doMotor, confidence: 0.6 };
    renderWithQueryClient(<FindingsList findings={[incerto]} analysisId="a1" />);
    expect(screen.getByText(/vale conferir/i)).toBeInTheDocument();
  });

  it("mostra a evidência que sustenta o achado", () => {
    renderWithQueryClient(<FindingsList findings={[doMotor]} analysisId="a1" />);
    expect(screen.getByText("def f(itens=[]):")).toBeInTheDocument();
  });

  it("continua renderizando achados antigos, sem os campos do motor", () => {
    // Análises gravadas antes do motor só têm os seis campos originais.
    const legado: Finding = {
      title: "Achado antigo",
      description: "Sem regra rastreável",
      suggestion: null,
      severity: "low",
      file_path: null,
      line: null,
    };
    renderWithQueryClient(<FindingsList findings={[legado]} analysisId="a1" />);
    expect(screen.getByText("Achado antigo")).toBeInTheDocument();
  });
});

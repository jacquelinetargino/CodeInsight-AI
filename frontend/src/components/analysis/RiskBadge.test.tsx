import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskBadge } from "./RiskBadge";
import type { RiskLevel } from "@/types";

describe("RiskBadge", () => {
  it.each<[RiskLevel, RegExp]>([
    ["low", /risco baixo/i],
    ["medium", /risco moderado/i],
    ["high", /risco alto/i],
    ["critical", /risco crítico/i],
  ])("names the %s level in words", (level, expected) => {
    render(<RiskBadge level={level} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("does not rely on colour alone to convey the level", () => {
    // Quem não distingue vermelho de verde precisa continuar entendendo o
    // veredito: cada nível carrega um ícone próprio além do rótulo.
    const { container: baixo } = render(<RiskBadge level="low" />);
    const { container: critico } = render(<RiskBadge level="critical" />);

    const iconeBaixo = baixo.querySelector("svg")?.getAttribute("class");
    const iconeCritico = critico.querySelector("svg")?.getAttribute("class");

    expect(iconeBaixo).toBeTruthy();
    expect(iconeCritico).toBeTruthy();
    expect(iconeBaixo).not.toEqual(iconeCritico);
  });

  it("hides the decorative icon from screen readers", () => {
    const { container } = render(<RiskBadge level="high" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

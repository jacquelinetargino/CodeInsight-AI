import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReadmePreview } from "./ReadmePreview";

/**
 * O README exibido aqui é gerado por IA a partir do conteúdo do repositório
 * analisado — que é dado não confiável. Se o markdown fosse renderizado com
 * HTML bruto habilitado, um repositório hostil poderia injetar markup na
 * página de quem pediu a análise.
 *
 * `react-markdown` não renderiza HTML bruto sem o plugin `rehype-raw`, e filtra
 * protocolos perigosos em links. **Nada verificava isso**: acrescentar
 * `rehypePlugins={[rehypeRaw]}` para "melhorar a formatação" abriria o buraco
 * sem quebrar teste algum.
 */
describe("ReadmePreview com conteúdo não confiável", () => {
  it("não renderiza HTML bruto vindo do markdown", () => {
    const { container } = render(
      <ReadmePreview content={"# Título\n\n<script>alert(1)</script>\n"} />,
    );

    expect(container.querySelector("script")).toBeNull();
    // O texto aparece como texto — escapar não pode virar apagar.
    expect(container.textContent).toContain("alert(1)");
  });

  it("não renderiza tag com manipulador de evento", () => {
    const { container } = render(<ReadmePreview content={'<img src=x onerror="alert(1)">'} />);

    expect(container.querySelector("img")).toBeNull();
  });

  it("não produz link com protocolo perigoso", () => {
    const { container } = render(<ReadmePreview content={"[clique](javascript:alert(1))"} />);

    const href = container.querySelector("a")?.getAttribute("href") ?? "";
    expect(href.toLowerCase().startsWith("javascript:")).toBe(false);
  });

  it("renderiza markdown legítimo", () => {
    // A trava do outro lado: não renderizar nada também passaria nos testes
    // acima.
    render(<ReadmePreview content={"# Projeto\n\nUm parágrafo com `código`."} />);

    expect(screen.getByRole("heading", { name: "Projeto" })).toBeInTheDocument();
    expect(screen.getByText("código")).toBeInTheDocument();
  });
});

/**
 * Auditoria de contraste dos tokens de cor, nos dois temas.
 *
 * Os valores são lidos do `index.css` e conferidos pela fórmula da WCAG. Isto
 * existe porque contraste é o tipo de regressão que ninguém percebe olhando: a
 * tela continua bonita, e só quem precisa do contraste é que sofre.
 *
 * Já pegou três defeitos reais — `warning` a 2,08:1 como texto, `destructive` a
 * 3,53:1 no tema escuro e a borda de campo de formulário a 1,27:1.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

type RGB = [number, number, number];

function hslParaRgb(valor: string): RGB {
  const [h, s, l] = valor.trim().split(/\s+/).map(parseFloat);
  const S = s / 100;
  const L = l / 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = S * Math.min(L, 1 - L);
  const f = (n: number) => L - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)].map((x) => Math.round(x * 255)) as RGB;
}

function luminancia([r, g, b]: RGB): number {
  const c = [r, g, b].map((x) => {
    const v = x / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function contraste(a: RGB, b: RGB): number {
  const l1 = luminancia(a);
  const l2 = luminancia(b);
  const [maior, menor] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (maior + 0.05) / (menor + 0.05);
}

/** Extrai os tokens de um bloco do index.css: `:root` (claro) ou `.dark`. */
function lerTokens(tema: "light" | "dark"): Record<string, string> {
  const css = readFileSync(join(process.cwd(), "src/index.css"), "utf-8");
  const marcador = tema === "dark" ? ".dark {" : ":root {";
  const inicio = css.indexOf(marcador);
  expect(inicio, `bloco ${marcador} não encontrado`).toBeGreaterThan(-1);
  const bloco = css.slice(inicio, css.indexOf("\n  }", inicio));

  const tokens: Record<string, string> = {};
  for (const [, nome, valor] of bloco.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    tokens[nome] = valor.trim();
  }
  return tokens;
}

const TEMAS = ["light", "dark"] as const;

/** Texto normal: mínimo 4.5:1 (WCAG 2.2 AA, 1.4.3). */
const TOKENS_DE_TEXTO = [
  "foreground",
  "muted-foreground",
  "primary-text",
  "destructive-text",
  "success-text",
  "warning-text",
];

/** Componente de interface: mínimo 3:1 (WCAG 2.2 AA, 1.4.11). */
const TOKENS_NAO_TEXTUAIS = ["input", "ring"];

/** Pares preenchimento/texto por cima. */
const PARES = [
  ["primary", "primary-foreground"],
  ["destructive", "destructive-foreground"],
];

describe.each(TEMAS)("contraste no tema %s", (tema) => {
  const tokens = lerTokens(tema);
  const fundos: RGB[] = [hslParaRgb(tokens.background), hslParaRgb(tokens.card)];

  it.each(TOKENS_DE_TEXTO)("%s tem ao menos 4.5:1 como texto", (nome) => {
    const cor = hslParaRgb(tokens[nome]);
    const pior = Math.min(...fundos.map((fundo) => contraste(cor, fundo)));
    expect(pior, `--${nome} no tema ${tema}: ${pior.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
  });

  it.each(TOKENS_NAO_TEXTUAIS)("%s tem ao menos 3:1 como elemento de interface", (nome) => {
    const cor = hslParaRgb(tokens[nome]);
    const pior = Math.min(...fundos.map((fundo) => contraste(cor, fundo)));
    expect(pior, `--${nome} no tema ${tema}: ${pior.toFixed(2)}:1`).toBeGreaterThanOrEqual(3);
  });

  it.each(PARES)("%s com %s por cima tem ao menos 4.5:1", (fundo, frente) => {
    const razao = contraste(hslParaRgb(tokens[frente]), hslParaRgb(tokens[fundo]));
    expect(razao, `${fundo}/${frente} no tema ${tema}: ${razao.toFixed(2)}:1`).toBeGreaterThanOrEqual(
      4.5,
    );
  });

  it("define todos os tokens que o tema claro define", () => {
    // Um token que existe só num dos temas herda o valor do outro em silêncio —
    // e é assim que uma cor de tema claro acaba pintada sobre fundo escuro.
    const claro = Object.keys(lerTokens("light"));
    const escuro = Object.keys(lerTokens("dark"));
    const faltando = claro.filter((t) => t !== "radius" && !escuro.includes(t));
    expect(faltando).toEqual([]);
  });
});

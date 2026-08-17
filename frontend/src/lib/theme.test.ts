import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyTheme,
  isThemePreference,
  readStoredPreference,
  resolveTheme,
  storePreference,
  THEME_STORAGE_KEY,
} from "./theme";

function mockMatchMedia(prefereEscuro: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: prefereEscuro,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
}

describe("preferência de tema", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("assume 'system' quando não há nada guardado", () => {
    expect(readStoredPreference()).toBe("system");
  });

  it("ignora valor inválido guardado em vez de aplicá-lo", () => {
    // O localStorage é do usuário e pode conter qualquer coisa — de uma versão
    // anterior, de outra aba, de uma extensão.
    localStorage.setItem(THEME_STORAGE_KEY, "roxo");
    expect(readStoredPreference()).toBe("system");
  });

  it("guarda e relê a escolha", () => {
    storePreference("dark");
    expect(readStoredPreference()).toBe("dark");
  });

  it("não quebra quando o localStorage lança", () => {
    // Navegação privativa ou cookies bloqueados. Um tema não é motivo para a
    // aplicação não carregar.
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("acesso negado");
    };
    expect(() => readStoredPreference()).not.toThrow();
    expect(readStoredPreference()).toBe("system");
    Storage.prototype.getItem = original;
  });

  it("valida a preferência", () => {
    expect(isThemePreference("dark")).toBe(true);
    expect(isThemePreference("azul")).toBe(false);
    expect(isThemePreference(null)).toBe(false);
  });
});

describe("resolução do tema", () => {
  it("uma escolha explícita ignora o sistema", () => {
    mockMatchMedia(true);
    expect(resolveTheme("light")).toBe("light");
    mockMatchMedia(false);
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("'system' acompanha a preferência do sistema", () => {
    mockMatchMedia(true);
    expect(resolveTheme("system")).toBe("dark");
    mockMatchMedia(false);
    expect(resolveTheme("system")).toBe("light");
  });
});

describe("aplicação do tema", () => {
  it("liga e desliga a classe que o Tailwind espera", () => {
    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    applyTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("define color-scheme", () => {
    // É o que faz o navegador pintar barra de rolagem e controles nativos na
    // variante certa — sem isso um input aparece branco numa tela escura.
    applyTheme("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });
});

describe("o script anti-flash", () => {
  it("usa a mesma chave do módulo", () => {
    // O script do index.html roda antes do bundle e precisa ler exatamente a
    // mesma chave. Divergirem traz o lampejo branco de volta, sem erro nenhum
    // para avisar.
    const html = readFileSync(join(process.cwd(), "index.html"), "utf-8");
    expect(html).toContain(`"${THEME_STORAGE_KEY}"`);
    expect(html).toContain("prefers-color-scheme: dark");
  });
});

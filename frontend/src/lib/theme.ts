/**
 * Tema claro/escuro.
 *
 * A infraestrutura já existia — `darkMode: ["class"]` no Tailwind e um bloco
 * `.dark` completo no `index.css` — mas nada aplicava a classe. Este módulo é a
 * peça que faltava, e é só função pura: quem decide *quando* aplicar é o store.
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

/** Chave no localStorage. O script anti-flash do `index.html` usa a mesma. */
export const THEME_STORAGE_KEY = "codeinsight-theme";

const PREFERENCIAS: readonly ThemePreference[] = ["light", "dark", "system"];

export function isThemePreference(valor: unknown): valor is ThemePreference {
  return typeof valor === "string" && (PREFERENCIAS as readonly string[]).includes(valor);
}

/**
 * Preferência guardada, ou "system" quando não há nenhuma.
 *
 * O acesso ao localStorage é protegido: em navegação privativa ou com cookies
 * bloqueados ele lança, e um tema não é motivo para a aplicação não carregar.
 */
export function readStoredPreference(): ThemePreference {
  try {
    const guardado = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(guardado) ? guardado : "system";
  } catch {
    return "system";
  }
}

export function storePreference(preference: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Sem persistência a escolha vale só para esta sessão — o que é melhor do
    // que quebrar a troca de tema.
  }
}

export function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

/** Traduz a preferência para o tema que de fato será pintado. */
export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system") return systemPrefersDark() ? "dark" : "light";
  return preference;
}

/**
 * Aplica o tema no elemento raiz.
 *
 * Também atualiza `color-scheme`, que é o que faz o navegador pintar as barras
 * de rolagem e os controles nativos de formulário na variante certa — sem isso
 * um input aparece branco no meio de uma tela escura.
 */
export function applyTheme(theme: ResolvedTheme): void {
  const raiz = document.documentElement;
  raiz.classList.toggle("dark", theme === "dark");
  raiz.style.colorScheme = theme;
}

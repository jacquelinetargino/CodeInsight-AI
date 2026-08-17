import { create } from "zustand";
import {
  applyTheme,
  readStoredPreference,
  resolveTheme,
  storePreference,
  type ResolvedTheme,
  type ThemePreference,
} from "@/lib/theme";

interface ThemeState {
  preference: ThemePreference;
  /** O tema realmente pintado. Com "system" ele acompanha o sistema operacional. */
  resolved: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
}

const inicial = readStoredPreference();

export const useThemeStore = create<ThemeState>((set) => ({
  preference: inicial,
  resolved: resolveTheme(inicial),
  setPreference: (preference) => {
    storePreference(preference);
    const resolved = resolveTheme(preference);
    applyTheme(resolved);
    set({ preference, resolved });
  },
}));

/**
 * Acompanha a preferência do sistema operacional enquanto a escolha for
 * "system".
 *
 * Sem isto, quem deixa o tema no automático e troca o modo do sistema com a
 * aplicação aberta continuaria vendo o tema antigo até recarregar a página.
 *
 * Registrado uma vez, no módulo, e nunca removido — o listener vive tanto
 * quanto a aplicação.
 */
if (typeof window !== "undefined" && window.matchMedia) {
  const consulta = window.matchMedia("(prefers-color-scheme: dark)");
  consulta.addEventListener("change", () => {
    const { preference } = useThemeStore.getState();
    if (preference !== "system") return;
    const resolved = resolveTheme("system");
    applyTheme(resolved);
    useThemeStore.setState({ resolved });
  });
}

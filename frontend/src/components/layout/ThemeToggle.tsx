import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ThemePreference } from "@/lib/theme";
import { useThemeStore } from "@/store/themeStore";

/**
 * Três estados em vez de dois.
 *
 * Um botão que só alterna claro/escuro obriga quem usa o tema do sistema a
 * escolher um dos dois para sempre — a partir do primeiro clique a aplicação
 * deixa de acompanhar o modo noturno automático. "Sistema" precisa ser um
 * destino, não só o ponto de partida.
 */
const OPCOES: { valor: ThemePreference; rotulo: string; icone: typeof Sun }[] = [
  { valor: "light", rotulo: "Tema claro", icone: Sun },
  { valor: "dark", rotulo: "Tema escuro", icone: Moon },
  { valor: "system", rotulo: "Acompanhar o sistema", icone: Monitor },
];

export function ThemeToggle({ className }: { className?: string }) {
  const preference = useThemeStore((estado) => estado.preference);
  const setPreference = useThemeStore((estado) => estado.setPreference);

  return (
    // `radiogroup`: são três opções mutuamente exclusivas, não três botões
    // soltos. É o que faz o leitor de tela anunciar "1 de 3" e qual está ativa.
    <div
      role="radiogroup"
      aria-label="Tema da interface"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border border-border p-0.5",
        className,
      )}
    >
      {OPCOES.map(({ valor, rotulo, icone: Icone }) => {
        const ativa = preference === valor;
        return (
          <button
            key={valor}
            type="button"
            role="radio"
            aria-checked={ativa}
            aria-label={rotulo}
            title={rotulo}
            onClick={() => setPreference(valor)}
            className={cn(
              // 36px de alvo — abaixo dos 44 recomendados para toque, mas esta
              // é uma barra de navegação de desktop com alvos equivalentes ao
              // redor; destoar aqui quebraria o alinhamento da linha.
              "flex h-9 w-9 items-center justify-center rounded-full transition-colors",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
              ativa
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icone className="h-4 w-4" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}

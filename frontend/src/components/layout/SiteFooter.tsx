import { cn } from "@/lib/utils";

const AUTHOR_NAME = "Jacqueline Targino";
const AUTHOR_GITHUB_URL = "https://github.com/jacquelinetargino";

/**
 * Rodapé comum a todas as telas. Só o nome da autora é link — o resto do
 * rodapé é texto, para não virar um alvo de clique gigante.
 */
export function SiteFooter({ className }: { className?: string }) {
  return (
    <footer className={cn("px-4 py-6 text-center text-xs text-muted-foreground", className)}>
      <p className="text-balance">
        © {new Date().getFullYear()} CodeInsight AI · Desenvolvido por{" "}
        <a
          href={AUTHOR_GITHUB_URL}
          target="_blank"
          // noopener: a aba nova não ganha acesso a `window.opener`;
          // noreferrer: o GitHub não recebe a URL de onde a pessoa veio.
          rel="noopener noreferrer"
          // O nome visível vem primeiro, para comandos de voz ("clicar em
          // Jacqueline Targino") continuarem funcionando; o resto avisa quem
          // usa leitor de tela que o link abre outra aba.
          aria-label={`${AUTHOR_NAME} no GitHub (abre em nova aba)`}
          className="rounded-sm font-medium text-foreground/80 underline-offset-4 transition-colors hover:text-primary-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {AUTHOR_NAME}
        </a>
      </p>
    </footer>
  );
}

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { GitHubIcon, GoogleIcon } from "@/components/auth/ProviderIcons";
import { Button } from "@/components/ui/button";
import { useAuthProviders } from "@/hooks/useOAuth";
import { oauthStartUrl, PROVIDER_LABEL } from "@/lib/oauth";
import type { OAuthProvider } from "@/types";

const ICONS: Record<OAuthProvider, typeof GoogleIcon> = {
  google: GoogleIcon,
  github: GitHubIcon,
};

/** "Continuar com Google/GitHub". Cada botão é uma navegação de página
 *  inteira para o backend — nenhum segredo nem token passa por aqui. */
export function OAuthButtons({ disabled = false }: { disabled?: boolean }) {
  const { data: providers } = useAuthProviders();
  const [redirecting, setRedirecting] = useState<OAuthProvider | null>(null);

  // Voltar do provedor pelo botão "voltar" do navegador restaura a página do
  // cache (bfcache) com o botão ainda girando. `pageshow` desfaz isso.
  useEffect(() => {
    const reset = () => setRedirecting(null);
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, []);

  function start(provider: OAuthProvider) {
    setRedirecting(provider);
    window.location.assign(oauthStartUrl(provider));
  }

  return (
    <div className="grid gap-2">
      {(["google", "github"] as const).map((provider) => {
        const Icon = ICONS[provider];
        // `undefined` = ainda carregando: deixa clicar. O backend devolve uma
        // mensagem amigável se o provedor não estiver configurado.
        const unavailable = providers !== undefined && !providers[provider];
        const label = PROVIDER_LABEL[provider];
        return (
          <Button
            key={provider}
            type="button"
            variant="outline"
            className="w-full"
            disabled={disabled || redirecting !== null || unavailable}
            onClick={() => start(provider)}
            title={unavailable ? `Login com ${label} indisponível neste servidor` : undefined}
          >
            {redirecting === provider ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Icon className="h-4 w-4" />
            )}
            {redirecting === provider ? "Redirecionando…" : `Continuar com ${label}`}
          </Button>
        );
      })}
    </div>
  );
}

/** Separador "ou" entre o login social e o formulário. */
export function AuthDivider() {
  return (
    <div className="relative my-5" role="separator">
      <div className="absolute inset-0 flex items-center" aria-hidden="true">
        <span className="w-full border-t border-border" />
      </div>
      <div className="relative flex justify-center text-xs uppercase">
        <span className="bg-card px-2 text-muted-foreground">ou</span>
      </div>
    </div>
  );
}

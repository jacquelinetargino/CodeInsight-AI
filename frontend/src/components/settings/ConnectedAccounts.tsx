import { AlertCircle, CheckCircle2, Link2, Loader2 } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { GitHubIcon, GoogleIcon } from "@/components/auth/ProviderIcons";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthProviders, useIdentities, useUnlinkIdentity } from "@/hooks/useOAuth";
import { ApiError, api } from "@/lib/api";
import { oauthErrorMessage, PROVIDER_LABEL } from "@/lib/oauth";
import type { OAuthProvider } from "@/types";

const ICONS: Record<OAuthProvider, typeof GoogleIcon> = {
  google: GoogleIcon,
  github: GitHubIcon,
};

/** Contas Google/GitHub ligadas ao usuário, para entrar sem senha.
 *
 *  Vincular só acontece AQUI, com a pessoa já logada — nunca no login, por
 *  e-mail igual. Ver `link_identity` no backend. */
export function ConnectedAccounts() {
  const [params] = useSearchParams();
  const { data: identities, isLoading } = useIdentities();
  const { data: providers } = useAuthProviders();
  const unlink = useUnlinkIdentity();
  const [busy, setBusy] = useState<OAuthProvider | null>(null);
  const [error, setError] = useState<string | null>(null);

  const linked = params.get("linked") as OAuthProvider | null;
  const shownError = error ?? oauthErrorMessage(params.get("oauth_error"));

  async function connect(provider: OAuthProvider) {
    setError(null);
    setBusy(provider);
    try {
      const { url } = await api.auth.oauthLinkStart(provider);
      window.location.assign(url);
    } catch (err) {
      setBusy(null);
      setError(err instanceof ApiError ? err.message : "Não foi possível iniciar a conexão.");
    }
  }

  async function disconnect(provider: OAuthProvider) {
    setError(null);
    setBusy(provider);
    try {
      await unlink.mutateAsync(provider);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível desconectar.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Link2 className="h-4 w-4" /> Contas conectadas
        </CardTitle>
        <CardDescription>
          Entre com o Google ou o GitHub em vez de digitar a senha. Conectar o GitHub aqui serve só
          para o login — não dá acesso aos seus repositórios; para isso, use o token abaixo.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {linked && PROVIDER_LABEL[linked] && !shownError && (
          <Alert>
            <CheckCircle2 className="h-4 w-4 text-success" />
            <AlertDescription>
              Conta {PROVIDER_LABEL[linked]} conectada. Agora você pode usar “Continuar com{" "}
              {PROVIDER_LABEL[linked]}” na tela de login.
            </AlertDescription>
          </Alert>
        )}
        {shownError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{shownError}</AlertDescription>
          </Alert>
        )}
        {identities && !identities.has_password && (
          <p className="text-xs text-muted-foreground">
            Sua conta ainda não tem senha. Para criar uma, use “Esqueceu sua senha?” na tela de
            login.
          </p>
        )}

        <ul className="divide-y divide-border rounded-md border">
          {(["google", "github"] as const).map((provider) => {
            const Icon = ICONS[provider];
            const identity = identities?.identities.find((i) => i.provider === provider);
            const unavailable = providers !== undefined && !providers[provider];
            return (
              <li
                key={provider}
                className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <Icon className="h-5 w-5 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{PROVIDER_LABEL[provider]}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {isLoading
                        ? "Carregando…"
                        : identity
                          ? (identity.email ?? "Conectada")
                          : unavailable
                            ? "Indisponível neste servidor"
                            : "Não conectada"}
                    </p>
                  </div>
                </div>
                {identity ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => disconnect(provider)}
                  >
                    {busy === provider && <Loader2 className="h-3 w-3 animate-spin" />}
                    Desconectar
                  </Button>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    disabled={busy !== null || unavailable || isLoading}
                    onClick={() => connect(provider)}
                  >
                    {busy === provider && <Loader2 className="h-3 w-3 animate-spin" />}
                    Conectar
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

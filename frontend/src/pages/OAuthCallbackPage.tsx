import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthShell } from "@/components/layout/AuthShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, api } from "@/lib/api";
import { readExchangeCode } from "@/lib/oauth";
import { tokenStorage } from "@/lib/tokenStorage";

/** Destino do backend depois do Google/GitHub: troca o código de uso único
 *  (que veio no fragmento da URL) pela sessão, ou conclui um vínculo. */
export function OAuthCallbackPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { completeLogin } = useAuth();
  const [error, setError] = useState<string | null>(null);
  // O código vale uma vez só. Em desenvolvimento o StrictMode roda o efeito
  // duas vezes; sem esta trava, a segunda troca falharia e mostraria erro.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const code = readExchangeCode(window.location.hash);
    // Tira o código da barra de endereço e do histórico já na chegada.
    window.history.replaceState(null, "", window.location.pathname);

    if (!code) {
      setError("Link de login inválido ou incompleto. Tente entrar de novo.");
      return;
    }

    api.auth
      .oauthExchange(code)
      .then((res) => {
        if (res.intent === "login" && res.access_token && res.user) {
          completeLogin(res.access_token, res.user);
          navigate("/dashboard", { replace: true });
          return;
        }
        queryClient.invalidateQueries({ queryKey: ["auth", "identities"] });
        navigate(`/settings?linked=${res.provider}`, { replace: true });
      })
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Não foi possível concluir o login. Tente de novo.",
        );
      });
  }, [completeLogin, navigate, queryClient]);

  if (!error) {
    return (
      <AuthShell title="Entrando…" description="Confirmando sua identidade com segurança.">
        <div className="flex justify-center py-4" role="status" aria-live="polite">
          <Loader2 className="h-6 w-6 animate-spin text-primary-text" aria-hidden="true" />
          <span className="sr-only">Carregando</span>
        </div>
      </AuthShell>
    );
  }

  const logado = !!tokenStorage.get();
  return (
    <AuthShell title="Não foi possível entrar" description="Nada foi alterado na sua conta.">
      <div className="space-y-4">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button asChild className="w-full">
          <Link to={logado ? "/settings" : "/login"}>
            {logado ? "Voltar para as configurações" : "Voltar para o login"}
          </Link>
        </Button>
      </div>
    </AuthShell>
  );
}

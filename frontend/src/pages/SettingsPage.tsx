import { AlertCircle, CheckCircle2, ExternalLink, KeyRound } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDeleteGithubToken, useGithubTokenStatus, useSetGithubToken } from "@/hooks/useSettings";
import { ApiError } from "@/lib/api";

export function SettingsPage() {
  const { data: status, isLoading } = useGithubTokenStatus();
  const setToken = useSetGithubToken();
  const deleteToken = useDeleteGithubToken();
  const [token, setTokenValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await setToken.mutateAsync(token);
      setTokenValue("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível salvar o token.");
    }
  }

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Configurações</h1>
        <p className="text-muted-foreground">Conecte um token do GitHub (opcional).</p>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" /> Personal Access Token do GitHub
          </CardTitle>
          <CardDescription>
            Sem token, você já pode analisar qualquer repositório público. Conecte um PAT para
            analisar repositórios privados e listar automaticamente os seus repositórios. Crie um em{" "}
            <a
              href="https://github.com/settings/tokens"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary-text hover:underline"
            >
              github.com/settings/tokens <ExternalLink className="h-3 w-3" />
            </a>{" "}
            (escopo <code>repo</code> para repositórios privados).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!isLoading && status?.connected && (
            <Alert>
              <CheckCircle2 className="h-4 w-4 text-success" />
              <AlertDescription>
                Um token do GitHub está conectado. Repositórios privados e listagem automática já
                funcionam.
              </AlertDescription>
            </Alert>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSave} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="github-token">
                {status?.connected ? "Substituir token" : "Token"}
              </Label>
              <Input
                id="github-token"
                type="password"
                placeholder="ghp_..."
                value={token}
                onChange={(e) => setTokenValue(e.target.value)}
                minLength={10}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={!token || setToken.isPending}>
                {setToken.isPending ? "Salvando…" : "Salvar token"}
              </Button>
              {status?.connected && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={deleteToken.isPending}
                  onClick={() => deleteToken.mutate()}
                >
                  Desconectar
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </AppShell>
  );
}

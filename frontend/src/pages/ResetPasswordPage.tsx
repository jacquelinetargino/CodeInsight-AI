import { AlertCircle, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthShell } from "@/components/layout/AuthShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Só um 400 do backend significa link vencido/usado; aí vale oferecer outro.
  const [linkRejected, setLinkRejected] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLinkRejected(false);
    if (password !== confirmation) {
      setError("As senhas não são iguais.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.auth.resetPassword(token, password);
      setDone(res.message);
    } catch (err) {
      setLinkRejected(err instanceof ApiError && err.status === 400);
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível redefinir a senha. Tente novamente.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthShell title="Link inválido" description="Este link de redefinição está incompleto.">
        <p className="text-center text-sm">
          <Link to="/forgot-password" className="font-medium text-primary-text hover:underline">
            Pedir um novo link
          </Link>
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Nova senha" description="Escolha a nova senha da sua conta.">
      {done ? (
        <div className="space-y-4 text-center">
          <CheckCircle2 className="mx-auto h-8 w-8 text-primary-text" />
          <p className="text-sm">{done}</p>
          <Button asChild className="w-full">
            <Link to="/login">Ir para o login</Link>
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {error}
                {linkRejected && (
                  <>
                    {" "}
                    <Link to="/forgot-password" className="font-medium underline">
                      Pedir um novo link
                    </Link>
                  </>
                )}
              </AlertDescription>
            </Alert>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="password">Nova senha</Label>
            <Input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
            <p className="text-xs text-muted-foreground">Mínimo de 8 caracteres.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirmation">Confirme a nova senha</Label>
            <Input
              id="confirmation"
              type="password"
              required
              minLength={8}
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Salvando…" : "Salvar nova senha"}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}

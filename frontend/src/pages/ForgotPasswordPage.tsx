import { AlertCircle, MailCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { AuthShell } from "@/components/layout/AuthShell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  // A mensagem vem do backend e é a mesma exista ou não a conta.
  const [sent, setSent] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.auth.forgotPassword(email);
      setSent(res.message);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível enviar o pedido. Tente novamente.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Esqueci minha senha"
      description="Informe o e-mail da sua conta e enviaremos um link para escolher uma nova senha."
    >
      {sent ? (
        <div className="space-y-4 text-center">
          <MailCheck className="mx-auto h-8 w-8 text-primary-text" />
          <p className="text-sm">{sent}</p>
          <p className="text-xs text-muted-foreground">
            O link vale por 30 minutos. Confira também a caixa de spam.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="email">E-mail</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Enviando…" : "Enviar link"}
          </Button>
        </form>
      )}
      <p className="mt-4 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary-text hover:underline">
          Voltar para o login
        </Link>
      </p>
    </AuthShell>
  );
}

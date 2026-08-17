import { AlertCircle, ScanSearch, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Segurança",
    desc: "Detecta segredos expostos, dependências vulneráveis e más práticas.",
  },
  {
    icon: ScanSearch,
    title: "Oito dimensões",
    desc: "Score de 0 a 100 por dimensão e nível de risco do repositório.",
  },
  // A ressalva é deliberada: prometer README e correções sem dizer que
  // dependem de configuração extra faria a tela mentir para quem não tem.
  { icon: Wand2, title: "README & correções", desc: "Opcional, com provedor de IA configurado." },
];

export function LoginPage() {
  const { isAuthenticated, isLoading, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível entrar. Tente novamente.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-background to-secondary/40 px-4 py-12">
      {/* Quem entra pela tela de login também precisa poder trocar o tema —
          aqui não existe barra de navegação. */}
      <ThemeToggle className="absolute right-4 top-4" />

      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg">
          <Sparkles className="h-7 w-7" />
        </span>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          CodeInsight <span className="text-primary-text">AI</span>
        </h1>
        <p className="max-w-md text-balance text-muted-foreground">
          Analise qualquer repositório do GitHub em oito dimensões: segurança, qualidade,
          dependências, arquitetura, testes, configuração, documentação e git — com score e nível de
          risco, sem precisar de chave de API.
        </p>
      </div>

      <Card className="w-full max-w-sm">
        <CardContent className="p-6">
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
            <div className="space-y-1.5">
              <Label htmlFor="password">Senha</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Entrando…" : "Entrar"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            Não tem conta?{" "}
            <Link to="/register" className="font-medium text-primary-text hover:underline">
              Cadastre-se
            </Link>
          </p>
        </CardContent>
      </Card>

      <div className="mt-14 grid w-full max-w-3xl gap-4 sm:grid-cols-3">
        {FEATURES.map((f) => (
          <Card key={f.title} className="animate-slide-up">
            <CardContent className="flex flex-col items-start gap-2 p-5">
              <f.icon className="h-5 w-5 text-primary-text" />
              <h3 className="text-sm font-semibold">{f.title}</h3>
              <p className="text-xs text-muted-foreground">{f.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

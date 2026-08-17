import { AlertCircle, GitFork, KeyRound, Lock, Plus, Star } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { SummaryCards } from "@/components/dashboard/SummaryCards";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useAddRepository, useImportedRepos, useMyGithubRepos } from "@/hooks/useRepos";
import { useGithubTokenStatus } from "@/hooks/useSettings";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: summary, isLoading: loadingSummary } = useDashboardSummary();
  const { data: imported, isLoading: loadingImported } = useImportedRepos();
  const { data: githubTokenStatus } = useGithubTokenStatus();
  const hasGithubToken = !!githubTokenStatus?.connected;
  const { data: githubRepos, isLoading: loadingGithub } = useMyGithubRepos(1, hasGithubToken);
  const addRepository = useAddRepository();

  const [repoInput, setRepoInput] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  const importedFullNames = useMemo(
    () => new Set((imported ?? []).map((r) => r.full_name)),
    [imported],
  );

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    try {
      const repo = await addRepository.mutateAsync(repoInput.trim());
      setRepoInput("");
      navigate(`/repos/${repo.id}`);
    } catch (err) {
      setAddError(
        err instanceof ApiError ? err.message : "Não foi possível adicionar o repositório.",
      );
    }
  }

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Analise qualquer repositório do GitHub em oito dimensões.
        </p>
      </div>

      {loadingSummary ? (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : (
        summary && (
          <div className="mb-6">
            <SummaryCards summary={summary} />
          </div>
        )
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Adicionar repositório</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleAdd} className="flex flex-col gap-3 sm:flex-row">
            <Input
              placeholder="owner/repo ou https://github.com/owner/repo"
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              required
            />
            <Button type="submit" disabled={addRepository.isPending} className="gap-1.5 sm:w-auto">
              <Plus className="h-4 w-4" />
              {addRepository.isPending ? "Adicionando…" : "Adicionar"}
            </Button>
          </form>
          {addError && (
            <Alert variant="destructive" className="mt-3">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{addError}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Tabs defaultValue="my-repos">
        <TabsList>
          <TabsTrigger value="my-repos">Meus repositórios</TabsTrigger>
          <TabsTrigger value="github">Repositórios do GitHub</TabsTrigger>
        </TabsList>

        <TabsContent value="my-repos">
          {loadingImported && <GridSkeleton />}
          {!loadingImported && (imported?.length ?? 0) === 0 && (
            <EmptyState message="Nenhum repositório adicionado ainda. Use o campo acima." />
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {imported?.map((repo) => (
              <Card
                key={repo.id}
                className="flex flex-col justify-between transition-shadow hover:shadow-md"
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    {repo.private && <Lock className="h-3.5 w-3.5 text-muted-foreground" />}
                    <span className="truncate">{repo.full_name}</span>
                  </CardTitle>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {repo.description ?? "Sem descrição"}
                  </p>
                </CardHeader>
                <CardFooter className="justify-between">
                  <span className="text-xs text-muted-foreground">
                    {repo.last_synced_at
                      ? `Última análise: ${formatDate(repo.last_synced_at)}`
                      : "Ainda não analisado"}
                  </span>
                  <Button size="sm" onClick={() => navigate(`/repos/${repo.id}`)}>
                    Analisar
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="github">
          {!hasGithubToken && (
            <div className="rounded-lg border border-dashed border-border p-8 text-center">
              <KeyRound className="mx-auto mb-3 h-6 w-6 text-muted-foreground" />
              <p className="mb-3 text-sm text-muted-foreground">
                Conecte um Personal Access Token do GitHub para listar seus repositórios
                automaticamente.
              </p>
              <Link to="/settings">
                <Button variant="outline">Ir para Configurações</Button>
              </Link>
            </div>
          )}

          {hasGithubToken && loadingGithub && <GridSkeleton />}

          {hasGithubToken && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {githubRepos?.map((repo) => {
                const isImported = importedFullNames.has(repo.full_name);
                return (
                  <Card key={repo.github_repo_id}>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        {repo.private && <Lock className="h-3.5 w-3.5 text-muted-foreground" />}
                        <span className="truncate">{repo.full_name}</span>
                      </CardTitle>
                      <p className="line-clamp-2 text-sm text-muted-foreground">
                        {repo.description ?? "Sem descrição"}
                      </p>
                    </CardHeader>
                    <CardContent className="flex items-center gap-3 pt-0 text-xs text-muted-foreground">
                      {repo.language && <Badge variant="secondary">{repo.language}</Badge>}
                      <span className="flex items-center gap-1">
                        <Star className="h-3.5 w-3.5" /> {repo.stargazers_count}
                      </span>
                    </CardContent>
                    <CardFooter>
                      <Button
                        size="sm"
                        variant={isImported ? "secondary" : "default"}
                        disabled={isImported || addRepository.isPending}
                        className="w-full gap-1.5"
                        onClick={() => addRepository.mutate(repo.full_name)}
                      >
                        <GitFork className="h-3.5 w-3.5" />{" "}
                        {isImported ? "Já adicionado" : "Adicionar"}
                      </Button>
                    </CardFooter>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}

function GridSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-40 w-full" />
      ))}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="mb-4 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

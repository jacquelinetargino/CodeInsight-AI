import { Download, FileText, Github, Info, Lightbulb, PlayCircle, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { DimensionCard } from "@/components/analysis/DimensionCard";
import { ReadmePreview } from "@/components/analysis/ReadmePreview";
import { RiskBadge } from "@/components/analysis/RiskBadge";
import { StatusBadge } from "@/components/analysis/StatusBadge";
import { SuggestionCard } from "@/components/analysis/SuggestionCard";
import { AppShell } from "@/components/layout/AppShell";
import { DimensionRadar } from "@/components/charts/DimensionRadar";
import { ScoreGauge } from "@/components/charts/ScoreGauge";
import { GithubSummaryPanel } from "@/components/repos/GithubSummaryPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAnalysisDetail, useAnalysisHistory, useCreateAnalysis, useGenerateReadme } from "@/hooks/useAnalysis";
import { useGithubSummary, useRepository } from "@/hooks/useRepos";
import { api } from "@/lib/api";
import { cn, formatDate, scoreColor } from "@/lib/utils";
import { dimensionLabel } from "@/types";

export function RepoAnalysisPage() {
  const { repoId } = useParams<{ repoId: string }>();
  const { data: repository, isLoading: loadingRepo } = useRepository(repoId);
  const { data: history, isLoading: loadingHistory } = useAnalysisHistory(repoId);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [downloadingPdf, setDownloadingPdf] = useState(false);

  useEffect(() => {
    if (!selectedId && history && history.length > 0) {
      setSelectedId(history[0].id);
    }
  }, [history, selectedId]);

  const { data: analysis } = useAnalysisDetail(selectedId);
  const { data: githubSummary, isLoading: loadingGithubSummary } = useGithubSummary(repoId);
  const createAnalysis = useCreateAnalysis();
  const generateReadme = useGenerateReadme(selectedId ?? "");

  async function handleNewAnalysis() {
    if (!repoId) return;
    const created = await createAnalysis.mutateAsync(repoId);
    setSelectedId(created.id);
  }

  async function handleDownloadPdf() {
    if (!analysis || !repository) return;
    setDownloadingPdf(true);
    try {
      await api.analysis.downloadPdf(analysis.id, `codeinsight-${repository.full_name.replace("/", "-")}.pdf`);
    } finally {
      setDownloadingPdf(false);
    }
  }

  return (
    <AppShell>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          {loadingRepo ? (
            <Skeleton className="h-8 w-64" />
          ) : (
            <h1 className="text-2xl font-bold tracking-tight">{repository?.full_name}</h1>
          )}
          <p className="text-muted-foreground">{repository?.description ?? "Sem descrição"}</p>
        </div>
        <Button onClick={handleNewAnalysis} disabled={createAnalysis.isPending} className="gap-2">
          <PlayCircle className="h-4 w-4" />
          {createAnalysis.isPending ? "Iniciando…" : "Nova análise"}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="text-sm">Histórico de análises</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {loadingHistory && <Skeleton className="h-16 w-full" />}
            {history?.length === 0 && (
              <p className="text-sm text-muted-foreground">Nenhuma análise ainda. Clique em "Nova análise".</p>
            )}
            {history?.map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedId(item.id)}
                className={cn(
                  "w-full rounded-lg border p-3 text-left text-sm transition-colors hover:bg-accent",
                  selectedId === item.id ? "border-primary bg-accent" : "border-border",
                )}
              >
                <div className="flex items-center justify-between">
                  <StatusBadge status={item.status} />
                  {item.overall_score !== null && (
                    <span className={cn("font-bold", scoreColor(item.overall_score))}>
                      {Math.round(item.overall_score)}
                    </span>
                  )}
                </div>
                <span className="mt-1 block text-xs text-muted-foreground">{formatDate(item.created_at)}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-6">
          {!analysis && !loadingHistory && (history?.length ?? 0) === 0 && (
            <Card>
              <CardContent className="p-10 text-center text-muted-foreground">
                Este repositório ainda não foi analisado. Clique em "Nova análise" para começar.
              </CardContent>
            </Card>
          )}

          {analysis && (
            <>
              <Card>
                <CardContent className="flex flex-col items-center gap-6 p-6 sm:flex-row sm:justify-around">
                  <div className="flex flex-col items-center gap-2">
                    <StatusBadge status={analysis.status} />
                    {analysis.status === "done" && analysis.overall_score !== null && (
                      <ScoreGauge score={analysis.overall_score} />
                    )}
                    {analysis.status === "done" && analysis.risk_level && (
                      <RiskBadge level={analysis.risk_level} />
                    )}
                    {analysis.status === "failed" && (
                      /* role=alert: a falha precisa ser anunciada por leitor de
                         tela, não só ficar vermelha na tela. */
                      <p role="alert" className="max-w-xs text-center text-sm text-destructive">
                        {analysis.error_message}
                      </p>
                    )}
                    {(analysis.status === "queued" || analysis.status === "running") && (
                      <p aria-live="polite" className="max-w-xs text-center text-sm text-muted-foreground">
                        Baixando e analisando o repositório — costuma levar menos de um minuto.
                      </p>
                    )}
                  </div>
                  {analysis.results.length > 0 && <DimensionRadar results={analysis.results} />}
                </CardContent>
              </Card>

              {analysis.results.length > 0 && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {analysis.results.map((result) => (
                    <DimensionCard key={result.dimension} result={result} analysisId={analysis.id} />
                  ))}
                </div>
              )}

              {/* Dimensão sem resultado não pode simplesmente sumir da tela:
                  a ausência do card seria lida como "nada a relatar aqui",
                  quando o que houve foi ausência de avaliação. */}
              {(analysis.unevaluated_dimensions?.length ?? 0) > 0 && (
                <Card>
                  <CardContent className="flex items-start gap-3 p-4">
                    <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <p className="text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">Não avaliado nesta análise:</span>{" "}
                      {analysis.unevaluated_dimensions!.map(dimensionLabel).join(", ")}. Estas dimensões
                      não entraram no score — ausência de avaliação não é ausência de problema.
                    </p>
                  </CardContent>
                </Card>
              )}

              {analysis.status === "done" && (
                <Tabs defaultValue="suggestions">
                  <TabsList>
                    <TabsTrigger value="suggestions" className="gap-1.5">
                      <Lightbulb className="h-3.5 w-3.5" /> Sugestões
                    </TabsTrigger>
                    <TabsTrigger value="fixes" className="gap-1.5">
                      <Wrench className="h-3.5 w-3.5" /> Correções ({analysis.fix_suggestions.length})
                    </TabsTrigger>
                    <TabsTrigger value="readme" className="gap-1.5">
                      <FileText className="h-3.5 w-3.5" /> README
                    </TabsTrigger>
                    <TabsTrigger value="github" className="gap-1.5">
                      <Github className="h-3.5 w-3.5" /> GitHub
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="suggestions" className="space-y-3">
                    {analysis.suggestions.length === 0 && (
                      <p className="text-sm text-muted-foreground">Nenhuma sugestão gerada.</p>
                    )}
                    {analysis.suggestions.map((s) => (
                      <SuggestionCard key={s.id} suggestion={s} />
                    ))}
                  </TabsContent>

                  <TabsContent value="fixes" className="space-y-3">
                    {analysis.fix_suggestions.length === 0 && (
                      <p className="text-sm text-muted-foreground">
                        Nenhuma correção solicitada ainda — clique em "Solicitar correção" em um achado acima.
                      </p>
                    )}
                    {analysis.fix_suggestions.map((fix) => (
                      <Card key={fix.id}>
                        <CardContent className="space-y-2 p-4">
                          {fix.file_path && (
                            <p className="text-xs text-muted-foreground">
                              <code>
                                {fix.file_path}
                                {fix.line ? `:${fix.line}` : ""}
                              </code>
                            </p>
                          )}
                          <p className="text-sm">{fix.explanation}</p>
                          <pre className="max-h-40 overflow-auto rounded-md bg-[#0d1117] p-3 text-xs text-[#c9d1d9]">
                            <code>{fix.suggested_code}</code>
                          </pre>
                        </CardContent>
                      </Card>
                    ))}
                  </TabsContent>

                  <TabsContent value="readme">
                    <ReadmeTab
                      analysisId={analysis.id}
                      hasReadme={analysis.has_readme}
                      onGenerate={() => generateReadme.mutate()}
                      isGenerating={generateReadme.isPending}
                    />
                  </TabsContent>

                  <TabsContent value="github">
                    {loadingGithubSummary && <Skeleton className="h-64 w-full" />}
                    {githubSummary && <GithubSummaryPanel summary={githubSummary} />}
                  </TabsContent>
                </Tabs>
              )}

              {analysis.status === "done" && (
                <div className="flex justify-end">
                  <Button variant="outline" className="gap-2" onClick={handleDownloadPdf} disabled={downloadingPdf}>
                    <Download className="h-4 w-4" />
                    {downloadingPdf ? "Gerando PDF…" : "Exportar relatório em PDF"}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function ReadmeTab({
  analysisId,
  hasReadme,
  onGenerate,
  isGenerating,
}: {
  analysisId: string;
  hasReadme: boolean;
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (hasReadme && !content) {
      setLoading(true);
      api.analysis
        .getReadme(analysisId)
        .then((res) => setContent(res.content))
        .finally(() => setLoading(false));
    }
  }, [hasReadme, analysisId, content]);

  async function handleGenerate() {
    onGenerate();
  }

  if (loading) return <Skeleton className="h-64 w-full" />;

  if (!hasReadme && !content) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center">
        <p className="mb-4 text-sm text-muted-foreground">
          Gere automaticamente um README.md profissional com base na análise deste repositório.
        </p>
        <Button onClick={handleGenerate} disabled={isGenerating}>
          {isGenerating ? "Gerando…" : "Gerar README com IA"}
        </Button>
      </div>
    );
  }

  return <ReadmePreview content={content ?? ""} />;
}

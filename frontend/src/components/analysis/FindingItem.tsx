import { AlertCircle, FileCode2, Wand2 } from "lucide-react";
import { useState } from "react";
import { SeverityBadge } from "@/components/analysis/SeverityBadge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useRequestFix } from "@/hooks/useAnalysis";
import { ApiError } from "@/lib/api";
import type { DetectionMethod, Finding, FixSuggestion } from "@/types";

/**
 * Traduz a confiança para linguagem, em vez de mostrar "0.7".
 *
 * Um número entre 0 e 1 não diz nada a quem lê o relatório; "detecção provável"
 * diz. As faixas são grosseiras de propósito — fingir precisão decimal numa
 * heurística seria falsa exatidão.
 */
function confidenceLabel(confidence: number): string {
  if (confidence >= 0.9) return "Detecção confirmada";
  if (confidence >= 0.7) return "Detecção provável";
  return "Detecção possível — vale conferir";
}

/**
 * Como o achado foi obtido.
 *
 * A confiança sozinha não separava as coisas: um `os.system()` confirmado pela
 * árvore sintática sai com 0.9 e um casamento de regex em JavaScript com 0.7 —
 * dois números que caem no mesmo rótulo e chegavam ao usuário como se fossem a
 * mesma evidência.
 */
const METHOD_LABELS: Record<DetectionMethod, { curto: string; explicacao: string }> = {
  ast: {
    curto: "árvore sintática",
    explicacao:
      "O parser confirmou a estrutura do código — não há ambiguidade sobre o que ele diz.",
  },
  text: {
    curto: "busca textual",
    explicacao:
      "Casamento de padrão sem parser. Não distingue código de string, comentário ou template, então vale conferir no arquivo.",
  },
  metadata: {
    curto: "metadados",
    explicacao: "Baseado em presença, nome ou tamanho de arquivo — o código em si não foi lido.",
  },
};

export function FindingItem({ finding, analysisId }: { finding: Finding; analysisId: string }) {
  const requestFix = useRequestFix(analysisId);
  const [open, setOpen] = useState(false);
  const [fix, setFix] = useState<FixSuggestion | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRequestFix() {
    setError(null);
    try {
      const result = await requestFix.mutateAsync({
        title: finding.title,
        description: finding.description,
        file_path: finding.file_path,
        line: finding.line,
      });
      setFix(result);
      setOpen(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível gerar a correção.");
    }
  }

  return (
    <li className="rounded-lg border border-border bg-secondary/40 p-4">
      <div className="mb-1 flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold">{finding.title}</h4>
        <SeverityBadge severity={finding.severity} />
      </div>

      {(finding.rule_id || typeof finding.confidence === "number") && (
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {finding.rule_id && (
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono">{finding.rule_id}</code>
          )}
          {typeof finding.confidence === "number" && (
            /* A confiança é declarada porque boa parte da análise é heurística:
               esconder a dúvida faria uma inferência parecer certeza. */
            <span>{confidenceLabel(finding.confidence)}</span>
          )}
          {finding.detection_method && METHOD_LABELS[finding.detection_method] && (
            <span
              className="cursor-help border-b border-dotted border-muted-foreground"
              title={METHOD_LABELS[finding.detection_method].explicacao}
            >
              via {METHOD_LABELS[finding.detection_method].curto}
            </span>
          )}
        </div>
      )}

      <p className="text-sm text-muted-foreground">{finding.description}</p>

      {finding.evidence && (
        <div className="mt-2">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Evidência</p>
          <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs leading-relaxed">
            <code>{finding.evidence}</code>
          </pre>
        </div>
      )}

      {finding.suggestion && (
        <p className="mt-2 text-sm">
          <span className="font-medium">Sugestão:</span> {finding.suggestion}
        </p>
      )}

      {error && (
        <Alert variant="destructive" className="mt-2">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="mt-2 flex items-center justify-between gap-2">
        {finding.file_path ? (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <FileCode2 className="h-3.5 w-3.5" />
            <code>
              {finding.file_path}
              {finding.line ? `:${finding.line}` : ""}
            </code>
          </div>
        ) : (
          <span />
        )}
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          onClick={handleRequestFix}
          disabled={requestFix.isPending}
        >
          <Wand2 className="h-3.5 w-3.5" />
          {requestFix.isPending ? "Gerando…" : "Solicitar correção"}
        </Button>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Correção sugerida</DialogTitle>
            <DialogDescription>{finding.title}</DialogDescription>
          </DialogHeader>
          {fix && (
            <div className="space-y-3">
              <div>
                <p className="mb-1 text-xs font-semibold text-muted-foreground">Código atual</p>
                <pre className="max-h-48 overflow-auto rounded-md bg-[#0d1117] p-3 text-xs leading-relaxed text-[#c9d1d9]">
                  <code>{fix.current_code}</code>
                </pre>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-muted-foreground">Código sugerido</p>
                <pre className="max-h-48 overflow-auto rounded-md bg-[#0d1117] p-3 text-xs leading-relaxed text-[#c9d1d9]">
                  <code>{fix.suggested_code}</code>
                </pre>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-muted-foreground">Explicação</p>
                <p className="text-sm">{fix.explanation}</p>
              </div>
              <p className="text-xs text-muted-foreground">
                Esta correção não foi aplicada no repositório — copie o trecho manualmente se quiser
                usá-la.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </li>
  );
}

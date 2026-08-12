import { AlertCircle, FileCode2, Wand2 } from "lucide-react";
import { useState } from "react";
import { SeverityBadge } from "@/components/analysis/SeverityBadge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useRequestFix } from "@/hooks/useAnalysis";
import { ApiError } from "@/lib/api";
import type { Finding, FixSuggestion } from "@/types";

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
      <div className="mb-1 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{finding.title}</h4>
        <SeverityBadge severity={finding.severity} />
      </div>
      <p className="text-sm text-muted-foreground">{finding.description}</p>
      {finding.suggestion && (
        <p className="mt-1 text-sm">
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
                Esta correção não foi aplicada no repositório — copie o trecho manualmente se quiser usá-la.
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </li>
  );
}

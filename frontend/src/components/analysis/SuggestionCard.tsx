import { FileCode2 } from "lucide-react";
import { SeverityBadge } from "@/components/analysis/SeverityBadge";
import type { Suggestion } from "@/types";

export function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{suggestion.title}</h4>
        <SeverityBadge severity={suggestion.severity} />
      </div>
      <p className="text-sm text-muted-foreground">{suggestion.description}</p>

      {suggestion.file_path && (
        <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
          <FileCode2 className="h-3.5 w-3.5" />
          <code>{suggestion.file_path}</code>
        </div>
      )}

      {suggestion.code_fix && (
        <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-[#0d1117] p-3 text-xs leading-relaxed text-[#c9d1d9]">
          <code>{suggestion.code_fix}</code>
        </pre>
      )}
    </div>
  );
}

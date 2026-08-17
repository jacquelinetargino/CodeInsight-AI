import { FindingItem } from "@/components/analysis/FindingItem";
import type { Finding } from "@/types";

export function FindingsList({
  findings,
  analysisId,
}: {
  findings: Finding[];
  analysisId: string;
}) {
  if (findings.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Nenhum problema relevante encontrado. 🎉</p>
    );
  }

  return (
    <ul className="space-y-3">
      {findings.map((finding, idx) => (
        <FindingItem key={idx} finding={finding} analysisId={analysisId} />
      ))}
    </ul>
  );
}

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FindingsList } from "@/components/analysis/FindingsList";
import { Progress } from "@/components/ui/progress";
import { cn, scoreColor } from "@/lib/utils";
import { dimensionLabel, type AnalysisResult } from "@/types";

export function DimensionCard({ result, analysisId }: { result: AnalysisResult; analysisId: string }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">{dimensionLabel(result.dimension)}</CardTitle>
        <span className={cn("text-xl font-bold", scoreColor(result.score))}>{result.score}</span>
      </CardHeader>
      <CardContent className="space-y-4">
        <Progress value={result.score} />
        <p className="text-sm text-muted-foreground">{result.summary}</p>
        <FindingsList findings={result.findings} analysisId={analysisId} />
      </CardContent>
    </Card>
  );
}

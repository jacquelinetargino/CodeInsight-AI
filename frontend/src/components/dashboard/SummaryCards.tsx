import { AlertTriangle, FolderGit2, Gauge, Lightbulb, ScanLine } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn, scoreColor } from "@/lib/utils";
import type { DashboardSummary } from "@/types";

const ITEMS = (summary: DashboardSummary) => [
  { icon: FolderGit2, label: "Repositórios analisados", value: summary.repositories_analyzed },
  { icon: ScanLine, label: "Análises realizadas", value: summary.total_analyses },
  {
    icon: Gauge,
    label: "Score médio",
    value: summary.average_score !== null ? Math.round(summary.average_score) : "—",
    valueClassName: summary.average_score !== null ? scoreColor(summary.average_score) : undefined,
  },
  { icon: AlertTriangle, label: "Problemas encontrados", value: summary.total_findings },
  { icon: Lightbulb, label: "Melhorias sugeridas", value: summary.total_suggestions },
];

export function SummaryCards({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      {ITEMS(summary).map((item) => (
        <Card key={item.label}>
          <CardContent className="flex items-center gap-3 p-4">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <item.icon className="h-4 w-4" />
            </span>
            <div>
              <div className={cn("text-xl font-bold", item.valueClassName)}>{item.value}</div>
              <div className="text-xs text-muted-foreground">{item.label}</div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

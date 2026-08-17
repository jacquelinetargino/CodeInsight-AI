import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AnalysisStatus } from "@/types";

const CONFIG: Record<
  AnalysisStatus,
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  queued: { label: "Na fila", icon: CircleDashed, className: "text-muted-foreground" },
  running: { label: "Analisando…", icon: Loader2, className: "text-primary-text" },
  done: { label: "Concluída", icon: CheckCircle2, className: "text-success-text" },
  failed: { label: "Falhou", icon: XCircle, className: "text-destructive-text" },
};

export function StatusBadge({ status }: { status: AnalysisStatus }) {
  const { label, icon: Icon, className } = CONFIG[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm font-medium", className)}>
      <Icon className={cn("h-4 w-4", status === "running" && "animate-spin")} />
      {label}
    </span>
  );
}

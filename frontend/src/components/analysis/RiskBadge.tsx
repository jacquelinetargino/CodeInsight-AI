import { AlertOctagon, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { RISK_LABELS, type RiskLevel } from "@/types";

/**
 * Cada nível carrega um ícone próprio além da cor.
 *
 * Nível de risco é exatamente o tipo de informação que não pode depender só de
 * cor: quem não distingue vermelho de verde precisa continuar entendendo o
 * veredito. O rótulo textual já diz "Risco alto"; o ícone dá a leitura rápida.
 */
const RISK_STYLES: Record<RiskLevel, { icon: typeof Info; className: string }> = {
  low: {
    icon: CheckCircle2,
    className: "border-success/40 bg-success/10 text-success-text",
  },
  medium: {
    icon: Info,
    className: "border-warning/40 bg-warning/10 text-warning-text",
  },
  high: {
    icon: AlertTriangle,
    className: "border-destructive/40 bg-destructive/10 text-destructive",
  },
  critical: {
    icon: AlertOctagon,
    className: "border-destructive bg-destructive text-destructive-foreground",
  },
};

export function RiskBadge({ level, className }: { level: RiskLevel; className?: string }) {
  const { icon: Icon, className: variant } = RISK_STYLES[level];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium",
        variant,
        className,
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      {RISK_LABELS[level]}
    </span>
  );
}

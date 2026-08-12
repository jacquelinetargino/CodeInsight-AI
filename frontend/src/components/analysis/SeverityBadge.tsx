import { Badge } from "@/components/ui/badge";
import { SEVERITY_LABELS, type Severity } from "@/types";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge variant={severity}>{SEVERITY_LABELS[severity]}</Badge>;
}

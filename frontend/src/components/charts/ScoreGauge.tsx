import { cn, scoreColor } from "@/lib/utils";

interface ScoreGaugeProps {
  score: number;
  size?: number;
  label?: string;
}

export function ScoreGauge({ score, size = 160, label = "Score Geral" }: ScoreGaugeProps) {
  const radius = size / 2 - 12;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circumference - (clamped / 100) * circumference;
  const center = size / 2;

  const colorClass = scoreColor(clamped);
  const strokeColor =
    clamped >= 80
      ? "hsl(var(--success))"
      : clamped >= 50
        ? "hsl(var(--warning))"
        : "hsl(var(--destructive))";

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={center}
          cy={center}
          r={radius}
          stroke="hsl(var(--secondary))"
          strokeWidth={12}
          fill="none"
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          stroke={strokeColor}
          strokeWidth={12}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
        />
        <text
          x={center}
          y={center}
          textAnchor="middle"
          dominantBaseline="central"
          className={cn("rotate-90 origin-center fill-current text-3xl font-bold", colorClass)}
          style={{ transform: `rotate(90deg)`, transformOrigin: `${center}px ${center}px` }}
        >
          {Math.round(clamped)}
        </text>
      </svg>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
    </div>
  );
}

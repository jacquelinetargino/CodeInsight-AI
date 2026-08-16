import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Cor do score como texto.
 *
 * Usa as variantes `-text` porque as cores vivas de success e warning reprovam
 * o contraste mínimo de 4.5:1 quando aplicadas a texto (medido: 3.13:1 e
 * 2.08:1 sobre o fundo claro).
 */
export function scoreColor(score: number): string {
  if (score >= 80) return "text-success-text";
  if (score >= 50) return "text-warning-text";
  return "text-destructive";
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

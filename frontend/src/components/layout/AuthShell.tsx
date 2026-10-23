import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Card, CardContent } from "@/components/ui/card";

/** Moldura das telas de conta fora do login (recuperar e redefinir senha). */
export function AuthShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-background to-secondary/40 px-4 py-12">
      <ThemeToggle className="absolute right-4 top-4" />

      <div className="mb-6 flex flex-col items-center gap-3 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg">
          <Sparkles className="h-6 w-6" />
        </span>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="max-w-sm text-balance text-sm text-muted-foreground">{description}</p>
      </div>

      <Card className="w-full max-w-sm">
        <CardContent className="p-6">{children}</CardContent>
      </Card>
    </div>
  );
}

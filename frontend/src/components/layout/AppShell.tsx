import type { ReactNode } from "react";
import { Navbar } from "./Navbar";
import { SiteFooter } from "./SiteFooter";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Navbar />
      {/* flex-1: em páginas curtas o rodapé fica no fim da tela, não no meio. */}
      <main className="container flex-1 py-8">{children}</main>
      <SiteFooter className="border-t border-border" />
    </div>
  );
}

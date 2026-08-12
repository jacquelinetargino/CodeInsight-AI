import type { ReactNode } from "react";
import { Navbar } from "./Navbar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="container py-8">{children}</main>
    </div>
  );
}

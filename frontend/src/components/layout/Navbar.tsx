import { Settings, Sparkles } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

export function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/dashboard" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-lg">
            CodeInsight <span className="text-primary">AI</span>
          </span>
        </Link>

        {user && (
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/dashboard")}
              className="text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              Dashboard
            </button>
            <button
              onClick={() => navigate("/settings")}
              className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              <Settings className="h-3.5 w-3.5" /> Configurações
            </button>
            <div className="flex items-center gap-2 rounded-full border border-border py-1 pl-1 pr-3">
              <Avatar className="h-7 w-7">
                <AvatarFallback>{user.username.slice(0, 2).toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="text-sm font-medium">{user.username}</span>
            </div>
            <Button variant="ghost" size="sm" onClick={logout}>
              Sair
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}

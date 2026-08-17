import { GitBranch, GitPullRequest, MessageSquare, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
import type { GithubRepoSummary } from "@/types";

export function GithubSummaryPanel({ summary }: { summary: GithubRepoSummary }) {
  const totalBytes = Object.values(summary.languages).reduce((sum, v) => sum + v, 0);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Linguagens</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {Object.entries(summary.languages).length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhuma linguagem detectada.</p>
          )}
          {Object.entries(summary.languages).map(([lang, bytes]) => {
            const pct = totalBytes > 0 ? Math.round((bytes / totalBytes) * 100) : 0;
            return (
              <div key={lang}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="font-medium">{lang}</span>
                  <span className="text-muted-foreground">{pct}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                  <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <GitBranch className="h-4 w-4" /> Branches
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-1.5">
          {summary.branches.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhuma branch encontrada.</p>
          )}
          {summary.branches.map((b) => (
            <Badge key={b.name} variant={b.protected ? "default" : "secondary"}>
              {b.name}
            </Badge>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <MessageSquare className="h-4 w-4" /> Últimos commits
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {summary.recent_commits.length === 0 && (
            <p className="text-sm text-muted-foreground">Sem commits.</p>
          )}
          {summary.recent_commits.slice(0, 8).map((c) => (
            <div key={c.sha} className="text-sm">
              <span className="font-mono text-xs text-muted-foreground">{c.sha}</span>{" "}
              <span>{c.message}</span>
              <div className="text-xs text-muted-foreground">
                {c.author} {c.date && `· ${formatDate(c.date)}`}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <GitPullRequest className="h-4 w-4" /> Issues & Pull Requests
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Issues ({summary.issues.length})
            </p>
            {summary.issues.slice(0, 5).map((issue) => (
              <div key={issue.number} className="flex items-center justify-between text-sm">
                <span className="truncate">
                  #{issue.number} {issue.title}
                </span>
                <Badge variant={issue.state === "open" ? "default" : "secondary"}>
                  {issue.state}
                </Badge>
              </div>
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              Pull Requests ({summary.pull_requests.length})
            </p>
            {summary.pull_requests.slice(0, 5).map((pr) => (
              <div key={pr.number} className="flex items-center justify-between text-sm">
                <span className="truncate">
                  #{pr.number} {pr.title}
                </span>
                <Badge variant={pr.merged_at ? "default" : "secondary"}>
                  {pr.merged_at ? "merged" : pr.state}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-sm">
            <Users className="h-4 w-4" /> Contribuidores
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          {summary.contributors.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum contribuidor encontrado.</p>
          )}
          {summary.contributors.map((c) => (
            <div
              key={c.username}
              className="flex items-center gap-2 rounded-full border border-border py-1 pl-1 pr-3 text-sm"
            >
              {c.avatar_url ? (
                <img src={c.avatar_url} alt={c.username} className="h-6 w-6 rounded-full" />
              ) : (
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-xs">
                  {c.username.slice(0, 2).toUpperCase()}
                </span>
              )}
              <span>{c.username}</span>
              <span className="text-xs text-muted-foreground">{c.contributions}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

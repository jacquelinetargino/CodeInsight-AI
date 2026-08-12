export interface User {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface GithubRepo {
  github_repo_id: number;
  full_name: string;
  description: string | null;
  default_branch: string;
  private: boolean;
  stargazers_count: number;
  language: string | null;
  updated_at: string | null;
}

export interface Repository {
  id: string;
  github_repo_id: number;
  full_name: string;
  description: string | null;
  default_branch: string;
  private: boolean;
  last_synced_at: string | null;
  created_at: string;
}

export interface GithubTokenStatus {
  connected: boolean;
}

export interface CommitSummary {
  sha: string;
  message: string;
  author: string | null;
  date: string | null;
}

export interface IssueSummary {
  number: number;
  title: string;
  state: string;
  created_at: string;
}

export interface PullRequestSummary {
  number: number;
  title: string;
  state: string;
  created_at: string;
  merged_at: string | null;
}

export interface ContributorSummary {
  username: string;
  avatar_url: string | null;
  contributions: number;
}

export interface BranchSummary {
  name: string;
  protected: boolean;
}

export interface GithubRepoSummary {
  languages: Record<string, number>;
  branches: BranchSummary[];
  recent_commits: CommitSummary[];
  issues: IssueSummary[];
  pull_requests: PullRequestSummary[];
  contributors: ContributorSummary[];
}

export type AnalysisStatus = "queued" | "running" | "done" | "failed";
export type Dimension = "security" | "quality" | "architecture" | "documentation" | "tests" | "git";
export type Severity = "low" | "medium" | "high" | "critical";

export interface Finding {
  title: string;
  description: string;
  suggestion: string | null;
  severity: Severity;
  file_path: string | null;
  line: number | null;
}

export interface AnalysisResult {
  dimension: Dimension;
  score: number;
  summary: string;
  findings: Finding[];
}

export interface Suggestion {
  id: string;
  title: string;
  description: string;
  severity: Severity;
  file_path: string | null;
  code_fix: string | null;
}

export interface FixSuggestion {
  id: string;
  file_path: string | null;
  line: number | null;
  current_code: string;
  suggested_code: string;
  explanation: string;
  created_at: string;
}

export interface Analysis {
  id: string;
  repository_id: string;
  status: AnalysisStatus;
  overall_score: number | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface AnalysisDetail extends Analysis {
  results: AnalysisResult[];
  suggestions: Suggestion[];
  fix_suggestions: FixSuggestion[];
  has_readme: boolean;
}

export interface DashboardHistoryItem {
  analysis_id: string;
  repository_full_name: string;
  status: AnalysisStatus;
  overall_score: number | null;
  created_at: string;
}

export interface DashboardSummary {
  repositories_analyzed: number;
  total_analyses: number;
  average_score: number | null;
  total_findings: number;
  total_suggestions: number;
  recent_history: DashboardHistoryItem[];
}

export const DIMENSION_LABELS: Record<Dimension, string> = {
  security: "Segurança",
  quality: "Qualidade",
  architecture: "Arquitetura",
  documentation: "Documentação",
  tests: "Testes",
  git: "Git",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  low: "Baixa",
  medium: "Média",
  high: "Alta",
  critical: "Crítica",
};

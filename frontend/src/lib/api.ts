import { tokenStorage } from "@/lib/tokenStorage";
import type {
  Analysis,
  AnalysisDetail,
  DashboardSummary,
  FixSuggestion,
  GithubRepo,
  GithubRepoSummary,
  GithubTokenStatus,
  Repository,
  TokenResponse,
  User,
} from "@/types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

interface PydanticValidationError {
  msg?: string;
  loc?: (string | number)[];
}

function extractErrorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    // Erro de validação do FastAPI/Pydantic: lista de {msg, loc, ...}.
    const messages = detail
      .map((item: PydanticValidationError) => {
        const field = item.loc?.[item.loc.length - 1];
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .filter(Boolean);
    if (messages.length > 0) return messages.join("; ");
  }

  return `Erro ${status}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = tokenStorage.get();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, extractErrorMessage(body, response.status));
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  auth: {
    register: (payload: { email: string; password: string; username: string }) =>
      request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
    login: (payload: { email: string; password: string }) =>
      request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
    me: () => request<User>("/auth/me"),
    logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  },
  settings: {
    getGithubTokenStatus: () => request<GithubTokenStatus>("/settings/github-token"),
    setGithubToken: (token: string) =>
      request<GithubTokenStatus>("/settings/github-token", {
        method: "PUT",
        body: JSON.stringify({ token }),
      }),
    deleteGithubToken: () => request<GithubTokenStatus>("/settings/github-token", { method: "DELETE" }),
  },
  repos: {
    listMineFromGithub: (page = 1) => request<GithubRepo[]>(`/repos/github/mine?page=${page}&per_page=30`),
    listImported: () => request<Repository[]>("/repos"),
    add: (repo: string) => request<Repository>("/repos", { method: "POST", body: JSON.stringify({ repo }) }),
    get: (id: string) => request<Repository>(`/repos/${id}`),
    getGithubSummary: (id: string) => request<GithubRepoSummary>(`/repos/${id}/github-summary`),
  },
  analysis: {
    create: (repositoryId: string) =>
      request<Analysis>("/analysis", {
        method: "POST",
        body: JSON.stringify({ repository_id: repositoryId }),
      }),
    get: (id: string) => request<AnalysisDetail>(`/analysis/${id}`),
    listForRepository: (repositoryId: string) =>
      request<Analysis[]>(`/analysis?repository_id=${repositoryId}`),
    generateReadme: (id: string) =>
      request<{ content: string }>(`/analysis/${id}/readme`, { method: "POST" }),
    getReadme: (id: string) => request<{ content: string }>(`/analysis/${id}/readme`),
    requestFix: (
      id: string,
      payload: { title: string; description: string; file_path: string | null; line: number | null },
    ) => request<FixSuggestion>(`/analysis/${id}/fix`, { method: "POST", body: JSON.stringify(payload) }),
    downloadPdf: async (id: string, filename: string) => {
      // Download via <a href> não funciona aqui: a autenticação é por header
      // "Authorization: Bearer" (não cookie), e uma navegação de link comum não
      // consegue anexar esse header. Buscamos o PDF via fetch autenticado e
      // disparamos o download a partir do blob.
      const token = tokenStorage.get();
      const response = await fetch(`${API_BASE_URL}/reports/${id}/pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new ApiError(response.status, "Falha ao gerar o relatório em PDF");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    },
  },
  dashboard: {
    getSummary: () => request<DashboardSummary>("/dashboard/summary"),
  },
};

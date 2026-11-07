import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "@/pages/LoginPage";
import { OAuthCallbackPage } from "@/pages/OAuthCallbackPage";
import { useAuthStore } from "@/store/authStore";

function resposta(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body } as Response;
}

function renderEm(path: string, element: ReactNode, extra: ReactNode = null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={path.split("?")[0]} element={element} />
          {extra}
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: null, isLoading: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("tela de login", () => {
  it("mostra os dois provedores, o link de recuperação e o cadastro", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => resposta(200, { google: true, github: true, password_reset: true })),
    );
    renderEm("/login", <LoginPage />);

    expect(screen.getByRole("button", { name: /continuar com google/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continuar com github/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /esqueceu sua senha\?/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByRole("link", { name: /cadastre-se/i })).toBeInTheDocument();
  });

  it("desabilita o provedor que o servidor não configurou", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => resposta(200, { google: true, github: false, password_reset: true })),
    );
    renderEm("/login", <LoginPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /continuar com github/i })).toBeDisabled(),
    );
    expect(screen.getByRole("button", { name: /continuar com google/i })).toBeEnabled();
  });

  it("explica um login social cancelado", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => resposta(200, { google: true, github: true, password_reset: true })),
    );
    renderEm("/login?oauth_error=cancelled", <LoginPage />);
    expect(screen.getByText(/login cancelado/i)).toBeInTheDocument();
  });
});

describe("retorno do login social", () => {
  it("troca o código do fragmento pela sessão e guarda o token", async () => {
    window.history.replaceState(null, "", "/auth/callback#code=codigo-de-uso-unico");
    const fetchMock = vi.fn(async () =>
      resposta(200, {
        intent: "login",
        provider: "google",
        access_token: "jwt-de-teste",
        token_type: "bearer",
        user: { id: "1", email: "ana@exemplo.com", username: "Ana", is_active: true },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderEm(
      "/auth/callback",
      <OAuthCallbackPage />,
      <Route path="/dashboard" element={<p>painel</p>} />,
    );

    expect(await screen.findByText("painel")).toBeInTheDocument();
    expect(localStorage.getItem("codeinsight_token")).toBe("jwt-de-teste");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/auth\/oauth\/exchange$/);
    expect(JSON.parse(init.body as string)).toEqual({ code: "codigo-de-uso-unico" });
    // O código sai da barra de endereço.
    expect(window.location.hash).toBe("");
  });

  it("mostra o motivo quando o backend recusa", async () => {
    window.history.replaceState(null, "", "/auth/callback#code=ja-usado");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => resposta(409, { detail: "Já existe uma conta com o e-mail da sua conta" })),
    );

    renderEm("/auth/callback", <OAuthCallbackPage />);

    expect(await screen.findByText(/já existe uma conta/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /voltar para o login/i })).toBeInTheDocument();
    expect(localStorage.getItem("codeinsight_token")).toBeNull();
  });

  it("sem código no fragmento, não chama o backend", async () => {
    window.history.replaceState(null, "", "/auth/callback");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderEm("/auth/callback", <OAuthCallbackPage />);

    expect(await screen.findByText(/inválido ou incompleto/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

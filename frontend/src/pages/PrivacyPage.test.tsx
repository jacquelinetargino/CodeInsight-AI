import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { LoginPage } from "@/pages/LoginPage";
import { PrivacyPage } from "@/pages/PrivacyPage";
import { useAuthStore } from "@/store/authStore";

afterEach(() => vi.unstubAllGlobals());

describe("política de privacidade", () => {
  it("é pública e tem contato, revogação de acesso e a política de dados do Google", () => {
    render(
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: /política de privacidade/i })).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "codeinsightai.suporte@gmail.com" })[0],
    ).toHaveAttribute("href", "mailto:codeinsightai.suporte@gmail.com");
    expect(
      screen.getByRole("link", { name: /myaccount\.google\.com\/permissions/ }),
    ).toHaveAttribute("href", "https://myaccount.google.com/permissions");
    expect(
      screen.getByRole("link", { name: /github\.com\/settings\/applications/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: /Política de Dados do Usuário dos Serviços de API do Google/,
      }),
    ).toHaveAttribute("href", "https://developers.google.com/terms/api-services-user-data-policy");
    // O que o texto promete precisa bater com o sistema: senha só como hash.
    expect(screen.getAllByText(/hash bcrypt/i).length).toBeGreaterThan(0);
  });

  it("a rota /privacidade abre sem login", () => {
    useAuthStore.setState({ user: null, isLoading: false });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/privacidade"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("heading", { name: /política de privacidade/i })).toBeInTheDocument();
  });

  it("a tela de login aponta para a política", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({
            ok: true,
            status: 200,
            json: async () => ({ google: true, github: true, password_reset: true }),
          }) as Response,
      ),
    );
    useAuthStore.setState({ user: null, isLoading: false });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("link", { name: /política de privacidade/i })).toHaveAttribute(
      "href",
      "/privacidade",
    );
  });
});

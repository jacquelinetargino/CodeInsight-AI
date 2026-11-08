import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { LoginPage } from "@/pages/LoginPage";
import { PrivacyPage } from "@/pages/PrivacyPage";
import { useAuthStore } from "@/store/authStore";

afterEach(() => vi.unstubAllGlobals());

describe("rodapé", () => {
  it("o nome da autora é link para o GitHub, em nova aba e sem opener", () => {
    render(<SiteFooter />);

    const link = screen.getByRole("link", { name: /Jacqueline Targino/ });
    expect(link).toHaveTextContent("Jacqueline Targino");
    expect(link).toHaveAttribute("href", "https://github.com/jacquelinetargino");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")?.split(" ")).toEqual(
      expect.arrayContaining(["noopener", "noreferrer"]),
    );
    // Quem usa leitor de tela fica sabendo que abre outra aba.
    expect(link).toHaveAccessibleName(/abre em nova aba/);
  });

  it("só o nome é clicável, não o rodapé inteiro", () => {
    render(<SiteFooter />);

    const rodape = screen.getByRole("contentinfo");
    const links = within(rodape).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent(/^Jacqueline Targino$/);
    expect(rodape).toHaveTextContent(/Desenvolvido por Jacqueline Targino/);
    expect(rodape.closest("a")).toBeNull();
  });

  it("aparece na tela de login e na política de privacidade", () => {
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

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Jacqueline Targino");
    unmount();

    render(
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Jacqueline Targino");
  });
});

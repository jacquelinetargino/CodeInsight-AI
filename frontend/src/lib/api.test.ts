import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api";

/**
 * O backend passou a limitar `POST /auth/login` e `POST /auth/register`, então
 * o 429 deixou de ser um caso raro de rota cara e virou algo que quem erra a
 * senha algumas vezes encontra.
 *
 * O corpo do slowapi é `{ error: "Rate limit exceeded: ..." }` — não o
 * `{ detail: ... }` do FastAPI. Sem tratamento, a mensagem exibida era só
 * "Erro 429".
 */

function respostaFalsa(status: number, body: unknown) {
  return {
    ok: false,
    status,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mensagem de erro da API", () => {
  it("explica o 429 em vez de mostrar o código cru", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respostaFalsa(429, { error: "Rate limit exceeded: 10 per 1 minute" })),
    );

    const erro = await api.auth
      .login({ email: "alguem@example.com", password: "senha" })
      .catch((e) => e);

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).status).toBe(429);
    expect((erro as ApiError).message).toMatch(/tentativas demais/i);
    expect((erro as ApiError).message).not.toMatch(/^Erro 429$/);
  });

  it("mostra a validação do pydantic com o nome do campo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        respostaFalsa(422, {
          detail: [{ loc: ["body", "password"], msg: "Value error, A senha passa de 72 bytes" }],
        }),
      ),
    );

    const erro = await api.auth
      .register({ email: "alguem@example.com", password: "x".repeat(200), username: "alguem" })
      .catch((e) => e);

    expect((erro as ApiError).message).toContain("password");
    expect((erro as ApiError).message).toContain("72 bytes");
  });

  it("mostra o detail simples quando o backend manda um texto", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respostaFalsa(401, { detail: "E-mail ou senha inválidos" })),
    );

    const erro = await api.auth
      .login({ email: "alguem@example.com", password: "senha" })
      .catch((e) => e);

    expect((erro as ApiError).message).toBe("E-mail ou senha inválidos");
  });
});

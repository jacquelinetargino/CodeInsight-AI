import { describe, expect, it } from "vitest";
import { oauthErrorMessage, oauthStartUrl, readExchangeCode } from "@/lib/oauth";

describe("login social — utilitários", () => {
  it("lê o código de troca do fragmento, com ou sem #", () => {
    expect(readExchangeCode("#code=gAAAAAabc%3D%3D")).toBe("gAAAAAabc==");
    expect(readExchangeCode("code=xyz")).toBe("xyz");
  });

  it("não inventa código quando o fragmento não tem", () => {
    expect(readExchangeCode("")).toBeNull();
    expect(readExchangeCode("#code=")).toBeNull();
    expect(readExchangeCode("#outra=coisa")).toBeNull();
  });

  it("traduz os códigos de erro do backend", () => {
    expect(oauthErrorMessage("cancelled")).toMatch(/cancelado/i);
    expect(oauthErrorMessage("state_mismatch")).toMatch(/expirou/i);
    expect(oauthErrorMessage("unavailable")).toMatch(/não está disponível/i);
  });

  it("código desconhecido vira mensagem genérica, nunca o código cru", () => {
    const msg = oauthErrorMessage("<script>x</script>");
    expect(msg).not.toContain("<script>");
    expect(msg).toMatch(/não foi possível/i);
    expect(oauthErrorMessage(null)).toBeNull();
  });

  it("o início do login aponta para o backend, não para o provedor", () => {
    expect(oauthStartUrl("google")).toMatch(/\/auth\/oauth\/google\/start$/);
    expect(oauthStartUrl("github")).toMatch(/\/auth\/oauth\/github\/start$/);
  });
});

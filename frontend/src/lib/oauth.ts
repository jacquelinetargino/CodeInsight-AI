import { API_BASE_URL } from "@/lib/api";
import type { OAuthProvider } from "@/types";

export const PROVIDER_LABEL: Record<OAuthProvider, string> = {
  google: "Google",
  github: "GitHub",
};

/** Início do login social: uma navegação de página inteira para o backend,
 *  que guarda state + PKCE num cookie HttpOnly e segue para o provedor. */
export function oauthStartUrl(provider: OAuthProvider): string {
  return `${API_BASE_URL}/auth/oauth/${provider}/start`;
}

/** Códigos que o backend põe em `?oauth_error=` ao devolver o navegador.
 *  Mantidos em sincronia com `OAuthError` em `app/services/oauth_service.py`
 *  e com `app/api/routes/oauth.py`. */
const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  cancelled: "Login cancelado. Nenhuma alteração foi feita.",
  unavailable: "Este tipo de login não está disponível no momento.",
  state_mismatch:
    "A sessão de login expirou ou não pôde ser confirmada. Tente de novo a partir desta página.",
  provider_error: "O provedor não respondeu como esperado. Tente de novo em instantes.",
  invalid_token: "Não foi possível confirmar sua identidade com o provedor. Tente de novo.",
  link_expired: "O pedido para conectar a conta expirou. Tente de novo.",
};

export function oauthErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return OAUTH_ERROR_MESSAGES[code] ?? "Não foi possível entrar. Tente de novo.";
}

/** O código de troca vem no FRAGMENTO (`#code=…`): o fragmento não é enviado
 *  a servidor nenhum nem vaza pelo Referer. */
export function readExchangeCode(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const code = params.get("code");
  return code && code.length > 0 ? code : null;
}

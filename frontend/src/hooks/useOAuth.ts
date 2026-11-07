import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { OAuthProvider } from "@/types";

/** O que o servidor tem configurado. Muda só com deploy, então pode ficar em
 *  cache por bastante tempo; enquanto carrega, os botões ficam habilitados. */
export function useAuthProviders() {
  return useQuery({
    queryKey: ["auth", "providers"],
    queryFn: api.auth.providers,
    staleTime: 10 * 60_000,
    retry: 1,
  });
}

export function useIdentities() {
  return useQuery({ queryKey: ["auth", "identities"], queryFn: api.auth.identities });
}

export function useUnlinkIdentity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (provider: OAuthProvider) => api.auth.unlinkIdentity(provider),
    onSuccess: (data) => {
      queryClient.setQueryData(["auth", "identities"], data);
    },
  });
}

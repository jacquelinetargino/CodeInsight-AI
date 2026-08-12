import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useGithubTokenStatus() {
  return useQuery({
    queryKey: ["settings", "github-token"],
    queryFn: api.settings.getGithubTokenStatus,
  });
}

export function useSetGithubToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => api.settings.setGithubToken(token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "github-token"] });
    },
  });
}

export function useDeleteGithubToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.settings.deleteGithubToken(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "github-token"] });
    },
  });
}

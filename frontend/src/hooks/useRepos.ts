import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useMyGithubRepos(page = 1, enabled = true) {
  return useQuery({
    queryKey: ["github-repos-mine", page],
    queryFn: () => api.repos.listMineFromGithub(page),
    enabled,
    retry: false,
  });
}

export function useImportedRepos() {
  return useQuery({
    queryKey: ["repos"],
    queryFn: api.repos.listImported,
  });
}

export function useRepository(id: string | undefined) {
  return useQuery({
    queryKey: ["repos", id],
    queryFn: () => api.repos.get(id!),
    enabled: !!id,
  });
}

export function useGithubSummary(id: string | undefined) {
  return useQuery({
    queryKey: ["repos", id, "github-summary"],
    queryFn: () => api.repos.getGithubSummary(id!),
    enabled: !!id,
    retry: false,
  });
}

export function useAddRepository() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repo: string) => api.repos.add(repo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

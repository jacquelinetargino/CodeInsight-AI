import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useAnalysisHistory(repositoryId: string | undefined) {
  return useQuery({
    queryKey: ["analysis", "history", repositoryId],
    queryFn: () => api.analysis.listForRepository(repositoryId!),
    enabled: !!repositoryId,
  });
}

export function useAnalysisDetail(analysisId: string | undefined) {
  return useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => api.analysis.get(analysisId!),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repositoryId: string) => api.analysis.create(repositoryId),
    onSuccess: (_data, repositoryId) => {
      queryClient.invalidateQueries({ queryKey: ["analysis", "history", repositoryId] });
    },
  });
}

export function useGenerateReadme(analysisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.analysis.generateReadme(analysisId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
    },
  });
}

export function useRequestFix(analysisId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      title: string;
      description: string;
      file_path: string | null;
      line: number | null;
    }) => api.analysis.requestFix(analysisId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis", analysisId] });
    },
  });
}

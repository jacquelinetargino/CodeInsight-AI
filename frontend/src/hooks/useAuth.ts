import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, ApiError } from "@/lib/api";
import { tokenStorage } from "@/lib/tokenStorage";
import { useAuthStore } from "@/store/authStore";

export function useAuth() {
  const { user, setUser, setLoading, isLoading } = useAuthStore();
  const queryClient = useQueryClient();

  const hasToken = !!tokenStorage.get();

  const query = useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.auth.me,
    retry: false,
    enabled: hasToken,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (!hasToken) {
      setLoading(false);
      return;
    }
    if (query.isSuccess) {
      setUser(query.data);
      setLoading(false);
    } else if (query.isError) {
      tokenStorage.clear();
      setUser(null);
      setLoading(false);
    }
  }, [hasToken, query.isSuccess, query.isError, query.data, setUser, setLoading]);

  async function login(email: string, password: string) {
    const { access_token, user: loggedInUser } = await api.auth.login({ email, password });
    tokenStorage.set(access_token);
    setUser(loggedInUser);
  }

  async function register(email: string, password: string, username: string) {
    const { access_token, user: newUser } = await api.auth.register({ email, password, username });
    tokenStorage.set(access_token);
    setUser(newUser);
  }

  async function logout() {
    try {
      await api.auth.logout();
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
    }
    tokenStorage.clear();
    setUser(null);
    queryClient.clear();
    window.location.href = "/login";
  }

  return {
    user,
    isLoading: isLoading || (hasToken && query.isLoading),
    isAuthenticated: !!user,
    login,
    register,
    logout,
  };
}

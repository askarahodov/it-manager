import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiFetch } from "./api";

export type CurrentUser = {
  email: string;
  role: "admin" | "operator" | "viewer" | "automation-only" | "user";
};

type AuthContextValue = {
  token: string | null;
  user: CurrentUser | null;
  status: "anonymous" | "loading" | "authenticated";
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const STORAGE_KEY = "it_manager_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY));
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>(token ? "loading" : "anonymous");

  const refresh = useCallback(async () => {
    if (!token) {
      setStatus("anonymous");
      setUser(null);
      return;
    }
    setStatus("loading");
    try {
      const me = await apiFetch<CurrentUser>("/api/v1/auth/me", { token });
      setUser(me);
      setStatus("authenticated");
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      setToken(null);
      setUser(null);
      setStatus("anonymous");
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      refresh().catch(() => undefined);
    }
  }, [token, refresh]);

  const login = useCallback(async (email: string, password: string) => {
    setStatus("loading");
    const response = await apiFetch<{ access_token: string }>("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem(STORAGE_KEY, response.access_token);
    setToken(response.access_token);

    const me = await apiFetch<CurrentUser>("/api/v1/auth/me", { token: response.access_token });
    setUser(me);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setToken(null);
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, status, login, logout, refresh }),
    [token, user, status, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth должен использоваться внутри AuthProvider");
  }
  return context;
}

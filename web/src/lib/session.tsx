"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";
import type { BrowserSession } from "./types";

type SessionState = { status: "loading" | "authenticated" | "unauthenticated" | "offline"; value: BrowserSession | null };
type SessionContextValue = SessionState & {
  refresh: () => Promise<void>;
  signIn: (credential: string) => Promise<BrowserSession>;
  signOut: () => Promise<void>;
  invalidate: () => void;
};
const Context = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading", value: null });
  const refresh = useCallback(async () => {
    try {
      const value = await api<BrowserSession>("/auth/session");
      setState({ status: "authenticated", value });
    } catch (error) {
      setState({ status: error instanceof ApiError && error.status === 401 ? "unauthenticated" : "offline", value: null });
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const signIn = useCallback(async (credential: string) => {
    const value = await api<BrowserSession>("/auth/session", { method: "POST", body: { credential } });
    setState({ status: "authenticated", value });
    return value;
  }, []);
  const signOut = useCallback(async () => {
    const token = state.value?.csrf_token;
    if (token) await api<void>("/auth/session", { method: "DELETE", csrf: token });
    setState({ status: "unauthenticated", value: null });
  }, [state.value?.csrf_token]);
  const invalidate = useCallback(() => setState({ status: "unauthenticated", value: null }), []);
  const context = useMemo(() => ({ ...state, refresh, signIn, signOut, invalidate }),
    [state, refresh, signIn, signOut, invalidate]);
  return <Context.Provider value={context}>{children}</Context.Provider>;
}

export function useSession() {
  const context = useContext(Context);
  if (!context) throw new Error("SessionProvider is missing");
  return context;
}

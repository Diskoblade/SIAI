// Reusable authentication layer.
//
// Exposes: user, isAuthenticated, loading, login(), logout(), refresh().
// On mount, if a token exists it is validated by calling /api/auth/me so the
// UI always reflects the CURRENT server-side account state (role/status).
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi } from "../services/auth.js";
import { clearToken, getToken, setToken } from "../services/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const hydrate = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.me();
      setUser(me);
    } catch {
      // Token invalid/expired or account no longer approved — force logout.
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const login = useCallback(async (email, password) => {
    const data = await authApi.login({ email, password });
    setToken(data.access_token);
    // Load the full profile (includes status) from /me for a consistent shape.
    const me = await authApi.me();
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Logout is best-effort; the client-side token removal is what matters.
    }
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      isAuthenticated: !!user,
      isAdmin: user?.role === "admin",
      login,
      logout,
      refresh: hydrate,
    }),
    [user, loading, login, logout, hydrate]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

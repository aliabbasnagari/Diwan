import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, setAuthToken } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [status, setStatus] = useState("checking"); // checking | authed | anon
  const [username, setUsername] = useState(null);

  const checkSession = useCallback(async () => {
    const token = localStorage.getItem("crate_token");
    if (!token) {
      setStatus("anon");
      return;
    }
    try {
      const me = await api.me();
      setUsername(me.username);
      setStatus("authed");
    } catch {
      setAuthToken(null);
      setStatus("anon");
    }
  }, []);

  useEffect(() => {
    checkSession();
    const onUnauthorized = () => {
      setAuthToken(null);
      setUsername(null);
      setStatus("anon");
    };
    window.addEventListener("crate:unauthorized", onUnauthorized);
    return () => window.removeEventListener("crate:unauthorized", onUnauthorized);
  }, [checkSession]);

  const login = useCallback(async (u, p) => {
    const res = await api.login(u, p);
    setAuthToken(res.token);
    setUsername(res.username);
    setStatus("authed");
    return res;
  }, []);

  const logout = useCallback(() => {
    api.logout().catch(() => {});
    setAuthToken(null);
    setUsername(null);
    setStatus("anon");
  }, []);

  return (
    <AuthContext.Provider value={{ status, username, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, formatApiError } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null); // null=checking, object=logged-in, false=logged-out
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        // Try /auth/me first. If the access token is expired/missing but the
        // refresh_token cookie is still valid, /auth/refresh will mint a new
        // access cookie and we retry /auth/me. Only after BOTH fail do we mark
        // the user as logged out. This is what fixes the "logout on page refresh"
        // bug on mobile Safari, where access-cookie eviction is more aggressive.
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch {
            try {
                await api.post("/auth/refresh");
                const { data } = await api.get("/auth/me");
                setUser(data);
            } catch {
                setUser(false);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const login = async (email, password) => {
        try {
            const { data } = await api.post("/auth/login", { email, password });
            setUser(data);
            return { ok: true };
        } catch (e) {
            return { ok: false, error: formatApiError(e.response?.data?.detail) || e.message };
        }
    };

    const register = async (payload) => {
        try {
            const { data } = await api.post("/auth/register", payload);
            setUser(data);
            return { ok: true };
        } catch (e) {
            return { ok: false, error: formatApiError(e.response?.data?.detail) || e.message };
        }
    };

    const logout = async () => {
        try {
            await api.post("/auth/logout");
        } catch {}
        setUser(false);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, setUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);

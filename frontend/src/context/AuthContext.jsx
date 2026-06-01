import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, formatApiError, saveTokens, clearTokens, getAccessToken } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null); // null=checking, object=logged-in, false=logged-out
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        // Try /auth/me first. If access token is missing/expired but a refresh
        // token is still valid (in localStorage or cookie), the global 401
        // interceptor in lib/api.js will silently refresh + retry. So /auth/me
        // will succeed on the retry. Only after the refresh itself fails do we
        // mark the user as logged out. This fixes the "logout on pull-to-refresh"
        // bug on mobile Safari, where access-cookie eviction is more aggressive.
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch {
            setUser(false);
            clearTokens();
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        // If we don't have any token yet and no cookie either, skip the call
        // (UX: avoid a flash of unauth state — refresh() handles it anyway).
        refresh();
    }, [refresh]);

    const login = async (email, password) => {
        try {
            const { data } = await api.post("/auth/login", { email, password });
            saveTokens(data); // <-- store Bearer tokens for mobile durability
            setUser(data);
            return { ok: true };
        } catch (e) {
            return { ok: false, error: formatApiError(e.response?.data?.detail) || e.message };
        }
    };

    const register = async (payload) => {
        try {
            const { data } = await api.post("/auth/register", payload);
            saveTokens(data);
            setUser(data);
            return { ok: true };
        } catch (e) {
            return { ok: false, error: formatApiError(e.response?.data?.detail) || e.message };
        }
    };

    const logout = async () => {
        try {
            await api.post("/auth/logout");
        } catch { /* ignore */ }
        clearTokens();
        setUser(false);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, setUser, hasToken: !!getAccessToken() }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);

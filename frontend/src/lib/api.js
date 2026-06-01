import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

// ---------- Token storage (mobile-safe Bearer fallback) ----------
// Cookies alone are unreliable on iOS Safari (ITP) — we ALSO persist tokens in
// localStorage and attach them as Authorization headers on every request. The
// server keeps setting cookies for desktop clients, so both paths work.
const ACCESS_KEY = "aop_at";
const REFRESH_KEY = "aop_rt";

export function saveTokens({ access_token, refresh_token }) {
    if (access_token) {
        try { localStorage.setItem(ACCESS_KEY, access_token); } catch { /* ignore */ }
    }
    if (refresh_token) {
        try { localStorage.setItem(REFRESH_KEY, refresh_token); } catch { /* ignore */ }
    }
}

export function clearTokens() {
    try { localStorage.removeItem(ACCESS_KEY); } catch { /* ignore */ }
    try { localStorage.removeItem(REFRESH_KEY); } catch { /* ignore */ }
}

export function getAccessToken() {
    try { return localStorage.getItem(ACCESS_KEY) || ""; } catch { return ""; }
}

export function getRefreshToken() {
    try { return localStorage.getItem(REFRESH_KEY) || ""; } catch { return ""; }
}

export const api = axios.create({
    baseURL: API,
    withCredentials: true,
});

// Attach Bearer header on every outbound request (in addition to cookies)
api.interceptors.request.use((config) => {
    const t = getAccessToken();
    if (t) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${t}`;
    }
    return config;
});

// Convert a relative storage URL like "/api/files/xyz" into an absolute URL
// that works regardless of whether REACT_APP_BACKEND_URL is the same origin as
// the page. Absolute http(s) URLs are returned unchanged. Empty/null values
// pass through. Use this anywhere you render an avatar / cover / image whose
// path may have been saved as a relative API URL.
export function mediaUrl(url) {
    if (!url) return url || "";
    if (/^(https?:|data:|blob:)/i.test(url)) return url;
    if (url.startsWith("/api/")) return `${BACKEND_URL}${url}`;
    if (url.startsWith("/")) return `${BACKEND_URL}${url}`;
    return url;
}

// ---------- Auto-refresh on 401 ----------
// When the access token cookie expires or gets evicted (common on mobile Safari
// due to ITP), the server returns 401. We transparently call /auth/refresh to
// mint a new access cookie + token, then replay the original request once. If
// the refresh itself fails (because the refresh cookie is also gone/expired) we
// surface the original 401 so AuthContext can flip the user to logged-out.
let refreshInFlight = null;

async function doRefresh() {
    const rt = getRefreshToken();
    // POST refresh — send the stored refresh token in the body so the
    // server doesn't depend on cookies which can be evicted on mobile.
    const { data } = await axios.post(`${API}/auth/refresh`, rt ? { refresh_token: rt } : {}, {
        withCredentials: true,
    });
    if (data?.access_token || data?.refresh_token) {
        saveTokens(data);
    }
    return data;
}

api.interceptors.response.use(
    (resp) => resp,
    async (error) => {
        const original = error.config;
        const status = error.response?.status;
        if (!original || status !== 401 || original._retried) {
            return Promise.reject(error);
        }
        // Don't recurse into auth endpoints themselves
        const url = original.url || "";
        if (url.includes("/auth/refresh") || url.includes("/auth/login")) {
            return Promise.reject(error);
        }
        original._retried = true;
        try {
            // De-duplicate concurrent refreshes
            if (!refreshInFlight) {
                refreshInFlight = doRefresh().finally(() => {
                    refreshInFlight = null;
                });
            }
            await refreshInFlight;
            return api(original);
        } catch (refreshErr) {
            return Promise.reject(error);
        }
    },
);

export function formatApiError(detail) {
    if (typeof detail === "string") return detail;
    if (!detail) return "Something went wrong";
    if (Array.isArray(detail)) return detail.map(formatApiError).join(", ");
    if (typeof detail === "object" && detail.msg) return detail.msg;
    return String(detail);
}

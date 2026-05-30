import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API,
    withCredentials: true,
});

// ---------- Auto-refresh on 401 ----------
// When the access token cookie expires or gets evicted (common on mobile Safari
// due to ITP), the server returns 401. We transparently call /auth/refresh to
// mint a new access cookie, then replay the original request once. If the
// refresh itself fails (because the refresh cookie is also gone/expired) we
// surface the original 401 so AuthContext can flip the user to logged-out.
let refreshInFlight = null;

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
                refreshInFlight = api.post("/auth/refresh").finally(() => {
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
    if (detail == null) return "Something went wrong. Please try again.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
        return detail
            .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
            .filter(Boolean)
            .join(" ");
    if (detail && typeof detail.msg === "string") return detail.msg;
    return String(detail);
}

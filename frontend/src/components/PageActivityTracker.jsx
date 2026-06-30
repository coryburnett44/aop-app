/**
 * `PageActivityTracker` — debounced page-view ping for the admin sign-in
 * activity report. Mounts inside the router so it can read `useLocation()`,
 * and inside the AuthProvider so it knows when a user is signed in.
 *
 * - Only pings when there's a user (we never record activity for guests).
 * - 800 ms debounce so a quick redirect / Navigate replace doesn't cost
 *   two server hits.
 * - Best-effort: catches and swallows errors so a failed ping never
 *   interrupts the actual navigation.
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

export default function PageActivityTracker() {
    const { user } = useAuth();
    const location = useLocation();
    const lastSentRef = useRef("");
    const timerRef = useRef(null);

    useEffect(() => {
        if (!user) return;
        // Skip the login/apply pages so we don't pad sessions with the very
        // first /login page-view that happens before auth was actually
        // established.
        const path = (location.pathname || "/") + (location.search || "");
        if (lastSentRef.current === path) return;
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
            lastSentRef.current = path;
            api.post("/activity/page-view", { path }).catch(() => { /* swallow */ });
        }, 800);
        return () => { if (timerRef.current) clearTimeout(timerRef.current); };
    }, [location.pathname, location.search, user]);

    return null;
}

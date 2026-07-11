import { createContext, useCallback, useContext, useEffect, useState } from "react";

/**
 * ThemeProvider — Iter 124.
 *
 * Four options:
 *   • "light"   — the default red/white/navy palette
 *   • "dark"    — navy-tinted dark palette (pre-existing .dark CSS class)
 *   • "mono"    — pure black/white high-contrast (a11y-friendly)
 *   • "system"  — follow the OS preference (light/dark only; mono is opt-in)
 *
 * Persisted in localStorage under "aop.theme". Applied by toggling
 * `.dark` and `.mono` classes on <html>. The `.mono` variant is defined
 * in index.css alongside `.dark`.
 */
const THEME_KEY = "aop.theme";
const VALID = new Set(["light", "dark", "mono", "system"]);

const ThemeContext = createContext({
    theme: "system",
    resolvedTheme: "light",
    setTheme: () => {},
});

function _systemPrefersDark() {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function _applyToDocument(resolved) {
    if (typeof document === "undefined") return;
    const html = document.documentElement;
    html.classList.remove("dark", "mono");
    if (resolved === "dark") html.classList.add("dark");
    else if (resolved === "mono") html.classList.add("mono");
    // Also expose the raw choice for CSS attribute selectors if we ever need it.
    html.setAttribute("data-theme", resolved);
}

export function ThemeProvider({ children }) {
    const [theme, setThemeState] = useState(() => {
        if (typeof window === "undefined") return "system";
        const stored = window.localStorage?.getItem(THEME_KEY);
        return VALID.has(stored) ? stored : "system";
    });
    const [resolvedTheme, setResolvedTheme] = useState(() =>
        theme === "system" ? (_systemPrefersDark() ? "dark" : "light") : theme
    );

    // Effect: whenever `theme` changes, resolve to a concrete theme and paint
    // the document. When `theme === "system"`, also subscribe to the OS
    // preference so a change in dark-mode setting is picked up live.
    useEffect(() => {
        function resolve() {
            const next = theme === "system"
                ? (_systemPrefersDark() ? "dark" : "light")
                : theme;
            setResolvedTheme(next);
            _applyToDocument(next);
        }
        resolve();
        if (theme !== "system") return undefined;
        const mq = window.matchMedia("(prefers-color-scheme: dark)");
        // Older Safari uses `addListener`, modern uses `addEventListener`.
        const handler = () => resolve();
        if (mq.addEventListener) mq.addEventListener("change", handler);
        else mq.addListener?.(handler);
        return () => {
            if (mq.removeEventListener) mq.removeEventListener("change", handler);
            else mq.removeListener?.(handler);
        };
    }, [theme]);

    const setTheme = useCallback((next) => {
        const t = VALID.has(next) ? next : "system";
        setThemeState(t);
        try { window.localStorage?.setItem(THEME_KEY, t); } catch (_) { /* ignore */ }
    }, []);

    return (
        <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme() {
    return useContext(ThemeContext);
}

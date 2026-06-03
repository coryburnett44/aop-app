import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";

const SiteSettingsContext = createContext({
    settings: null,
    refresh: () => {},
});

export function SiteSettingsProvider({ children }) {
    const [settings, setSettings] = useState(null);

    const refresh = useCallback(async () => {
        try {
            const { data } = await api.get("/site-settings");
            setSettings(data);
        } catch {
            // Public endpoint — failures shouldn't break the app, fall back to baked-in defaults.
            setSettings(null);
        }
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    return (
        <SiteSettingsContext.Provider value={{ settings, refresh }}>
            {children}
        </SiteSettingsContext.Provider>
    );
}

export function useSiteSettings() {
    return useContext(SiteSettingsContext);
}

// Helper: returns the configured override OR the provided default.
export function usePageTitle(slug, fallback) {
    const { settings } = useSiteSettings();
    return settings?.page_titles?.[slug] || fallback;
}

export function useNavLabel(slug, fallback) {
    const { settings } = useSiteSettings();
    return settings?.nav_labels?.[slug] || fallback;
}

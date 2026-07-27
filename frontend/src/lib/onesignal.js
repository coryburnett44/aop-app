/**
 * OneSignal Web SDK integration hook.
 *
 * Initializes OneSignal exactly once (guarded via window flag so React
 * StrictMode's double-mount + hot reloads don't blow up), then keeps the
 * logged-in user's `external_id` in sync with our Mongo `user.id`. The
 * subscription id is POSTed to `/api/push/subscription` so the backend
 * knows who is reachable.
 *
 * Runs only when `REACT_APP_ONESIGNAL_APP_ID` is set — silently no-ops
 * otherwise so preview/dev keeps working.
 */
import { useEffect } from "react";
import OneSignal from "react-onesignal";
import { api } from "./api";

const APP_ID = process.env.REACT_APP_ONESIGNAL_APP_ID || "";

async function ensureInitialized() {
    if (!APP_ID) return false;
    if (typeof window === "undefined") return false;
    if (window.__aopOneSignalReady) return true;
    if (window.__aopOneSignalInitializing) {
        // Another mount is already awaiting init — wait for it.
        for (let i = 0; i < 30 && !window.__aopOneSignalReady; i++) {
            // eslint-disable-next-line no-await-in-loop
            await new Promise((r) => setTimeout(r, 100));
        }
        return !!window.__aopOneSignalReady;
    }
    window.__aopOneSignalInitializing = true;
    try {
        await OneSignal.init({
            appId: APP_ID,
            allowLocalhostAsSecureOrigin: true,
            serviceWorkerPath: "OneSignalSDKWorker.js",
            serviceWorkerParam: { scope: "/" },
            notifyButton: { enable: false }, // we render our own prompt UI
        });
        window.__aopOneSignalReady = true;
        return true;
    } catch (e) {
        // Bad domain, HTTP page, or unsupported browser — non-fatal.
        console.warn("[OneSignal] init failed:", e);
        return false;
    } finally {
        window.__aopOneSignalInitializing = false;
    }
}

async function pushSubscriptionSnapshot() {
    try {
        const subId = OneSignal?.User?.PushSubscription?.id || "";
        const optedIn = !!OneSignal?.User?.PushSubscription?.optedIn;
        await api.post("/push/subscription", { subscription_id: subId, opted_in: optedIn });
    } catch {
        // Non-fatal — subscription tracking is best-effort.
    }
}

/**
 * Call once on any page that has an authenticated user. Pass `user` from
 * your auth context so we can login/logout the OneSignal external_id.
 */
export function useOneSignal(user) {
    useEffect(() => {
        let cancelled = false;
        (async () => {
            const ok = await ensureInitialized();
            if (cancelled || !ok) return;
            try {
                if (user?.id) {
                    await OneSignal.login(user.id);
                } else if (OneSignal?.logout) {
                    await OneSignal.logout();
                }
                // Keep the backend snapshot fresh so admins targeting by
                // opted_in members see accurate counts.
                await pushSubscriptionSnapshot();
                // Re-emit whenever the browser flips permission state.
                if (OneSignal?.User?.PushSubscription?.addEventListener) {
                    OneSignal.User.PushSubscription.addEventListener("change", () => {
                        pushSubscriptionSnapshot();
                    });
                }
            } catch (e) {
                console.warn("[OneSignal] identity sync failed:", e);
            }
        })();
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?.id]);
}

/** Trigger the browser's native push permission prompt. */
export async function requestPushPermission() {
    const ok = await ensureInitialized();
    if (!ok) return { ok: false, reason: "onesignal_unavailable" };
    try {
        await OneSignal.Notifications.requestPermission();
        await pushSubscriptionSnapshot();
        return { ok: true, permission: OneSignal.Notifications.permission };
    } catch (e) {
        return { ok: false, reason: String(e?.message || e) };
    }
}

/** Opt out from within our app without opening browser settings. */
export async function optOutOfPush() {
    const ok = await ensureInitialized();
    if (!ok) return { ok: false };
    try {
        await OneSignal.User.PushSubscription.optOut();
        await pushSubscriptionSnapshot();
        return { ok: true };
    } catch (e) {
        return { ok: false, reason: String(e?.message || e) };
    }
}

export async function optInToPush() {
    const ok = await ensureInitialized();
    if (!ok) return { ok: false };
    try {
        await OneSignal.User.PushSubscription.optIn();
        await pushSubscriptionSnapshot();
        return { ok: true };
    } catch (e) {
        return { ok: false, reason: String(e?.message || e) };
    }
}

/** Read the current permission + subscription state (no side effects). */
export async function readPushState() {
    const ok = await ensureInitialized();
    if (!ok) return { available: false };
    try {
        return {
            available: true,
            permission: OneSignal.Notifications?.permission || "default",
            opted_in: !!OneSignal.User.PushSubscription?.optedIn,
            subscription_id: OneSignal.User.PushSubscription?.id || "",
        };
    } catch {
        return { available: false };
    }
}

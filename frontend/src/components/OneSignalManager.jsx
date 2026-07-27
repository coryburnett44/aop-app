/**
 * Mounts once (from App.js) and keeps OneSignal identity in sync with the
 * currently-authenticated user. No UI — the actual "Enable notifications"
 * prompt lives on the Profile page so users control it explicitly.
 */
import { useAuth } from "../context/AuthContext";
import { useOneSignal } from "../lib/onesignal";

export default function OneSignalManager() {
    const { user } = useAuth();
    useOneSignal(user);
    return null;
}

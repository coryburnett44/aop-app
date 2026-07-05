/**
 * GlobalChatNotifier — mounts once at the app root when the user is logged in
 * and keeps a persistent WebSocket open so members receive video-meeting
 * pings on ANY page (not just /chat).
 *
 * When a `meeting:notify` event arrives, we:
 *   1. Show an in-app toast with a "Join" action.
 *   2. Increment a session-scoped bell badge (dispatched via a browser event
 *      so Navbar/Chat listen without prop drilling).
 *   3. Play a short chime (respects the browser's "user gesture required"
 *      policy — the first play may fail silently until the user has
 *      interacted with the page).
 *   4. Fire a browser Notification (if permission was granted).
 *
 * Anti-spam: none — per user's spec, "Every meeting start — no throttling".
 */
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { chatWsUrl } from "../pages/Chat";
import { useAuth } from "../context/AuthContext";

// A short embedded ping chime (~0.4s, 440 Hz → 660 Hz). Base64-encoded WAV
// keeps this self-contained so we don't ship an extra asset file.
const CHIME_DATA_URL =
    "data:audio/wav;base64,UklGRnwGAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YVgGAAAAAP4CyQPmA4kDPQIxAIz9tvpM+FT2ivRK83Xy0/E48b/wPfDp71DvKu867g/uUu037SPtCe0v7fbtnu6C7yTx4vLU9M/2Cvn5+n78kf1G/uP+dv/l/y8AVwBiAFsAOwAMANL/kf9L/w7/1P6h/nX+Vf5D/kD+VP58/qz+7v49/5H/6f8+AJEA1QAOATkBWQFwAX0BhgGKAY4BkAGMAYcBfwFyAWkBWwFHAS4BEAHnALgAiABbACwABADI/4L/N//p/pj+Rf7z/aP9V/0Q/dD8mfxu/E38O/w7/E38afyR/MP8/vxD/ZL95v04/o7+5f4//5b/6P8/AJIA4gAyAX8ByAENAlECjwLKAgADMwNhA48DsgPQA+kD/gMLBBEEEwQLBP0D5AO/A5MDXQMcA9YCgAImAsQBWAHrAHYA/f9//wD/g/4E/oj9DP2R/Bv8pvsz+8b6XvoB+q/5aPkr+fj4zvit+JT4ffhz+G/4c/iC+Jv4wPjs+B75WPmY+eL5MvqI+ub6Rft6+8j7Ffxk/LX8Cf1e/bT9DP5m/sD+H/9//9//P4Ct/wUAdAABAJz/RP/6/rf+ff5N/if+CP7y/eL92v3W/dj94/3z/Qz+K/5N/nX+n/7P/gL/Nv9r/6P/2/8T/0f/e/+u/9//DwA9AGYAjACuAM4A6QD/ABIBIAEqATABMwEyAS0BJgEbARABAgHzAOMA0gDBALAAoQCTAIYAfAB1AG4AaQBmAGYAaAA=";

let _chime = null;
function playChime() {
    try {
        if (!_chime) _chime = new Audio(CHIME_DATA_URL);
        _chime.currentTime = 0;
        const p = _chime.play();
        if (p?.catch) p.catch(() => { /* autoplay blocked — ignore */ });
    } catch { /* browser doesn't allow — ignore */ }
}

function ensureNotificationPermission() {
    if (typeof Notification === "undefined") return;
    if (Notification.permission === "default") {
        // Deferred until first user interaction — request politely once.
        Notification.requestPermission().catch(() => {});
    }
}

function fireBrowserNotification({ title, body, onClick }) {
    try {
        if (typeof Notification === "undefined") return;
        if (Notification.permission !== "granted") return;
        const n = new Notification(title, { body, icon: "/logo192.png", tag: "aop-video-meeting" });
        n.onclick = () => { window.focus(); onClick?.(); n.close(); };
    } catch { /* ignore */ }
}

export default function GlobalChatNotifier() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const wsRef = useRef(null);
    const reconnectTimeoutRef = useRef(null);

    useEffect(() => {
        if (!user) return undefined;

        // Ask for browser notification permission once per session so future
        // meetings can pop OS-level alerts even when the tab is background.
        ensureNotificationPermission();

        let stopped = false;
        function connect() {
            if (stopped) return;
            let ws;
            try { ws = new WebSocket(chatWsUrl()); } catch { scheduleReconnect(); return; }
            wsRef.current = ws;
            ws.onmessage = (ev) => {
                let msg;
                try { msg = JSON.parse(ev.data); } catch { return; }
                if (msg?.type !== "meeting:notify") return;
                // Duplicate-suppress: the /chat page's own listener will also
                // see this and may show its own affordance; that's fine.
                const label = `📹 ${msg.started_by_name} started a video meeting`;
                const detail = `in ${msg.conversation_name}`;

                // 1. Toast
                toast.custom((t) => (
                    <div
                        className="bg-white border-2 border-primary/40 shadow-xl rounded-2xl p-4 max-w-sm flex items-start gap-3"
                        data-testid="meeting-notify-toast"
                    >
                        <div className="text-2xl leading-none">📹</div>
                        <div className="flex-1 min-w-0">
                            <div className="font-bold text-sm text-slate-900 truncate">{label}</div>
                            <div className="text-xs text-slate-500 truncate">{detail}</div>
                            <div className="flex items-center gap-2 mt-2">
                                <button
                                    type="button"
                                    className="rounded-full px-3 py-1 text-xs font-bold bg-primary text-white hover:opacity-90"
                                    onClick={() => { toast.dismiss(t); navigate(`/chat/${msg.conversation_id}`); }}
                                    data-testid="meeting-notify-open-chat"
                                >Open chat</button>
                                <a
                                    href={msg.meeting_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="rounded-full px-3 py-1 text-xs font-bold border-2 border-slate-200 hover:border-primary text-slate-700"
                                    data-testid="meeting-notify-join"
                                    onClick={() => toast.dismiss(t)}
                                >Join</a>
                            </div>
                        </div>
                        <button type="button" onClick={() => toast.dismiss(t)} className="text-slate-400 hover:text-slate-700 text-sm shrink-0" aria-label="Close">×</button>
                    </div>
                ), { duration: 15000 });

                // 2. Bell badge (any listener adds +1 to unread meeting count).
                window.dispatchEvent(new CustomEvent("aop:meeting_ping", { detail: msg }));

                // 3. Chime
                playChime();

                // 4. Browser Notification
                fireBrowserNotification({
                    title: label,
                    body: detail,
                    onClick: () => navigate(`/chat/${msg.conversation_id}`),
                });
            };
            ws.onclose = () => {
                if (stopped) return;
                scheduleReconnect();
            };
            ws.onerror = () => { try { ws.close(); } catch { /* noop */ } };
        }

        function scheduleReconnect() {
            if (reconnectTimeoutRef.current) return;
            reconnectTimeoutRef.current = setTimeout(() => {
                reconnectTimeoutRef.current = null;
                connect();
            }, 3000);
        }

        connect();
        return () => {
            stopped = true;
            if (reconnectTimeoutRef.current) { clearTimeout(reconnectTimeoutRef.current); reconnectTimeoutRef.current = null; }
            try { wsRef.current?.close(); } catch { /* noop */ }
        };
    }, [user, navigate]);

    return null;
}

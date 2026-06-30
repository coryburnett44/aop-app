/**
 * Admin view: sign-in activity log.
 *
 * Lists recent sessions (most recent first) with: who, when they logged in,
 * how long they stayed, IP, browser, and how many pages they hit. Click a
 * row to expand and see the actual list of pages with timestamps.
 *
 * Wired to `GET /api/admin/login-activity` (list, no pages_visited payload
 * to keep the response small) and `GET /api/admin/login-activity/{id}`
 * (single row, full pages_visited).
 *
 * Only registered in Admin.jsx when `perms.admin_role === "full"` so
 * chapter-scoped or sub-role admins don't see this tab.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { fmtET } from "../lib/eventTime";
import { ChevronDown, ChevronRight, Search, RefreshCw, Activity } from "lucide-react";

function fmtDuration(seconds) {
    if (seconds == null) return "—";
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    if (m < 60) return `${m}m ${seconds % 60}s`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
}

function shortUA(ua) {
    if (!ua) return "—";
    // Distill verbose user-agents to a friendly short label.
    const u = ua.toLowerCase();
    if (u.includes("iphone")) return "iPhone Safari";
    if (u.includes("ipad")) return "iPad Safari";
    if (u.includes("android")) return "Android";
    if (u.includes("chrome")) return "Chrome";
    if (u.includes("firefox")) return "Firefox";
    if (u.includes("safari")) return "Safari";
    if (u.includes("edg/")) return "Edge";
    if (u.startsWith("curl/")) return "curl";
    return ua.slice(0, 32) + (ua.length > 32 ? "…" : "");
}

export default function SignInActivityAdmin() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(false);
    const [q, setQ] = useState("");
    const [expanded, setExpanded] = useState({}); // session_id -> full doc

    async function load() {
        setLoading(true);
        try {
            const { data } = await api.get("/admin/login-activity?limit=300");
            setRows(data || []);
        } catch { setRows([]); }
        setLoading(false);
    }
    useEffect(() => { load(); }, []);

    async function toggleExpand(row) {
        if (expanded[row.id]) {
            const next = { ...expanded };
            delete next[row.id];
            setExpanded(next);
            return;
        }
        try {
            const { data } = await api.get(`/admin/login-activity/${row.id}`);
            setExpanded({ ...expanded, [row.id]: data });
        } catch { /* ignore */ }
    }

    const filtered = useMemo(() => {
        const needle = q.trim().toLowerCase();
        if (!needle) return rows;
        return rows.filter((r) =>
            (r.user_name || "").toLowerCase().includes(needle) ||
            (r.user_email || "").toLowerCase().includes(needle) ||
            (r.ip || "").toLowerCase().includes(needle)
        );
    }, [rows, q]);

    return (
        <div className="space-y-4" data-testid="signin-activity-admin">
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <h2 className="font-heading text-2xl font-bold flex items-center gap-2">
                        <Activity className="h-6 w-6 text-primary" /> Sign-in activity
                    </h2>
                    <p className="text-sm text-muted-foreground">Recent member sign-ins — when they logged in, how long they stayed, and which pages they viewed.</p>
                </div>
                <Button
                    onClick={load}
                    disabled={loading}
                    variant="outline"
                    className="rounded-full"
                    data-testid="signin-activity-refresh"
                >
                    <RefreshCw className={`h-4 w-4 mr-1.5 ${loading ? "animate-spin" : ""}`} /> Refresh
                </Button>
            </div>

            <div className="relative max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Filter by name, email, or IP…"
                    className="rounded-full pl-9"
                    data-testid="signin-activity-search"
                />
            </div>

            <div className="border rounded-2xl overflow-hidden bg-card">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="text-left px-3 py-2 w-8"></th>
                                <th className="text-left px-3 py-2">Member</th>
                                <th className="text-left px-3 py-2">Login (ET)</th>
                                <th className="text-left px-3 py-2">Duration</th>
                                <th className="text-left px-3 py-2">Pages</th>
                                <th className="text-left px-3 py-2">IP</th>
                                <th className="text-left px-3 py-2">Browser</th>
                                <th className="text-left px-3 py-2">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 && !loading && (
                                <tr><td colSpan={8} className="text-center text-muted-foreground py-8">No sessions recorded yet.</td></tr>
                            )}
                            {filtered.map((r) => {
                                const isOpen = !!expanded[r.id];
                                return (
                                    <>
                                        <tr
                                            key={r.id}
                                            className="border-t hover:bg-muted/30 cursor-pointer"
                                            onClick={() => toggleExpand(r)}
                                            data-testid={`signin-row-${r.id}`}
                                        >
                                            <td className="px-3 py-2">
                                                {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                                            </td>
                                            <td className="px-3 py-2">
                                                <div className="font-semibold">{r.user_name || <em className="text-muted-foreground">unknown</em>}</div>
                                                <div className="text-xs text-muted-foreground">{r.user_email}</div>
                                            </td>
                                            <td className="px-3 py-2 whitespace-nowrap">{fmtET(r.login_at, "MMM d, yyyy · h:mm a zzz")}</td>
                                            <td className="px-3 py-2 whitespace-nowrap" data-testid={`signin-duration-${r.id}`}>{fmtDuration(r.duration_seconds)}</td>
                                            <td className="px-3 py-2">{r.pages_count}</td>
                                            <td className="px-3 py-2 font-mono text-xs">{r.ip || "—"}</td>
                                            <td className="px-3 py-2 text-xs">{shortUA(r.user_agent)}</td>
                                            <td className="px-3 py-2">
                                                {r.logout_at
                                                    ? <span className="text-[10px] uppercase tracking-wider bg-muted text-muted-foreground rounded-full px-2 py-0.5 font-semibold">Signed out</span>
                                                    : <span className="text-[10px] uppercase tracking-wider bg-primary/15 text-primary rounded-full px-2 py-0.5 font-semibold">Active</span>}
                                            </td>
                                        </tr>
                                        {isOpen && (
                                            <tr key={r.id + "-detail"} className="border-t bg-muted/10">
                                                <td colSpan={8} className="px-6 py-4">
                                                    <PagesVisited rowId={r.id} detail={expanded[r.id]} />
                                                </td>
                                            </tr>
                                        )}
                                    </>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function PagesVisited({ rowId, detail }) {
    if (!detail) {
        return <div className="text-sm text-muted-foreground">Loading session details…</div>;
    }
    const pages = detail.pages_visited || [];
    if (pages.length === 0) {
        return <div className="text-sm text-muted-foreground">No page views recorded for this session.</div>;
    }
    return (
        <div className="space-y-2" data-testid={`signin-pages-${rowId}`}>
            <div className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">
                Pages visited ({pages.length})
            </div>
            <ol className="space-y-1 text-sm">
                {pages.map((p, i) => (
                    <li key={i} className="flex items-baseline justify-between gap-4 border-b border-dashed border-muted py-1">
                        <span className="font-mono text-xs sm:text-sm">{p.path}</span>
                        <span className="text-xs text-muted-foreground whitespace-nowrap">{fmtET(p.at, "MMM d · h:mm:ss a zzz")}</span>
                    </li>
                ))}
            </ol>
        </div>
    );
}

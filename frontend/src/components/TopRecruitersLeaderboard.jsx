import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { UserPlus, Users } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";
const GOLD = "#F9D466";

/**
 * Home-page widget: top 5 chapters + top 5 recruiters by recruitment count
 * for the selected period. Mirrors TopDonorsLeaderboard so all three
 * homepage leaderboards feel like a coordinated family.
 */
export default function TopRecruitersLeaderboard() {
    const [data, setData] = useState(null);
    const [tab, setTab] = useState("chapters");
    const [period, setPeriod] = useState(() => `q${Math.floor(new Date().getMonth() / 3) + 1}`);
    const currentYear = new Date().getFullYear();

    useEffect(() => {
        (async () => {
            try {
                const { data: d } = await api.get(`/leaderboards/top-recruiters?period=${period}`);
                setData(d);
            } catch {
                setData({ top_chapters: [], top_members: [], period_label: "This Quarter" });
            }
        })();
    }, [period]);

    if (!data) {
        return <section className="py-12 max-w-6xl mx-auto px-6 lg:px-10"><div className="h-64 bg-muted rounded-2xl animate-pulse" /></section>;
    }

    return (
        <section className="py-14" data-testid="home-top-recruiters">
            <div className="max-w-6xl mx-auto px-6 lg:px-10">
                <div className="text-center mb-8">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>{data.period_label || "This Quarter"}</div>
                    <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight flex items-center justify-center gap-3" style={{ color: NAVY }}>
                        <UserPlus className="h-7 w-7 sm:h-9 sm:w-9" style={{ color: GOLD }} />
                        Top Recruiters Leader Board
                    </h2>
                    <p className="text-sm sm:text-base text-slate-600 mt-2">Members who brought new brothers &amp; sisters home this {data.period_label ? data.period_label.split(" ")[0].toLowerCase() : "quarter"}.</p>
                </div>

                {/* Period switcher — Q1..Q4 + full year (no "all time" per org policy). */}
                <div className="flex justify-center mb-4" data-testid="top-recruiters-period-switcher">
                    <div className="inline-flex bg-white/70 border border-slate-200 rounded-full p-1 flex-wrap gap-1">
                        {["q1", "q2", "q3", "q4", "year"].map((p) => {
                            const label = p === "year" ? String(currentYear) : p.toUpperCase();
                            const active = period === p;
                            return (
                                <button
                                    key={p}
                                    type="button"
                                    onClick={() => setPeriod(p)}
                                    className={`rounded-full px-3 sm:px-4 py-1.5 text-xs sm:text-sm font-bold transition-colors ${active ? "bg-primary text-white shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                                    data-testid={`top-recruiters-period-${p}`}
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div className="flex justify-center mb-6">
                    <div className="inline-flex bg-white rounded-full p-1 border-2 border-slate-200">
                        <button
                            type="button"
                            onClick={() => setTab("chapters")}
                            className={`rounded-full px-5 py-2 text-sm font-bold transition-colors ${tab === "chapters" ? "bg-slate-100 text-foreground shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="top-recruiters-tab-chapters"
                        >
                            Top Chapters
                        </button>
                        <button
                            type="button"
                            onClick={() => setTab("members")}
                            className={`rounded-full px-5 py-2 text-sm font-bold transition-colors ${tab === "members" ? "bg-slate-100 text-foreground shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="top-recruiters-tab-members"
                        >
                            Top Recruiters
                        </button>
                    </div>
                </div>

                {tab === "chapters" ? (
                    <div className="space-y-2 max-w-2xl mx-auto" data-testid="top-recruiters-chapters-list">
                        {data.top_chapters.length === 0 ? (
                            <EmptyState text={`No recruitment activity recorded for ${data.period_label} yet.`} />
                        ) : data.top_chapters.map((c, idx) => (
                            <Row
                                key={c.chapter_id || `unassigned-${idx}`}
                                rank={idx + 1}
                                title={c.chapter_name}
                                subtitle={`${c.member_count || 0} active member${c.member_count !== 1 ? "s" : ""} · ${c.recruiter_count} recruiter${c.recruiter_count !== 1 ? "s" : ""}`}
                                count={c.count}
                                avatar={c.logo_url}
                                icon={<Users className="h-5 w-5" />}
                                testid={`top-recruiters-chapter-${c.chapter_id || "unassigned"}`}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="space-y-2 max-w-2xl mx-auto" data-testid="top-recruiters-members-list">
                        {data.top_members.length === 0 ? (
                            <EmptyState text={`No individual recruitments recorded for ${data.period_label} yet.`} />
                        ) : data.top_members.map((m, idx) => (
                            <Row
                                key={m.user_id}
                                rank={idx + 1}
                                title={m.user_name}
                                subtitle={`${m.chapter_name || "Unassigned"}`}
                                count={m.count}
                                avatar={m.avatar_url}
                                testid={`top-recruiters-member-${m.user_id}`}
                            />
                        ))}
                    </div>
                )}
            </div>
        </section>
    );
}

function rankColor(rank) {
    if (rank === 1) return GOLD;
    if (rank === 2) return "#C0C0C0";
    if (rank === 3) return "#CD7F32";
    return "#94a3b8";
}

function Row({ rank, title, subtitle, count, icon, avatar, testid }) {
    return (
        <div
            className="flex items-center gap-3 sm:gap-4 bg-white border-2 border-slate-200 rounded-2xl p-3 sm:p-4 transition-all hover:border-slate-300 hover:shadow-sm"
            data-testid={testid}
        >
            <div
                className="w-10 h-10 sm:w-12 sm:h-12 rounded-full grid place-items-center font-heading font-black text-base sm:text-lg shrink-0"
                style={{ backgroundColor: rankColor(rank), color: rank <= 3 ? "#fff" : "#0f172a" }}
            >
                {rank}
            </div>

            {avatar ? (
                <img src={mediaUrl(avatar)} alt="" className="w-9 h-9 sm:w-11 sm:h-11 rounded-full object-contain bg-slate-100 shrink-0" onError={(e) => { e.currentTarget.style.display = "none"; }} />
            ) : icon ? (
                <div className="w-9 h-9 sm:w-11 sm:h-11 rounded-full grid place-items-center shrink-0" style={{ backgroundColor: NAVY, color: "#fff" }}>{icon}</div>
            ) : null}

            <div className="flex-1 min-w-0">
                <div className="font-heading font-bold truncate text-base sm:text-lg" style={{ color: NAVY }}>{title}</div>
                <div className="text-xs sm:text-sm text-slate-500 truncate">{subtitle}</div>
            </div>

            <div className="text-right shrink-0">
                <div className="font-heading font-black text-xl sm:text-2xl" style={{ color: RED }}>{count}</div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 flex items-center gap-1 justify-end">
                    <UserPlus className="h-3 w-3" />recruited
                </div>
            </div>
        </div>
    );
}

function EmptyState({ text }) {
    return <div className="text-center py-12 text-sm text-slate-500 border-2 border-dashed border-slate-300 rounded-2xl">{text}</div>;
}

import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { Trophy, Clock, Users } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";
const GOLD = "#F9D466";

/**
 * Home-page widget: top 5 chapters + top 5 members by approved volunteer hours
 * for the current quarter.
 */
export default function CommunityServiceLeaderboard() {
    const [data, setData] = useState(null);
    const [tab, setTab] = useState("chapters"); // chapters | members

    useEffect(() => {
        // Try the current quarter first. If it comes back empty (fresh org or
        // a new quarter that hasn't accumulated hours yet), silently retry
        // with `period=all` so returning visitors always see the leaderboard
        // populated with the org's historical top performers instead of an
        // empty widget.
        (async () => {
            try {
                const { data: q } = await api.get("/leaderboards/community-service?period=quarter");
                if ((q.top_chapters?.length || 0) + (q.top_members?.length || 0) > 0) {
                    setData(q);
                    return;
                }
                const { data: allTime } = await api.get("/leaderboards/community-service?period=all");
                setData({ ...allTime, period_label: allTime.period_label || "All time" });
            } catch {
                setData({ top_chapters: [], top_members: [], period_label: "This Quarter" });
            }
        })();
    }, []);

    if (!data) {
        return <section className="py-12 max-w-6xl mx-auto px-6 lg:px-10"><div className="h-64 bg-muted rounded-2xl animate-pulse" /></section>;
    }
    // NOTE: we deliberately keep the section mounted even when both lists are
    // empty. Previously we returned null here, but that silently removed the
    // entire leaderboard heading + tabs, which the user perceived as "the
    // leaderboard is missing." The EmptyState below is a much clearer signal.

    return (
        <section className="py-14 bg-white" data-testid="home-leaderboard">
            <div className="max-w-6xl mx-auto px-6 lg:px-10">
                <div className="text-center mb-8">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>{data.period_label || "This Quarter"}</div>
                    <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight flex items-center justify-center gap-3" style={{ color: NAVY }}>
                        <Trophy className="h-7 w-7 sm:h-9 sm:w-9" style={{ color: GOLD }} />
                        Community Service Leader Board
                    </h2>
                    <p className="text-sm sm:text-base text-slate-600 mt-2">{data.period_label === "All time" ? "All-time top performers by approved volunteer hours." : "Top performers this quarter — approved volunteer hours."}</p>
                </div>

                {/* Tab toggle */}
                <div className="flex justify-center mb-6">
                    <div className="inline-flex bg-muted rounded-full p-1">
                        <button
                            type="button"
                            onClick={() => setTab("chapters")}
                            className={`rounded-full px-5 py-2 text-sm font-bold transition-colors ${tab === "chapters" ? "bg-white shadow-warm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="leaderboard-tab-chapters"
                        >
                            Top Chapters
                        </button>
                        <button
                            type="button"
                            onClick={() => setTab("members")}
                            className={`rounded-full px-5 py-2 text-sm font-bold transition-colors ${tab === "members" ? "bg-white shadow-warm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="leaderboard-tab-members"
                        >
                            Top Members
                        </button>
                    </div>
                </div>

                {/* Top 5 list */}
                {tab === "chapters" ? (
                    <div className="space-y-2 max-w-2xl mx-auto" data-testid="leaderboard-chapters-list">
                        {data.top_chapters.length === 0 ? (
                            <EmptyState text="No chapter activity this quarter yet." />
                        ) : data.top_chapters.map((c, idx) => (
                            <LeaderRow
                                key={c.chapter_id || `unassigned-${idx}`}
                                rank={idx + 1}
                                title={c.chapter_name}
                                subtitle={`${c.member_count} active member${c.member_count !== 1 ? "s" : ""} · ${c.count} entr${c.count !== 1 ? "ies" : "y"}`}
                                hours={c.hours}
                                avatar={c.logo_url}
                                icon={<Users className="h-5 w-5" />}
                                testid={`leaderboard-chapter-${c.chapter_id || "unassigned"}`}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="space-y-2 max-w-2xl mx-auto" data-testid="leaderboard-members-list">
                        {data.top_members.length === 0 ? (
                            <EmptyState text="No individual activity this quarter yet." />
                        ) : data.top_members.map((m, idx) => (
                            <LeaderRow
                                key={m.user_id}
                                rank={idx + 1}
                                title={m.user_name}
                                subtitle={`${m.chapter_name || "Unassigned"} · ${m.count} entr${m.count !== 1 ? "ies" : "y"}`}
                                hours={m.hours}
                                avatar={m.avatar_url}
                                testid={`leaderboard-member-${m.user_id}`}
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

function LeaderRow({ rank, title, subtitle, hours, icon, avatar, testid }) {
    return (
        <div
            className="flex items-center gap-3 sm:gap-4 bg-white border-2 border-slate-200 rounded-2xl p-3 sm:p-4 transition-all hover:border-slate-300 hover:shadow-sm"
            data-testid={testid}
        >
            {/* Rank badge */}
            <div
                className="w-10 h-10 sm:w-12 sm:h-12 rounded-full grid place-items-center font-heading font-black text-base sm:text-lg shrink-0"
                style={{ backgroundColor: rankColor(rank), color: rank <= 3 ? "#fff" : "#0f172a" }}
            >
                {rank}
            </div>

            {/* Avatar / Icon */}
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
                <div className="font-heading font-black text-xl sm:text-2xl" style={{ color: RED }}>{hours.toFixed(1)}<span className="text-xs ml-0.5">h</span></div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 flex items-center gap-1 justify-end">
                    <Clock className="h-3 w-3" />approved
                </div>
            </div>
        </div>
    );
}

function EmptyState({ text }) {
    return <div className="text-center py-12 text-sm text-slate-500 border-2 border-dashed border-slate-300 rounded-2xl">{text}</div>;
}

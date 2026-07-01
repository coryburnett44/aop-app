import { useEffect, useState } from "react";
import { api, mediaUrl } from "../lib/api";
import { HeartHandshake, DollarSign, Users } from "lucide-react";

const NAVY = "#0A2463";
const RED = "#C8102E";
const GOLD = "#F9D466";

/**
 * Home-page widget: top 5 chapters + top 5 members by completed donation $
 * for the current quarter. Mirrors CommunityServiceLeaderboard's layout so
 * the two leaderboards feel like a coordinated pair on the home page.
 */
export default function TopDonorsLeaderboard() {
    const [data, setData] = useState(null);
    const [tab, setTab] = useState("chapters");

    useEffect(() => {
        // Same fallback strategy as CommunityServiceLeaderboard — if the
        // current quarter has no donations yet, roll up to all-time so
        // fresh orgs and the very start of each quarter still show
        // meaningful data instead of a hidden section.
        (async () => {
            try {
                const { data: q } = await api.get("/leaderboards/top-donors?period=quarter");
                if ((q.top_chapters?.length || 0) + (q.top_members?.length || 0) > 0) {
                    setData(q);
                    return;
                }
                const { data: allTime } = await api.get("/leaderboards/top-donors?period=all");
                setData({ ...allTime, period_label: allTime.period_label || "All time" });
            } catch {
                setData({ top_chapters: [], top_members: [], period_label: "This Quarter" });
            }
        })();
    }, []);

    if (!data) {
        return <section className="py-12 max-w-6xl mx-auto px-6 lg:px-10"><div className="h-64 bg-muted rounded-2xl animate-pulse" /></section>;
    }
    // Keep the section rendered even when empty — the EmptyState UI below is
    // much clearer than the section vanishing entirely. See parallel comment
    // in CommunityServiceLeaderboard.jsx.

    return (
        <section className="py-14 bg-slate-50" data-testid="home-top-donors">
            <div className="max-w-6xl mx-auto px-6 lg:px-10">
                <div className="text-center mb-8">
                    <div className="text-xs uppercase tracking-[0.25em] font-bold mb-2" style={{ color: RED }}>{data.period_label || "This Quarter"}</div>
                    <h2 className="font-heading text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight flex items-center justify-center gap-3" style={{ color: NAVY }}>
                        <HeartHandshake className="h-7 w-7 sm:h-9 sm:w-9" style={{ color: GOLD }} />
                        Top Donors Leader Board
                    </h2>
                    <p className="text-sm sm:text-base text-slate-600 mt-2">{data.period_label === "All time" ? "Top donors across the whole org — completed donations only." : "Top donors this quarter — completed donations only."}</p>
                </div>

                <div className="flex justify-center mb-6">
                    <div className="inline-flex bg-white rounded-full p-1 border-2 border-slate-200">
                        <button
                            type="button"
                            onClick={() => setTab("chapters")}
                            className={`rounded-full px-5 py-2 text-sm font-bold transition-colors ${tab === "chapters" ? "bg-slate-100 text-foreground shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="top-donors-tab-chapters"
                        >
                            Top Chapters
                        </button>
                        <button
                            type="button"
                            onClick={() => setTab("members")}
                            className={`rounded-full px-5 py-2 text-sm font-bold transition-colors ${tab === "members" ? "bg-slate-100 text-foreground shadow-warm" : "text-muted-foreground hover:text-foreground"}`}
                            data-testid="top-donors-tab-members"
                        >
                            Top Members
                        </button>
                    </div>
                </div>

                {tab === "chapters" ? (
                    <div className="space-y-2 max-w-2xl mx-auto" data-testid="top-donors-chapters-list">
                        {data.top_chapters.length === 0 ? (
                            <EmptyState text={data.period_label === "All time" ? "No donations recorded yet. Be the first!" : "No chapter donations this quarter yet."} />
                        ) : data.top_chapters.map((c, idx) => (
                            <DonorRow
                                key={c.chapter_id || `unassigned-${idx}`}
                                rank={idx + 1}
                                title={c.chapter_name}
                                subtitle={`${c.member_count} active member${c.member_count !== 1 ? "s" : ""} · ${c.count} gift${c.count !== 1 ? "s" : ""}`}
                                amount={c.amount}
                                avatar={c.logo_url}
                                icon={<Users className="h-5 w-5" />}
                                testid={`top-donors-chapter-${c.chapter_id || "unassigned"}`}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="space-y-2 max-w-2xl mx-auto" data-testid="top-donors-members-list">
                        {data.top_members.length === 0 ? (
                            <EmptyState text={data.period_label === "All time" ? "No donations recorded yet." : "No individual donations this quarter yet."} />
                        ) : data.top_members.map((m, idx) => (
                            <DonorRow
                                key={m.user_id}
                                rank={idx + 1}
                                title={m.user_name}
                                subtitle={`${m.chapter_name || "Unassigned"} · ${m.count} gift${m.count !== 1 ? "s" : ""}`}
                                amount={m.amount}
                                avatar={m.avatar_url}
                                testid={`top-donors-member-${m.user_id}`}
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

function fmtMoney(n) {
    return `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: n % 1 === 0 ? 0 : 2, maximumFractionDigits: 2 })}`;
}

function DonorRow({ rank, title, subtitle, amount, icon, avatar, testid }) {
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
                <div className="font-heading font-black text-xl sm:text-2xl" style={{ color: RED }}>{fmtMoney(amount)}</div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-400 flex items-center gap-1 justify-end">
                    <DollarSign className="h-3 w-3" />donated
                </div>
            </div>
        </div>
    );
}

function EmptyState({ text }) {
    return <div className="text-center py-12 text-sm text-slate-500 border-2 border-dashed border-slate-300 rounded-2xl">{text}</div>;
}

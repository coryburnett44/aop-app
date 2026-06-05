import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Medal, Star, Heart, GraduationCap, Sparkles, Trophy, Award as AwardIcon } from "lucide-react";
import { format, parseISO } from "date-fns";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";

const ICON_MAP = {
    medal: Medal,
    star: Star,
    heart: Heart,
    "graduation-cap": GraduationCap,
    sparkles: Sparkles,
    trophy: Trophy,
    award: AwardIcon,
};

export default function Awards() {
    const [awards, setAwards] = useState([]);
    const [recent, setRecent] = useState([]);

    useEffect(() => {
        api.get("/awards").then(({ data }) => setAwards(data)).catch(() => {});
        // Collect recent grants from all members (use directory + per-member call lightweight)
        (async () => {
            const { data: members } = await api.get("/members");
            const all = [];
            await Promise.all(members.slice(0, 20).map(async (m) => {
                try {
                    const { data } = await api.get(`/members/${m.id}/awards`);
                    data.forEach((g) => all.push({ ...g, member: m }));
                } catch {}
            }));
            all.sort((a, b) => (b.granted_at || "").localeCompare(a.granted_at || ""));
            setRecent(all.slice(0, 12));
        })().catch(() => {});
    }, []);

    return (
        <div className="max-w-6xl mx-auto px-6 lg:px-10 py-12">
            <h1 className="font-heading text-4xl sm:text-5xl font-bold tracking-tight">Awards & Honors</h1>
            <p className="text-muted-foreground mt-2">Recognition for the members who show up, lead, and lift others.</p>

            <h2 className="font-heading text-2xl font-semibold mt-10 mb-4">Awards catalog</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {awards.map((a) => {
                    const Icon = ICON_MAP[a.icon] || Trophy;
                    return (
                        <div key={a.id} className="bg-card rounded-2xl border border-border p-6 shadow-warm relative overflow-hidden" data-testid={`award-${a.id}`}>
                            <div
                                className="absolute -top-6 -right-6 w-32 h-32 rounded-full opacity-20"
                                style={{ backgroundColor: a.color }}
                            />
                            <div
                                className="w-14 h-14 rounded-2xl grid place-items-center relative z-10"
                                style={{ backgroundColor: `${a.color}33`, color: a.color }}
                            >
                                <Icon className="h-7 w-7" />
                            </div>
                            <h3 className="font-heading font-bold text-xl mt-4 relative z-10">{a.name}</h3>
                            <p className="text-sm text-muted-foreground mt-2 leading-relaxed relative z-10">{a.description}</p>
                            <div className="mt-4 text-xs font-semibold text-muted-foreground relative z-10">
                                {(() => {
                                    // Iter 37: catalog now shows BOTH distinct recipients and total grants
                                    // (because a single member can earn the same award multiple times).
                                    const total = a.granted_count || 0;
                                    const distinct = a.granted_distinct_count == null ? total : a.granted_distinct_count;
                                    if (total === distinct) {
                                        return `Granted to ${distinct} member${distinct !== 1 ? "s" : ""}`;
                                    }
                                    return `Granted ${total} times to ${distinct} member${distinct !== 1 ? "s" : ""}`;
                                })()}
                            </div>
                        </div>
                    );
                })}
                {awards.length === 0 && <div className="col-span-full text-muted-foreground">No awards configured yet.</div>}
            </div>

            {recent.length > 0 && (
                <>
                    <h2 className="font-heading text-2xl font-semibold mt-12 mb-4">Recent recipients</h2>
                    <div className="space-y-3">
                        {recent.map((g) => {
                            const Icon = ICON_MAP[g.award_icon] || Trophy;
                            const initials = (g.user_name || "M").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
                            // Iter 37: when a member earned the same award more than once, surface the
                            // ordinal ("2nd Award") so it's clear this is a repeat grant. The backend
                            // sets both `ordinal` (this grant's order) and `award_count` (total grants
                            // of this award to this same member).
                            const ord = g.ordinal || 0;
                            const totalForMember = g.award_count || 0;
                            const ordinalLabel = ord === 1 ? "1st Award" : ord === 2 ? "2nd Award" : ord === 3 ? "3rd Award" : ord ? `${ord}th Award` : "";
                            const showOrdinalPill = ord && totalForMember > 1;
                            return (
                                <div key={g.id} className="bg-card rounded-2xl border border-border p-5 flex items-center gap-4" data-testid={`grant-${g.id}`}>
                                    <div
                                        className="w-12 h-12 rounded-2xl grid place-items-center"
                                        style={{ backgroundColor: `${g.award_color}33`, color: g.award_color }}
                                    >
                                        <Icon className="h-6 w-6" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium flex items-center gap-2 flex-wrap">
                                            <span>{g.award_name}</span>
                                            {showOrdinalPill && (
                                                <span
                                                    className="text-[10px] uppercase tracking-wider font-bold rounded-full px-2 py-0.5 bg-primary/10 text-primary"
                                                    data-testid={`grant-ordinal-${g.id}`}
                                                    title={`This member's ${ordinalLabel.toLowerCase()} of this honor`}
                                                >
                                                    {ordinalLabel}
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {g.granted_at && format(parseISO(g.granted_at), "MMM d, yyyy")}
                                            {g.reason && ` · ${g.reason}`}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Avatar className="h-8 w-8">
                                            {g.member?.avatar_url && <AvatarImage src={g.member.avatar_url} />}
                                            <AvatarFallback className="bg-primary/15 text-primary text-xs">{initials}</AvatarFallback>
                                        </Avatar>
                                        <span className="text-sm font-medium hidden sm:inline">{g.user_name}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </>
            )}
        </div>
    );
}
